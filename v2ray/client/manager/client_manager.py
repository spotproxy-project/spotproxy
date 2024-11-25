import inspect
import re
import sys
from types import NoneType
import socks
import socket
import time
import grpc
from app.proxyman.command import command_pb2, command_pb2_grpc

import config_pb2
import google.protobuf.any_pb2 as any_pb2
import proxy.vmess.outbound.config_pb2 as vmess
from app.proxyman.config_pb2 import SenderConfig, MultiplexingConfig
from common.net.address_pb2 import IPOrDomain
from common.protocol.server_spec_pb2 import ServerEndpoint
from common.protocol.user_pb2 import User
from proxy.vmess.account_pb2 import Account as VmessAccount

# todo set constants from env
PROXY_ADDR = "10.255.1.1"
SERVER_MANAGER_ADDR = "127.0.0.1"

SOCKS_PORT = 1080
API_PORT = 9090
MIGRATION_PORT = 1248
PROXY_PORT = 10086


def make_any(value: any) -> any_pb2.Any:
    result = any_pb2.Any()
    result.Pack(value)
    result.type_url = result.type_url.removeprefix("type.googleapis.com/")
    return result


def parse_chunks(data: bytes, sizes: list[int]) -> list[bytes]:
    result = []
    for size in sizes:
        result.append(data[:size])
        data = data[size:]
    return result


def is_ipv4_address(x: bytes) -> bool:
    return (
        re.compile(r"\d{1-3}\.\d{1-3}\.\d{1-3}\.\d{1-3}").fullmatch(x.decode())
        is not None
    )


def log(*args) -> NoneType:
    calling_frame = inspect.stack()[1]
    location = f"{calling_frame.function} at {calling_frame.filename}:{calling_frame.lineno}"
    print(f"[{location}]", *args, file=sys.stderr)


def migrate(ip: str, port: int) -> NoneType:
    log(f"proxy migrating to: new address {ip}, port {port}")

    remove_req = command_pb2.RemoveOutboundRequest(tag="spotproxy-outbound")

    sender_config = SenderConfig(
        multiplex_settings=MultiplexingConfig(
            enabled=True,
            concurrency=1024,
        )
    )
    sender = make_any(sender_config)

    account_config = VmessAccount(id="deadbeef-dead-beef-dead-beefdeadbeef")
    account = make_any(account_config)

    proxy_config = vmess.Config(
        Receiver=[
            ServerEndpoint(
                address=IPOrDomain(ip=socket.inet_aton(ip)),
                port=port,
                user=[
                    User(
                        account=account,
                    )
                ],
            )
        ]
    )
    proxy = make_any(proxy_config)

    outbound = config_pb2.OutboundHandlerConfig(
        tag="spotproxy-outbound",
        sender_settings=sender,
        proxy_settings=proxy,
    )
    add_req = command_pb2.AddOutboundRequest(outbound=outbound)

    with grpc.insecure_channel(f"{PROXY_ADDR}:{API_PORT}") as channel:
        stub = command_pb2_grpc.HandlerServiceStub(channel)

        remove_response = stub.RemoveOutbound(remove_req)
        log(f"gRPC API (remove) returned response: {remove_response}")

        add_response = stub.AddOutbound(add_req)
        log(f"gRPC API (add) returned response: {add_response}")

    log(f"migrate {ip} complete!")


def handle(manager_ip: str, manager_port: int) -> tuple[str, int]:
    with socks.socksocket(socket.AF_INET, socket.SOCK_STREAM) as outbound:
        print("SOCKS socket created")
        # Use client v2ray instance as SOCKS proxy
        outbound.set_proxy(socks.SOCKS5, PROXY_ADDR, SOCKS_PORT)
        # Connect to server manager through the proxy
        time.sleep(1)
        outbound.connect((manager_ip, manager_port))
        log(f"connected to {manager_ip}:{manager_port}")

        MAX_MESSAGE_LENGTH = len(b"XXX.XXX.XXX.XXX")

        msg = b""
        while data := outbound.recv(MAX_MESSAGE_LENGTH - len(msg)):
            msg += data

    log(f"recv'd data on migration connection: {msg}")
    if not is_ipv4_address(msg):
        log(f"message not an IPv4 address, ignoring: {msg}")
        return manager_ip, manager_port

    new_server_ip, new_server_port = msg.decode(), PROXY_PORT
    new_manager_ip, new_manager_port = "127.0.0.1", MIGRATION_PORT

    log(
        f"received new_proxy_ip {new_server_ip} and new_proxy_port {new_server_port}"
    )
    log(
        f"received new_manager_ip {new_manager_ip} and new_manager_port {new_manager_port}"
    )

    migrate(new_server_ip, new_server_port)
    return new_manager_ip, new_manager_port


def main() -> NoneType:
    log("starting main")
    manager_ip = SERVER_MANAGER_ADDR
    manager_port = MIGRATION_PORT
    while True:
        manager_ip, manager_port = handle(manager_ip, manager_port)


if __name__ == "__main__":
    main()
