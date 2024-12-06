import inspect
import sys
import threading
from types import NoneType
import socket
import re

from typing import Generic, NoReturn, TypeVar


CLIENT_MIGRATION_PORT = 1248
CONTROLLER_MIGRATION_PORT = 8089
SERVER_PORT = 10086


T = TypeVar("T")


class Event(threading.Event, Generic[T]):
    def __init__(self):
        super().__init__()
        self.message: T | NoneType = None

    def set(self, message: T) -> NoneType:
        self.message = message
        return super().set()

    def wait(self) -> T:
        super().wait()
        return self.message


InetAddress = tuple[str, int]


def log(*args) -> NoneType:
    calling_frame = inspect.stack()[1]
    location = f"{calling_frame.function} at {calling_frame.filename}:{calling_frame.lineno}"
    print(f"[{location}]", *args, file=sys.stderr)


def is_ipv4_address(x: bytes) -> bool:
    return (
        re.compile(r"\d{1-3}\.\d{1-3}\.\d{1-3}\.\d{1-3}").fullmatch(x.decode())
        is not None
    )


class ServerManager:
    def __init__(self) -> NoneType:
        self.migration_event = Event[bytes]()

    def handle_client(self, conn: socket.socket, addr: InetAddress) -> NoneType:
        log(f"handling client at address {addr[0]}:{addr[1]}")
        with conn:
            conn.sendall(self.migration_event.wait())
        log(f"informed client at {addr[0]}:{addr[1]} of migration")

    def handle_controller(
        self, conn: socket.socket, addr: InetAddress
    ) -> NoneType:
        log(f"handling controller at address {addr[0]}:{addr[1]}")

        MAX_MESSAGE_LENGTH = len(b"migrate XXX.XXX.XXX.XXX")
        msg = b""
        with conn:
            while data := conn.recv(MAX_MESSAGE_LENGTH - len(msg)):
                msg += data

        command, *args = msg.split()
        match command, args:
            case b"migrate", [arg, _, *_]:
                log("too many arguments given in migrate command")
            case b"migrate", [arg, *_]:  # todo check if it's an ip address
                self.migration_event.set(arg)
            case b"migrate", []:
                log("no argument given in migrate command")
            case _:
                log(f"unrecognized command received: {command}")

    def talk_to_clients(self) -> NoReturn:
        with socket.create_server(
            ("0.0.0.0", CLIENT_MIGRATION_PORT)
        ) as listen_sock:
            listen_sock.listen(5)
            while True:
                self.handle_client(*listen_sock.accept())

    def talk_to_controller(self) -> NoReturn:
        with socket.create_server(
            ("0.0.0.0", CONTROLLER_MIGRATION_PORT)
        ) as listen_sock:
            listen_sock.listen(5)
            while True:
                self.handle_controller(*listen_sock.accept())

    def run(self) -> NoneType:
        threading.Thread(target=self.talk_to_clients).start()
        threading.Thread(target=self.talk_to_controller).start()


if __name__ == "__main__":
    ServerManager().run()
