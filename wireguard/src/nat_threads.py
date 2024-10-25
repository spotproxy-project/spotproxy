import threading
from struct import pack
import socket
import struct
import requests
import sys
import os
from scapy.all import IP, Raw
from time import time
import redis
import logging


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    stream=sys.stdout
)

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
        self.running = True


    def receive_pkt(self):
        try:
            data_len = self.client_socket.recv(4)
            if not data_len or len(data_len) != 4:
                logging.info(f"Got {data_len} instead of 4")
                return None

            pkt_len = struct.unpack('>I', data_len)[0]
            logging.info(f"Expecting packet of length: {pkt_len}")
            pkt_data = bytearray()
            while len(pkt_data) < pkt_len:
                part = self.client_socket.recv(pkt_len - len(pkt_data))
                if not part:
                    return None
                pkt_data.extend(part)
                
            return pkt_data
        except Exception as e:
            logging.error(f"Error receiving packet: {e}")
            return None

    def send_response(self, response_data: bytes):
        data_len = len(response_data)
        buffer = bytearray(4 + data_len)

        # Pack length and data
        struct.pack_into('>I', buffer, 0, data_len)
        buffer[4:] = response_data

        try:
            self.client_socket.sendall(buffer)
            logging.info(f"Sent response: {data_len} bytes")
        except Exception as e:
            logging.error(f"Error sending response: {e}") 


    def process_packet(self, packet_data):
        try:
            # Parse the original packet
            original_packet = IP(packet_data)
            logging.info(f"Processing packet: {original_packet.summary()}")

            response_packet = IP(
                src=original_packet[IP].dst,
                dst=original_packet[IP].src,
                proto=original_packet[IP].proto
            )

            response_packet = response_packet/Raw(load=bytes(original_packet[IP].payload))

            return bytes(response_packet)
            
        except Exception as e:
            logging.error(f"Error processing packet: {e}")
            return None


    def run(self):
        logging.info(f"Started handling connection from {self.client_address}")
        
        while self.running:
            try:
                packet_data = self.receive_pkt()
                if not packet_data:
                    logging.info("Connection closed by client")
                    break

                logging.info(f"Received packet: {len(packet_data)} bytes")
                
                # Process the packet
                response_data = self.process_packet(packet_data)
                if response_data:
                    self.send_response(response_data)
                
            except Exception as e:
                logging.error(f"Error in processing: {e}")
                break

        self.client_socket.close()
        logging.info(f"Closed connection from {self.client_address}")


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
