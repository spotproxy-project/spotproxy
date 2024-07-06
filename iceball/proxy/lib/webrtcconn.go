package snowflake_proxy

import (
	"context"
	"fmt"
	"io"
	"log"
	"net"
	"regexp"
	"sync"
	"time"

	"github.com/pion/ice/v2"
	"github.com/pion/sdp/v3"
	"github.com/pion/webrtc/v3"
	"gitlab.torproject.org/tpo/anti-censorship/pluggable-transports/snowflake/v2/common/event"
)

const maxBufferedAmount uint64 = 512 * 1024 // 512 KB

var remoteIPPatterns = []*regexp.Regexp{
	/* IPv4 */
	regexp.MustCompile(`(?m)^c=IN IP4 ([\d.]+)(?:(?:\/\d+)?\/\d+)?(:? |\r?\n)`),
	/* IPv6 */
	regexp.MustCompile(`(?m)^c=IN IP6 ([0-9A-Fa-f:.]+)(?:\/\d+)?(:? |\r?\n)`),
}

type webRTCConn struct {
	dc *webrtc.DataChannel
	pc *webrtc.PeerConnection
	pr *io.PipeReader

	lock sync.Mutex // Synchronization for DataChannel destruction
	once sync.Once  // Synchronization for PeerConnection destruction

	isClosing bool

	bytesLogger bytesLogger
	eventLogger event.SnowflakeEventReceiver

	inactivityTimeout time.Duration
	activity          chan struct{}
	sendMoreCh        chan struct{}
	cancelTimeoutLoop context.CancelFunc
}

func newWebRTCConn(pc *webrtc.PeerConnection, dc *webrtc.DataChannel, pr *io.PipeReader, eventLogger event.SnowflakeEventReceiver) *webRTCConn {
	conn := &webRTCConn{pc: pc, dc: dc, pr: pr, eventLogger: eventLogger}
	conn.isClosing = false
	conn.bytesLogger = newBytesSyncLogger()
	conn.activity = make(chan struct{}, 100)
	conn.sendMoreCh = make(chan struct{}, 1)
	conn.inactivityTimeout = 3600 * time.Second
	ctx, cancel := context.WithCancel(context.Background())
	conn.cancelTimeoutLoop = cancel
	go conn.timeoutLoop(ctx)
	return conn
}

func (c *webRTCConn) timeoutLoop(ctx context.Context) {
	timer := time.NewTimer(c.inactivityTimeout)
	for {
		select {
		case <-timer.C:
			c.Close()
			log.Println("Closed connection due to inactivity")
			return
		case <-c.activity:
			if !timer.Stop() {
				<-timer.C
			}
			timer.Reset(c.inactivityTimeout)
			continue
		case <-ctx.Done():
			return
		}
	}
}

func (c *webRTCConn) Read(b []byte) (int, error) {
	return c.pr.Read(b)
}

func (c *webRTCConn) Write(b []byte) (int, error) {
	c.bytesLogger.AddInbound(int64(len(b)))
	select {
	case c.activity <- struct{}{}:
	default:
	}
	c.lock.Lock()
	defer c.lock.Unlock()
	if c.dc != nil {
		c.dc.Send(b)
		if !c.isClosing && c.dc.BufferedAmount()+uint64(len(b)) > maxBufferedAmount {
			<-c.sendMoreCh
		}
	}
	return len(b), nil
}

func (c *webRTCConn) Close() (err error) {
	c.isClosing = true
	select {
	case c.sendMoreCh <- struct{}{}:
	default:
	}
	c.once.Do(func() {
		c.cancelTimeoutLoop()
		err = c.pc.Close()
	})
	return
}

func (c *webRTCConn) LocalAddr() net.Addr {
	return nil
}

func (c *webRTCConn) RemoteAddr() net.Addr {
	//Parse Remote SDP offer and extract client IP
	clientIP := remoteIPFromSDP(c.pc.RemoteDescription().SDP)
	if clientIP == nil {
		return nil
	}
	return &net.IPAddr{IP: clientIP, Zone: ""}
}

func (c *webRTCConn) SetDeadline(t time.Time) error {
	// nolint: golint
	return fmt.Errorf("SetDeadline not implemented")
}

func (c *webRTCConn) SetReadDeadline(t time.Time) error {
	// nolint: golint
	return fmt.Errorf("SetReadDeadline not implemented")
}

func (c *webRTCConn) SetWriteDeadline(t time.Time) error {
	// nolint: golint
	return fmt.Errorf("SetWriteDeadline not implemented")
}

func remoteIPFromSDP(str string) net.IP {
	// Look for remote IP in "a=candidate" attribute fields
	// https://tools.ietf.org/html/rfc5245#section-15.1
	var desc sdp.SessionDescription
	err := desc.Unmarshal([]byte(str))
	if err != nil {
		log.Println("Error parsing SDP: ", err.Error())
		return nil
	}
	for _, m := range desc.MediaDescriptions {
		for _, a := range m.Attributes {
			if a.IsICECandidate() {
				c, err := ice.UnmarshalCandidate(a.Value)
				if err == nil {
					ip := net.ParseIP(c.Address())
					if ip != nil && isRemoteAddress(ip) {
						return ip
					}
				}
			}
		}
	}
	// Finally look for remote IP in "c=" Connection Data field
	// https://tools.ietf.org/html/rfc4566#section-5.7
	for _, pattern := range remoteIPPatterns {
		m := pattern.FindStringSubmatch(str)
		if m != nil {
			// Ignore parsing errors, ParseIP returns nil.
			ip := net.ParseIP(m[1])
			if ip != nil && isRemoteAddress(ip) {
				return ip
			}

		}
	}

	return nil
}
