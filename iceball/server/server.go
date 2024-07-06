// Snowflake-specific websocket server plugin. It reports the transport name as
// "snowflake".
package main

import (
	"errors"
	"flag"
	"fmt"
	"io"
	"io/ioutil"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"syscall"

	"gitlab.torproject.org/tpo/anti-censorship/pluggable-transports/snowflake/v2/common/safelog"
	"gitlab.torproject.org/tpo/anti-censorship/pluggable-transports/snowflake/v2/common/version"
	"golang.org/x/crypto/acme/autocert"

	pt "gitlab.torproject.org/tpo/anti-censorship/pluggable-transports/goptlib"
	sf "gitlab.torproject.org/tpo/anti-censorship/pluggable-transports/snowflake/v2/server/lib"
)

const ptMethodName = "snowflake"

var ptInfo pt.ServerInfo

func usage() {
	fmt.Fprintf(os.Stderr, `Usage: %s [OPTIONS]

WebSocket server pluggable transport for Snowflake. Works only as a managed
proxy. Uses TLS with ACME (Let's Encrypt) by default. Set the certificate
hostnames with the --acme-hostnames option. Use ServerTransportListenAddr in
torrc to choose the listening port. When using TLS, this program will open an
additional HTTP listener on port 80 to work with ACME.

`, os.Args[0])
	flag.PrintDefaults()
}

// proxy copies data bidirectionally from one connection to another.
func proxy(local *net.TCPConn, conn net.Conn) {
	var wg sync.WaitGroup
	wg.Add(2)

	go func() {
		if _, err := io.Copy(conn, local); err != nil && !errors.Is(err, io.ErrClosedPipe) {
			log.Printf("error copying ORPort to WebSocket %v", err)
		}
		local.CloseRead()
		conn.Close()
		wg.Done()
	}()
	go func() {
		if _, err := io.Copy(local, conn); err != nil && !errors.Is(err, io.EOF) && !errors.Is(err, io.ErrClosedPipe) {
			log.Printf("error copying WebSocket to ORPort %v", err)
		}
		local.CloseWrite()
		conn.Close()
		wg.Done()
	}()

	wg.Wait()
}

// handleConn bidirectionally connects a client snowflake connection with the
// ORPort. If orPortSrcAddr is not nil, addresses from the given range are used
// when dialing the ORPOrt.
func handleConn(conn net.Conn, orPortSrcAddr *net.IPNet) error {
	addr := conn.RemoteAddr().String()
	statsChannel <- addr != ""

	dialer := net.Dialer{
		Control: dialerControl,
	}
	if orPortSrcAddr != nil {
		// Use a random source IP address in the given range.
		ip, err := randIPAddr(orPortSrcAddr)
		if err != nil {
			return err
		}
		dialer.LocalAddr = &net.TCPAddr{IP: ip}
	}
	or, err := pt.DialOrWithDialer(&dialer, &ptInfo, addr, ptMethodName)
	if err != nil {
		return fmt.Errorf("failed to connect to ORPort: %s", err)
	}
	defer or.Close()

	proxy(or.(*net.TCPConn), conn)
	return nil
}

// acceptLoop accepts incoming client snowflake connections and passes them to
// handleConn. If orPortSrcAddr is not nil, addresses from the given range are
// used when dialing the ORPOrt.
func acceptLoop(ln net.Listener, orPortSrcAddr *net.IPNet) {
	for {
		conn, err := ln.Accept()
		if err != nil {
			if err, ok := err.(net.Error); ok && err.Temporary() {
				continue
			}
			log.Printf("Snowflake accept error: %s", err)
			break
		}
		go func() {
			defer conn.Close()
			err := handleConn(conn, orPortSrcAddr)
			if err != nil {
				log.Printf("handleConn: %v", err)
			}
		}()
	}
}

func getCertificateCacheDir() (string, error) {
	stateDir, err := pt.MakeStateDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(stateDir, "snowflake-certificate-cache"), nil
}

func main() {
	var acmeEmail string
	var acmeHostnamesCommas string
	var disableTLS bool
	var logFilename string
	var unsafeLogging bool
	var versionFlag bool

	flag.Usage = usage
	flag.StringVar(&acmeEmail, "acme-email", "", "optional contact email for Let's Encrypt notifications")
	flag.StringVar(&acmeHostnamesCommas, "acme-hostnames", "", "comma-separated hostnames for TLS certificate")
	flag.BoolVar(&disableTLS, "disable-tls", false, "don't use HTTPS")
	flag.StringVar(&logFilename, "log", "", "log file to write to")
	flag.BoolVar(&unsafeLogging, "unsafe-logging", false, "prevent logs from being scrubbed")
	flag.BoolVar(&versionFlag, "version", false, "display version info to stderr and quit")
	flag.Parse()

	if versionFlag {
		fmt.Fprintf(os.Stderr, "snowflake-server %s", version.ConstructResult())
		os.Exit(0)
	}

	log.SetFlags(log.LstdFlags | log.LUTC)

	var logOutput io.Writer = os.Stderr
	if logFilename != "" {
		f, err := os.OpenFile(logFilename, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0600)
		if err != nil {
			log.Fatalf("can't open log file: %s", err)
		}
		defer f.Close()
		logOutput = f
	}
	if unsafeLogging {
		log.SetOutput(logOutput)
	} else {
		// We want to send the log output through our scrubber first
		log.SetOutput(&safelog.LogScrubber{Output: logOutput})
	}

	log.Printf("snowflake-server %s\n", version.GetVersion())

	if !disableTLS && acmeHostnamesCommas == "" {
		log.Fatal("the --acme-hostnames option is required")
	}
	acmeHostnames := strings.Split(acmeHostnamesCommas, ",")

	log.Printf("starting")
	var err error
	ptInfo, err = pt.ServerSetup(nil)
	if err != nil {
		log.Fatalf("error in setup: %s", err)
	}

	go statsThread()

	var certManager *autocert.Manager
	if !disableTLS {
		log.Printf("ACME hostnames: %q", acmeHostnames)

		var cache autocert.Cache
		var cacheDir string
		cacheDir, err = getCertificateCacheDir()
		if err == nil {
			log.Printf("caching ACME certificates in directory %q", cacheDir)
			cache = autocert.DirCache(cacheDir)
		} else {
			log.Printf("disabling ACME certificate cache: %s", err)
		}

		certManager = &autocert.Manager{
			Prompt:     autocert.AcceptTOS,
			HostPolicy: autocert.HostWhitelist(acmeHostnames...),
			Email:      acmeEmail,
			Cache:      cache,
		}
	}

	// The ACME HTTP-01 responder only works when it is running on port 80.
	// We actually open the port in the loop below, so that any errors can
	// be reported in the SMETHOD-ERROR of some bindaddr.
	// https://github.com/ietf-wg-acme/acme/blob/master/draft-ietf-acme-acme.md#http-challenge
	needHTTP01Listener := !disableTLS

	listeners := make([]net.Listener, 0)
	for _, bindaddr := range ptInfo.Bindaddrs {
		if bindaddr.MethodName != ptMethodName {
			pt.SmethodError(bindaddr.MethodName, "no such method")
			continue
		}

		if needHTTP01Listener {
			addr := *bindaddr.Addr
			addr.Port = 80
			log.Printf("Starting HTTP-01 ACME listener")
			var lnHTTP01 *net.TCPListener
			lnHTTP01, err = net.ListenTCP("tcp", &addr)
			if err != nil {
				log.Printf("error opening HTTP-01 ACME listener: %s", err)
				pt.SmethodError(bindaddr.MethodName, "HTTP-01 ACME listener: "+err.Error())
				continue
			}
			server := &http.Server{
				Addr:    addr.String(),
				Handler: certManager.HTTPHandler(nil),
			}
			go func() {
				log.Fatal(server.Serve(lnHTTP01))
			}()
			listeners = append(listeners, lnHTTP01)
			needHTTP01Listener = false
		}

		// We're not capable of listening on port 0 (i.e., an ephemeral port
		// unknown in advance). The reason is that while the net/http package
		// exposes ListenAndServe and ListenAndServeTLS, those functions never
		// return, so there's no opportunity to find out what the port number
		// is, in between the Listen and Serve steps.
		// https://groups.google.com/d/msg/Golang-nuts/3F1VRCCENp8/3hcayZiwYM8J
		if bindaddr.Addr.Port == 0 {
			err := fmt.Errorf(
				"cannot listen on port %d; configure a port using ServerTransportListenAddr",
				bindaddr.Addr.Port)
			log.Printf("error opening listener: %s", err)
			pt.SmethodError(bindaddr.MethodName, err.Error())
			continue
		}

		var transport *sf.Transport
		args := pt.Args{}
		if disableTLS {
			args.Add("tls", "no")
			transport = sf.NewSnowflakeServer(nil)
		} else {
			args.Add("tls", "yes")
			for _, hostname := range acmeHostnames {
				args.Add("hostname", hostname)
			}
			transport = sf.NewSnowflakeServer(certManager.GetCertificate)
		}

		// Are we requested to use source addresses from a particular
		// range when dialing the ORPort for this transport?
		var orPortSrcAddr *net.IPNet
		if orPortSrcAddrCIDR, ok := bindaddr.Options.Get("orport-srcaddr"); ok {
			ipnet, err := parseIPCIDR(orPortSrcAddrCIDR)
			if err != nil {
				err = fmt.Errorf("parsing srcaddr: %w", err)
				log.Println(err)
				pt.SmethodError(bindaddr.MethodName, err.Error())
				continue
			}
			orPortSrcAddr = ipnet
		}

		numKCPInstances := 1
		// Are we requested to run a certain number of KCP state
		// machines?
		if value, ok := bindaddr.Options.Get("num-turbotunnel"); ok {
			n, err := strconv.Atoi(value)
			if err == nil && n < 1 {
				err = fmt.Errorf("cannot be less than 1")
			}
			if err != nil {
				err = fmt.Errorf("parsing num-turbotunnel: %w", err)
				log.Println(err)
				pt.SmethodError(bindaddr.MethodName, err.Error())
				continue
			}
			numKCPInstances = n
		}

		ln, err := transport.Listen(bindaddr.Addr, numKCPInstances)
		if err != nil {
			log.Printf("error opening listener: %s", err)
			pt.SmethodError(bindaddr.MethodName, err.Error())
			continue
		}
		defer ln.Close()
		go acceptLoop(ln, orPortSrcAddr)
		pt.SmethodArgs(bindaddr.MethodName, bindaddr.Addr, args)
		listeners = append(listeners, ln)
	}
	pt.SmethodsDone()

	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGTERM)

	if os.Getenv("TOR_PT_EXIT_ON_STDIN_CLOSE") == "1" {
		// This environment variable means we should treat EOF on stdin
		// just like SIGTERM: https://bugs.torproject.org/15435.
		go func() {
			if _, err := io.Copy(ioutil.Discard, os.Stdin); err != nil {
				log.Printf("error copying os.Stdin to ioutil.Discard: %v", err)
			}
			log.Printf("synthesizing SIGTERM because of stdin close")
			sigChan <- syscall.SIGTERM
		}()
	}

	// Wait for a signal.
	sig := <-sigChan

	// Signal received, shut down.
	log.Printf("caught signal %q, exiting", sig)
	for _, ln := range listeners {
		ln.Close()
	}
}
