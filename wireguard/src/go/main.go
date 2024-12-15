package main

import (
	"encoding/binary"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"sync"
	"syscall"
	"time"

	"github.com/google/gopacket"
	"github.com/google/gopacket/layers"
	"github.com/google/gopacket/pcap"
	"go.uber.org/zap"
	"go.uber.org/zap/zapcore"
)

const (
    ifn = "wg0"
    natIPv4 = "10.27.0.20" // Should set to NAT IP
    natPort = "8000"
    snapLen = 1024
    promiscuous = false
	  timeout     = 10 * time.Second
)

// Stream represents a single client data stream
type Stream struct {
    ID        string
    ClientIP  net.IP
    ClientPort uint16
    DestIP    net.IP
    DestPort  uint16
    Created   time.Time
}

// Proxy handles the main proxy functionality
type Proxy struct {
    natConn          net.Conn
    wgHandle         *pcap.Handle
    logger           *zap.Logger
    streams          map[string]*Stream
    streamMutex      sync.RWMutex
    
    // Channels for packet handling
    wgPacketChan     chan *gopacket.Packet
    natPacketChan    chan *gopacket.Packet
    done             chan struct{}
}

var (
//    currentIPv4       string
    defaultInterface *net.Interface
    natConn net.Conn
//    wgHandle *pcap.Handle
    logger  *zap.Logger
)

func tehranTimeEncoder(t time.Time, enc zapcore.PrimitiveArrayEncoder) {
    loc, err := time.LoadLocation("Asia/Tehran")
    if err != nil {
        // Fallback to UTC if Tehran timezone can't be loaded
        enc.AppendString(t.UTC().Format(time.RFC3339))
        return
    }
    enc.AppendString(t.In(loc).Format(time.RFC3339))
}

func initLogger() error {
	if err := os.MkdirAll("logs", 0755); err != nil {
		return fmt.Errorf("failed to create log directory: %v", err)
	}

  logFile, err := os.OpenFile(
    filepath.Join("logs", "proxy.log"),
    os.O_CREATE|os.O_APPEND|os.O_WRONLY,
		0644,
	)

	if err != nil {
		return fmt.Errorf("failed to open log file: %v", err)
  }

  fileSyncer := zapcore.AddSync(logFile)
	fileEncoder := zapcore.NewJSONEncoder(zapcore.EncoderConfig{
		TimeKey:        "timestamp",
		LevelKey:       "level",
		NameKey:        "logger",
		CallerKey:      "caller",
    FunctionKey:    zapcore.OmitKey,
		MessageKey:     "msg",
		StacktraceKey:  "stacktrace",
    LineEnding:     zapcore.DefaultLineEnding,
		EncodeLevel:    zapcore.CapitalLevelEncoder,
		EncodeTime:     tehranTimeEncoder,
    EncodeDuration: zapcore.SecondsDurationEncoder,
		EncodeCaller:   zapcore.ShortCallerEncoder,
	})

	consoleSyncer := zapcore.AddSync(os.Stdout)
	consoleEncoder := zapcore.NewConsoleEncoder(zapcore.EncoderConfig{
		TimeKey:        "timestamp",
		LevelKey:       "level",
		NameKey:        "logger",
		CallerKey:      "caller",
		MessageKey:     "msg",
		StacktraceKey:  "stacktrace",
		LineEnding:     zapcore.DefaultLineEnding,
		EncodeLevel:    zapcore.CapitalLevelEncoder,
		EncodeTime:     tehranTimeEncoder,
		EncodeDuration: zapcore.StringDurationEncoder,
		EncodeCaller:   zapcore.ShortCallerEncoder,
	})

	core := zapcore.NewTee(
		zapcore.NewCore(fileEncoder, fileSyncer, zapcore.DebugLevel),
		zapcore.NewCore(consoleEncoder, consoleSyncer, zapcore.DebugLevel),
	)

  logger = zap.New(core, zap.AddCaller(), zap.AddStacktrace(zapcore.ErrorLevel))

	return nil
}

func init() {
    var err error
    defaultInterface, err = getDefalutInterface()
    if err != nil {
        log.Fatalf("Failed to get default interface: %v", err)
    }
//    currentIPv4, err = getPublicIP()
//    if err != nil {
//        logger.Fatalf("Failed to get public IP: %v", err)
//    }
}

func NewProxy(logger *zap.Logger) (*Proxy, error) {
    wgHandle, err := pcap.OpenLive(ifn, snapLen, promiscuous, timeout)
    if err != nil {
        return nil, fmt.Errorf("failed to open WireGuard interface: %v", err)
    }

    return &Proxy{
        logger:        logger,
        wgHandle:      wgHandle,
        streams:       make(map[string]*Stream),
        wgPacketChan: make(chan *gopacket.Packet, 1000),
        natPacketChan:    make(chan *gopacket.Packet, 1000),
        done:          make(chan struct{}),
    }, nil
}

func (p *Proxy) connectToNAT() error {
    natPoint := fmt.Sprintf("%s:%s", "nat", natPort)
    maxRetries := 5
    for i := 0; i < maxRetries; i++ {
        conn, err := net.Dial("tcp", natPoint)
        if err == nil {
            p.natConn = conn
            return nil
        }
        p.logger.Warn("Failed to connect to NAT server", 
            zap.Int("attempt", i+1), 
            zap.Error(err))
        time.Sleep(time.Second * 2)
    }
    return fmt.Errorf("failed to connect to NAT server after %d attempts", maxRetries)
}

func (p *Proxy) captureWgPackets() {
    pktSrc := gopacket.NewPacketSource(p.wgHandle, p.wgHandle.LinkType())
    for pkt := range pktSrc.Packets() {
        p.logger.Debug("Processing WG packet",
            zap.Int("packet_size", len(pkt.Data())),
            zap.String("layer_dump", pkt.Dump()))
        
        select {
        case <-p.done:
            return
        case p.wgPacketChan <- &pkt:
        }
    }
}

func (p *Proxy) handleClientPkt(pkt *gopacket.Packet) error {
    p.logger.Debug("Processing client packet")
    
    ipLayer := (*pkt).Layer(layers.LayerTypeIPv4)
    if ipLayer == nil {
        return fmt.Errorf("no IP layer found")
    }
    
    ipHeader := ipLayer.(*layers.IPv4)
    var streamKey string
    
    // Create stream key based on protocol
    switch {
    case (*pkt).Layer(layers.LayerTypeTCP) != nil:
        tcpLayer := (*pkt).Layer(layers.LayerTypeTCP).(*layers.TCP)
        streamKey = fmt.Sprintf("tcp-%s:%d-%s:%d", 
            ipHeader.SrcIP, tcpLayer.SrcPort,
            ipHeader.DstIP, tcpLayer.DstPort)
            
    case (*pkt).Layer(layers.LayerTypeUDP) != nil:
        udpLayer := (*pkt).Layer(layers.LayerTypeUDP).(*layers.UDP)
        streamKey = fmt.Sprintf("udp-%s:%d-%s:%d",
            ipHeader.SrcIP, udpLayer.SrcPort,
            ipHeader.DstIP, udpLayer.DstPort)
            
    case (*pkt).Layer(layers.LayerTypeICMPv4) != nil:
        icmpLayer := (*pkt).Layer(layers.LayerTypeICMPv4).(*layers.ICMPv4)
        streamKey = fmt.Sprintf("icmp-%s-%s-%d-%d",
            ipHeader.SrcIP, ipHeader.DstIP,
            icmpLayer.TypeCode.Type(), icmpLayer.TypeCode.Code())
            
    default:
        return fmt.Errorf("unsupported protocol")
    }

    // Get the complete packet data - we want to preserve all headers
    pData := (*pkt).Data()
    
    p.logPktDetails(pkt)
    // Prepare the buffer
    // Protocol: [stream key length][stream key][payload length][payload]
    streamKeyLen := uint32(len(streamKey))
    payloadLen := uint32(len(pData))
    totalLen := 4 + streamKeyLen + 4 + payloadLen
    
    buf := make([]byte, totalLen)
    offset := 0
    
    // Write stream key length (4 bytes)
    binary.BigEndian.PutUint32(buf[offset:offset+4], streamKeyLen)
    offset += 4
    
    // Write stream key
    copy(buf[offset:offset+int(streamKeyLen)], streamKey)
    offset += int(streamKeyLen)
    
    // Write payload length (4 bytes)
    binary.BigEndian.PutUint32(buf[offset:offset+4], payloadLen)
    offset += 4
    
    // Write complete packet data
    copy(buf[offset:], pData)
    
    // Log packet details before sending
    p.logger.Debug("Forwarding packet to NAT",
        zap.String("stream_key", streamKey),
        zap.Uint32("packet_length", payloadLen))
    
    // Send to NAT server
    _, err := p.natConn.Write(buf)
    if err != nil {
        return fmt.Errorf("failed to write to NAT: %v", err)
    }
    
    p.logger.Info("Packet forwarded successfully", zap.Uint32("bytes", payloadLen))
    return nil
}

func (p *Proxy) readNATPkt() {
    for {
        select {
        case <-p.done:
            return
        default:
            // Read stream key length
            lenBuf := make([]byte, 4)
            if _, err := io.ReadFull(p.natConn, lenBuf); err != nil {
                if err == io.EOF {
                    p.logger.Info("Connection closed by NAT server")
                    return
                }
                p.logger.Warn("Error reading stream key length", zap.Error(err))
                continue
            }
            streamKeyLen := binary.BigEndian.Uint32(lenBuf)
            
            // Read stream key
            streamKey := make([]byte, streamKeyLen)
            if _, err := io.ReadFull(p.natConn, streamKey); err != nil {
                p.logger.Warn("Error reading stream key", zap.Error(err))
                continue
            }
            
            // Read payload length
            if _, err := io.ReadFull(p.natConn, lenBuf); err != nil {
                p.logger.Warn("Error reading payload length", zap.Error(err))
                continue
            }
            payloadLen := binary.BigEndian.Uint32(lenBuf)
            
            // Read payload
            payload := make([]byte, payloadLen)
            if _, err := io.ReadFull(p.natConn, payload); err != nil {
                p.logger.Warn("Error reading payload", zap.Error(err))
                continue
            }
            
            // Create packet and send to channel
            pkt := gopacket.NewPacket(payload, layers.LayerTypeIPv4, gopacket.Default)
            p.logPktDetails(&pkt)
            p.natPacketChan <- &pkt
        }
    }
}

func (p *Proxy) logPktDetails(pkt *gopacket.Packet) {
    logFields := []zap.Field{
        zap.Int("total_layers", len((*pkt).Layers())),
    }

    // Log IPv4 layer details
    if ipLayer := (*pkt).Layer(layers.LayerTypeIPv4); ipLayer != nil {
        ip, _ := ipLayer.(*layers.IPv4)
        logFields = append(logFields,
            zap.String("src_ip", ip.SrcIP.String()),
            zap.String("dst_ip", ip.DstIP.String()),
            zap.Int("ttl", int(ip.TTL)),
            zap.Int("length", int(ip.Length)),
            zap.String("protocol", ip.Protocol.String()),
        )
    }

    // Log TCP layer details
    if tcpLayer := (*pkt).Layer(layers.LayerTypeTCP); tcpLayer != nil {
        tcp, _ := tcpLayer.(*layers.TCP)
        logFields = append(logFields,
            zap.Uint16("src_port", uint16(tcp.SrcPort)),
            zap.Uint16("dst_port", uint16(tcp.DstPort)),
            zap.Uint32("seq_num", tcp.Seq),
            zap.Uint32("ack_num", tcp.Ack),
            zap.Bool("syn_flag", tcp.SYN),
            zap.Bool("ack_flag", tcp.ACK),
            zap.Bool("fin_flag", tcp.FIN),
            zap.Bool("rst_flag", tcp.RST),
            zap.Bool("psh_flag", tcp.PSH),
            zap.Int("window_size", int(tcp.Window)),
        )
    }

    // Log UDP layer details
    if udpLayer := (*pkt).Layer(layers.LayerTypeUDP); udpLayer != nil {
        udp, _ := udpLayer.(*layers.UDP)
        logFields = append(logFields,
            zap.Uint16("src_port", uint16(udp.SrcPort)),
            zap.Uint16("dst_port", uint16(udp.DstPort)),
            zap.Int("length", int(udp.Length)),
        )
    }

    // Log ICMP layer details
    if icmpLayer := (*pkt).Layer(layers.LayerTypeICMPv4); icmpLayer != nil {
        icmp, _ := icmpLayer.(*layers.ICMPv4)
        logFields = append(logFields,
            zap.Uint8("icmp_type", icmp.TypeCode.Type()),
            zap.Uint8("icmp_code", icmp.TypeCode.Code()),
        )
    }

    // Log DNS layer details
    if dnsLayer := (*pkt).Layer(layers.LayerTypeDNS); dnsLayer != nil {
        dns, _ := dnsLayer.(*layers.DNS)
        questions := make([]string, 0, len(dns.Questions))
        for _, q := range dns.Questions {
            questions = append(questions, string(q.Name))
        }
        logFields = append(logFields,
            zap.Uint16("dns_id", dns.ID),
            zap.Bool("is_response", dns.QR),
            zap.Strings("questions", questions),
            zap.Int("answer_count", len(dns.Answers)),
        )
    }

    // Log application layer details
    if appLayer := (*pkt).ApplicationLayer(); appLayer != nil {
        logFields = append(logFields,
            zap.Int("payload_length", len(appLayer.Payload())),
        )
    }

    // Log any errors in packet
    if errLayer := (*pkt).ErrorLayer(); errLayer != nil {
        logFields = append(logFields,
            zap.Error(errLayer.Error()),
        )
    }

    p.logger.Info("Packet details", logFields...)
}

func (p *Proxy) worker() {
    for {
        select {
        case <-p.done:
            return
        case packet := <-p.wgPacketChan:
            p.handleClientPkt(packet)
        case packet := <-p.natPacketChan:
            p.forwardToClient(packet)
        }
    }
}

func (p *Proxy) forwardToClient(pkt *gopacket.Packet) {
    ipLayer := (*pkt).Layer(layers.LayerTypeIPv4)

    ip, _ := ipLayer.(*layers.IPv4) // might need to check for ok here
    logger.Info("Forwarding from Client", 
        zap.String("OriginalSRC", ip.SrcIP.String()), zap.String("DST", ip.DstIP.String()))
    if err := p.wgHandle.WritePacketData((*pkt).Data()); err != nil {
        logger.Warn("Error sending packet to client", zap.Error(err))
    } else {
        logger.Info("Packet forwarded to client")
    }
}

func (p *Proxy) Run() error {
    if err := p.connectToNAT(); err != nil {
        return err
    }
    
    // Start packet capture
    go p.captureWgPackets()
    
    // Start NAT response processing
    go p.readNATPkt()
    
    // Start worker
    go p.worker()
    
    sigChan := make(chan os.Signal, 1)
    defer close(sigChan)
    signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

    // Wait for shutdown signal
    <-sigChan

    // Initiate graceful shutdown
    close(p.done)  // Signal all goroutines to stop
    
    // Close channels
    close(p.wgPacketChan)
    close(p.natPacketChan)

    // Close connections
    if p.natConn != nil {
        p.natConn.Close()
    }
    if p.wgHandle != nil {
        p.wgHandle.Close()
    }

    p.logger.Info("Proxy server shut down gracefully")
    return nil
}

func main() {
    if err := initLogger(); err != nil {
		    logger.Fatal("Failed to initialize logger: %v", zap.Error(err))
        os.Exit(1)
	  }
    
    var err error
    logger.Info("Starting Proxy Server")
    proxy, err := NewProxy(logger)
    if err != nil {
        logger.Fatal("Proxy initiation failed", zap.Error(err))
    }

    if err := proxy.Run(); err != nil {
        logger.Fatal("Failed to run proxy server",
            zap.Error(err))
    }

//    wgHandle, err = pcap.OpenLive(ifn, snapLen, promiscuous, timeout)
//    if err != nil {
//        logger.Fatal("Error at OpenLive: %v",zap.Error(err))
//    }
//    defer wgHandle.Close()

//    err = connectToNAT()
//    if err != nil {
//        logger.Fatal("Connection to NAT server failed", zap.Error(err))
//    }
//    defer natConn.Close()

//    wgPacketChan := make(chan *gopacket.Packet, 1000)
//    dfPacketChan := make(chan *gopacket.Packet, 1000)
//    go captureWgPackets(wgPacketChan)
//    go readNATPkt(natConn, dfPacketChan)
//    go worker(wgPacketChan, dfPacketChan)
//
//    sigChan := make(chan os.Signal, 1)
//    defer close(sigChan)
//    signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)
//
//    <-sigChan
//    close(wgPacketChan)
//    close(dfPacketChan)
//
//
//    logger.Info("Proxy server shut down gracefully")
}

//func connectToNAT() error {
//    natPoint := fmt.Sprintf("%s:%s", "nat", natPort)
//    maxRetries := 5
//    retryDelay := time.Second * 5
//
//    for i := 0; i < maxRetries; i++ {
//        var err error
//        natConn, err = net.Dial("tcp", natPoint)
//        if err == nil {
//            return nil
//        }
//        logger.Warn("Failed to connect to NAT server", 
//            zap.Int("attempt", i+1), 
//            zap.Int("max", maxRetries), 
//            zap.Error(err))
//
//        if i < maxRetries-1 {
//            time.Sleep(retryDelay)
//        }
//    }
//    return fmt.Errorf("failed to connect to NAT server after %d attempts", maxRetries)
//}
//
//// Modified packet structure: [4 bytes total length][packet data]
//func forwardToNAT(pkt *gopacket.Packet, ip *layers.IPv4) error {
//    logger.Info("Forwarding to NAT", 
//        zap.String("ClientIP", ip.SrcIP.String()), zap.String("DST", ip.DstIP.String()))
//
//    pdata := (*pkt).Data()
//    plen := uint32(len(pdata))
//
//    buff := make([]byte, 4+len(pdata))
//    binary.BigEndian.PutUint32(buff[:4], plen)
//    copy(buff[4:], pdata)
//
//    _, err := natConn.Write(buff)
//    if err != nil {
//        return fmt.Errorf("Error sending packet to NAT: %v", err)
//    }
//
//    logger.Info("Packet forwarded successfully", zap.Uint32("bytes", plen))
//
//    return nil
//}
//
//func readNATPkt(natConn net.Conn, dfPacketChan chan<- *gopacket.Packet) {
//    for {
//        var encapsulatedLen uint32
//        err := binary.Read(natConn, binary.BigEndian, &encapsulatedLen)
//        if err != nil {
//            if err == io.EOF {
//                logger.Info("Connection closed by NAT server")
//                return
//            }
//            logger.Warn("Error reading encapsulated packet length", zap.Error(err))
//            continue
//        }
//
//        logger.Debug("Reading packet", zap.Uint32("encapsulated_length", encapsulatedLen))
//
//        data := make([]byte, encapsulatedLen)
//        _, err = io.ReadFull(natConn, data)
//        if err != nil {
//            logger.Warn("Error reading encapsulated packet data", zap.Error(err))
//            continue
//        }
//
//        pkt := gopacket.NewPacket(data, layers.LayerTypeIPv4, gopacket.Default)
//        
//        logFields := []zap.Field{
//            zap.Int("total_layers", len(pkt.Layers())),
//        }
//
//        if ipLayer := pkt.Layer(layers.LayerTypeIPv4); ipLayer != nil {
//            ip, _ := ipLayer.(*layers.IPv4)
//            logFields = append(logFields,
//                zap.String("src_ip", ip.SrcIP.String()),
//                zap.String("dst_ip", ip.DstIP.String()),
//                zap.Int("ttl", int(ip.TTL)),
//                zap.Int("length", int(ip.Length)),
//                zap.String("protocol", ip.Protocol.String()),
//            )
//        }
//
//        if tcpLayer := pkt.Layer(layers.LayerTypeTCP); tcpLayer != nil {
//            tcp, _ := tcpLayer.(*layers.TCP)
//            logFields = append(logFields,
//                zap.Uint16("src_port", uint16(tcp.SrcPort)),
//                zap.Uint16("dst_port", uint16(tcp.DstPort)),
//                zap.Uint32("seq_num", tcp.Seq),
//                zap.Uint32("ack_num", tcp.Ack),
//                zap.Bool("syn_flag", tcp.SYN),
//                zap.Bool("ack_flag", tcp.ACK),
//                zap.Bool("fin_flag", tcp.FIN),
//                zap.Bool("rst_flag", tcp.RST),
//                zap.Bool("psh_flag", tcp.PSH),
//                zap.Int("window_size", int(tcp.Window)),
//            )
//        }
//
//        if udpLayer := pkt.Layer(layers.LayerTypeUDP); udpLayer != nil {
//            udp, _ := udpLayer.(*layers.UDP)
//            logFields = append(logFields,
//                zap.Uint16("src_port", uint16(udp.SrcPort)),
//                zap.Uint16("dst_port", uint16(udp.DstPort)),
//                zap.Int("length", int(udp.Length)),
//            )
//        }
//
//        if icmpLayer := pkt.Layer(layers.LayerTypeICMPv4); icmpLayer != nil {
//            icmp, _ := icmpLayer.(*layers.ICMPv4)
//            logFields = append(logFields,
//                zap.Uint8("icmp_type", icmp.TypeCode.Type()),
//                zap.Uint8("icmp_code", icmp.TypeCode.Code()),
//            )
//        }
//
//        if dnsLayer := pkt.Layer(layers.LayerTypeDNS); dnsLayer != nil {
//            dns, _ := dnsLayer.(*layers.DNS)
//            questions := make([]string, 0, len(dns.Questions))
//            for _, q := range dns.Questions {
//                questions = append(questions, string(q.Name))
//            }
//            logFields = append(logFields,
//                zap.Uint16("dns_id", dns.ID),
//                zap.Bool("is_response", dns.QR),
//                zap.Strings("questions", questions),
//                zap.Int("answer_count", len(dns.Answers)),
//            )
//        }
//
//        if appLayer := pkt.ApplicationLayer(); appLayer != nil {
//            logFields = append(logFields,
//                zap.Int("payload_length", len(appLayer.Payload())),
//            )
//        }
//
//        if err := pkt.ErrorLayer(); err != nil {
//            logFields = append(logFields,
//                zap.Error(err.Error()),
//            )
//        }
//
//        logger.Info("Received and extracted packet from NAT", logFields...)
//
//        dfPacketChan <- &pkt
//    }
//}


//func forwardToClient(pkt *gopacket.Packet) {
//    ipLayer := (*pkt).Layer(layers.LayerTypeIPv4)
//
//    ip, _ := ipLayer.(*layers.IPv4) // might need to check for ok here
//    logger.Info("Forwarding from Client", 
//        zap.String("OriginalSRC", ip.SrcIP.String()), zap.String("DST", ip.DstIP.String()))
//    if err := wgHandle.WritePacketData((*pkt).Data()); err != nil {
//        logger.Warn("Error sending packet to client", zap.Error(err))
//    } else {
//        logger.Info("Packet forwarded to client")
//    }
//}
//
//func captureWgPackets(wgPacketChan chan<- *gopacket.Packet) {
//    pktSrc := gopacket.NewPacketSource(wgHandle, wgHandle.LinkType())
//    for pkt := range pktSrc.Packets() {
//        logger.Debug("Processing WG packet",
//          zap.Int("packet_size", len(pkt.Data())),
//          zap.String("layer_dump", pkt.Dump()))
//        wgPacketChan <- &pkt
//    }
//}

//we migh not need this
// Pkt Sent from Client(Proxy -> NAT)
//func handleWgPkt(pkt *gopacket.Packet) {
//    logger.Debug("In handleWgPkt")
//    ipLayer := (*pkt).Layer(layers.LayerTypeIPv4)
//
//    if ipLayer == nil {
//        logger.Warn("Not an IPv4 packet. Skipping.")
//        return
//    }
//
//    ip, _ := ipLayer.(*layers.IPv4) // might need to check for ok here
//    if ip != nil && ip.SrcIP.String() != natIPv4 {
//        if err := forwardToNAT(pkt, ip); err != nil {
//            logger.Fatal("Could not send to NAT\n", zap.Error(err))
//        }
//	  } 
//}
//
//func worker(wgPacketChan <-chan *gopacket.Packet, dfPacketChan <-chan *gopacket.Packet) {
//    for {
//        select {
//        case pkt := <- wgPacketChan:
//            handleWgPkt(pkt)
//        case pkt := <- dfPacketChan:
//            forwardToClient(pkt)
//        }
//    }
//}

func getPublicIP() (string, error) {
    client := http.Client{Timeout: timeout}
    res, err := client.Get("https://httpbin.org/ip")
    if err != nil {
        logger.Fatal("Error at getting public IP", zap.Error(err))
        return "", err
    }
    defer res.Body.Close()

    if res.StatusCode != http.StatusOK {
        return "", fmt.Errorf("Unexpected status code: %d", res.StatusCode)
    }

    body, err := io.ReadAll(res.Body)
    if err != nil {
        return "", fmt.Errorf("error reading response body: %w", err)
    }
    var ipRes struct {
        Origin string `json:"origin"`
    }
    
    if err := json.Unmarshal(body, &ipRes); err != nil {
        return "", fmt.Errorf("error parsing JSON response: %w", err)
    }

    return ipRes.Origin, nil
}

func getDefalutInterface() (*net.Interface, error) {
    interfaces, err := net.Interfaces()
    if err != nil {
        return nil, err
    }
    for _, iface := range interfaces {
        if iface.Flags&net.FlagUp != 0 && iface.Flags&net.FlagLoopback == 0 {
            addrs, err := iface.Addrs()
            if err != nil {
                continue
            }

            for _, addr := range addrs {
                if ipnet, ok := addr.(*net.IPNet); ok && !ipnet.IP.IsLoopback() {
                    if ipnet.IP.To4() != nil {
                        return &iface, nil
                    }
                }
            }
        }
    }
    return nil, fmt.Errorf("no suitable interface found")
}
