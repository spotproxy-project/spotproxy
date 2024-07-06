/*
Package snowflake_server implements the functionality necessary to accept Snowflake
connections from Snowflake clients.

Included in the package is a Transport type that implements the Pluggable Transports v2.1 Go API
specification. To start a TLS Snowflake server using the golang.org/x/crypto/acme/autocert
library, configure a certificate manager for the server's domain name and then create a new
Transport as follows:

	// The snowflake server runs a websocket server. To run this securely, you will
	// need a valid certificate.
	certManager := &autocert.Manager{
		Prompt:     autocert.AcceptTOS,
		HostPolicy: autocert.HostWhitelist("snowflake.yourdomain.com"),
		Email:      "you@yourdomain.com",
	}

	transport := snowflake_server.NewSnowflakeServer(certManager.GetCertificate)

The Listen function starts a new listener, and Accept will return incoming Snowflake connections:

	ln, err := transport.Listen(addr)
	if err != nil {
		// handle error
	}
	for {
		conn, err := ln.Accept()
		if err != nil {
			// handle error
		}
		// handle conn
	}
*/
package snowflake_server

import (
	"crypto/tls"
	"errors"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"sync"
	"time"

	"github.com/xtaci/kcp-go/v5"
	"github.com/xtaci/smux"
	"gitlab.torproject.org/tpo/anti-censorship/pluggable-transports/snowflake/v2/common/turbotunnel"
	"golang.org/x/net/http2"
)

const (
	// WindowSize is the number of packets in the send and receive window of a KCP connection.
	WindowSize = 65535
	// StreamSize controls the maximum amount of in flight data between a client and server.
	StreamSize = 1048576 //1MB
)

// Transport is a structure with methods that conform to the Go PT v2.1 API
// https://github.com/Pluggable-Transports/Pluggable-Transports-spec/blob/master/releases/PTSpecV2.1/Pluggable%20Transport%20Specification%20v2.1%20-%20Go%20Transport%20API.pdf
type Transport struct {
	getCertificate func(*tls.ClientHelloInfo) (*tls.Certificate, error)
}

// NewSnowflakeServer returns a new server-side Transport for Snowflake.
func NewSnowflakeServer(getCertificate func(*tls.ClientHelloInfo) (*tls.Certificate, error)) *Transport {

	return &Transport{getCertificate: getCertificate}
}

// Listen starts a listener on addr that will accept both turbotunnel
// and legacy Snowflake connections.
func (t *Transport) Listen(addr net.Addr, numKCPInstances int) (*SnowflakeListener, error) {
	listener := &SnowflakeListener{
		addr:   addr,
		queue:  make(chan net.Conn, 65534),
		closed: make(chan struct{}),
		ln:     make([]*kcp.Listener, 0, numKCPInstances),
	}

	// kcp-go doesn't provide an accessor for the current MTU setting (and
	// anyway we could not create a kcp.Listener without creating a
	// net.PacketConn for it first), so assume the default kcp.IKCP_MTU_DEF
	// (1400 bytes) and don't increase it elsewhere.
	handler := newHTTPHandler(addr, numKCPInstances, kcp.IKCP_MTU_DEF)
	server := &http.Server{
		Addr:        addr.String(),
		Handler:     handler,
		ReadTimeout: requestTimeout,
	}
	// We need to override server.TLSConfig.GetCertificate--but first
	// server.TLSConfig needs to be non-nil. If we just create our own new
	// &tls.Config, it will lack the default settings that the net/http
	// package sets up for things like HTTP/2. Therefore we first call
	// http2.ConfigureServer for its side effect of initializing
	// server.TLSConfig properly. An alternative would be to make a dummy
	// net.Listener, call Serve on it, and let it return.
	// https://github.com/golang/go/issues/16588#issuecomment-237386446
	err := http2.ConfigureServer(server, nil)
	if err != nil {
		return nil, err
	}
	server.TLSConfig.GetCertificate = t.getCertificate

	// Another unfortunate effect of the inseparable net/http ListenAndServe
	// is that we can't check for Listen errors like "permission denied" and
	// "address already in use" without potentially entering the infinite
	// loop of Serve. The hack we apply here is to wait a short time,
	// listenAndServeErrorTimeout, to see if an error is returned (because
	// it's better if the error message goes to the tor log through
	// SMETHOD-ERROR than if it only goes to the snowflake log).
	errChan := make(chan error)
	go func() {
		if t.getCertificate == nil {
			// TLS is disabled
			log.Printf("listening with plain HTTP on %s", addr)
			err := server.ListenAndServe()
			if err != nil {
				log.Printf("error in ListenAndServe: %s", err)
			}
			errChan <- err
		} else {
			log.Printf("listening with HTTPS on %s", addr)
			err := server.ListenAndServeTLS("", "")
			if err != nil {
				log.Printf("error in ListenAndServeTLS: %s", err)
			}
			errChan <- err
		}
	}()
	select {
	case err = <-errChan:
		break
	case <-time.After(listenAndServeErrorTimeout):
		break
	}
	if err != nil {
		return nil, err
	}

	listener.server = server

	// Start the KCP engines, set up to read and write its packets over the
	// WebSocket connections that arrive at the web server.
	// handler.ServeHTTP is responsible for encapsulation/decapsulation of
	// packets on behalf of KCP. KCP takes those packets and turns them into
	// sessions which appear in the acceptSessions function.
	for i, pconn := range handler.pconns {
		ln, err := kcp.ServeConn(nil, 0, 0, pconn)
		if err != nil {
			server.Close()
			return nil, err
		}
		go func() {
			defer ln.Close()
			err := listener.acceptSessions(ln)
			if err != nil {
				log.Printf("acceptSessions %d: %v", i, err)
			}
		}()
		listener.ln = append(listener.ln, ln)
	}

	return listener, nil

}

type SnowflakeListener struct {
	addr      net.Addr
	queue     chan net.Conn
	server    *http.Server
	ln        []*kcp.Listener
	closed    chan struct{}
	closeOnce sync.Once
}

// Accept allows the caller to accept incoming Snowflake connections.
// We accept connections from a queue to accommodate both incoming
// smux Streams and legacy non-turbotunnel connections.
func (l *SnowflakeListener) Accept() (net.Conn, error) {
	select {
	case <-l.closed:
		//channel has been closed, no longer accepting connections
		return nil, io.ErrClosedPipe
	case conn := <-l.queue:
		return conn, nil
	}
}

// Addr returns the address of the SnowflakeListener
func (l *SnowflakeListener) Addr() net.Addr {
	return l.addr
}

// Close closes the Snowflake connection.
func (l *SnowflakeListener) Close() error {
	// Close our HTTP server and our KCP listener
	l.closeOnce.Do(func() {
		close(l.closed)
		l.server.Close()
		for _, ln := range l.ln {
			ln.Close()
		}
	})
	return nil
}

// acceptStreams layers an smux.Session on the KCP connection and awaits streams
// on it. Passes each stream to our SnowflakeListener accept queue.
func (l *SnowflakeListener) acceptStreams(conn *kcp.UDPSession) error {
	// Look up the IP address associated with this KCP session, via the
	// ClientID that is returned by the session's RemoteAddr method.
	addr, ok := clientIDAddrMap.Get(conn.RemoteAddr().(turbotunnel.ClientID))
	if !ok {
		// This means that the map is tending to run over capacity, not
		// just that there was not client_ip on the incoming connection.
		// We store "" in the map in the absence of client_ip. This log
		// message means you should increase clientIDAddrMapCapacity.
		log.Printf("no address in clientID-to-IP map (capacity %d)", clientIDAddrMapCapacity)
	}

	smuxConfig := smux.DefaultConfig()
	smuxConfig.Version = 2
	smuxConfig.KeepAliveTimeout = 4 * time.Minute
	smuxConfig.MaxStreamBuffer = StreamSize
	sess, err := smux.Server(conn, smuxConfig)
	if err != nil {
		return err
	}

	for {
		stream, err := sess.AcceptStream()
		if err != nil {
			if err, ok := err.(net.Error); ok && err.Temporary() {
				continue
			}
			return err
		}
		l.queueConn(&SnowflakeClientConn{stream: stream, address: addr})
	}
}

// acceptSessions listens for incoming KCP connections and passes them to
// acceptStreams. It is handler.ServeHTTP that provides the network interface
// that drives this function.
func (l *SnowflakeListener) acceptSessions(ln *kcp.Listener) error {
	for {
		conn, err := ln.AcceptKCP()
		if err != nil {
			if err, ok := err.(net.Error); ok && err.Temporary() {
				continue
			}
			return err
		}
		// Permit coalescing the payloads of consecutive sends.
		conn.SetStreamMode(true)
		// Set the maximum send and receive window sizes to a high number
		// Removes KCP bottlenecks: https://gitlab.torproject.org/tpo/anti-censorship/pluggable-transports/snowflake/-/issues/40026
		conn.SetWindowSize(WindowSize, WindowSize)
		// Disable the dynamic congestion window (limit only by the
		// maximum of local and remote static windows).
		conn.SetNoDelay(
			0, // default nodelay
			0, // default interval
			0, // default resend
			1, // nc=1 => congestion window off
		)
		go func() {
			defer conn.Close()
			err := l.acceptStreams(conn)
			if err != nil && !errors.Is(err, io.ErrClosedPipe) {
				log.Printf("acceptStreams: %v", err)
			}
		}()
	}
}

func (l *SnowflakeListener) queueConn(conn net.Conn) error {
	select {
	case <-l.closed:
		return fmt.Errorf("accepted connection on closed listener")
	case l.queue <- conn:
		return nil
	}
}

// SnowflakeClientConn is a wrapper for the underlying turbotunnel conn
// (smux.Stream). It implements the net.Conn and io.WriterTo interfaces. The
// RemoteAddr method is overridden to refer to a real IP address, looked up from
// the client address map, rather than an abstract client ID.
type SnowflakeClientConn struct {
	stream  *smux.Stream
	address net.Addr
}

// Forward net.Conn methods, other than RemoteAddr, to the inner stream.
func (conn *SnowflakeClientConn) Read(b []byte) (int, error)    { return conn.stream.Read(b) }
func (conn *SnowflakeClientConn) Write(b []byte) (int, error)   { return conn.stream.Write(b) }
func (conn *SnowflakeClientConn) Close() error                  { return conn.stream.Close() }
func (conn *SnowflakeClientConn) LocalAddr() net.Addr           { return conn.stream.LocalAddr() }
func (conn *SnowflakeClientConn) SetDeadline(t time.Time) error { return conn.stream.SetDeadline(t) }
func (conn *SnowflakeClientConn) SetReadDeadline(t time.Time) error {
	return conn.stream.SetReadDeadline(t)
}
func (conn *SnowflakeClientConn) SetWriteDeadline(t time.Time) error {
	return conn.stream.SetWriteDeadline(t)
}

// RemoteAddr returns the mapped client address of the Snowflake connection.
func (conn *SnowflakeClientConn) RemoteAddr() net.Addr {
	return conn.address
}

// WriteTo implements the io.WriterTo interface by passing the call to the
// underlying smux.Stream.
func (conn *SnowflakeClientConn) WriteTo(w io.Writer) (int64, error) {
	return conn.stream.WriteTo(w)
}
