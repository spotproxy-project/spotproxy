import threading
import socket
import subprocess
from settings import WIREGUARD_CONFIG_LOCATION
import psutil
from time import sleep
import json
from logger import log
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    stream=sys.stdout
)

client_addresses = []
client_sockets = []
nat_sockets = []


class ForwardThread(threading.Thread):
    def __init__(
        self,
        source_socket: socket.socket,
        destination_socket: socket.socket,
        description: str,
    ):
        threading.Thread.__init__(self)
        self.source_socket = source_socket
        self.destination_socket = destination_socket
        self.description = description

    def run(self):
        data = " "
        try:
            while data:
                data = self.source_socket.recv(1024)
                if data:
                    self.destination_socket.sendall(data)
                    request = data.decode('utf-8')
                    if request.startswith('GET') or request.startswith('POST'):
                        website = request.split()[1]
                        client_ip = self.source_socket.getpeername()[0]
                        logging.info(f"Client {client_ip} requested: {website}")
                else:
                    try:
                        self.source_socket.close()
                        self.destination_socket.close()
                    except:
                        # log('connection closed')
                        break
        except:
            # log('connection closed')
            try:
                self.source_socket.close()
            except:
                pass
            try:
                self.destination_socket.close()
            except:
                pass


class ForwardingServerThread(threading.Thread):
    def __init__(self, listen_endpoint: tuple, forward_endpoint: tuple):
        threading.Thread.__init__(self)

        self.listen_endpoint = listen_endpoint
        self.forward_endpoint = forward_endpoint

    def run(self):
        global client_addresses, client_sockets, nat_sockets
        try:
            dock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            dock_socket.bind((self.listen_endpoint[0], self.listen_endpoint[1]))
            dock_socket.listen(5)
            while True:
                client_socket, client_address = dock_socket.accept()
                if client_address not in client_addresses:
                    client_addresses.append(client_address)
                    client_sockets.append(client_socket)
                    logging.info(f"New client connected: {client_address[0]}:{client_address[1]}")

                if len(client_addresses) % 10 == 0:
                    print(len(client_addresses))
                    logging.info(f"Total clients connected: {len(client_addresses)}")
                nat_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                nat_socket.connect((self.forward_endpoint[0], self.forward_endpoint[1]))
                nat_sockets.append(nat_socket)
                way1 = ForwardThread(client_socket, nat_socket, "client -> server")
                way2 = ForwardThread(nat_socket, client_socket, "server -> client")
                way1.start()
                way2.start()
        except Exception as e:
            print("ERROR: a fatal error has happened")
            print(str(e))


class MigratingAgent(threading.Thread):
    def __init__(self, client_socket: socket.socket):
        threading.Thread.__init__(self)
        self.client_socket = client_socket

    def run(self):
        data = " "
        full_file_data = b""
        # log(f"==== recieving migration data")
        while data:
            data = self.client_socket.recv(1024)
            if data:
                full_file_data += data
            else:
                self.client_socket.shutdown(socket.SHUT_RD)
                break
        migration_string = full_file_data.decode()
        peers = migration_string.split("Peer")
        if len(peers) == 1:
            # log("ERROR: Migrated data was empty!")
            return
        peers = peers[1:]

        # Update wireguard w0
        for peer in peers:
            lines_in_peer = peer.split("\n")
            public_key = ""
            allowed_ips = ""
            for line in lines_in_peer:
                if "PublicKey" in line:
                    public_key = line[line.find("=") + 1 :].strip()
                if "AllowedIPs" in line:
                    allowed_ips = line[line.find("=") + 1 :].strip()

            subprocess.run(
                f'wg set wg0 peer "{public_key}" allowed-ips {allowed_ips}', shell=True
            )
            subprocess.run(f"ip -4 route add {allowed_ips} dev wg0", shell=True)

        # Update config file
        new_peers = ["["]
        new_peers.extend(peers)
        new_peers_string = "\n" + "Peer".join(new_peers)
        with open(WIREGUARD_CONFIG_LOCATION, "a") as f:
            f.write(new_peers_string)
        # log("SUCCESS: updated config file")


class MigrationHandler(threading.Thread):
    def __init__(self, listen_endpoint: tuple):
        threading.Thread.__init__(self)
        self.listen_endpoint = listen_endpoint

    def run(self):
        try:
            # log(f"==== migration handler listening on {self.listen_endpoint[0]}:{self.listen_endpoint[1]}")
            dock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            dock_socket.bind((self.listen_endpoint[0], self.listen_endpoint[1]))
            dock_socket.listen(5)

            while True:
                client_socket, client_address = dock_socket.accept()
                # log(f"==== migration request from {client_address}:{self.listen_endpoint[1]}")
                agent = MigratingAgent(client_socket)
                agent.start()
        finally:
            dock_socket.close()
            new_server = MigrationHandler(self.listen_endpoint)
            new_server.start()


def calculate_network_throughput(interval=0.01):
    net_io_before = psutil.net_io_counters()
    sleep(interval)
    net_io_after = psutil.net_io_counters()
    sent_throughput = (net_io_after.bytes_sent - net_io_before.bytes_sent) / interval

    return sent_throughput


class PollingHandler(threading.Thread):
    def __init__(self, listen_endpoint: tuple):
        threading.Thread.__init__(self)
        self.listen_endpoint = listen_endpoint

    def run(self):
        try:
            # log(f"==== polling handler listening on {self.listen_endpoint[0]}:{self.listen_endpoint[1]}")
            dock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            dock_socket.bind((self.listen_endpoint[0], self.listen_endpoint[1]))
            dock_socket.listen(5)

            while True:
                poller_socket, poller_address = dock_socket.accept()
                data = poller_socket.recv(1024)

                cpu_utilization = psutil.cpu_percent(interval=0.01)
                throughput = calculate_network_throughput()
                report = {}
                report["utility"] = cpu_utilization
                report["throughput"] = throughput
                report["connected_clients"] = client_addresses

                message_to_send = json.dumps(report)
                poller_socket.sendall(message_to_send.encode())
                poller_socket.close()
                logging.info(f"Polling report: CPU: {cpu_utilization}%, Throughput: {throughput}, Clients: {len(client_addresses)}")

        except Exception as e:
            logging.error(f"Error in PollingHandler: {str(e)}")

        finally:
            dock_socket.close()
            new_server = PollingHandler(self.listen_endpoint)
            new_server.start()
