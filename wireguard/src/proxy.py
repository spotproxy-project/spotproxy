from server_threads import *
from settings import *
import requests
from logger import log
from time import time


def get_public_ip():
    try:
        response = requests.get("https://httpbin.org/ip")
        if response.status_code == 200:
            public_ip = response.json()["origin"]
            return public_ip
        else:
            # log(f"Failed to retrieve public IP. Status code: {response.status_code}")
            pass

    except requests.RequestException as e:
        # log(f"Request error: {e}")
        pass

    return None


def check_connectivity():
    while True:
        try:
            nat_result = subprocess.run(["ping", "-c", "1", "172.31.41.62"], capture_output=True, text=True)
            if nat_result.returncode == 0:
                logging.info("Connectivity to NAT VM: OK")
            else:
                logging.warning(f"Cannot reach NAT VM: {nat_result.stderr}")

            internet_result = subprocess.run(["ping", "-c", "1", "8.8.8.8"], capture_output=True, text=True)
            if internet_result.returncode == 0:
                logging.info("Internet connectivity: OK")
            else:
                logging.warning(f"Cannot reach internet: {internet_result.stderr}")
        except Exception as e:
            logging.error(f"Error checking connectivity: {e}")
        sleep(60)

class Proxy:
    def __init__(
        self,
        wireguard_interface,
        wireguard_endpoint,
        nat_endpoint,
        broker_endpoint,
        migration_endpoint,
        polling_endpoint,
    ) -> None:
        """
        endpoints are tuples of: (address, port)
        """
        self.my_number = int(socket.gethostbyname(socket.gethostname()).split(".")[-1])
        print(f"hostname(my_number) is: {self.my_number}")
        self.wireguard_endpoint = wireguard_endpoint
        self.nat_endpoint = nat_endpoint
        self.broker_endpoint = broker_endpoint
        self.migration_endpoint = migration_endpoint
        self.polling_endpoint = polling_endpoint
        self.wireguard_interface = wireguard_interface

    def migrate(self, new_proxy_ip):
        start_time = time()
        # migrate address
        global client_addresses, client_sockets, nat_sockets
        with open(WIREGUARD_CONFIG_LOCATION, "rb") as f:
            data = f.read()
        new_proxy_address = new_proxy_ip
        new_proxy_socket = MIGRATION_PORT
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((new_proxy_address, new_proxy_socket))
        s.sendall(data)

        print(f"sending migration notice to {len(client_addresses)} clients")

        for i in range(len(client_addresses)):
            address = client_addresses[i]
            cli_sock = client_sockets[i]
            dest_sock = nat_sockets[i]
            cli_sock.send("bye!".encode())
            cli_sock.close()
            dest_sock.close()
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((address[0], MIGRATION_PORT))
            s.sendall(f"{new_proxy_address}:{WIREGUARD_PORT}".encode())
            s.close()
        print(f"sent to all successfully! GGs.")

        nat_sockets = []
        migration_time = time() - start_time
        # url = f"http://{CONTROLLER_IP_ADDRESS}:8000/assignments/postavgproxy"

        data = {"avg": migration_time}

        # response = requests.post(url, json=data)

        # if response.status_code == 200:
        #     print(f'sent data successfully. val was: {migration_time}. Done here')

    def run(self):
        ip = get_public_ip()
        print(f"my endpoint is: {ip}:51820")

        connectivity_thread = threading.Thread(target=check_connectivity, daemon=True)
        connectivity_thread.start()
        forwarding_server = ForwardingServerThread(
            ip,self.wireguard_interface, self.nat_endpoint
        )
        migration_handler = MigrationHandler(self.migration_endpoint)
        polling_handler = PollingHandler(self.polling_endpoint)
        polling_handler.start()
        migration_handler.start()
        forwarding_server.start()

        dock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        dock_socket.bind((self.broker_endpoint[0], self.broker_endpoint[1]))
        dock_socket.listen(5)

        while True:
            broker_socket, broker_address = dock_socket.accept()
            
            data = broker_socket.recv(1024)

            print(f'INFO: got message from {broker_address}: {data.decode()}')

            command = data.decode().strip().lower().split()
            broker_socket.close()

            if command[0] == "migrate":
                if len(command) > 1:
                    self.migrate(command[1])
                else:
                    self.migrate(f"172.17.0.{self.my_number + 1}")
            else:
                print('ERROR: Unknown command. Ignoring...')
