#!/bin/bash

sudo apt update
sudo apt install git wireguard-tools nano iputils-ping iproute2 make python3 python3-pip -y

git clone https://github.com/spotproxy-project/spotproxy.git

cd spotproxy/wireguard

# make ready name=server # Fix this
sudo cp key_store/server2/wg0.conf /etc/wireguard/

sudo pip install -r requirements.txt

wg-quick up wg0

cd src

sudo python3 server.py <NAT_IP>:8000
