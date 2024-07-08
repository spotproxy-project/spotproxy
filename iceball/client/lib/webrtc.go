package snowflake_client

import (
	"bytes"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/ioutil"
	"log"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/pion/ice/v2"
	"github.com/pion/webrtc/v3"
	"gitlab.torproject.org/tpo/anti-censorship/pluggable-transports/snowflake/v2/common/event"
	"gitlab.torproject.org/tpo/anti-censorship/pluggable-transports/snowflake/v2/common/messages"
	"gitlab.torproject.org/tpo/anti-censorship/pluggable-transports/snowflake/v2/common/util"
)

// WebRTCPeer represents a WebRTC connection to a remote snowflake proxy.
//
// Each WebRTCPeer only ever has one DataChannel that is used as the peer's transport.
type WebRTCPeer struct {
	id        string
	pc        *webrtc.PeerConnection
	transport *webrtc.DataChannel
	message   *webrtc.DataChannel

	recvPipe  *io.PipeReader
	writePipe *io.PipeWriter

	mu          sync.Mutex // protects the following:
	lastReceive time.Time

	open   chan struct{} // Channel to notify when datachannel opens
	closed chan struct{}

	once sync.Once // Synchronization for PeerConnection destruction

	bytesLogger  bytesLogger
	eventsLogger event.SnowflakeEventReceiver

	backUpProxy string
	probeTimer  *time.Timer
}

type ClientOffer struct {
	NatType     string `json:"natType"`
	Sdp         []byte `json:"sdp"`
	Fingerprint []byte `json:"fingerprint"`
	Cid         string `json:"cid"`
}

// test
// var connected = make(chan bool)
var transfer = false

func NewWebRTCPeer(config *webrtc.Configuration,
	broker *BrokerChannel) (*WebRTCPeer, error) {
	return NewWebRTCPeerWithEvents(config, broker, nil)
}

// NewWebRTCPeerWithEvents constructs a WebRTC PeerConnection to a snowflake proxy.
//
// The creation of the peer handles the signaling to the Snowflake broker, including
// the exchange of SDP information, the creation of a PeerConnection, and the establishment
// of a DataChannel to the Snowflake proxy.
func NewWebRTCPeerWithEvents(config *webrtc.Configuration,
	broker *BrokerChannel, eventsLogger event.SnowflakeEventReceiver) (*WebRTCPeer, error) {
	if eventsLogger == nil {
		eventsLogger = event.NewSnowflakeEventDispatcher()
	}

	connection := new(WebRTCPeer)
	{
		var buf [8]byte
		if _, err := rand.Read(buf[:]); err != nil {
			panic(err)
		}
		connection.id = "snowflake-" + hex.EncodeToString(buf[:])
	}
	connection.closed = make(chan struct{})

	// Override with something that's not NullLogger to have real logging.
	connection.bytesLogger = &bytesNullLogger{}

	// Pipes remain the same even when DataChannel gets switched.
	connection.recvPipe, connection.writePipe = io.Pipe()

	connection.eventsLogger = eventsLogger

	err := connection.connect(config, broker)
	if err != nil {
		connection.Close()
		return nil, err
	}
	//Initial timer is large, will be reset by probe message
	connection.probeTimer = time.NewTimer(6000 * time.Second)
	go func() {
		<-connection.probeTimer.C
		log.Printf("WebRTC: %s Probe timer expired", connection.id)
		//<-connected
		log.Printf("WebRTC: %s close old connection", connection.id)
		connection.Close()
	}()
	return connection, nil
}

// Read bytes from local SOCKS.
// As part of |io.ReadWriter|
func (c *WebRTCPeer) Read(b []byte) (int, error) {
	return c.recvPipe.Read(b)
}

// Writes bytes out to remote WebRTC.
// As part of |io.ReadWriter|
func (c *WebRTCPeer) Write(b []byte) (int, error) {
	err := c.transport.Send(b)
	if err != nil {
		return 0, err
	}
	c.bytesLogger.addOutbound(int64(len(b)))
	return len(b), nil
}

// Closed returns a boolean indicated whether the peer is closed.
func (c *WebRTCPeer) Closed() bool {
	select {
	case <-c.closed:
		return true
	default:
	}
	return false
}

// Close closes the connection the snowflake proxy.
func (c *WebRTCPeer) Close() error {
	c.once.Do(func() {
		close(c.closed)
		c.cleanup()
		log.Printf("WebRTC: Closing")
	})
	return nil
}

// Prevent long-lived broken remotes.
// Should also update the DataChannel in underlying go-webrtc's to make Closes
// more immediate / responsive.
func (c *WebRTCPeer) checkForStaleness(timeout time.Duration) {
	c.mu.Lock()
	c.lastReceive = time.Now()
	c.mu.Unlock()
	for {
		c.mu.Lock()
		lastReceive := c.lastReceive
		c.mu.Unlock()
		if time.Since(lastReceive) > timeout {
			log.Printf("WebRTC: No messages received for %v -- closing stale connection.",
				timeout)
			err := errors.New("no messages received, closing stale connection")
			c.eventsLogger.OnNewSnowflakeEvent(event.EventOnSnowflakeConnectionFailed{Error: err})
			c.Close()
			return
		}
		select {
		case <-c.closed:
			return
		case <-time.After(time.Second):
		}
	}
}

// connect does the bulk of the work: gather ICE candidates, send the SDP offer to broker,
// receive an answer from broker, and wait for data channel to open
func (c *WebRTCPeer) connect(config *webrtc.Configuration, broker *BrokerChannel) error {
	log.Println(c.id, " connecting...")
	err := c.preparePeerConnection(config)
	localDescription := c.pc.LocalDescription()
	c.eventsLogger.OnNewSnowflakeEvent(event.EventOnOfferCreated{
		WebRTCLocalDescription: localDescription,
		Error:                  err,
	})
	if err != nil {
		return err
	}

	answer, err := broker.Negotiate(localDescription)
	c.eventsLogger.OnNewSnowflakeEvent(event.EventOnBrokerRendezvous{
		WebRTCRemoteDescription: answer,
		Error:                   err,
	})
	if err != nil {
		return err
	}
	log.Printf("Received Answer.\n")
	err = c.pc.SetRemoteDescription(*answer)
	if nil != err {
		log.Println("WebRTC: Unable to SetRemoteDescription:", err)
		return err
	}
	c.pc.SetLocalDescription(*localDescription)

	// Wait for the datachannel to open or time out
	select {
	case <-c.open:

	case <-time.After(DataChannelTimeout):
		c.transport.Close()
		c.message.Close()
		err = errors.New("timeout waiting for DataChannel.OnOpen")
		c.eventsLogger.OnNewSnowflakeEvent(event.EventOnSnowflakeConnectionFailed{Error: err})
		return err
	}

	//go c.checkForStaleness(SnowflakeTimeout)
	return nil
}

// preparePeerConnection creates a new WebRTC PeerConnection and returns it
// after non-trickle ICE candidate gathering is complete.
func (c *WebRTCPeer) preparePeerConnection(config *webrtc.Configuration) error {
	var err error
	s := webrtc.SettingEngine{}
	s.SetICEMulticastDNSMode(ice.MulticastDNSModeDisabled)
	api := webrtc.NewAPI(webrtc.WithSettingEngine(s))
	c.pc, err = api.NewPeerConnection(*config)
	if err != nil {
		log.Printf("NewPeerConnection ERROR: %s", err)
		return err
	}
	ordered := true
	dataChannelOptions := &webrtc.DataChannelInit{
		Ordered: &ordered,
	}
	// We must create the data channel before creating an offer
	// https://github.com/pion/webrtc/wiki/Release-WebRTC@v3.0.0
	dc, err := c.pc.CreateDataChannel(c.id, dataChannelOptions)
	if err != nil {
		log.Printf("CreateDataChannel ERROR: %s", err)
		return err
	}
	dc2, err := c.pc.CreateDataChannel("control", dataChannelOptions)
	if err != nil {
		log.Printf("CreateMsgDataChannel ERROR: %s", err)
		return err
	}
	dc.OnOpen(func() {
		c.eventsLogger.OnNewSnowflakeEvent(event.EventOnSnowflakeConnected{})
		log.Println("WebRTC: DataChannel.OnOpen")
		close(c.open)
	})
	dc.OnClose(func() {
		log.Println("WebRTC: DataChannel.OnClose")
		c.Close()
	})
	dc.OnError(func(err error) {
		c.eventsLogger.OnNewSnowflakeEvent(event.EventOnSnowflakeConnectionFailed{Error: err})
	})
	dc.OnMessage(func(msg webrtc.DataChannelMessage) {
		if len(msg.Data) <= 0 {
			log.Println("0 length message---")
		}
		n, err := c.writePipe.Write(msg.Data)
		c.bytesLogger.addInbound(int64(n))
		if err != nil {
			// TODO: Maybe shouldn't actually close.
			log.Println("Error writing to SOCKS pipe")
			if inerr := c.writePipe.CloseWithError(err); inerr != nil {
				log.Printf("c.writePipe.CloseWithError returned error: %v", inerr)
			}
		}
		c.mu.Lock()
		c.lastReceive = time.Now()
		c.mu.Unlock()
	})
	dc2.OnOpen(func() {
		if transfer {
			log.Println("Transfer DataChannel.OnOpen")
			//connected <- true
			transfer = false
		}
		log.Println("WebRTC: MsgDataChannel.OnOpen")
	})
	dc2.OnClose(func() {
		log.Println("WebRTC: MsgDataChannel.OnClose")
		c.Close()
	})
	dc2.OnError(func(err error) {
		log.Printf("WebRTC: MsgDataChannel.OnError %s", err)
	})
	dc2.OnMessage(func(msg webrtc.DataChannelMessage) {
		probeMsg := messages.ProbeMessage{}
		log.Printf("WebRTC: Received probe message: %s", msg.Data)
		err := json.Unmarshal(msg.Data, &probeMsg)
		if err != nil {
			log.Printf("WebRTC: Error unmarshalling probe message: %s", err)
			return
		}

		if probeMsg.BackupProxyIP != "" {
			if c.backUpProxy != probeMsg.BackupProxyIP {
				transfer = true
				c.backUpProxy = probeMsg.BackupProxyIP
				log.Printf("WebRTC: Received new backup proxy: %s", c.backUpProxy)
				peer, err := DirectConnect(config, c.backUpProxy)
				if err != nil {
					log.Printf("WebRTC: Error connecting to new IP: %s", err)
					return
				}
				//Snowflakes.Consume()
				Snowflakes.Push(peer)
			}
		}

		if probeMsg.TimeVal != 0 {
			log.Printf("WebRTC: Resetting probe timer to %d seconds on %s", probeMsg.TimeVal, c.id)
			c.probeTimer.Stop()
			result := c.probeTimer.Reset(time.Duration(probeMsg.TimeVal) * time.Second)
			log.Printf("WebRTC: Reset probe timer result: %t on %s", result, c.id)
		} else {
			log.Printf("WebRTC: Resetting probe timer to 1 millisecond")
			c.probeTimer.Stop()
			c.probeTimer.Reset(1 * time.Millisecond)
		}

	})
	c.transport = dc
	c.message = dc2
	c.open = make(chan struct{})
	log.Println("WebRTC: DataChannel created")

	offer, err := c.pc.CreateOffer(nil)
	// TODO: Potentially timeout and retry if ICE isn't working.
	if err != nil {
		log.Println("Failed to prepare offer", err)
		c.pc.Close()
		return err
	}
	log.Println("WebRTC: Created offer")

	// Allow candidates to accumulate until ICEGatheringStateComplete.
	done := webrtc.GatheringCompletePromise(c.pc)
	// Start gathering candidates
	err = c.pc.SetLocalDescription(offer)
	if err != nil {
		log.Println("Failed to apply offer", err)
		c.pc.Close()
		return err
	}
	log.Println("WebRTC: Set local description")

	<-done // Wait for ICE candidate gathering to complete.

	if !strings.Contains(c.pc.LocalDescription().SDP, "\na=candidate:") {
		return fmt.Errorf("SDP offer contains no candidate")
	}
	return nil
}

// cleanup closes all channels and transports
func (c *WebRTCPeer) cleanup() {
	// Close this side of the SOCKS pipe.
	if c.writePipe != nil { // c.writePipe can be nil in tests.
		c.writePipe.Close()
	}
	if c.probeTimer != nil {
		c.probeTimer.Stop()
	}
	if nil != c.transport {
		log.Printf("WebRTC: closing DataChannel")
		c.transport.Close()
	}
	if nil != c.message {
		c.message.Close()
	}
	if nil != c.pc {
		log.Printf("WebRTC: closing PeerConnection")
		err := c.pc.Close()
		log.Printf("WebRTC: closed PeerConnection")
		if nil != err {
			log.Printf("Error closing peerconnection...")
		}
	}
}

// Directly connect to a snowflake proxy without using a broker.
func DirectConnect(config *webrtc.Configuration, ip string) (*WebRTCPeer, error) {
	log.Printf("WebRTC: Directly connecting to %s", ip)
	eventsLogger := event.NewSnowflakeEventDispatcher()
	connection := new(WebRTCPeer)
	{
		var buf [8]byte
		if _, err := rand.Read(buf[:]); err != nil {
			panic(err)
		}
		connection.id = "snowflake-" + hex.EncodeToString(buf[:])
	}
	connection.closed = make(chan struct{})

	// Override with something that's not NullLogger to have real logging.
	connection.bytesLogger = &bytesNullLogger{}

	// Pipes remain the same even when DataChannel gets switched.
	connection.recvPipe, connection.writePipe = io.Pipe()

	connection.eventsLogger = eventsLogger
	err := connection.preparePeerConnection(config)
	if err != nil {
		log.Printf("WebRTC: Error preparing peer connection: %s", err)
		connection.Close()
		return nil, err
	}
	sdp := connection.pc.LocalDescription()
	offerSDP, err := util.SerializeSessionDescription(sdp)
	if err != nil {
		return nil, err
	}

	req := &ClientOffer{
		NatType:     "unknown",
		Sdp:         []byte(offerSDP),
		Fingerprint: []byte(""),
		Cid:         ClientID,
	}
	encReq, _ := json.Marshal(req)
	resp, err := http.Post("http://"+ip+":51821/add", "application/json", bytes.NewReader(encReq))
	if err != nil {
		log.Printf("WebRTC: Error sending POST request: %s", err)
		return nil, err
	}
	if resp.StatusCode != 200 {
		log.Printf("WebRTC: Error response from proxy: %s", resp.Status)
		return nil, err
	}
	body, err := ioutil.ReadAll(resp.Body)
	if err != nil {
		log.Printf("WebRTC: Error reading response body: %s", err)
		return nil, err
	}
	decResp, err := messages.DecodeClientPollResponse(body)
	if err != nil {
		log.Printf("WebRTC: Error decoding response: %s", err)
		return nil, err
	}
	answerSDP, err := util.DeserializeSessionDescription(decResp.Answer)
	if err != nil {
		log.Printf("WebRTC: Error deserializing answer: %s", err)
		return nil, err
	}
	log.Printf("WebRTC: Received answer")
	err = connection.pc.SetRemoteDescription(*answerSDP)
	if err != nil {
		log.Printf("WebRTC: Error setting remote description: %s", err)
		return nil, err
	}
	log.Printf("WebRTC: Set remote description")
	//Initial timer is large, will be reset by probe message
	connection.probeTimer = time.NewTimer(6000 * time.Second)
	go func() {
		<-connection.probeTimer.C
		//<-connected
		log.Printf("WebRTC: Probe timer expired")
		connection.Close()
	}()
	return connection, nil
}
