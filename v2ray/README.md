# V2Ray in SpotProxy

## Design

The client and server each run an instance of V2Ray, connected directly as in a typical V2Ray setup. Each additionally runs a manager program. The client manager connects to the server manager via TCP through V2Ray using a multiplexed outbound, ensuring that there is only a single connection between the client and the server in order to resist fingerprinting.

The client manager and server manager[^1] each control the local V2Ray instance using V2Ray's gRPC API. The client removes and replaces its outbound using the handler API when informed of a migration by the server, and in the future the server will likely query its V2Ray instance for connection statistics using the stats API and possibly configure its inbound dynamically using the handler API.

## TODOs and potential TODOs (in roughly decreasing priority)

- work with NAT
- talk to broker on client startup, add initial outbound
- respond to requests for usage reports
- be more careful routing traffic to local IP addresses
- figure out what to do for client auth
  - figure out how to send config to new proxy (in-memory structure + gRPC?)
- add ip and port as environment variables
- maybe streamline launch somehow (still liking docker compose)
- change protocol to make parsing migrate notices easier
- unify `use_*_launch_templates` in instance manager
- investigate possible inconsistency in `launch_templates` `lanuch-templates`
- figure out what's unnecessary in v2ray input-args

[^1]: nothing yet implemented for the server that requires this
