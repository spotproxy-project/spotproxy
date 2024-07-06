//go:build linux
// +build linux

package main

import (
	"syscall"

	"golang.org/x/sys/unix"
)

// dialerControl prepares a syscall.RawConn for a future bind-before-connect by
// setting the IP_BIND_ADDRESS_NO_PORT socket option.
//
// On Linux, setting the IP_BIND_ADDRESS_NO_PORT socket option helps conserve
// ephemeral ports when binding to a specific IP addresses before connecting
// (bind before connect), by not assigning the port number when bind is called,
// but waiting until connect. But problems arise if there are multiple processes
// doing bind-before-connect, and some of them use IP_BIND_ADDRESS_NO_PORT and
// some of them do not. When there is a mix, the ones that do will have their
// ephemeral ports reserved by the ones that do not, leading to EADDRNOTAVAIL
// errors.
//
// tor does bind-before-connect when the OutboundBindAddress option is set in
// torrc. Since version 0.4.7.13 (January 2023), tor sets
// IP_BIND_ADDRESS_NO_PORT unconditionally on platforms that support it, and
// therefore we must do the same, to avoid EADDRNOTAVAIL errors.
//
// # References
//
// https://bugs.torproject.org/tpo/anti-censorship/pluggable-transports/snowflake/40201#note_2839472
// https://forum.torproject.net/t/tor-relays-inet-csk-bind-conflict/5757/10
// https://blog.cloudflare.com/how-to-stop-running-out-of-ephemeral-ports-and-start-to-love-long-lived-connections/
// https://blog.cloudflare.com/the-quantum-state-of-a-tcp-port/
// https://forum.torproject.net/t/stable-release-0-4-5-16-and-0-4-7-13/6216
func dialerControl(network, address string, c syscall.RawConn) error {
	var sockErr error
	err := c.Control(func(fd uintptr) {
		sockErr = syscall.SetsockoptInt(int(fd), unix.SOL_IP, unix.IP_BIND_ADDRESS_NO_PORT, 1)
	})
	if err == nil {
		err = sockErr
	}
	return err
}
