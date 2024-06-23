## Wireguard active migration functionality test:

All the following steps (except Step 2) should be executed on separate VMs. 
1. Set up the NAT: 
- Create VM
- Git clone this repo
- Install Docker: https://docs.docker.com/engine/install/ubuntu/
- cd to spotproxy/wireguard
-  sudo docker build -t nat-image -f NATDockerfile .
-  sudo docker run -it -p 8000:8000 --cap-add=NET_ADMIN --name=nat nat-image
- choose 1 for NAT server (remove this choice later)

2. Setup the instance manager to support active migration. 
<!-- - Fork this GitHub repository -->
<!-- - Within the forked repository, modify the <forked_repository_url> and <NAT_IP> arguments within the `wireguard/startup-scripts/secondary-proxy-boot.sh` file.  -->
<!-- - Commit and push these changes.  -->
- On your AWS account, create an EC2 launch template:
    - Within your AWS account EC2 `Launch Templates` menu, create a new launch template: 
        - Choose Ubuntu 22.04
        - Select an appropriate key-pair
        - Create a permissible security group (allowing all traffic)
        - Under advanced details: select the "Spot instances" purchasing option. 
        - Under advanced details, paste the text within `wireguard/startup-scripts/secondary-proxy-boot.sh` file, with the <NAT_IP> argument modified to use the public IP of the NAT VM created in the previous step.
        - Create the launch template, and record down the resulting "Launch template ID" field. 
    - Within the instance manager VM, modify the `instance_manager/input-args-wireguard.json` "launch-template" field to use the ID obtained above. 
    - Start the instance manager: 
    ```bash
    cd instance_manager
    python3 api.py input-args-wireguard.json
    ```

3. Set up main proxy:
- Create VM
- Git clone this repo
- Modify NAT in settings.py
- install docker: https://docs.docker.com/engine/install/ubuntu/
- cd to spotproxy/wireguard
- Initialize the Docker container
```bash
sudo docker build -t server-image -f ServerDockerfile .
sudo docker run -it -p 51820:51820 --cap-add=NET_ADMIN --name=server server-image
```

4. Set up client:
- Create VM
- Git clone this repo
- sudo apt install wireguard-tools 
- Modify MAIN_PROXY_ENDPOINT in settings.py
- Modify key_store/peer1/wg0.conf Endpoint IP only
- run buildkeys script
- install docker: https://docs.docker.com/engine/install/ubuntu/
- cd to spotproxy/wireguard
- Initialize the Docker container:
```bash
sudo docker build -t client-image -f Peer1Dockerfile .
sudo docker run -it --cap-add=NET_ADMIN --name=client client-image
```