# V2Ray Client Manager

## Local dev setup

v2ray-core is included here as a submodule, needed for its protobuf files in order to generate gRPC stubs.

Clone it, and then in a Python environment with the [requirements](requirements.txt) installed run:

```zsh
python -m grpc_tools.protoc -Iv2ray-core --python_out=. --pyi_out=. --grpc_python_out=. v2ray-core/**/*.proto
```

For shells that don't support globstar, you can use the line from the [Dockerfile](Dockerfile) instead:

```bash
find v2ray-core/ -name '*.proto' -exec python -m grpc_tools.protoc -Iv2ray-core --python_out=. --pyi_out=. --grpc_python_out=. {} +
```

## TODO

- speak the same protocol the controller speaks
- work with NAT
- respond to requests for usage reports
- figure out what to do for client auth
  - figure out how to send config to new proxy (in-memory structure + gRPC?)
- maybe streamline launch somehow (still liking docker compose)
