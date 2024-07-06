package main

import (
	"bytes"
	"container/heap"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log"
	"net"
	"net/http"
	"os"
	"slices"

	"gitlab.torproject.org/tpo/anti-censorship/pluggable-transports/snowflake/v2/common/bridgefingerprint"

	"github.com/prometheus/client_golang/prometheus"
	"gitlab.torproject.org/tpo/anti-censorship/pluggable-transports/snowflake/v2/common/messages"
)

const (
	ClientTimeout = 10
	ProxyTimeout  = 10

	NATUnknown      = "unknown"
	NATRestricted   = "restricted"
	NATUnrestricted = "unrestricted"
)

type IPC struct {
	ctx *BrokerContext
}

var Proxy2Client = make(map[string][]*Client)
var Cid2Client = make(map[string]*Client)
var ProxyIP2Snowflake = make(map[string]*Snowflake)

var file, _ = os.Create("broker.log")

func (i *IPC) Debug(_ interface{}, response *string) error {
	var unknowns int
	var natRestricted, natUnrestricted, natUnknown int
	proxyTypes := make(map[string]int)

	i.ctx.snowflakeLock.Lock()
	s := fmt.Sprintf("current snowflakes available: %d\n", len(i.ctx.idToSnowflake))
	for _, snowflake := range i.ctx.idToSnowflake {
		if messages.KnownProxyTypes[snowflake.proxyType] {
			proxyTypes[snowflake.proxyType]++
		} else {
			unknowns++
		}

		switch snowflake.natType {
		case NATRestricted:
			natRestricted++
		case NATUnrestricted:
			natUnrestricted++
		default:
			natUnknown++
		}

	}
	i.ctx.snowflakeLock.Unlock()

	for pType, num := range proxyTypes {
		s += fmt.Sprintf("\t%s proxies: %d\n", pType, num)
	}
	s += fmt.Sprintf("\tunknown proxies: %d", unknowns)

	s += fmt.Sprintf("\nNAT Types available:")
	s += fmt.Sprintf("\n\trestricted: %d", natRestricted)
	s += fmt.Sprintf("\n\tunrestricted: %d", natUnrestricted)
	s += fmt.Sprintf("\n\tunknown: %d", natUnknown)

	*response = s
	return nil
}

func (i *IPC) ProxyPolls(arg messages.Arg, response *[]byte) error {
	sid, proxyType, natType, clients, _, relayPatternSupported, err := messages.DecodeProxyPollRequestWithRelayPrefix(arg.Body)
	addr := arg.RemoteAddr
	log.Printf("proxy poll request from %s", addr)
	if err != nil {
		return messages.ErrBadRequest
	}

	if !relayPatternSupported {
		i.ctx.metrics.lock.Lock()
		i.ctx.metrics.proxyPollWithoutRelayURLExtension++
		i.ctx.metrics.promMetrics.ProxyPollWithoutRelayURLExtensionTotal.With(prometheus.Labels{"nat": natType, "type": proxyType}).Inc()
		i.ctx.metrics.lock.Unlock()
	} else {
		i.ctx.metrics.lock.Lock()
		i.ctx.metrics.proxyPollWithRelayURLExtension++
		i.ctx.metrics.promMetrics.ProxyPollWithRelayURLExtensionTotal.With(prometheus.Labels{"nat": natType, "type": proxyType}).Inc()
		i.ctx.metrics.lock.Unlock()
	}

	// Log geoip stats
	remoteIP, _, err := net.SplitHostPort(arg.RemoteAddr)
	if err != nil {
		log.Println("Warning: cannot process proxy IP: ", err.Error())
	} else {
		i.ctx.metrics.lock.Lock()
		i.ctx.metrics.UpdateCountryStats(remoteIP, proxyType, natType)
		i.ctx.metrics.RecordIPAddress(remoteIP)
		i.ctx.metrics.lock.Unlock()
	}

	i.ctx.snowflakeLock.Lock()
	Snowflake := &Snowflake{
		id:            sid,
		proxyType:     proxyType,
		ip:            addr,
		natType:       natType,
		offerChannel:  make(chan *ClientOffer),
		answerChannel: make(chan string),
		clients:       clients,
		index:         -1,
	}
	ProxyIP2Snowflake[addr] = Snowflake
	i.ctx.idToSnowflake[sid] = Snowflake
	if natType == NATUnrestricted {
		log.Printf("Proxy: Added unrestricted snowflake %s", sid)
		heap.Push(i.ctx.snowflakes, Snowflake)
	} else {
		log.Printf("Proxy: Added restricted snowflake %s", sid)
		heap.Push(i.ctx.restrictedSnowflakes, Snowflake)
	}
	i.ctx.snowflakeLock.Unlock()

	return nil

}

func sendClientResponse(resp *messages.ClientPollResponse, response *[]byte) error {
	data, err := resp.EncodePollResponse()
	if err != nil {
		log.Printf("error encoding answer")
		return messages.ErrInternal
	} else {
		*response = []byte(data)
		return nil
	}
}

func (i *IPC) ClientOffers(arg messages.Arg, response *[]byte) error {
	//startTime := time.Now()

	log.Printf("IPC decoding client poll request")
	req, err := messages.DecodeClientPollRequest(arg.Body)
	if err != nil {
		return sendClientResponse(&messages.ClientPollResponse{Error: err.Error()}, response)
	}

	offer := &ClientOffer{
		NatType: req.NAT,
		Sdp:     []byte(req.Offer),
		Cid:     req.Id,
	}

	fingerprint, err := hex.DecodeString(req.Fingerprint)
	if err != nil {
		return sendClientResponse(&messages.ClientPollResponse{Error: err.Error()}, response)
	}

	BridgeFingerprint, err := bridgefingerprint.FingerprintFromBytes(fingerprint)
	if err != nil {
		return sendClientResponse(&messages.ClientPollResponse{Error: err.Error()}, response)
	}

	if _, err := i.ctx.GetBridgeInfo(BridgeFingerprint); err != nil {
		return err
	}

	offer.Fingerprint = BridgeFingerprint.ToBytes()

	snowflake := i.matchSnowflake(offer.NatType)
	if snowflake != nil {
		url := snowflake.ip
		ip, _, _ := net.SplitHostPort(url)

		log.Printf("Client: Matched with %s", ip)
		offerJSON, err := json.Marshal(offer)
		if err != nil {
			return sendClientResponse(&messages.ClientPollResponse{Error: err.Error()}, response)
		}
		newPort := "51821"
		proxyPath := fmt.Sprintf("http://%s:%s/add", ip, newPort)
		log.Printf("Sending offer to %s", proxyPath)
		resp, err := http.Post(proxyPath, "application/json", bytes.NewBuffer(offerJSON))
		if err != nil {
			return sendClientResponse(&messages.ClientPollResponse{Error: err.Error()}, response)
		}
		if resp.StatusCode != http.StatusOK {
			return sendClientResponse(&messages.ClientPollResponse{Error: messages.StrNoProxies}, response)
		}
		log.Printf("response status code: %d", resp.StatusCode)
		answer := messages.ClientPollResponse{}
		err = json.NewDecoder(resp.Body).Decode(&answer)
		if err != nil {
			return sendClientResponse(&messages.ClientPollResponse{Error: err.Error()}, response)
		}

		//newTicker := time.NewTicker(time.Second * 120000)
		client := &Client{proxy: snowflake, ticker: nil, id: req.Id, natType: offer.NatType}
		Proxy2Client[snowflake.ip] = append(Proxy2Client[snowflake.ip], client)
		Cid2Client[req.Id] = client
		/*
			backupIP := i.matchSnowflake(offer.NatType).ip
			transferReq1 := messages.TransferRequest{Cid: req.Id, NewIp: backupIP, TransferNow: false}
			transferReqJSON1, _ := json.Marshal(transferReq1)
			transferPath1 := fmt.Sprintf("http://%s:%s/transfer", ip, newPort)
			_, _ = http.Post(transferPath1, "application/json", bytes.NewBuffer(transferReqJSON1))
		*/
		/*go func() {
			//no default switching for now

			intervals := [7]int{120, 30, 30, 30, 30, 30, 30}

				triggerInterval := time.Until(TriggerTime)
				if triggerInterval < 0 {
					triggerInterval = time.Second * 10
				}

			newTicker := time.NewTicker(time.Second * time.Duration(120))
			client := &Client{proxy: snowflake, ticker: newTicker, id: req.Id}
			count := 0
			quit := make(chan bool)
			for {
				select {
				case <-newTicker.C:
					write_content := fmt.Sprintf("%s client switching proxies at %s\n", req.Id, time.Now().String())
					file.WriteString(write_content)
					log.Printf(client.proxy.ip)
					log.Printf("client switching proxies")
					oldProxy := client.proxy
					client.proxy = i.matchSnowflake(offer.NatType)
					if client.proxy == nil {
						client.proxy = oldProxy
						continue
					}
					transferReq := messages.TransferRequest{Cid: client.id, NewIp: client.proxy.ip, TransferNow: true}
					//transferReq := messages.TransferRequest{Cid: client.id, NewIp: "18.118.29.29:51821", TransferNow: true}
					transferReqJSON, err := json.Marshal(transferReq)
					if err != nil {
						log.Printf("error marshalling transfer request")
						continue
					}
					oldIp, _, _ := net.SplitHostPort(oldProxy.ip)
					//testing
					//oldIp = "13.59.55.180"
					transferPath := fmt.Sprintf("http://%s:%s/transfer", oldIp, newPort)
					log.Printf("sending transfer request to %s", transferPath)
					resp, err := http.Post(transferPath, "application/json", bytes.NewBuffer(transferReqJSON))
					if err != nil {
						log.Printf("error sending transfer request")
						continue
					}
					if resp.StatusCode != http.StatusOK {
						log.Printf("error sending transfer request")
						log.Printf("response status code: %d", resp.StatusCode)
						continue
					}
					//temporary, for testing
					count++
					newTicker.Stop()
					if count < 1 {
						newTicker = time.NewTicker(time.Second * time.Duration(intervals[count]))
					} else {
						log.Printf("client has been transferred 7 times")
						quit <- true
					}
				case <-quit:
					log.Printf("ticker stopped")
					return
				default:
					continue
				}
			}
		}()
		*/
		sendClientResponse(&answer, response)
	} else {
		i.ctx.metrics.lock.Lock()
		i.ctx.metrics.clientDeniedCount++
		i.ctx.metrics.promMetrics.ClientPollTotal.With(prometheus.Labels{"nat": offer.NatType, "status": "denied"}).Inc()
		if offer.NatType == NATUnrestricted {
			i.ctx.metrics.clientUnrestrictedDeniedCount++
		} else {
			i.ctx.metrics.clientRestrictedDeniedCount++
		}
		i.ctx.metrics.lock.Unlock()
		resp := &messages.ClientPollResponse{Error: messages.StrNoProxies}
		return sendClientResponse(resp, response)
	}

	i.ctx.snowflakeLock.Lock()
	i.ctx.metrics.promMetrics.AvailableProxies.With(prometheus.Labels{"nat": snowflake.natType, "type": snowflake.proxyType}).Dec()
	delete(i.ctx.idToSnowflake, snowflake.id)
	i.ctx.snowflakeLock.Unlock()

	return err
}

func (i *IPC) ProxyNotice(cid string, action string, proxyIP string) {
	client := Cid2Client[cid]
	if action == "add" {
		Proxy2Client[proxyIP] = append(Proxy2Client[proxyIP], client)
	} else if action == "delete" {
		idx := slices.Index(Proxy2Client[proxyIP], client)
		if idx != -1 {
			Proxy2Client[proxyIP] = slices.Delete(Proxy2Client[proxyIP], idx, idx+1)
		}
	}
}

func (i *IPC) Rescale(oldIPs []string, newIPs []string) bool {
	i.ctx.snowflakeLock.Lock()
	defer i.ctx.snowflakeLock.Unlock()

	for ip := range Proxy2Client {
		proxy := ProxyIP2Snowflake[ip]
		i.ctx.snowflakes.Remove(proxy)
		delete(ProxyIP2Snowflake, ip)
		for idx := 0; idx < len(Proxy2Client[ip]); idx++ {
			client := Proxy2Client[ip][idx]
			newProxy := i.matchSnowflake(client.natType)
			if newProxy == nil {
				return false
			}

			transferReq := messages.TransferRequest{Cid: client.id, NewIp: newProxy.ip, TransferNow: true}
			transferReqJSON, _ := json.Marshal(transferReq)
			transferPath := fmt.Sprintf("http://%s:%s/transfer", ip, "51821")
			//error handling in the future
			_, _ = http.Post(transferPath, "application/json", bytes.NewBuffer(transferReqJSON))
		}
		delete(Proxy2Client, ip)
	}
	return true
}

// Need to cleanup: using spot proxy all snowflake should be unrestricted
func (i *IPC) matchSnowflake(natType string) *Snowflake {
	// Only hand out known restricted snowflakes to unrestricted clients
	log.Printf("Matching snowflake with nat type %s", natType)
	var snowflakeHeap *SnowflakeHeap
	if natType == NATUnrestricted {
		snowflakeHeap = i.ctx.restrictedSnowflakes
	} else {
		snowflakeHeap = i.ctx.snowflakes
	}

	i.ctx.snowflakeLock.Lock()
	defer i.ctx.snowflakeLock.Unlock()

	if snowflakeHeap.Len() > 0 {
		result := heap.Pop(snowflakeHeap).(*Snowflake)
		heap.Push(snowflakeHeap, result)
		result.clients++
		return result
	} else {
		if natType == NATUnrestricted {
			snowflakeHeap = i.ctx.snowflakes
			if snowflakeHeap.Len() > 0 {
				result := heap.Pop(snowflakeHeap).(*Snowflake)
				heap.Push(snowflakeHeap, result)
				result.clients++
				return result
			} else {
				return nil
			}
		}
		return nil
	}
}

func (i *IPC) ProxyAnswers(arg messages.Arg, response *[]byte) error {
	answer, id, err := messages.DecodeAnswerRequest(arg.Body)
	if err != nil || answer == "" {
		return messages.ErrBadRequest
	}

	var success = true
	i.ctx.snowflakeLock.Lock()
	snowflake, ok := i.ctx.idToSnowflake[id]
	i.ctx.snowflakeLock.Unlock()
	if !ok || snowflake == nil {
		// The snowflake took too long to respond with an answer, so its client
		// disappeared / the snowflake is no longer recognized by the Broker.
		success = false
		log.Printf("Warning: matching with snowflake client failed")
	}

	b, err := messages.EncodeAnswerResponse(success)
	if err != nil {
		log.Printf("Error encoding answer: %s", err.Error())
		return messages.ErrInternal
	}
	*response = b

	if success {
		snowflake.answerChannel <- answer
	}

	return nil
}
