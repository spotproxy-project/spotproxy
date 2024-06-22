#!/bin/bash

sudo apt update
sudo apt install git wireguard-tools nano iputils-ping iproute2 make python3 python3-pip -y

# git clone https://github.com/johnsinak/hush-proxy.git

cd hush-proxy

# make ready name=server # Fix this
TEMPOID=$(curl http://3.91.73.130:8000/assignments/getid)
ID=$(echo "$TEMPOID" | tr -d "\"")
echo "this is the id: $ID"

sudo cp key_store/peer$ID/wg0.conf /etc/wireguard/

sudo pip install -r requirements.txt

wg-quick up wg0

cd src

sudo python3 client.py $ID
