#!/bin/bash

#apt update
#apt install git wireguard-tools nano iputils-ping iproute2 make python3 python3-pip -y

# git clone https://github.com/johnsinak/hush-proxy.git

# cd hush-proxy

# make ready name=server # Fix this
cp key_store/peer1/wg0.conf /etc/wireguard/

pip install -r requirements.txt

wg-quick up wg0

ip route add default dev wg0

cd src

python3 client.py
