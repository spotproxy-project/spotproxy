# Spotproxy Wireguard

Code for the spotproxy research, relating to wireguard solutions.

## Important note | Setup

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

To run each component in Docker, we have created several docker files with the names "<component>Dockerfile". Simply build and run any of them to run the corresponding component. To build and run a Docker container, you can refer to the code block below:
