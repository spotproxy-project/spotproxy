#!/bin/bash

apt update
apt install git wireguard-tools nano iputils-ping iproute2 make python3 python3-pip -y

# git clone https://github.com/johnsinak/hush-proxy.git

# cd hush-proxy

# make ready name=server # Fix this
cp key_store/server/wg0.conf /etc/wireguard/

pip install -r requirements.txt

wg-quick up wg0

cd src

python3 server.py