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

PROXY_ADDR = "10.255.1.1"
SERVER_MANAGER_ADDR = "10.254.1.2"

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


def migrate(ip: bytes, port: int) -> NoneType:
    print(
        f"proxy migrating to: new address {socket.inet_ntoa(ip)}, port {port}"
    )

    remove_req = command_pb2.RemoveOutboundRequest(tag="spotproxy-outbound")
    print(f"*** remove_req: {remove_req}")

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
                address=IPOrDomain(ip=ip),
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
    print(f"*** add_req: {add_req}")

    with grpc.insecure_channel(f"{PROXY_ADDR}:{API_PORT}") as channel:
        stub = command_pb2_grpc.HandlerServiceStub(channel)

        remove_response = stub.RemoveOutbound(remove_req)
        print(f"[remove] gRPC API returned response: {remove_response}")

        add_response = stub.AddOutbound(add_req)
        print(f"[add] gRPC API returned response: {add_response}")

    print(f"migrate {socket.inet_ntoa(ip)} complete!")


def handle(manager_ip: str, manager_port: int) -> tuple[str, int]:
    with socks.socksocket(socket.AF_INET, socket.SOCK_STREAM) as outbound:
        print("SOCKS socket created")
        # Use client v2ray instance as SOCKS proxy
        outbound.set_proxy(socks.SOCKS5, PROXY_ADDR, SOCKS_PORT)
        # Connect to server manager through the proxy
        time.sleep(1)
        outbound.connect((manager_ip, manager_port))
        print(f"connected to {manager_ip}:{manager_port}")

        msg = outbound.recv(12, socket.MSG_WAITALL)
        print(f"recv'd data on migration connection: {msg}")
        new_server_ip, new_server_port, new_manager_ip, new_manager_port = (
            parse_chunks(msg, [4, 2, 4, 2])
        )
        print(
            f"received new_proxy_ip {socket.inet_ntoa(new_server_ip)} and new_proxy_port {int.from_bytes(new_server_port, "big")}"
        )
        print(
            f"received new_manager_ip {socket.inet_ntoa(new_manager_ip)} and new_manager_port {int.from_bytes(new_manager_port, "big")}"
        )

    migrate(new_server_ip, int.from_bytes(new_server_port, "big"))
    return socket.inet_ntoa(new_manager_ip), int.from_bytes(
        new_manager_port, "big"
    )


def main() -> NoneType:
    time.sleep(10)
    print("starting main")
    manager_ip = SERVER_MANAGER_ADDR
    manager_port = MIGRATION_PORT
    while True:
        manager_ip, manager_port = handle(manager_ip, manager_port)


if __name__ == "__main__":
    main()
