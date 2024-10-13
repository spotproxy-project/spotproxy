package main

import (
	"encoding/json"
	"fmt"
  "net"
	"io"
	"log"
	"net/http"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"

	"github.com/google/gopacket"
	"github.com/google/gopacket/layers"
	"github.com/google/gopacket/pcap"
)

const (
    ifn = "wg0"
    natIPv4 = "" // Should be filled with NAT IP
    snapLen = 1024
    promiscuous = false
	  timeout     = 30 * time.Second
)

var (
	clientAddresses  sync.Map
	currentIPv4       string
)

func main() {
    var err error
    currentIPv4, err = getPublicIP()
    if err != nil {
        log.Fatalf("Failed to get public IP: %v", err)
    }

    handle, err := pcap.OpenLive(ifn, snapLen, promiscuous, timeout)
    if err != nil {
        log.Fatalf("Error at OpenLive: %v",err)
    }
    defer handle.Close()

    packetChan := make(chan *gopacket.Packet, 1000)
    var wg sync.WaitGroup

    go capturePackets(handle, packetChan)
    wg.Add(1)
    go worker(handle, packetChan, &wg)

    sigChan := make(chan os.Signal, 1)
    defer close(sigChan)
    signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

    <-sigChan
    close(packetChan)
    wg.Wait()

    log.Println("Packet forwarder shut down gracefully")
}

func forwardToNATv4(handle *pcap.Handle, pkt *gopacket.Packet, ip *layers.IPv4) {
	  if ip.SrcIP.String() != natIPv4 {
        log.Printf("Forwarding to NAT (IPv4): Original SRC: %s, DST: %s", ip.SrcIP, ip.DstIP)
		    clientAddresses.Store(ip.SrcIP.String(), true)
        ip.SrcIP = net.ParseIP(currentIPv4)
        ip.DstIP = net.ParseIP(natIPv4)

        if err := updateChecksums(pkt); err != nil {
            log.Printf("Error updating checksums: %v", err)
		        return
        }

        if err := handle.WritePacketData((*pkt).Data()); err != nil {
            log.Printf("Error sending packet to client: %v", err)
        } else {
            log.Printf("Packet forwarded to NAT: %s -> %s", currentIPv4, natIPv4)
        }
	  }
}

func forwardToClientv4(handle *pcap.Handle, pkt *gopacket.Packet, ip *layers.IPv4) {
	log.Printf("Forwarding from NAT (IPv4): Original SRC: %s, DST: %s", ip.SrcIP, ip.DstIP)

	clientIP := "10.27.0.2"
	if clientIP == "" {
		log.Println("No IPv4 client IP available for forwarding")
		return
	}

	ip.DstIP = net.ParseIP(clientIP)

	if err := updateChecksums(pkt); err != nil {
		log.Printf("Error updating checksums: %v", err)
		return
	}

	if err := handle.WritePacketData((*pkt).Data()); err != nil {
		log.Printf("Error sending packet to client: %v", err)
	} else {
		log.Printf("Packet forwarded to client: %s -> %s", natIPv4, clientIP)
	}
}

func updateChecksums(pkt *gopacket.Packet) error {
	ipLayer := (*pkt).Layer(layers.LayerTypeIPv4)
	ip, _ := ipLayer.(*layers.IPv4)
	ip.Checksum = 0

	if tcpLayer := (*pkt).Layer(layers.LayerTypeTCP); tcpLayer != nil {
		tcp, _ := tcpLayer.(*layers.TCP)
		tcp.SetNetworkLayerForChecksum(ip)
	} else if udpLayer := (*pkt).Layer(layers.LayerTypeUDP); udpLayer != nil {
		udp, _ := udpLayer.(*layers.UDP)
		udp.SetNetworkLayerForChecksum(ip)
	}

	buf := gopacket.NewSerializeBuffer()
	opts := gopacket.SerializeOptions{ComputeChecksums: true, FixLengths: true}
	err := gopacket.SerializePacket(buf, opts, *pkt)
	if err != nil {
		return fmt.Errorf("failed to serialize packet: %v", err)
	}

	return nil
}

func capturePackets(handle *pcap.Handle, packetChan chan<- *gopacket.Packet) {
    pktSrc := gopacket.NewPacketSource(handle, handle.LinkType())
    for pkt := range pktSrc.Packets() {
        log.Printf("Captured packet: %s", packetsum(&pkt))
        packetChan <- &pkt
    }
}

func handlePackets(handle *pcap.Handle, pkt *gopacket.Packet) {
    log.Println("In HandlePacket")
    ipLayer := (*pkt).Layer(layers.LayerTypeIPv4)
	  ipv6Layer := (*pkt).Layer(layers.LayerTypeIPv6)

    if ipLayer != nil || ipv6Layer != nil{
		    forwardToNATv4(handle, pkt, ipLayer.(*layers.IPv4))
	  } else {
		    log.Println("Not an IP packet. Skipping.")
	  }
}

func worker(handle *pcap.Handle, packetChan <-chan *gopacket.Packet, wg *sync.WaitGroup) {
    defer wg.Done()
    for pkt := range packetChan {
        log.Printf("Got Packet: %v", pkt)
        handlePackets(handle, pkt)
    }    
}

func packetsum(pkt *gopacket.Packet) string {
    sum := ""
    if ipLayer := (*pkt).Layer(layers.LayerTypeIPv4); ipLayer != nil {
        ip, _ := ipLayer.(*layers.IPv4)
		    sum += fmt.Sprintf("IP %s -> %s | ", ip.SrcIP, ip.DstIP)
    } else if ipLayer := (*pkt).Layer(layers.LayerTypeIPv6); ipLayer != nil {
		    ip, _ := ipLayer.(*layers.IPv6)
		    sum += fmt.Sprintf("IPv6 %s -> %s | ", ip.SrcIP, ip.DstIP)
	  }


    if tcpLayer := (*pkt).Layer(layers.LayerTypeTCP); tcpLayer != nil {
		    tcp, _ := tcpLayer.(*layers.TCP)
		    sum += fmt.Sprintf("TCP %d -> %d | ", tcp.SrcPort, tcp.DstPort)
	  }

	  if udpLayer := (*pkt).Layer(layers.LayerTypeUDP); udpLayer != nil {
        udp, _ := udpLayer.(*layers.UDP)
        sum += fmt.Sprintf("UDP %d -> %d | ", udp.SrcPort, udp.DstPort)
    }

    if icmpLayer := (*pkt).Layer(layers.LayerTypeICMPv4); icmpLayer != nil {
        icmp, _ := icmpLayer.(*layers.ICMPv4)
        sum += fmt.Sprintf("ICMP %v | ", icmp.Contents)
    }

    if appLayer := (*pkt).ApplicationLayer(); appLayer != nil {
        sum += fmt.Sprintf("Payload %d bytes | ", len(appLayer.Payload()))
    }

    return sum
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
