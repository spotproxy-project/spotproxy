package main

import (
	"bytes"
	"net"
	"testing"
)

func mustParseCIDR(s string) *net.IPNet {
	_, ipnet, err := net.ParseCIDR(s)
	if err != nil {
		panic(err)
	}
	return ipnet
}

func TestRandAddr(t *testing.T) {
outer:
	for _, ipnet := range []*net.IPNet{
		mustParseCIDR("127.0.0.1/0"),
		mustParseCIDR("127.0.0.1/24"),
		mustParseCIDR("127.0.0.55/32"),
		mustParseCIDR("2001:db8::1234/0"),
		mustParseCIDR("2001:db8::1234/32"),
		mustParseCIDR("2001:db8::1234/128"),
		// Non-canonical masks (that don't consist of 1s followed by 0s)
		// work too, why not.
		&net.IPNet{
			IP:   net.IP{1, 2, 3, 4},
			Mask: net.IPMask{0x00, 0x07, 0xff, 0xff},
		},
	} {
		for i := 0; i < 100; i++ {
			ip, err := randIPAddr(ipnet)
			if err != nil {
				t.Errorf("%v returned error %v", ipnet, err)
				continue outer
			}
			if !ipnet.Contains(ip) {
				t.Errorf("%v does not contain %v", ipnet, ip)
				continue outer
			}
		}
	}
}

func TestRandAddrUnequalLengths(t *testing.T) {
	for _, ipnet := range []*net.IPNet{
		&net.IPNet{
			IP:   net.IP{1, 2, 3, 4},
			Mask: net.CIDRMask(32, 128),
		},
		&net.IPNet{
			IP:   net.IP{1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15},
			Mask: net.CIDRMask(24, 32),
		},
		&net.IPNet{
			IP:   net.IP{1, 2, 3, 4},
			Mask: net.IPMask{},
		},
		&net.IPNet{
			IP:   net.IP{1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15},
			Mask: net.IPMask{},
		},
	} {
		_, err := randIPAddr(ipnet)
		if err == nil {
			t.Errorf("%v did not result in error, but should have", ipnet)
		}
	}
}

func BenchmarkRandAddr(b *testing.B) {
	for _, test := range []struct {
		label string
		ipnet net.IPNet
	}{
		{"IPv4/32", net.IPNet{IP: net.IP{127, 0, 0, 1}, Mask: net.CIDRMask(32, 32)}},
		{"IPv4/24", net.IPNet{IP: net.IP{127, 0, 0, 1}, Mask: net.CIDRMask(32, 32)}},
		{"IPv6/64", net.IPNet{
			IP:   net.IP{0x20, 0x01, 0x0d, 0xb8, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0x12, 0x34},
			Mask: net.CIDRMask(64, 128),
		}},
		{"IPv6/128", net.IPNet{
			IP:   net.IP{0x20, 0x01, 0x0d, 0xb8, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0x12, 0x34},
			Mask: net.CIDRMask(128, 128),
		}},
	} {
		b.Run(test.label, func(b *testing.B) {
			for i := 0; i < b.N; i++ {
				_, err := randIPAddr(&test.ipnet)
				if err != nil {
					b.Fatal(err)
				}
			}
		})
	}
}

func ipNetEqual(a, b *net.IPNet) bool {
	if !a.IP.Equal(b.IP) {
		return false
	}
	// Comparing masks for equality is a little tricky because they may be
	// different lengths. For masks in canonical form (those for which
	// Size() returns other than (0, 0)), we consider two masks equal if the
	// numbers of bits *not* covered by the prefix are equal; e.g.
	// (120, 128) is equal to (24, 32), because they both have 8 bits not in
	// the prefix. If either mask is not in canonical form, we require them
	// to be equal as byte arrays (which includes length).
	aOnes, aBits := a.Mask.Size()
	bOnes, bBits := b.Mask.Size()
	if aBits == 0 || bBits == 0 {
		return bytes.Equal(a.Mask, b.Mask)
	} else {
		return aBits-aOnes == bBits-bOnes
	}
}

func TestParseIPCIDR(t *testing.T) {
	// Well-formed inputs.
	for _, test := range []struct {
		input    string
		expected *net.IPNet
	}{
		{"127.0.0.123", mustParseCIDR("127.0.0.123/32")},
		{"127.0.0.123/0", mustParseCIDR("127.0.0.123/0")},
		{"127.0.0.123/24", mustParseCIDR("127.0.0.123/24")},
		{"127.0.0.123/32", mustParseCIDR("127.0.0.123/32")},
		{"2001:db8::1234", mustParseCIDR("2001:db8::1234/128")},
		{"2001:db8::1234/0", mustParseCIDR("2001:db8::1234/0")},
		{"2001:db8::1234/32", mustParseCIDR("2001:db8::1234/32")},
		{"2001:db8::1234/128", mustParseCIDR("2001:db8::1234/128")},
	} {
		ipnet, err := parseIPCIDR(test.input)
		if err != nil {
			t.Errorf("%q returned error %v", test.input, err)
			continue
		}
		if !ipNetEqual(ipnet, test.expected) {
			t.Errorf("%q → %v, expected %v", test.input, ipnet, test.expected)
		}
	}

	// Bad inputs.
	for _, input := range []string{
		"",
		"1.2.3",
		"1.2.3/16",
		"2001:db8:1234",
		"2001:db8:1234/64",
		"localhost",
	} {
		_, err := parseIPCIDR(input)
		if err == nil {
			t.Errorf("%q did not result in error, but should have", input)
		}
	}
}
