
## Wireguard active migration functionality test:
1. Set up NAT: 
- Create VM
- Git clone this repo
- Install Docker: https://docs.docker.com/engine/install/ubuntu/
- cd to spotproxy/wireguard
-  sudo docker build -t nat-image -f NATDockerfile .
-  sudo docker run -it -p 8000:8000 --cap-add=NET_ADMIN --name=nat nat-image
- choose 1 for NAT server (remove this choice later)

2. Set up main proxy:
- Create VM
- Git clone this repo
- Modify NAT in settings.py
- install docker: https://docs.docker.com/engine/install/ubuntu/
- cd to spotproxy/wireguard
- sudo docker build -t server-image -f ServerDockerfile .
- sudo docker run -it -p 51820:51820 --cap-add=NET_ADMIN --name=server server-image

2. Set up client:
- Create VM
- Git clone this repo
- sudo apt install wireguard-tools 
- Modify MAIN_PROXY_ENDPOINT in settings.py
- Modify key_store/peer1/wg0.conf Endpoint IP only
- run buildkeys script
- install docker: https://docs.docker.com/engine/install/ubuntu/
- cd to spotproxy/wireguard
- sudo docker build -t client-image -f Peer1Dockerfile .
- sudo docker run -it --cap-add=NET_ADMIN --name=client client-image