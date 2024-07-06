<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**

- [Dependencies](#dependencies)
- [Building the standalone Snowflake proxy](#building-the-standalone-snowflake-proxy)
- [Running a standalone Snowflake proxy](#running-a-standalone-snowflake-proxy)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

This is a standalone (not browser-based) version of the Snowflake proxy. For browser-based versions of the Snowflake proxy, see https://gitlab.torproject.org/tpo/anti-censorship/pluggable-transports/snowflake-webext.

### Dependencies

- Go 1.15+
- We use the [pion/webrtc](https://github.com/pion/webrtc) library for WebRTC communication with Snowflake proxies. Note: running `go get` will fetch this dependency automatically during the build process.

### Building the standalone Snowflake proxy

To build the Snowflake proxy, make sure you are in the `proxy/` directory, and then run:

```
go get
go build
```

### Running a standalone Snowflake proxy

The Snowflake proxy can be run with the following options:
```
Usage of ./proxy:
  -allow-non-tls-relay
        allow relay without tls encryption
  -allowed-relay-hostname-pattern string
        a pattern to specify allowed hostname pattern for relay URL. (default "snowflake.torproject.net$")
  -broker string
        broker URL (default "https://snowflake-broker.torproject.net/")
  -capacity uint
        maximum concurrent clients (default is to accept an unlimited number of clients)
  -ephemeral-ports-range string
        ICE UDP ephemeral ports range (format:"<min>:<max>")
  -keep-local-addresses
        keep local LAN address ICE candidates
  -log string
        log filename
  -nat-retest-interval duration
        the time interval in second before NAT type is retested, 0s disables retest. Valid time units are "s", "m", "h".  (default 24h0m0s)
  -relay string
        websocket relay URL (default "wss://snowflake.bamsoftware.com/")
  -outbound-address string
        bind a specific outbound address. Replace all host candidates with this address without validation. 
  -stun string
        stun URL (default "stun:stun.l.google.com:19302")
  -summary-interval duration
        the time interval to output summary, 0s disables summaries. Valid time units are "s", "m", "h".  (default 1h0m0s)
  -unsafe-logging
        prevent logs from being scrubbed
  -verbose
        increase log verbosity
  -version
        display version info to stderr and quit
```

For more information on how to run a Snowflake proxy in deployment, see our [community documentation](https://community.torproject.org/relay/setup/snowflake/standalone/).
