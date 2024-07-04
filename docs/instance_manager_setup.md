## Instance manager setup
This assumes you are executing the instructions in a machine that was setup with the instructions provided in `docs/INSTALLATION.md`. 

### Environment setup
1. [Install Conda](https://docs.anaconda.com/miniconda/#quick-command-line-install). 
2. Setup and activate our Conda environment
```bash
conda env create -f environment.yml
conda activate spotproxy-im
```

### Initiate the instance manager
1. Within your AWS account EC2 `Launch Templates` menu, create a new launch template: 
    1. Choose Ubuntu 22.04: under `Application and OS Images` -> `Quick Start` -> `Ubuntu`
    2. Select an appropriate key-pair: any will do, we do need to SSH into the VMs. 
    3. Create a permissible security group (allowing all traffic): select `Create security group`, and under `Add security group rule` select "All traffic" for `Type` and "Anywhere" for `Source Type`. 
    4. Under `Advanced details`: select the "Spot instances" `Purchasing option`. 
    5. Under `Advanced details`, within the `User data` option: paste the text within `wireguard/startup-scripts/secondary-proxy-boot.sh` file, with the <NAT_IP> argument modified to use the public IP of the NAT VM created in the previous step.
    6. Create the launch template, and record down the resulting "Launch template ID" field. 
2. SSH into the instance manager VM. 
3. Within the VM: modify the file `instance_manager/input-args-wireguard.json`: "launch-template" field to use the ID obtained above. 
4. CD into the `instance_manager` directory. 
5. Make sure that your AWS credentials (e.g., AWS_ACCESS_KEY) are exported in the current terminal session. Instructions are located in [INSTALLATION.MD](https://github.com/spotproxy-project/spotproxy/blob/main/docs/INSTALLATION.md).
6. Run the commands in the following sections as needed. 

## Artifact evaluation Experiment E1 Minimal working example:
Cost arbitrage test: this is a scaled down test compared with experiment E3 that creates 1 instance of the cheapest AWS VM within a selected region. 
```bash
python3 api.py input-args-wireguard.json simple-test
```
This test will eventually terminate the instances and stop (after a few minutes), but feel free to perform these steps manually: stop the script, and terminate the instances manually through your AWS Console. 

## Artifact evaluation Experiment E3 Minimal working example:

Instance rejuvenation test: this will create a selection of VMs that are periodically rejuvenated, using the instance rejuvenation method. 
```bash
python3 api.py input-args-wireguard.json
```
Note: This test will not terminate, and you have to perform these steps manually: stop the script, and terminate the **instances** manually through your AWS Console. 

Live IP rejuvenation test: this will create a selection of VMs that are periodically rejuvenated, using the live IP rejuvenation method. 
1. Modify the `mode` field value to "liveip" within `input-args-wireguard.json`. 
2. Execute the instance manager
```bash
python3 api.py input-args-wireguard.json
```
Note: This test will not terminate, and you have to perform these steps manually: stop the script, and terminate the **instances and elastic IPs** manually through your AWS Console. 