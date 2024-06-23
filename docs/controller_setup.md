The controller will be used for testing active migration functionality of Wireguard in experiment E4 of the artifact evaluation. 
## Wireguard controller setup procedures
1. Create an AWS VM running Ubuntu 22.04, with a security group allowing all TCP traffic (for the convenience of artifact evaluation). 
2. SSH into that VM. 
3. Git clone this repository. 
```bash
git clone https://github.com/spotproxy-project/spotproxy.git
```
4. [Install Docker](https://docs.docker.com/engine/install/ubuntu/)
5. Follow the instructions in [spotcontroller/README.md](https://github.com/spotproxy-project/spotproxy/blob/main/spotcontroller/README.md)