package main

import (
	"crypto/rand"
	"fmt"
	"net"
)

// randIPAddr generates a random IP address within the network represented by
// ipnet.
func randIPAddr(ipnet *net.IPNet) (net.IP, error) {
	if len(ipnet.IP) != len(ipnet.Mask) {
		return nil, fmt.Errorf("IP and mask have unequal lengths (%v and %v)", len(ipnet.IP), len(ipnet.Mask))
	}
	ip := make(net.IP, len(ipnet.IP))
	_, err := rand.Read(ip)
	if err != nil {
		return nil, err
	}
	for i := 0; i < len(ipnet.IP); i++ {
		ip[i] = (ipnet.IP[i] & ipnet.Mask[i]) | (ip[i] & ^ipnet.Mask[i])
	}
	return ip, nil
}

// parseIPCIDR parses a CIDR-notation IP address and prefix length; or if that
// fails, as a plain IP address (with the prefix length equal to the address
// length).
func parseIPCIDR(s string) (*net.IPNet, error) {
	_, ipnet, err := net.ParseCIDR(s)
	if err == nil {
		return ipnet, nil
	}
	// IP/mask failed; try just IP now, but remember err, to return it in
	// case that fails too.
	ip := net.ParseIP(s)
	if ip != nil {
		return &net.IPNet{IP: ip, Mask: net.CIDRMask(len(ip)*8, len(ip)*8)}, nil
	}
	return nil, err
}
