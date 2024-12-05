package main

import (
	"encoding/json"
  "encoding/binary"
	"fmt"
  "net"
	"io"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/google/gopacket"
	"github.com/google/gopacket/layers"
	"github.com/google/gopacket/pcap"
)

const (
    ifn = "wg0"
    natIPv4 = "54.164.191.175" // Should set to NAT IP
    natPort = "8000"
    snapLen = 1024
    promiscuous = false
	  timeout     = 10 * time.Second
)

var (
    currentIPv4       string
    defaultInterface *net.Interface
    natConn net.Conn
    dfHndl *pcap.Handle
    wgHandle *pcap.Handle
)

func init() {
    var err error
    defaultInterface, err = getDefalutInterface()
    if err != nil {
        log.Fatalf("Failed to get default interface: %v", err)
    }
    currentIPv4, err = getPublicIP()
    if err != nil {
        log.Fatalf("Failed to get public IP: %v", err)
    }
}

func main() {
    var err error
    log.Println("Starting Proxy Server")
    wgHandle, err = pcap.OpenLive(ifn, snapLen, promiscuous, timeout)
    if err != nil {
        log.Fatalf("Error at OpenLive: %v",err)
    }
    defer wgHandle.Close()

    err = connectToNAT()
    if err != nil {
        log.Fatalf("Connection to NAT server failed: %v", err)
    }
    defer natConn.Close()

    dfHndl, err = pcap.OpenLive(defaultInterface.Name, snapLen, promiscuous, pcap.BlockForever)
    if err != nil {
		    log.Fatalf("Error opening default interface %s: %v", defaultInterface.Name, err)
	  }
	  defer dfHndl.Close()

    wgPacketChan := make(chan *gopacket.Packet, 1000)
    dfPacketChan := make(chan *gopacket.Packet, 1000)
    go captureWgPackets(wgPacketChan)
    go readNATPkt(natConn, dfPacketChan)
    go worker(wgPacketChan, dfPacketChan)

    sigChan := make(chan os.Signal, 1)
    defer close(sigChan)
    signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

    <-sigChan
    close(wgPacketChan)
    close(dfPacketChan)


    log.Println("Proxy server shut down gracefully")
}

func connectToNAT() error {
    natPoint := fmt.Sprintf("%s:%s", natIPv4, natPort)
    var err error
    natConn, err = net.Dial("tcp", natPoint)
    if err != nil {
        return fmt.Errorf("failed to connect to NAT server: %v", err)
    }
    return nil
}

// Modified packet structure: [4 bytes total length][packet data]
func forwardToNAT(pkt *gopacket.Packet, ip *layers.IPv4) error {
    log.Printf("Forwarding to NAT (IPv4): Client IP: %s, DST: %s", 
               ip.SrcIP, ip.DstIP)

    pdata := (*pkt).Data()
    plen := uint32(len(pdata))

    buff := make([]byte, 4+len(pdata))
    binary.BigEndian.PutUint32(buff[:4], plen)
    copy(buff[4:], pdata)

    _, err := natConn.Write(buff)
    if err != nil {
        return fmt.Errorf("Error sending packet to NAT: %v", err)
    }

    log.Printf("Packet forwarded successfully: %d bytes", plen)

    return nil
}

func readNATPkt(natConn net.Conn, dfPacketChan chan<- *gopacket.Packet) {
    // TODO: adding reconnection
    for {
        var encapsulatedLen uint32
        err := binary.Read(natConn, binary.BigEndian, &encapsulatedLen)
        if err != nil {
            if err == io.EOF {
                log.Println("Connection closed by NAT server")
                return
            }
            log.Printf("Error reading encapsulated packet length: %v", err)
            continue
        }

        data := make([]byte, encapsulatedLen)
        _, err = io.ReadFull(natConn, data)
        if err != nil {
            log.Printf("Error reading encapsulated packet data: %v", err)
            continue
        }
        pkt := gopacket.NewPacket(data, layers.LayerTypeIPv4, gopacket.Default)
        dfPacketChan <- &pkt

        log.Println("Received and extracted original packet from NAT")
    }
}


func forwardToClient(pkt *gopacket.Packet) {
    ipLayer := (*pkt).Layer(layers.LayerTypeIPv4)

    ip, _ := ipLayer.(*layers.IPv4) // might need to check for ok here
    log.Printf("Forwarding from Client (IPv4): Original SRC: %s, DST: %s", ip.SrcIP, ip.DstIP)
    if err := wgHandle.WritePacketData((*pkt).Data()); err != nil {
        log.Printf("Error sending packet to client: %v", err)
    } else {
        log.Println("Packet forwarded to client")
    }
}

func captureWgPackets(wgPacketChan chan<- *gopacket.Packet) {
    pktSrc := gopacket.NewPacketSource(wgHandle, wgHandle.LinkType())
    for pkt := range pktSrc.Packets() {
        log.Printf("Got Packet: \n%s", pkt.Dump())
        wgPacketChan <- &pkt
    }
}

//we migh not need this
// Pkt Sent from Client(Proxy -> NAT)
func handleWgPkt(pkt *gopacket.Packet) {
    log.Println("In HandlePacket")
    ipLayer := (*pkt).Layer(layers.LayerTypeIPv4)

    if ipLayer == nil {
        log.Println("Not an IPv4 packet. Skipping.")
        return
    }

    ip, _ := ipLayer.(*layers.IPv4) // might need to check for ok here
    if ip != nil && ip.SrcIP.String() != natIPv4 {
        if err := forwardToNAT(pkt, ip); err != nil {
            log.Fatalf("could not send to NAT: %v", err)
        }
	  } 
}

func worker(wgPacketChan <-chan *gopacket.Packet, dfPacketChan <-chan *gopacket.Packet) {
    for {
        select {
        case pkt := <- wgPacketChan:
            handleWgPkt(pkt)
        case pkt := <- dfPacketChan:
            forwardToClient(pkt)
        }
    }
}

func getPublicIP() (string, error) {
    client := http.Client{Timeout: timeout}
    res, err := client.Get("https://httpbin.org/ip")
    if err != nil {
        log.Fatalf("Error at getting public IP: %e", err)
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
