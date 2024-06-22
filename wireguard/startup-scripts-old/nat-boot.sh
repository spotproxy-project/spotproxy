#!/bin/bash

sudo apt update
sudo apt install git nano iputils-ping iproute2 make python3 python3-pip -y

git clone https://github.com/johnsinak/hush-proxy.git

python3 hush-proxy/src/nat.py
