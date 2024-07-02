## Wireguard active migration functionality test:
All the following steps (except Step 2) should be executed on separate VMs. 

### Step 1: Set up the NAT. 
1. Create an AWS VM running Ubuntu 22.04, with a security group allowing all traffic (for the convenience of artifact evaluation).
2. SSH into the VM. 
3. Git clone this repo
4. [Install Docker](https://docs.docker.com/engine/install/ubuntu/)
5. Follow the NAT-related instructions in [wireguard/README.md](https://github.com/spotproxy-project/spotproxy/tree/main/wireguard).

### Step 2: Set up the main proxy.
1. Create an AWS VM running Ubuntu 22.04, with a security group allowing all traffic (for the convenience of artifact evaluation).
2. SSH into the VM. 
3. Git clone this repo.
4. [Install Docker](https://docs.docker.com/engine/install/ubuntu/)
5. Follow the main proxy-related instructions in [wireguard/README.md](https://github.com/spotproxy-project/spotproxy/tree/main/wireguard).

### Step 3: Set up the client.
1. Create an AWS VM running Ubuntu 22.04, with a security group allowing all traffic (for the convenience of artifact evaluation).
2. SSH into the VM. 
3. Git clone this repo.
4. [Install Docker](https://docs.docker.com/engine/install/ubuntu/)
5. Follow the client-related instructions in [wireguard/README.md](https://github.com/spotproxy-project/spotproxy/tree/main/wireguard).

### Step 4: Set up the Controller.

1. Setup the controller following the steps mentioned in [docs/controller_setup.md](https://github.com/spotproxy-project/spotproxy/tree/main/docs/controller_setup.md).
2. Add the main proxy to the controller database by using the [Django Admin](https://docs.djangoproject.com/en/5.0/ref/contrib/admin/) panel:
- On your local browser, access `http://<controller-public-IP>:8000/admin`
- Use the login credentials: username as `admintest` and password as `123`.
- Create the following objects (note: when prompted, required attributes can have any value):
    - Create a new `Proxy` object: set the IP to the main proxy VM's public IP.
    - Create a new `Client` object: set the IP to the client VM's public IP. 
    - Create a new `Assignment` object: select the newly created proxy and client object as appropriate. 

### Step 5: Setup the instance manager to support active migration.
<!-- - Fork this GitHub repository -->
<!-- - Within the forked repository, modify the <forked_repository_url> and <NAT_IP> arguments within the `wireguard/startup-scripts/secondary-proxy-boot.sh` file.  -->
<!-- - Commit and push these changes.  -->
1. Within your AWS account EC2 `Launch Templates` menu, create a new launch template: 
    1. Choose Ubuntu 22.04: under `Application and OS Images` -> `Quick Start` -> `Ubuntu`
    2. Select an appropriate key-pair: any will do, we do need to SSH into the VMs. 
    3. Create a permissible security group (allowing all traffic): select `Create security group`, and under `Add security group rule` select "All traffic" for `Type` and "Anywhere" for `Source Type`. 
    4. Under `Advanced details`: select the "Spot instances" `Purchasing option`. 
    5. Under `Advanced details`, within the `User data` option: paste the text within `wireguard/startup-scripts/secondary-proxy-boot.sh` file, with the <NAT_IP> argument modified to use the public IP of the NAT VM created in the previous step.
    6. Create the launch template, and record down the resulting "Launch template ID" field. 
2. SSH into the instance manager VM. 
3. Within the VM, modify the file `instance_manager/input-args-wireguard.json`:
- "launch-template" field to use the ID obtained above. 
- "controller-IP" field to use the public IP of the Controller created in the previous step. 
- "initial_proxy_ip" field to use the public IP of the main proxy created earlier. 
4. Ensure you have exported the required AWS CLI credentials (e.g., AWS_ACCESS_KEY) outlined earlier in [INSTALLATION.MD](https://github.com/spotproxy-project/spotproxy/blob/main/docs/INSTALLATION.md).
5. Start the instance manager: 
```bash
cd instance_manager
python3 api.py input-args-wireguard.json
```
This will create a number of proxies that will be periodically rejuvenated. 

### Step 6: Observe expected output from the client VM terminal
1. Messages beginning with "here at..." indicate that the client is able to access the default website successfully. 
2. Messages beginning with "migration request from.." indicate that the client has successfully migrated to a new proxy. This may take a few minutes to produce. 
3. Once both message types are produced, you have completed the experiment. 
