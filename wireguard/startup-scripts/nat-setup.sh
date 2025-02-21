#!/bin/bash
set -e

# Flush existing rules (for debugging)
iptables -F
iptables -t nat -F

# Allow forwarding from the proxy to the internet
iptables -A FORWARD -i eth0 -o eth0 -j ACCEPT

# NAT packets sent from the proxy to the internet
iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE

# Log some packets for debugging
iptables -t nat -A POSTROUTING -o eth0 -j LOG --log-prefix "NAT_POST: " --log-level 4

ip route add 10.27.0.0/24 via 54.90.191.175

echo "✅ NAT Server is running. Use tcpdump for debugging."

# Start tcpdump (logs packets to stdout so we can see in `docker logs nat-container`)
tcpdump -i any -nn -l -vv > /var/log/tcpdump.log &
pgrep -f "tcpdump" || echo "Error: tcpdump did not start successfully!"
exec tail -f /var/log/tcpdump.log
