#!/bin/bash

#sudo apt update
#sudo apt install git wireguard-tools nano iputils-ping iproute2 make python3 python3-pip -y

# git clone https://github.com/johnsinak/hush-proxy.git

#cd hush-proxy

# make ready name=server # Fix this
#sudo cp key_store/server/wg0.conf /etc/wireguard/

#sudo pip install -r requirements.txt

wg-quick down wg0
wg-quick up wg0

/app/main
