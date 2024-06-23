## Wireguard active migration functionality test:
All the following steps (except Step 2) should be executed on separate VMs. 

### Step 1: Set up the NAT. 
1. Create an AWS VM running Ubuntu 22.04, with a security group allowing all traffic (for the convenience of artifact evaluation).
2. SSH into the VM. 
3. Git clone this repo
4. [Install Docker](https://docs.docker.com/engine/install/ubuntu/)
5. Follow the NAT-related instructions in [wireguard/README.md](https://github.com/spotproxy-project/spotproxy/tree/main/wireguard).

### Step 2: Setup the instance manager to support active migration.
<!-- - Fork this GitHub repository -->
<!-- - Within the forked repository, modify the <forked_repository_url> and <NAT_IP> arguments within the `wireguard/startup-scripts/secondary-proxy-boot.sh` file.  -->
<!-- - Commit and push these changes.  -->
1. Within your AWS account EC2 `Launch Templates` menu, create a new launch template: 
    1. Choose Ubuntu 22.04
    2. Select an appropriate key-pair
    3. Create a permissible security group (allowing all traffic)
    4. Under advanced details: select the "Spot instances" purchasing option. 
    5. Under advanced details, paste the text within `wireguard/startup-scripts/secondary-proxy-boot.sh` file, with the <NAT_IP> argument modified to use the public IP of the NAT VM created in the previous step.
    6. Create the launch template, and record down the resulting "Launch template ID" field. 
2. SSH into the instance manager VM, modify the `instance_manager/input-args-wireguard.json` "launch-template" field to use the ID obtained above. 
3. Start the instance manager: 
```bash
cd instance_manager
python3 api.py input-args-wireguard.json
```
This will create a number of proxies that will be periodically rejuvenated. 

### Step 3: Set up the main proxy.
1. Create an AWS VM running Ubuntu 22.04, with a security group allowing all traffic (for the convenience of artifact evaluation).
2. SSH into the VM. 
2. Git clone this repo.
3. [Install Docker](https://docs.docker.com/engine/install/ubuntu/)
4. Follow the main proxy-related instructions in [wireguard/README.md](https://github.com/spotproxy-project/spotproxy/tree/main/wireguard).

### Step 4: Set up the client.
1. Create an AWS VM running Ubuntu 22.04, with a security group allowing all traffic (for the convenience of artifact evaluation).
2. SSH into the VM. 
2. Git clone this repo.
3. [Install Docker](https://docs.docker.com/engine/install/ubuntu/)
4. Follow the client-related instructions in [wireguard/README.md](https://github.com/spotproxy-project/spotproxy/tree/main/wireguard).