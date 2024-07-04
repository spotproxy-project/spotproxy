# flash-controller

The controller for the spotproxy project. This code also contains the censor simulator.

## Usage guide

Refer to the following section to learn how to use the controller or run the simulation.

### Running the controller

1. Build the docker file ```Dockerfile``` and run it using:

```sh
    sudo docker build -t controller-image -f Dockerfile .
    sudo docker run -it -p 8000:8000 --cap-add=NET_ADMIN --name=controller controller-image
```

Output of the following line `Starting development server at http://0.0.0.0:8000/` indicates success. 

2. (Optional) To test successful connectivity to the controller, feel free to execute the script in `spotcontroller/controller/misc/sample-request.py` (which executes a simple POST request to the controller) on a separate machine. 

### Running the simulation

1. Build the docker file ```SimulationDockerfile``` and run it using:

```sh
    sudo docker build -t simulation-image -f SimulationDockerfile .
    sudo docker run -it --name=simulation simulation-image
```

This simulation should take a few minutes only to complete.  

2. Inspect the results by reentering the exited docker container:
```sh
sudo docker ps --all # Get the CONTAINER ID of the docker container that you ran earlier 
sudo docker commit <container-ID> test-commit # Create a new commit based on the current state of the container
sudo docker run -it test-commit /bin/bash # Access the docker container
ls results # Retrieve the required simulation output file within this folder
```
The `.csv` file within `results` is the resultant simulation output. If this file exists, the simulation was a success. 
