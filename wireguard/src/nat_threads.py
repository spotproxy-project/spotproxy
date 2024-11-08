import threading
from typing import Optional
from struct import pack
import socket
import struct
import requests
import sys
import os
from scapy.all import Raw, IP, DNS, TCP, UDP
from scapy.layers.inet import ICMP
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
        self.udp_sockets = {} # (dst_ip, dst_port) -> socket

    def get_udp_socket(self, dst_ip: str, dst_port: int) -> socket.socket:
        """Create or get existing UDP socket for destination"""
        key = (dst_ip, dst_port)
        if key not in self.udp_sockets:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_sockets[key] = sock
        return self.udp_sockets[key]


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


    def handle_tcp_pkt(self, pkt: IP) -> Optional[bytes]:
        """Handle TCP packets"""
        try:
            tcp_layer = pkt[TCP]
            dst_ip = pkt[IP].dst
            dst_port = tcp_layer.dport
            payload = bytes(tcp_layer.payload)

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)  # 10 second timeout
            sock.connect((dst_ip, dst_port))

            if payload:
                sock.send(payload)

            response = sock.recv(65535)
            sock.close()

            response_packet = IP(
                src=pkt[IP].dst,
                dst=pkt[IP].src,
                proto=pkt[IP].proto
            )/TCP(
                sport=tcp_layer.dport,
                dport=tcp_layer.sport,
                flags='A'  # ACK flag
            )/Raw(load=response)

            return bytes(response_packet)

        except Exception as e:
            logging.error(f"Error handling TCP packet: {e}")
            return None

    def handle_udp_pkt(self, packet: IP) -> Optional[bytes]:
        """Handle UDP packets"""
        try:
            udp_layer = packet[UDP]
            dst_ip = packet[IP].dst
            dst_port = udp_layer.dport
            payload = bytes(udp_layer.payload)

            # Get or create UDP socket
            sock = self.get_udp_socket(dst_ip, dst_port)
            sock.settimeout(5)

            # Send the payload
            sock.sendto(payload, (dst_ip, dst_port))

            # Receive response
            response, _ = sock.recvfrom(65535)

            # Special handling for DNS packets
            if dst_port == 53 and DNS in packet:
                response_packet = IP(
                    src=packet[IP].dst,
                    dst=packet[IP].src
                )/UDP(
                    sport=udp_layer.dport,
                    dport=udp_layer.sport
                )/DNS(response)
            else:
                response_packet = IP(
                    src=packet[IP].dst,
                    dst=packet[IP].src
                )/UDP(
                    sport=udp_layer.dport,
                    dport=udp_layer.sport
                )/Raw(load=response)

            return bytes(response_packet)

        except Exception as e:
            logging.error(f"Error handling UDP packet: {e}")
            return None

    def handle_icmp_pkt(self, packet: IP) -> Optional[bytes]:
        """Handle ICMP packets (like ping)"""
        try:
            dst_ip = packet[IP].dst
            
            # Create raw socket for ICMP
            sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
            sock.settimeout(5)

            # Send the ICMP packet
            sock.sendto(bytes(packet[ICMP]), (dst_ip, 0))

            # Receive response
            response, _ = sock.recvfrom(65535)
            sock.close()

            # Create response packet
            response_packet = IP(
                src=packet[IP].dst,
                dst=packet[IP].src
            )/ICMP(response[20:])  # Skip IP header

            return bytes(response_packet)

        except Exception as e:
            logging.error(f"Error handling ICMP packet: {e}")
            return None

    def process_packet(self, packet_data) -> bytes | None:
        try:
            # Parse the original packet
            original_packet = IP(packet_data)
            logging.info(f"Processing packet: {original_packet.summary()}")

            if TCP in original_packet:
                return self.handle_tcp_pkt(original_packet)
            elif UDP in original_packet:
                return self.handle_udp_pkt(original_packet)
            elif ICMP in original_packet:
                return self.handle_icmp_pkt(original_packet)
            else:
                logging.warning(f"Unsupported protocol: {original_packet.proto}")
                return None

           
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
