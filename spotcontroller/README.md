# flash-controller

The controller for the spotproxy project. This code also contains the censor simulator.

## Usage guide

Refer to the following section to learn how to use the controller or run the simulation.

### Running the controller

Build the docker file ```Dockerfile``` and run it using:

```sh
    sudo docker build -t controller-image -f Dockerfile .
    sudo docker run -it -p 8000:8000 --cap-add=NET_ADMIN --name=controller controller-image
```

### Running the simulation

To run the simulation, repeat the steps above, but with the the file ```SimulationDockerfile``` instead.
