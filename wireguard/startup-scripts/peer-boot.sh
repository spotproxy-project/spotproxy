#!/bin/bash

#apt update
#apt install git wireguard-tools nano iputils-ping iproute2 make python3 python3-pip -y

# git clone https://github.com/johnsinak/hush-proxy.git

# cd hush-proxy

# make ready name=server # Fix this
cp key_store/peer1/wg0.conf /etc/wireguard/
chmod +x /etc/wireguard/wg0.conf 
pip install -r requirements.txt

wg-quick down wg0 || true
wg-quick up wg0

sleep 2

if ! ip link show wg0 > /dev/null 2>&1; then
    echo "WireGuard interface wg0 failed to initialize"
    exit 1
fi

ip route add default dev wg0

sleep 3

cd src

python3 client.py
