# Iceball

A fork of snowflake that works as standalone proxy hosted in spot vm.

### Structure of this Repository

- `broker/` contains code for the Iceball broker
- `client/` contains the Tor pluggable transport client and client library code
- `common/` contains generic libraries used by multiple pieces of Snowflake
- `proxy/` contains code for the Go standalone Iceball proxy
- `probetest/` contains code for a NAT probetesting service
- `server/` contains the Tor pluggable transport server and server library code

### Usage

#### Building from source

Install golang from [golang offical website](https://go.dev/doc/install)
In go.mod, replace the last argument of last line with the path of this project
For building the broker, client, and proxy, go to the respective directory (e.g. iceball/broker) and run
```
go get
go build
```

#### Using Iceball client with Tor

To use the Iceball client with Tor, you will need to add the appropriate `Bridge` and `ClientTransportPlugin` lines to your [torrc](https://2019.www.torproject.org/docs/tor-manual.html.en) file. An example file is in client/. Replace the value of `ClientTransportPlugin` with the path to the Iceball client executable and `-url` with the domain name of the broker. 
To run the client with Tor, use
```
tor -f torrc
```

#### Running an Iceball Proxy
Build the proxy first and then run:
```
./proxy -broker [url of broker]
```

#### Running the broker
The broker requires a domain pointing to the ip address where the broker is hosted. The broker also needs permission to bind on port 443
After building the broker, run:
```
sudo setcap CAP_NET_BIND_SERVICE=+eip [path to broker executable]
./broker --metrics-log [path to log] --acme-hostnames [domain of the broker] --acme-email [email] --acme-cert-cache [cache path]
```
Example:
```
./broker --metrics-log /home/ubuntu/iceball/broker/metrics.log --acme-hostnames [yourdomain].com --acme-email [youremail] --acme-cert-cache /home/ubuntu/iceball/broker/acme-cert-cache 2>&1
```

### Running Tests in AWS

For configuring AWS spot instances and running tests on them, refer to AWS Guide.pdf

