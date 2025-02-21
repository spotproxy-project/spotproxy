#!/bin/bash
set -e

# Flush existing rules (for debugging)
iptables -F
iptables -t nat -F

echo "Removing existing default route..."
ip route del default || true  # Ignore errors if no default route exists

echo "Adding new default route via NAT server..."
ip route add default via 54.90.59.253 dev eth0

echo "Setting up IP forwarding rules..."
# Forward packets from WireGuard (wg0) to NAT server
iptables -A FORWARD -i wg0 -o eth0 -j ACCEPT

# Log forwarded packets (optional)
iptables -A FORWARD -j LOG --log-prefix "PROXY_FWD: " --log-level 4

wg-quick up wg0
echo "✅ Proxy Server is running."

# Start tcpdump inside Proxy container
tcpdump -i any -nn -l -vv > /var/log/tcpdump.log &
exec tail -f /var/log/tcpdump.log
