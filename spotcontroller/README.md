# flash-controller

The controller for the spotproxy project. This code also contains the censor simulator.

## Usage guide

Refer to the following section to learn how to use the controller or run the simulation.

### Running the controller

Build the docker file ```Dockerfile``` and run it using:

```sh
    docker build -t controller-image -f Dockerfile .
    docker run -it --cap-add=NET_ADMIN --name=controller controller-image
```

### Running the simulation

To run the simulation, repeat the steps above, but with the the file ```SimulationDockerfile``` instead.
