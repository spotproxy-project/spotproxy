/*
Package snowflake_proxy provides functionality for creating, starting, and stopping a snowflake
proxy.

To run a proxy, you must first create a proxy configuration. Unconfigured fields
will be set to the defined defaults.

	proxy := snowflake_proxy.SnowflakeProxy{
		BrokerURL: "https://snowflake-broker.example.com",
		STUNURL: "stun:stun.l.google.com:19302",
		// ...
	}

You may then start and stop the proxy. Stopping the proxy will close existing connections and
the proxy will not poll for more clients.

	go func() {
		err := proxy.Start()
		// handle error
	}

	// ...

	proxy.Stop()
*/
package snowflake_proxy

import (
	"bytes"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"io/ioutil"
	"log"
	"main/common/messages"
	"net"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"

	"github.com/gorilla/websocket"
	"github.com/pion/ice/v2"
	"github.com/pion/webrtc/v3"
	"gitlab.torproject.org/tpo/anti-censorship/pluggable-transports/snowflake/v2/common/event"

	//"gitlab.torproject.org/tpo/anti-censorship/pluggable-transports/snowflake/v2/common/messages"
	"gitlab.torproject.org/tpo/anti-censorship/pluggable-transports/snowflake/v2/common/namematcher"
	"gitlab.torproject.org/tpo/anti-censorship/pluggable-transports/snowflake/v2/common/task"
	"gitlab.torproject.org/tpo/anti-censorship/pluggable-transports/snowflake/v2/common/util"
	"gitlab.torproject.org/tpo/anti-censorship/pluggable-transports/snowflake/v2/common/websocketconn"
)

const (
	DefaultBrokerURL   = "https://snowflake-broker.torproject.net/"
	DefaultNATProbeURL = "https://snowflake-broker.torproject.net:8443/probe"
	DefaultRelayURL    = "wss://snowflake.bamsoftware.com/"
	DefaultSTUNURL     = "stun:stun.l.google.com:19302"
	DefaultProxyType   = "standalone"
)

const (
	// NATUnknown represents a NAT type which is unknown.
	NATUnknown = "unknown"

	// NATRestricted represents a restricted NAT.
	NATRestricted = "restricted"

	// NATUnrestricted represents an unrestricted NAT.
	NATUnrestricted = "unrestricted"
)

const (
	pollInterval = 5 * time.Second

	// Amount of time after sending an SDP answer before the proxy assumes the
	// client is not going to connect
	dataChannelTimeout = 20 * time.Second

	//Maximum number of bytes to be read from an HTTP request
	readLimit = 100000

	sessionIDLength = 16

	probeTime = 3000
)

const bufferedAmountLowThreshold uint64 = 256 * 1024 // 256 KB

var broker *SignalingServer

var currentNATTypeAccess = &sync.RWMutex{}

// currentNATType describes local network environment.
// Obtain currentNATTypeAccess before access.
var currentNATType = NATUnknown

func getCurrentNATType() string {
	currentNATTypeAccess.RLock()
	defer currentNATTypeAccess.RUnlock()
	return currentNATType
}

var (
	tokens *tokens_t
	config webrtc.Configuration
	client http.Client
)

// SnowflakeProxy is used to configure an embedded
// Snowflake in another Go application.
type SnowflakeProxy struct {
	// Capacity is the maximum number of clients a Snowflake will serve.
	// Proxies with a capacity of 0 will accept an unlimited number of clients.
	Capacity uint
	// STUNURL is the URL of the STUN server the proxy will use
	STUNURL string
	// BrokerURL is the URL of the Snowflake broker
	BrokerURL string
	// KeepLocalAddresses indicates whether local SDP candidates will be sent to the broker
	KeepLocalAddresses bool
	// RelayURL is the URL of the Snowflake server that all traffic will be relayed to
	RelayURL string
	// OutboundAddress specify an IP address to use as SDP host candidate
	OutboundAddress string
	// Ephemeral*Port limits the pool of ports that ICE UDP connections can allocate from
	EphemeralMinPort uint16
	EphemeralMaxPort uint16
	// RelayDomainNamePattern is the pattern specify allowed domain name for relay
	// If the pattern starts with ^ then an exact match is required.
	// The rest of pattern is the suffix of domain name.
	// There is no look ahead assertion when matching domain name suffix,
	// thus the string prepend the suffix does not need to be empty or ends with a dot.
	RelayDomainNamePattern string
	AllowNonTLSRelay       bool
	// NATProbeURL is the URL of the probe service we use for NAT checks
	NATProbeURL string
	// NATTypeMeasurementInterval is time before NAT type is retested
	NATTypeMeasurementInterval time.Duration
	// ProxyType is the type reported to the broker, if not provided it "standalone" will be used
	ProxyType       string
	EventDispatcher event.SnowflakeEventDispatcher
	shutdown        chan struct{}
}

type ClientOffer struct {
	NatType     string `json:"natType"`
	Sdp         []byte `json:"sdp"`
	Fingerprint []byte `json:"fingerprint"`
	Cid         string `json:"cid"`
}

var client2Dc = make(map[string]*webrtc.DataChannel)
var client2TransferIP = make(map[string]string)

// Checks whether an IP address is a remote address for the client
func isRemoteAddress(ip net.IP) bool {
	return !(util.IsLocal(ip) || ip.IsUnspecified() || ip.IsLoopback())
}

func genSessionID() string {
	buf := make([]byte, sessionIDLength)
	_, err := rand.Read(buf)
	if err != nil {
		panic(err.Error())
	}
	return strings.TrimRight(base64.StdEncoding.EncodeToString(buf), "=")
}

func limitedRead(r io.Reader, limit int64) ([]byte, error) {
	p, err := ioutil.ReadAll(&io.LimitedReader{R: r, N: limit + 1})
	if err != nil {
		return p, err
	} else if int64(len(p)) == limit+1 {
		return p[0:limit], io.ErrUnexpectedEOF
	}
	return p, err
}

// SignalingServer keeps track of the SignalingServer in use by the Snowflake
type SignalingServer struct {
	url                *url.URL
	transport          http.RoundTripper
	keepLocalAddresses bool
}

func newSignalingServer(rawURL string, keepLocalAddresses bool) (*SignalingServer, error) {
	var err error
	s := new(SignalingServer)
	s.keepLocalAddresses = keepLocalAddresses
	s.url, err = url.Parse(rawURL)
	if err != nil {
		return nil, fmt.Errorf("invalid broker url: %s", err)
	}

	s.transport = http.DefaultTransport.(*http.Transport)
	s.transport.(*http.Transport).ResponseHeaderTimeout = 30 * time.Second

	return s, nil
}

// Post sends a POST request to the SignalingServer
func (s *SignalingServer) Post(path string, payload io.Reader) ([]byte, error) {
	req, err := http.NewRequest("POST", path, payload)
	if err != nil {
		return nil, err
	}

	resp, err := s.transport.RoundTrip(req)
	if err != nil {
		return nil, err
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("remote returned status code %d", resp.StatusCode)
	}

	defer resp.Body.Close()
	return limitedRead(resp.Body, readLimit)
}

// pollOffer communicates the proxy's capabilities with broker
// and retrieves a compatible SDP offer
func (s *SignalingServer) pollOffer(sid string, proxyType string, acceptedRelayPattern string, shutdown chan struct{}) (*webrtc.SessionDescription, string) {
	brokerPath := s.url.ResolveReference(&url.URL{Path: "proxy"})

	ticker := time.NewTicker(pollInterval)
	defer ticker.Stop()

	// Run the loop once before hitting the ticker
	for ; true; <-ticker.C {
		select {
		case <-shutdown:
			return nil, ""
		default:
			numClients := int((tokens.count() / 8) * 8) // Round down to 8
			currentNATTypeLoaded := getCurrentNATType()
			body, err := messages.EncodeProxyPollRequestWithRelayPrefix(sid, proxyType, currentNATTypeLoaded, numClients, acceptedRelayPattern)
			if err != nil {
				log.Printf("Error encoding poll message: %s", err.Error())
				return nil, ""
			}

			resp, err := s.Post(brokerPath.String(), bytes.NewBuffer(body))
			if err != nil {
				log.Printf("error polling broker: %s", err.Error())
			}

			offer, _, relayURL, err := messages.DecodePollResponseWithRelayURL(resp)
			if err != nil {
				log.Printf("Error reading broker response: %s", err.Error())
				log.Printf("body: %s", resp)
				return nil, ""
			}
			if offer != "" {
				offer, err := util.DeserializeSessionDescription(offer)
				if err != nil {
					log.Printf("Error processing session description: %s", err.Error())
					return nil, ""
				}
				return offer, relayURL
			}
		}
	}
	return nil, ""
}

func (sf *SnowflakeProxy) changeClient(clientID string, isAdd bool) {
	var msg messages.ClientChange
	if isAdd {
		msg = messages.ClientChange{Cid: clientID, Action: "add"}
	} else {
		msg = messages.ClientChange{Cid: clientID, Action: "delete"}
	}
	msgJSON, _ := json.Marshal(msg)
	brokerPath := broker.url.ResolveReference(&url.URL{Path: "change-client"})
	broker.Post(brokerPath.String(), bytes.NewBuffer(msgJSON))

}

// sendAnswer encodes an SDP answer, sends it to the broker
// and wait for its response
func (s *SignalingServer) sendAnswer(sid string, pc *webrtc.PeerConnection) error {
	ld := pc.LocalDescription()
	if !s.keepLocalAddresses {
		ld = &webrtc.SessionDescription{
			Type: ld.Type,
			SDP:  util.StripLocalAddresses(ld.SDP),
		}
	}

	answer, err := util.SerializeSessionDescription(ld)
	if err != nil {
		return err
	}

	body, err := messages.EncodeAnswerRequest(answer, sid)
	if err != nil {
		return err
	}

	brokerPath := s.url.ResolveReference(&url.URL{Path: "answer"})
	resp, err := s.Post(brokerPath.String(), bytes.NewBuffer(body))
	if err != nil {
		return fmt.Errorf("error sending answer to broker: %s", err.Error())
	}

	success, err := messages.DecodeAnswerResponse(resp)
	if err != nil {
		return err
	}
	if !success {
		return fmt.Errorf("broker returned client timeout")
	}

	return nil
}

func copyLoop(c1 io.ReadWriteCloser, c2 io.ReadWriteCloser, shutdown chan struct{}) {
	var once sync.Once
	defer c2.Close()
	defer c1.Close()
	done := make(chan struct{})
	copyer := func(dst io.ReadWriteCloser, src io.ReadWriteCloser) {
		// Ignore io.ErrClosedPipe because it is likely caused by the
		// termination of copyer in the other direction.
		if _, err := io.Copy(dst, src); err != nil && err != io.ErrClosedPipe {
			log.Printf("io.Copy inside CopyLoop generated an error: %v", err)
		}
		once.Do(func() {
			close(done)
		})
	}

	go copyer(c1, c2)
	go copyer(c2, c1)

	select {
	case <-done:
	case <-shutdown:
	}
	log.Println("copy loop ended")
}

// We pass conn.RemoteAddr() as an additional parameter, rather than calling
// conn.RemoteAddr() inside this function, as a workaround for a hang that
// otherwise occurs inside conn.pc.RemoteDescription() (called by RemoteAddr).
// https://bugs.torproject.org/18628#comment:8
func (sf *SnowflakeProxy) datachannelHandler(conn *webRTCConn, remoteAddr net.Addr, relayURL string) {
	defer conn.Close()
	defer tokens.ret()

	if relayURL == "" {
		relayURL = sf.RelayURL
	}

	u, err := url.Parse(relayURL)
	if err != nil {
		log.Fatalf("invalid relay url: %s", err)
	}

	if remoteAddr != nil {
		// Encode client IP address in relay URL
		q := u.Query()
		clientIP := remoteAddr.String()
		q.Set("client_ip", clientIP)
		u.RawQuery = q.Encode()
	} else {
		log.Printf("no remote address given in websocket")
	}

	ws, _, err := websocket.DefaultDialer.Dial(u.String(), nil)
	if err != nil {
		log.Printf("error dialing relay: %s = %s", u.String(), err)
		return
	}

	wsConn := websocketconn.New(ws)
	log.Printf("Connected to relay: %v", relayURL)
	defer wsConn.Close()
	copyLoop(conn, wsConn, sf.shutdown)
	log.Printf("datachannelHandler ends")
}

type dataChannelHandlerWithRelayURL struct {
	RelayURL string
	sf       *SnowflakeProxy
}

func (d dataChannelHandlerWithRelayURL) datachannelHandler(conn *webRTCConn, remoteAddr net.Addr) {
	d.sf.datachannelHandler(conn, remoteAddr, d.RelayURL)
}

func (sf *SnowflakeProxy) makeWebRTCAPI() *webrtc.API {
	settingsEngine := webrtc.SettingEngine{}

	if sf.EphemeralMinPort != 0 && sf.EphemeralMaxPort != 0 {
		err := settingsEngine.SetEphemeralUDPPortRange(sf.EphemeralMinPort, sf.EphemeralMaxPort)
		if err != nil {
			log.Fatal("Invalid port range: min > max")
		}
	}

	if sf.OutboundAddress != "" {
		// replace SDP host candidates with the given IP without validation
		// still have server reflexive candidates to fall back on
		settingsEngine.SetNAT1To1IPs([]string{sf.OutboundAddress}, webrtc.ICECandidateTypeHost)
	}

	settingsEngine.SetICEMulticastDNSMode(ice.MulticastDNSModeDisabled)

	settingsEngine.SetDTLSInsecureSkipHelloVerify(true)

	return webrtc.NewAPI(webrtc.WithSettingEngine(settingsEngine))
}

// Create a PeerConnection from an SDP offer. Blocks until the gathering of ICE
// candidates is complete and the answer is available in LocalDescription.
// Installs an OnDataChannel callback that creates a webRTCConn and passes it to
// datachannelHandler.
func (sf *SnowflakeProxy) makePeerConnectionFromOffer(sdp *webrtc.SessionDescription,
	config webrtc.Configuration,
	dataChan chan struct{},
	handler func(conn *webRTCConn, remoteAddr net.Addr),
	clientId string) (*webrtc.PeerConnection, error) {

	api := sf.makeWebRTCAPI()
	pc, err := api.NewPeerConnection(config)
	if err != nil {
		return nil, fmt.Errorf("accept: NewPeerConnection: %s", err)
	}

	pc.OnDataChannel(func(dc *webrtc.DataChannel) {
		log.Printf("New Data Channel %s-%d\n", dc.Label(), dc.ID())
		if dc.Label() != "control" {
			close(dataChan)

			pr, pw := io.Pipe()
			conn := newWebRTCConn(pc, dc, pr, sf.EventDispatcher)

			dc.SetBufferedAmountLowThreshold(bufferedAmountLowThreshold)

			dc.OnBufferedAmountLow(func() {
				select {
				case conn.sendMoreCh <- struct{}{}:
				default:
				}
			})

			dc.OnOpen(func() {
				log.Printf("Data Channel %s-%d open\n", dc.Label(), dc.ID())

				if sf.OutboundAddress != "" {
					selectedCandidatePair, err := pc.SCTP().Transport().ICETransport().GetSelectedCandidatePair()
					if err != nil {
						log.Printf("Warning: couldn't get the selected candidate pair")
					}

					log.Printf("Selected Local Candidate: %s:%d", selectedCandidatePair.Local.Address, selectedCandidatePair.Local.Port)
					if sf.OutboundAddress != selectedCandidatePair.Local.Address {
						log.Printf("Warning: the IP address provided by --outbound-address is not used for establishing peerconnection")
					}
				}
			})
			dc.OnClose(func() {
				conn.lock.Lock()
				defer conn.lock.Unlock()
				log.Printf("Data Channel %s-%d close\n", dc.Label(), dc.ID())
				log.Println(conn.bytesLogger.ThroughputSummary())
				in, out := conn.bytesLogger.GetStat()
				conn.eventLogger.OnNewSnowflakeEvent(event.EventOnProxyConnectionOver{
					InboundTraffic:  in,
					OutboundTraffic: out,
				})
				conn.dc = nil
				dc.Close()
				pw.Close()
			})
			dc.OnMessage(func(msg webrtc.DataChannelMessage) {
				var n int
				n, err = pw.Write(msg.Data)
				if err != nil {
					if inerr := pw.CloseWithError(err); inerr != nil {
						log.Printf("close with error generated an error: %v", inerr)
					}
				}
				conn.bytesLogger.AddOutbound(int64(n))
				if n != len(msg.Data) {
					panic("short write")
				}
			})

			go handler(conn, conn.RemoteAddr())
		} else {
			client2Dc[clientId] = dc
			//log.Printf("update map: %v", client2Dc)
			dcClosed := make(chan bool)
			dc.OnOpen(func() {
				log.Printf("Data Channel %s-%d open\n", dc.Label(), dc.ID())
				sf.changeClient(clientId, true)
				ticker := time.NewTicker(probeTime * time.Second)
				go func() {
					for {
						select {
						case <-ticker.C:
							log.Printf("send probe to client: %v", clientId)
							msg := messages.ProbeMessage{TimeVal: int(probeTime * 2), BackupProxyIP: client2TransferIP[clientId]}
							probeMsg, err := json.Marshal(msg)
							if err != nil {
								log.Printf("error: %v", err)
							}
							dc.Send(probeMsg)
						case <-dcClosed:
							log.Printf("stop sending probe to client: %v", clientId)
							ticker.Stop()
						}
					}
				}()
			})
			dc.OnClose(func() {
				sf.changeClient(clientId, false)
				delete(client2Dc, clientId)
				delete(client2TransferIP, clientId)
				dcClosed <- true
			})

		}
	})
	// As of v3.0.0, pion-webrtc uses trickle ICE by default.
	// We have to wait for candidate gathering to complete
	// before we send the offer
	done := webrtc.GatheringCompletePromise(pc)
	err = pc.SetRemoteDescription(*sdp)
	if err != nil {
		if inerr := pc.Close(); inerr != nil {
			log.Printf("unable to call pc.Close after pc.SetRemoteDescription with error: %v", inerr)
		}
		return nil, fmt.Errorf("accept: SetRemoteDescription: %s", err)
	}

	log.Println("Generating answer...")
	answer, err := pc.CreateAnswer(nil)
	// blocks on ICE gathering. we need to add a timeout if needed
	// not putting this in a separate go routine, because we need
	// SetLocalDescription(answer) to be called before sendAnswer
	if err != nil {
		if inerr := pc.Close(); inerr != nil {
			log.Printf("ICE gathering has generated an error when calling pc.Close: %v", inerr)
		}
		return nil, err
	}

	err = pc.SetLocalDescription(answer)
	if err != nil {
		if err = pc.Close(); err != nil {
			log.Printf("pc.Close after setting local description returned : %v", err)
		}
		return nil, err
	}

	// Wait for ICE candidate gathering to complete
	<-done

	if !strings.Contains(pc.LocalDescription().SDP, "\na=candidate:") {
		return nil, fmt.Errorf("SDP answer contains no candidate")
	}
	log.Printf("Answer: \n\t%s", strings.ReplaceAll(pc.LocalDescription().SDP, "\n", "\n\t"))

	return pc, nil
}

// Create a new PeerConnection. Blocks until the gathering of ICE
// candidates is complete and the answer is available in LocalDescription.
func (sf *SnowflakeProxy) makeNewPeerConnection(config webrtc.Configuration,
	dataChan chan struct{}) (*webrtc.PeerConnection, error) {

	api := sf.makeWebRTCAPI()
	pc, err := api.NewPeerConnection(config)
	if err != nil {
		return nil, fmt.Errorf("accept: NewPeerConnection: %s", err)
	}

	// Must create a data channel before creating an offer
	// https://github.com/pion/webrtc/wiki/Release-WebRTC@v3.0.0
	dc, err := pc.CreateDataChannel("test", &webrtc.DataChannelInit{})
	log.Printf("Created data channel: %v", dc)
	if err != nil {
		log.Printf("CreateDataChannel ERROR: %s", err)
		return nil, err
	}
	dc.OnOpen(func() {
		log.Println("WebRTC: DataChannel.OnOpen")
		close(dataChan)
	})
	dc.OnClose(func() {
		log.Println("WebRTC: DataChannel.OnClose")
		dc.Close()
	})

	offer, err := pc.CreateOffer(nil)
	// TODO: Potentially timeout and retry if ICE isn't working.
	if err != nil {
		log.Println("Failed to prepare offer", err)
		pc.Close()
		return nil, err
	}
	log.Println("Probetest: Created Offer")

	// As of v3.0.0, pion-webrtc uses trickle ICE by default.
	// We have to wait for candidate gathering to complete
	// before we send the offer
	done := webrtc.GatheringCompletePromise(pc)
	// start the gathering of ICE candidates
	err = pc.SetLocalDescription(offer)
	if err != nil {
		log.Println("Failed to apply offer", err)
		pc.Close()
		return nil, err
	}
	log.Println("Probetest: Set local description")

	// Wait for ICE candidate gathering to complete
	<-done

	if !strings.Contains(pc.LocalDescription().SDP, "\na=candidate:") {
		return nil, fmt.Errorf("Probetest SDP offer contains no candidate")
	}

	return pc, nil
}

func (sf *SnowflakeProxy) runSession(sid string) {
	offer, relayURL := broker.pollOffer(sid, sf.ProxyType, sf.RelayDomainNamePattern, sf.shutdown)
	if offer == nil {
		log.Printf("bad offer from broker")
		tokens.ret()
		return
	}
	log.Printf("Received Offer From Broker: \n\t%s", strings.ReplaceAll(offer.SDP, "\n", "\n\t"))

	matcher := namematcher.NewNameMatcher(sf.RelayDomainNamePattern)
	parsedRelayURL, err := url.Parse(relayURL)
	if err != nil {
		log.Printf("bad offer from broker: bad Relay URL %v", err.Error())
		tokens.ret()
		return
	}

	if relayURL != "" && (!matcher.IsMember(parsedRelayURL.Hostname()) || (!sf.AllowNonTLSRelay && parsedRelayURL.Scheme != "wss")) {
		log.Printf("bad offer from broker: rejected Relay URL")
		tokens.ret()
		return
	}

	dataChan := make(chan struct{})
	dataChannelAdaptor := dataChannelHandlerWithRelayURL{RelayURL: relayURL, sf: sf}
	pc, err := sf.makePeerConnectionFromOffer(offer, config, dataChan, dataChannelAdaptor.datachannelHandler, "dummy")
	if err != nil {
		log.Printf("error making WebRTC connection: %s", err)
		tokens.ret()
		return
	}

	err = broker.sendAnswer(sid, pc)
	if err != nil {
		log.Printf("error sending answer to client through broker: %s", err)
		if inerr := pc.Close(); inerr != nil {
			log.Printf("error calling pc.Close: %v", inerr)
		}
		tokens.ret()
		return
	}
	// Set a timeout on peerconnection. If the connection state has not
	// advanced to PeerConnectionStateConnected in this time,
	// destroy the peer connection and return the token.
	select {
	case <-dataChan:
		log.Println("Connection successful")
	case <-time.After(dataChannelTimeout):
		log.Println("Timed out waiting for client to open data channel.")
		if err := pc.Close(); err != nil {
			log.Printf("error calling pc.Close: %v", err)
		}
		tokens.ret()
	}
}

// Start configures and starts a Snowflake, fully formed and special. Configuration
// values that are unset will default to their corresponding default values.
func (sf *SnowflakeProxy) Start() error {
	var err error

	sf.EventDispatcher.OnNewSnowflakeEvent(event.EventOnProxyStarting{})
	sf.shutdown = make(chan struct{})

	// blank configurations revert to default
	if sf.BrokerURL == "" {
		sf.BrokerURL = DefaultBrokerURL
	}
	if sf.RelayURL == "" {
		sf.RelayURL = DefaultRelayURL
	}
	if sf.STUNURL == "" {
		sf.STUNURL = DefaultSTUNURL
	}
	if sf.NATProbeURL == "" {
		sf.NATProbeURL = DefaultNATProbeURL
	}
	if sf.ProxyType == "" {
		sf.ProxyType = DefaultProxyType
	}
	if sf.EventDispatcher == nil {
		sf.EventDispatcher = event.NewSnowflakeEventDispatcher()
	}

	broker, err = newSignalingServer(sf.BrokerURL, sf.KeepLocalAddresses)
	if err != nil {
		return fmt.Errorf("error configuring broker: %s", err)
	}

	_, err = url.Parse(sf.STUNURL)
	if err != nil {
		return fmt.Errorf("invalid stun url: %s", err)
	}
	_, err = url.Parse(sf.RelayURL)
	if err != nil {
		return fmt.Errorf("invalid relay url: %s", err)
	}

	if !namematcher.IsValidRule(sf.RelayDomainNamePattern) {
		return fmt.Errorf("invalid relay domain name pattern")
	}

	config = webrtc.Configuration{
		ICEServers: []webrtc.ICEServer{
			{
				URLs: []string{sf.STUNURL},
			},
		},
	}
	tokens = newTokens(sf.Capacity)

	sf.checkNATType(config, sf.NATProbeURL)
	currentNATTypeLoaded := getCurrentNATType()
	sf.EventDispatcher.OnNewSnowflakeEvent(&event.EventOnCurrentNATTypeDetermined{CurNATType: currentNATTypeLoaded})

	NatRetestTask := task.Periodic{
		Interval: sf.NATTypeMeasurementInterval,
		Execute: func() error {
			sf.checkNATType(config, sf.NATProbeURL)
			return nil
		},
	}

	if sf.NATTypeMeasurementInterval != 0 {
		NatRetestTask.WaitThenStart()
		defer NatRetestTask.Close()
	}

	numClients := int((tokens.count() / 8) * 8) // Round down to 8
	sid := genSessionID()
	body, err := messages.EncodeProxyPollRequestWithRelayPrefix(sid, sf.ProxyType, currentNATTypeLoaded, numClients, sf.RelayDomainNamePattern)
	if err != nil {
		log.Printf("Error encoding poll message: %s", err.Error())
		return nil
	}

	log.Printf("Polling broker: %s", sf.BrokerURL)
	brokerPath := broker.url.ResolveReference(&url.URL{Path: "proxy"})
	resp, err := broker.Post(brokerPath.String(), bytes.NewBuffer(body))
	if err != nil {
		log.Printf("error polling broker: %s", err.Error())
	}
	log.Print("Response from broker:")
	log.Print(string(resp))

	log.Printf("Starting Snowflake proxy http server on :51821")

	http.HandleFunc("/add", sf.addHandler)
	http.HandleFunc("/transfer", sf.transferHandler)
	http.HandleFunc("/data", sf.dataHandler)
	http.ListenAndServe(":51821", nil)

	return nil
}

// Stop closes all existing connections and shuts down the Snowflake.
func (sf *SnowflakeProxy) Stop() {
	close(sf.shutdown)
}

// checkNATType use probetest to determine NAT compatability by
// attempting to connect with a known symmetric NAT. If success,
// it is considered "unrestricted". If timeout it is considered "restricted"
func (sf *SnowflakeProxy) checkNATType(config webrtc.Configuration, probeURL string) {

	probe, err := newSignalingServer(probeURL, false)
	if err != nil {
		log.Printf("Error parsing url: %s", err.Error())
	}

	dataChan := make(chan struct{})
	pc, err := sf.makeNewPeerConnection(config, dataChan)
	if err != nil {
		log.Printf("error making WebRTC connection: %s", err)
		return
	}

	offer := pc.LocalDescription()
	log.Printf("Probetest offer: \n\t%s", strings.ReplaceAll(offer.SDP, "\n", "\n\t"))
	sdp, err := util.SerializeSessionDescription(offer)
	if err != nil {
		log.Printf("Error encoding probe message: %s", err.Error())
		return
	}

	// send offer
	body, err := messages.EncodePollResponse(sdp, true, "")
	if err != nil {
		log.Printf("Error encoding probe message: %s", err.Error())
		return
	}

	resp, err := probe.Post(probe.url.String(), bytes.NewBuffer(body))
	if err != nil {
		log.Printf("error polling probe: %s", err.Error())
		return
	}

	sdp, _, err = messages.DecodeAnswerRequest(resp)
	if err != nil {
		log.Printf("Error reading probe response: %s", err.Error())
		return
	}

	answer, err := util.DeserializeSessionDescription(sdp)
	if err != nil {
		log.Printf("Error setting answer: %s", err.Error())
		return
	}

	err = pc.SetRemoteDescription(*answer)
	if err != nil {
		log.Printf("Error setting answer: %s", err.Error())
		return
	}

	currentNATTypeLoaded := getCurrentNATType()

	currentNATTypeTestResult := NATUnknown
	select {
	case <-dataChan:
		currentNATTypeTestResult = NATUnrestricted
	case <-time.After(dataChannelTimeout):
		currentNATTypeTestResult = NATRestricted
	}

	currentNATTypeToStore := NATUnknown
	switch currentNATTypeLoaded + "->" + currentNATTypeTestResult {
	case NATUnrestricted + "->" + NATUnknown:
		currentNATTypeToStore = NATUnrestricted

	case NATRestricted + "->" + NATUnknown:
		currentNATTypeToStore = NATRestricted

	default:
		currentNATTypeToStore = currentNATTypeTestResult
	}

	log.Printf("NAT Type measurement: %v -> %v = %v\n", currentNATTypeLoaded, currentNATTypeTestResult, currentNATTypeToStore)
	log.Printf("NAT Type measurement: %v\n", currentNATTypeToStore)

	currentNATTypeAccess.Lock()
	currentNATType = currentNATTypeToStore
	currentNATTypeAccess.Unlock()

	if err := pc.Close(); err != nil {
		log.Printf("error calling pc.Close: %v", err)
	}
}

func (sf *SnowflakeProxy) addHandler(w http.ResponseWriter, r *http.Request) {

	offer := ClientOffer{}
	if sdpErr := json.NewDecoder(r.Body).Decode(&offer); sdpErr != nil {
		panic(sdpErr)
	}

	offerSDP := webrtc.SessionDescription{}
	json.Unmarshal(offer.Sdp, &offerSDP)
	log.Printf("Received Offer From Client: %s\n", offer.Cid)

	dataChan := make(chan struct{})
	relayURL := sf.RelayURL
	dataChannelAdaptor := dataChannelHandlerWithRelayURL{RelayURL: relayURL, sf: sf}

	pc, err := sf.makePeerConnectionFromOffer(&offerSDP, config, dataChan, dataChannelAdaptor.datachannelHandler, offer.Cid)
	if err != nil {
		log.Printf("error making WebRTC connection: %s", err)
		tokens.ret()
		pc.Close()
		return
	}

	answer := pc.LocalDescription()
	log.Printf("Answer: \n\t%s", strings.ReplaceAll(answer.SDP, "\n", "\n\t"))
	answerJSON, _ := json.Marshal(answer)

	answerRespond := messages.ClientPollResponse{
		Answer: string(answerJSON),
		Error:  "",
	}
	answerRespondJSON, _ := json.Marshal(answerRespond)
	w.Write(answerRespondJSON)

	go func() {
		select {
		case <-dataChan:
			log.Println("Connection successful")
		case <-time.After(dataChannelTimeout):
			log.Println("Timed out waiting for client to open data channel.")
			if err := pc.Close(); err != nil {
				log.Printf("error calling pc.Close: %v", err)
			}
			tokens.ret()
		}
	}()

}

func (sf *SnowflakeProxy) transferHandler(w http.ResponseWriter, r *http.Request) {
	transReq := messages.TransferRequest{}
	if err := json.NewDecoder(r.Body).Decode(&transReq); err != nil {
		panic(err)
	}
	log.Printf("Received transfer request: %v", transReq)
	ip, _, _ := net.SplitHostPort(transReq.NewIp)
	client2TransferIP[transReq.Cid] = ip
	log.Printf("update ip: %v", client2TransferIP[transReq.Cid])
	if client2Dc[transReq.Cid] == nil {
		//log.Printf("Client not found: %v", transReq.Cid)
		return
	}
	if transReq.TransferNow {
		msg := messages.ProbeMessage{TimeVal: 0, BackupProxyIP: ip}
		probeMsg, err := json.Marshal(msg)
		if err != nil {
			log.Printf("error: %v", err)
		}
		client2Dc[transReq.Cid].Send(probeMsg)
		dummyData := "dummy"
		resp, err := http.Post("http://"+ip+":51821/data", "application/json", bytes.NewBuffer([]byte(dummyData)))
		if err != nil {
			log.Printf("Error sending data to new proxy: %v", err)
		}
		if resp.StatusCode != http.StatusOK {
			log.Printf("Error sending data to new proxy: %v", resp.StatusCode)
		}
	}

}

func (sf *SnowflakeProxy) dataHandler(w http.ResponseWriter, r *http.Request) {
	data, _ := ioutil.ReadAll(r.Body)
	log.Printf("Received data: %v", data)
}
