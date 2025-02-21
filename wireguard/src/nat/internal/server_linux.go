package internal

import (
	"encoding/binary"
	"io"
	"log"
	"net"
	"os"
	"os/signal"
	"sync"
	"syscall"

	"github.com/google/gopacket"
	"github.com/google/gopacket/layers"
)

const (
	interfaceName = "eth0" // Change this to the correct outgoing interface
	natIP = "54.90.59.253"
)


type Address struct {
	ip string
	port uint16
}

type Stream struct {
	client_addr Address
	pkt *gopacket.Packet
}

type NatServer interface {
	// maybe using context?
	listener(conn net.Conn) // receive from proxy server, put into receiving channel
	sendToUpstreamServer(s Stream) // process(decapsulate) proxy packets, syscall.Sendto(af_packet sock fd)
	readResponse() // receive from upstream, syscall.Recvfrom(af_packet sock fd) put into sending channel
	sender() // receive from sending channel, write to proxy tcp conn
}

// one server will be connected to multiple proxy servers
type Server struct {
	receivingChann chan Stream 
	sendingChann chan *gopacket.Packet 
	singal chan int
	af_socket_fd int 
	client_addr Address
	proxy_conn net.Conn
}

func NewServer() *Server {
	return &Server{
		receivingChann: make(chan Stream, 1000),
		sendingChann: make(chan *gopacket.Packet, 1000),
	}
}

func(s *Server) Run() {
	// Create a DGRAM() AF_PACKET socket for all protocls(ipv4/6, ARP, VLAN, Captures IEEE 802.3 raw packets)
	// DGRAM because we only care about L3 and above; if set to RAW, that would include L2 and we should construct it too which we don't want
	// No need to bind because we want to listen to all interfaces(I don't know which interface it will use and we don't care)
	// Checkout the man 7 packet
	fd, err := syscall.Socket(syscall.AF_PACKET, syscall.SOCK_DGRAM, int(htons(syscall.ETH_P_IP)))
	if err != nil {
		log.Fatalf("Failed to create AF_PACKET socket: %v", err)
	}
	defer syscall.Close(fd)

	s.af_socket_fd = fd
	log.Println("AF_PACKET socket set up for packet capture")

    // WaitGroup to ensure all goroutines exit properly
    var wg sync.WaitGroup

    // Capture OS signals (CTRL+C) to gracefully shut down
    stopChan := make(chan os.Signal, 1)
    signal.Notify(stopChan, os.Interrupt, syscall.SIGTERM)

    // Start necessary goroutines (TCP server, packet reading, processing)
	// 3 is not accurate, just for testing purposes
    wg.Add(3)

    go func() {
        defer wg.Done()
        s.startTCPServer()
    }()
    go func() {
        defer wg.Done()
        s.poller()
    }()
    go func() {
        defer wg.Done()
        s.readResponse()
    }()

    <-stopChan // Block until signal is received

    log.Println("Shutting down server gracefully...")

    close(s.receivingChann)
    close(s.sendingChann)

    // Close AF_PACKET socket
    syscall.Close(s.af_socket_fd)
    
    // Close proxy connection (if open)
    if s.proxy_conn != nil {
        s.proxy_conn.Close()
    }

    wg.Wait() // Wait for all goroutines to exit
    log.Println("NAT server shut down successfully.")
}



// This is for setting up the tcp socket in which we will be receiving packets from proxy server
func(s *Server) startTCPServer() {
	ln, err := net.Listen("tcp", "0.0.0.0:8000") // Listen for connections from proxy
	if err != nil {
		log.Fatalf("Failed to start NAT server: %v", err)
	}
	defer ln.Close()

	log.Println("NAT server listening on port 8000")

	for {
		// Accept is a blocking call so it won't cause busy-waiting
		conn, err := ln.Accept()
		if err != nil {
			log.Printf("Connection error: %v", err)
			continue
		}
		log.Printf("New connection from %s", conn.RemoteAddr().String())
		s.proxy_conn = conn
		go s.listener(conn)
	}
}

func(s *Server) listener(conn net.Conn) {
	// should close?
//	defer conn.Close()

	// what happens here? why is it inside a for loop
	// I think we keep reading from Proxy, we should not read until there is something to read.
	// TODO: change the code to avoid busy waiting
	for {
		log.Println("READING FROM PROXY")
		var encapsulatedLen uint32
		err := binary.Read(conn, binary.BigEndian, &encapsulatedLen)
		if err != nil {
			if err == io.EOF {
				log.Println("Connection closed by Proxy server")
				return
			}
			log.Println("Error reading encapsulated length")
			continue
		}

		// Read payload
		if encapsulatedLen > 65535 { // Maximum IPv4 packet size
            log.Printf("Invalid packet length received: %d", encapsulatedLen)
            continue
        }

        // Read payload
        payload := make([]byte, encapsulatedLen)
        if _, err = io.ReadFull(conn, payload); err != nil {
            log.Println("Error reading payload:", err)
            continue
        }

        // Create packet and handle parsing errors
        pkt := gopacket.NewPacket(payload, layers.LayerTypeIPv4, gopacket.Default)
        
        // Check for errors in packet parsing
        if err := pkt.ErrorLayer(); err != nil {
            log.Println("Error decoding packet:", err.Error())
            continue
        }

        // Get IP layer
        ipv4Layer := pkt.Layer(layers.LayerTypeIPv4)
        if ipv4Layer == nil {
            log.Println("Packet doesn't contain IPv4 layer")
            continue
        }

        ipLayer, ok := ipv4Layer.(*layers.IPv4)
        if !ok {
            log.Println("Failed to decode IPv4 layer")
            continue
        }

        // Initialize port
        var port uint16
        var foundTransportLayer bool

        // Handle TCP layer
        if tcpLayer := pkt.Layer(layers.LayerTypeTCP); tcpLayer != nil {
            if tcp, ok := tcpLayer.(*layers.TCP); ok {
                port = uint16(tcp.SrcPort)
                foundTransportLayer = true
            }
        }

        // Handle UDP layer
        if !foundTransportLayer {
            if udpLayer := pkt.Layer(layers.LayerTypeUDP); udpLayer != nil {
                if udp, ok := udpLayer.(*layers.UDP); ok {
                    port = uint16(udp.SrcPort)
                    foundTransportLayer = true
                }
            }
        }

        // If neither TCP nor UDP was found
        if !foundTransportLayer {
            log.Println("Packet contains neither TCP nor UDP layer")
            continue
        }

        // Create address structure with proper string conversion of IP
        c_addr := Address{
            ip:   ipLayer.SrcIP.String(), // Convert IP to string properly
            port: port,
        }

        // Create stream and send to channel
        st := Stream{
            client_addr: c_addr,
            pkt:        &pkt,
        }
		s.receivingChann <- st 
	}
}

func(s *Server) poller() {
	for {
		select {
		case st := <- s.receivingChann:
			s.processPacket(st)
		case p := <- s.sendingChann:
			s.sender(p)
		}
	}
}

func(s *Server) sender(pkt *gopacket.Packet) {
	// change the dst IP and port to the client, Recalculate checksum
	p_bytes := (*pkt).Data()

	ipHeader := p_bytes[:20]

	// Modify source IP (bytes 12-15 in IP header)
	newSrcIP := net.ParseIP(natIP).To4() // Change to NAT server IP
	copy(ipHeader[12:16], newSrcIP)

	// Recalculate checksum (clear old checksum first)
	ipHeader[10] = 0
	ipHeader[11] = 0
	newChecksum := calculateIPChecksum(ipHeader)
	binary.BigEndian.PutUint16(ipHeader[10:12], newChecksum)

	log.Printf("Forwarding packet: SRC=%s -> DST=%s", newSrcIP, net.IP(p_bytes[16:20]))

	s.proxy_conn.Write(p_bytes)
}

func(s *Server) readResponse() {
	buf := make([]byte, 65536)	
	for {
		log.Println("reading from af_packet socket")
		n,_,err := syscall.Recvfrom(s.af_socket_fd, buf, 0)
		if err != nil {
			log.Println("Error reading from socket:", err)
			continue
		}
		if n < 20 {
			log.Println("Received packet too small, discarding")
			continue
		}

		pkt := gopacket.NewPacket(buf[:n], layers.LayerTypeIPv4, gopacket.Default)
		ipv4Layer := pkt.Layer(layers.LayerTypeIPv4)
		if ipv4Layer == nil {
			log.Println("Ignoring non-IPv4 packet")
			continue
		}

		ipLayer := ipv4Layer.(*layers.IPv4)
		log.Printf("on readResponse IP: src:%s   dst:%s", ipLayer.SrcIP, ipLayer.DstIP )
		
		// Discard invalid packets
		if tcpLayer := pkt.Layer(layers.LayerTypeTCP); tcpLayer != nil {
            tcp := tcpLayer.(*layers.TCP)
            if tcp.DstPort == 8000 {
                continue // Ignore packets for NAT's own TCP port
            }
        }

//		if ipLayer.SrcIP.String() != natIP{
//			log.Println("Got unexpected source IP, ignoring packet")
//			continue
//		}

		s.sendingChann <- &pkt
	}
}

func(s *Server) processPacket(st Stream) {
	// Extract IP header (first 20 bytes for IPv4)
	packet := (*(st.pkt)).Data()
	ipHeader := packet[:20]

	// Modify source IP (bytes 12-15 in IP header)
	newSrcIP := net.ParseIP(natIP).To4() // Change to NAT server IP
	copy(ipHeader[12:16], newSrcIP)

	// Recalculate checksum (clear old checksum first)
	ipHeader[10] = 0
	ipHeader[11] = 0
	newChecksum := calculateIPChecksum(ipHeader)
	binary.BigEndian.PutUint16(ipHeader[10:12], newChecksum)

	log.Printf("Forwarding packet: SRC=%s -> DST=%s", newSrcIP, net.IP(packet[16:20]))

	// Send packet using AF_PACKET
	s.sendToUpstreamServer(packet)
}

func calculateIPChecksum(header []byte) uint16 {
	var sum uint32
	for i := 0; i < len(header); i += 2 {
		sum += uint32(binary.BigEndian.Uint16(header[i : i+2]))
	}
	for sum > 0xFFFF {
		sum = (sum >> 16) + (sum & 0xFFFF)
	}
	return uint16(^sum)
}

func (s *Server) sendToUpstreamServer(data []byte) {
    // Convert packet to raw bytes
    if len(data) == 0 {
        log.Println("Packet has no data, skipping send")
        return
    }

    // Define the socket address structure (destination)
    sockAddr := &syscall.SockaddrLinklayer{
        Protocol: htons(syscall.ETH_P_IP), // Sending an IPv4 packet
        Ifindex:  s.getInterfaceIndex("eth0"), // Replace "eth0" with the correct interface name
    }

    // Send the packet
    err := syscall.Sendto(s.af_socket_fd, data, 0, sockAddr) 
    if err != nil {
        log.Printf("Failed to send packet: %v", err)
    } else {
        log.Println("Packet sent successfully")
    }
}

func (s *Server) getInterfaceIndex(ifaceName string) int {
    iface, err := net.InterfaceByName(ifaceName)
    if err != nil {
        log.Printf("Failed to get interface %s: %v", ifaceName, err)
        return 0
    }
    return iface.Index
}

func htons(i uint16) uint16 {
	return (i<<8)&0xff00 | i>>8
}
