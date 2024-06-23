# Spotproxy Wireguard

Code for the spotproxy research, relating to Wireguard solutions.

All the steps below assume you are within the `wireguard` directory. 

## Wireguard NAT setup
Execute the following commands to initialize the NAT server. 
```bash
cd to spotproxy/wireguard
sudo docker build -t nat-image -f NATDockerfile .
sudo docker run -it -p 8000:8000 --cap-add=NET_ADMIN --name=nat nat-image 
```
Choose option 1 in the dropdown. After that, the NAT server will be running. 

## Wireguard main proxy setup
1. Modify the first element of the `NAT_ENDPOINT` (i.e., IP component) in `src/settings.py` to be the public IP of the AWS VM NAT server created earlier.
2. Execute the following commands to initialize the main proxy. 
```bash
sudo docker build -t server-image -f ServerDockerfile .
sudo docker run -it --network host --cap-add=NET_ADMIN --name=server server-image
```
The resultant output of the form `my endpoint is: <main-proxy-public-ip>:51820` indicates that the main proxy is not running successfully. 

## Wireguard client setup
1. Install Wireguard tools: 
```bash
sudo apt install wireguard-tools 
```
2. Modify the `MAIN_PROXY_ENDPOINT` in `src/settings.py` to be the public IP of the AWS main proxy server created earlier.
3. Modify the IP component of the `Endpoint` (i.e., leave the `:51820` part untouched) in `key_store/peer1/wg0.conf` to be the public IP of the AWS main proxy server created earlier.
4. Run the following commands:
```bash
python3 buildbulkeys.py
sudo docker build -t client-image -f Peer1Dockerfile .
sudo docker run -it --cap-add=NET_ADMIN --name=client client-image
```
The resultant output of the form `here at Xs, got Y data` indicates that the client is successfully running, and able to access its intended destination through the proxy and NAT devices set up (feel free to check their respective console outputs too). 


<!-- ## Important note | Setup

To setup this code, the NAT proxy and and the main proxy ips have to be set in the config files.

1. Set the NAT endpoint in the src/settings.py
2. Set the MAIN proxy ip (the first proxy the user connects to) in src/settings.py
3. Go to key_store/peer1/wg0.conf and set the endpoint for the first peer to the MAIN proxy ip.
4. Run ```python buildkeys.py"

## Running the code

There are two methods to run this code. We recommend using a VM and bash, but Docker also works.

### Using Bash

To run each component of this code, we have developed a startup script located in the ```startup-script/``` folder. simply run ```bash startup-scripts/<intended_scruot>``` to run the code. Preferably, do not use this scripts on your personal device.

### Using Docker

To run each component in Docker, we have created several docker files with the names "<component>Dockerfile". Simply build and run any of them to run the corresponding component. To build and run a Docker container, you can refer to the code block below: -->
