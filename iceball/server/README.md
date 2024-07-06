<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**

- [Setup](#setup)
- [TLS](#tls)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

This is the server transport plugin for Snowflake.
The actual transport protocol it uses is
[WebSocket](https://tools.ietf.org/html/rfc6455).
In Snowflake, the client connects to the proxy using WebRTC,
and the proxy connects to the server (this program) using WebSocket.


# Setup

The server needs to be able to listen on port 80
in order to generate its TLS certificates.
On Linux, use the `setcap` program to enable
the server to listen on port 80 without running as root:
```
setcap 'cap_net_bind_service=+ep' /usr/local/bin/snowflake-server
```

Here is a short example of configuring your torrc file
to run the Snowflake server under Tor:
```
SocksPort 0
ORPort 9001
ExtORPort auto
BridgeRelay 1

ServerTransportListenAddr snowflake 0.0.0.0:443
ServerTransportPlugin snowflake exec ./server --acme-hostnames snowflake.example --acme-email admin@snowflake.example --log /var/log/tor/snowflake-server.log
```
The domain names given to the `--acme-hostnames` option
should resolve to the IP address of the server.
You can give more than one, separated by commas.


# TLS

The server uses TLS WebSockets by default: wss:// not ws://.
There is a `--disable-tls` option for testing purposes,
but you should use TLS in production.

The server automatically fetches certificates
from [Let's Encrypt](https://en.wikipedia.org/wiki/Let's_Encrypt) as needed.
Use the `--acme-hostnames` option to tell the server
what hostnames it may request certificates for.
You can optionally provide a contact email address,
using the `--acme-email` option,
so that Let's Encrypt can inform you of any problems.
The server will cache TLS certificate data in the directory
`pt_state/snowflake-certificate-cache` inside the tor state directory.

In order to fetch certificates automatically,
the server needs to listen on port 80,
in addition to whatever ports it is listening on
for WebSocket connections.
This is a requirement of the ACME protocol used by Let's Encrypt.
The program will exit if it can't bind to port 80.
On Linux, you can use the `setcap` program,
part of libcap2, to enable the server to bind to low-numbered ports
without having to run as root:
```
setcap 'cap_net_bind_service=+ep' /usr/local/bin/snowflake-server
```


# Multiple KCP state machines

The server internally uses a network protocol called KCP
to manage and persist client sessions.
Each KCP scheduler runs on a single thread.
When there are many simultaneous users (thousands),
a single KCP scheduler can be a bottleneck.
The `num-turbotunnel` pluggable transport option
lets you control the number of KCP instances,
which can help with CPU scaling:
https://bugs.torproject.org/tpo/anti-censorship/pluggable-transports/snowflake/40200

There is currently no way to set this option automatically.
You have to tune it manually.

```
ServerTransportOptions snowflake num-turbotunnel=2
```


# Controlling source addresses

Use the `orport-srcaddr` pluggable transport option to control what source addresses
are used when connecting to the upstream Tor ExtORPort or ORPort.
The value of the option may be a single IP address (e.g. "127.0.0.2")
or a CIDR range (e.g. "127.0.2.0/24"). If a range is given,
an IP address from the range is randomly chosen for each new connection.

Use `ServerTransportOptions` in torrc to set the option:
```
ServerTransportOptions snowflake orport-srcaddr=127.0.2.0/24
```

You can combine it with other options:
```
ServerTransportOptions snowflake num-turbotunnel=2 orport-srcaddr=127.0.2.0/24
```

Specifying a source address range other than the default 127.0.0.1
can help with conserving localhost ephemeral ports on servers
that receive a lot of connections:
https://bugs.torproject.org/tpo/anti-censorship/pluggable-transports/snowflake/40198
