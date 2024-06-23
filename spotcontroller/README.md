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

To run the simulation, repeat the steps above, but with the the file ```SimulationDockerfile``` instead.
