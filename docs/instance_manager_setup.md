# Instance manager setup
This assumes you are executing the instructions in a machine that was setup with the instructions provided in `docs/INSTALLATION.md`. 

1. [Install Conda](https://docs.anaconda.com/miniconda/#quick-command-line-install). 
2. Setup and activate our Conda environment
```bash
conda env create -f environment.yml
conda activate spotproxy-im
```

4. Initiate the instance manager
- CD into the `instance_manager` directory. 
- Modify the `launch-template` fields for both `input-args-snowflake.json` and `input-args-wireguard.json` accordingly. 
- Run the commands in the following sections as needed. 

## Artifact evaluation Experiment E1 Minimal working example:
Cost arbitrage test: this is a scaled down test compared with experiment E3 that creates 5 instances of the cheapest AWS VM within a selected region. 
```bash
python3 api.py input-args-wireguard.json simple-test
```

## Artifact evaluation Experiment E3 Minimal working example:
Instance rejuvenation test: this will create a selection of VMs that are periodically rejuvenated, using the instance rejuvenation method. 
```bash
python3 api.py input-args-wireguard.json
```


Live IP rejuvenation test: this will create a selection of VMs that are periodically rejuvenated, using the live IP rejuvenation method. 
1. Modify the `mode` field value to "liveip" within `input-args-wireguard.json`. 
2. Execute the instance manager
```bash
python3 api.py input-args-wireguard.json
```