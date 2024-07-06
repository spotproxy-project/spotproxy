//go:build !linux
// +build !linux

package main

import "syscall"

// dialerControl does nothing.
//
// On Linux, this function would set the IP_BIND_ADDRESS_NO_PORT socket option
// in preparation for a future bind-before-connect.
func dialerControl(network, address string, c syscall.RawConn) error {
	return nil
}
