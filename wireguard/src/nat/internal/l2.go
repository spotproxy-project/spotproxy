package internal


import (
	"fmt"
	"os/exec"
	"strings"
)

// GetDefaultGateway finds the gateway IP
func getDefaultGateway() (string, error) {
	cmd := exec.Command("ip", "route", "show", "default")
	output, err := cmd.Output()
	if err != nil {
		return "", fmt.Errorf("failed to get default gateway: %v", err)
	}

	fields := strings.Fields(string(output))
	for i, field := range fields {
		if field == "via" && i+1 < len(fields) {
			return fields[i+1], nil
		}
	}
	return "", fmt.Errorf("default gateway not found")
}

func GetGatewayMAC() (string, error) {
	gatewayIP, err := getDefaultGateway()
	if err != nil {
		return "", err
	}
	cmd := exec.Command("ip", "neigh", "show", gatewayIP)
	output, err := cmd.Output()
	if err != nil {
		return "", fmt.Errorf("failed to run arp command: %v", err)
	}

	fields := strings.Fields(string(output))
	for i, field := range fields {
		if field == "lladdr" && i+1 < len(fields) {
			return fields[i+1], nil
		}
	}
	return "", fmt.Errorf("MAC address not found in ARP table")
}
