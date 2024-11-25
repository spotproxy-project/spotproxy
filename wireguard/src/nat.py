import socket
import os
import requests

from nat_threads import EchoThread, NATThread, KVThread, BEEGThread


def echo_server(host, port):
    nat_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    nat_socket.bind((host, port))
    nat_socket.listen(5)

    print("yes")

    while True:
        client_socket, client_address = nat_socket.accept()
        print(f"Accepted connection from {client_address}")

        thr = EchoThread(client_socket, client_address)
        thr.start()


def nat_server(host, port):
    nat_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    nat_socket.bind((host, port))
    nat_socket.listen(5)

    print("yes")

    while True:
        client_socket, client_address = nat_socket.accept()
        print(f"Accepted connection from {client_address}")

        thr = NATThread(client_socket, client_address)
        thr.start()


def nat_server_with_bulk_downloads(host, port, beeg_file_path):
    nat_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    nat_socket.bind((host, port))
    nat_socket.listen(5)

    print("going beeg")

    while True:
        client_socket, client_address = nat_socket.accept()
        print(f"Accepted connection from {client_address}")

        thr = BEEGThread(client_socket, client_address, beeg_file_path)
        thr.start()


def nat_server_with_kv_store(host, port):
    nat_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    nat_socket.bind((host, port))
    nat_socket.listen(5)

    print("going kv")

    while True:
        client_socket, client_address = nat_socket.accept()
        print(f"Accepted connection from {client_address}")

        thr = KVThread(client_socket, client_address)
        thr.start()


def get_public_ip():
    try:
        response = requests.get("https://httpbin.org/ip")

        if response.status_code == 200:
            public_ip = response.json()["origin"]
            return public_ip
        else:
            print(
                f"Failed to retrieve public IP. Status code: {response.status_code}"
            )

    except requests.RequestException as e:
        print(f"Request error: {e}")

    return None


if __name__ == "__main__":
    host = "0.0.0.0"
    port = 8000
    beeg_file_path = "random.img"
    print(os.path.exists(beeg_file_path))
    pub_ip = get_public_ip()
    print(f"Nat server is listening on {pub_ip}:{port}")

    choice = int(
        input(
            "input 0 for echo, 1 for NAT server, 2 for beeg file, 3 for kv: "
        ).strip()
    )

    if choice == 0:
        print("echo server...", end=" ")
        echo_server(host, port)
    elif choice == 1:
        print("nat server...", end=" ")
        nat_server(host, port)
    elif choice == 2:
        print("beeg server...", end=" ")
        nat_server_with_bulk_downloads(host, port, beeg_file_path)
    elif choice == 3:
        print("kv server...", end=" ")
        nat_server_with_kv_store(host, port)
    else:
        print("incorrect choice!")
