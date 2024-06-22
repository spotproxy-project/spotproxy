import threading
from struct import pack
import socket
import requests
import os
from time import time
import redis


def get_public_ip():
    try:
        response = requests.get("https://httpbin.org/ip")

        if response.status_code == 200:
            public_ip = response.json()["origin"]
            return public_ip
        else:
            print(f"Failed to retrieve public IP. Status code: {response.status_code}")

    except requests.RequestException as e:
        print(f"Request error: {e}")

    return None


class EchoThread(threading.Thread):
    def __init__(self, client_socket: socket.socket, client_address: str):
        threading.Thread.__init__(self)
        self.client_socket = client_socket
        self.client_address = client_address

    def run(self):
        data = self.client_socket.recv(1024)
        while data:
            self.client_socket.send(data)
            data = self.client_socket.recv(1024)

        print(f"Connection from {self.client_address} closed.")
        self.client_socket.close()


class NATThread(threading.Thread):
    def __init__(self, client_socket: socket.socket, client_address: str):
        threading.Thread.__init__(self)
        self.client_socket = client_socket
        self.client_address = client_address

    def run(self):
        data = self.client_socket.recv(1024)
        while data:
            url = data.decode()
            response = requests.get(url)
            message = response.text.encode()
            length = pack(">Q", len(message))

            self.client_socket.sendall(length)
            self.client_socket.sendall(message)

            data = self.client_socket.recv(1024)
        self.client_socket.close()


class BEEGThread(threading.Thread):
    def __init__(
        self, client_socket: socket.socket, client_address: str, beeg_file_path
    ):
        threading.Thread.__init__(self)
        self.client_socket = client_socket
        self.client_address = client_address
        self.beeg_file_path = beeg_file_path

    def run(self):
        beeg_file_size = os.path.getsize(self.beeg_file_path)
        chunk_size = int(0.5 * (10**6))  # request sizes
        data = self.client_socket.recv(1024)
        start_time = time()
        i = 0
        while data:
            client_request = data.decode().split()
            if len(client_request) < 2:
                print("wierd request, skipping...")
                break
            try:
                client_loc = int(client_request[1]) % beeg_file_size
            except:
                print("client request was jibberish")
                break

            with open(self.beeg_file_path, "rb") as f:
                f.seek(client_loc)
                data = f.read(chunk_size)

            length = pack(">Q", len(data))

            self.client_socket.sendall(length)
            self.client_socket.sendall(data)
            # if time() - start_time > i * 5:
            #     print(f'{int(time() - start_time)}s:send {len(data)} size file')
            #     i += 1

            data = self.client_socket.recv(1024)
        self.client_socket.close()


class KVThread(threading.Thread):
    def __init__(self, client_socket: socket.socket, client_address: str):
        threading.Thread.__init__(self)
        self.client_socket = client_socket
        self.client_address = client_address

    def run(self):
        key = "testing_key"
        redis_client = redis.StrictRedis(
            host="3.80.71.88", port=6379, password="foobared", decode_responses=True
        )
        redis_client.set(
            key,
            "0833a59570177bc10f98bcfcd24e2c977c33262125319d44ff88fa42cb83534eabfc9ea63e8d7f324d3331af204ff00410cc5d77a3a494c64b2e59290960c2ddeab78525d8a3af9204d8fde813affbaf",
        )
        data = self.client_socket.recv(1024)
        start_time = time()
        i = 0
        while data:
            client_request = data.decode()
            data = redis_client.get(key).encode()

            length = pack(">Q", len(data))

            self.client_socket.sendall(length)
            self.client_socket.sendall(data)
            # if time() - start_time > i * 2:
            #     print(f'{int(time() - start_time)}s:send {len(data)} size file')
            #     i += 1

            data = self.client_socket.recv(1024)
        self.client_socket.close()
