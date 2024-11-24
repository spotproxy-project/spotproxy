import threading
from types import NoneType
import socket

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


class ServerManager:
    def __init__(self) -> NoneType:
        self.relocation_event = Event[bytes]()

    def handle_client(self, conn: socket.socket, addr: InetAddress) -> NoneType:
        print(f"handling client at address {addr[0]}:{addr[1]}")
        with conn:
            conn.sendall(self.relocation_event.wait())

    def handle_controller(
        self, conn: socket.socket, addr: InetAddress
    ) -> NoneType:
        print(f"handling controller at address {addr[0]}:{addr[1]}")
        msg = conn.recv(12, socket.MSG_WAITALL)
        self.relocation_event.set(msg)

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
