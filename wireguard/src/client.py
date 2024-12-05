import socket
import threading
from settings import *
from utils import *
import subprocess
from time import sleep, time
from struct import unpack
from logger import log
import sys
import requests
import re


class MigrationHandler(threading.Thread):
    def __init__(self, listen_endpoint: tuple):
        threading.Thread.__init__(self)
        self.listen_endpoint = listen_endpoint

    def run(self):
        log(
            f"==== client migration handler listening on {self.listen_endpoint[0]}:{self.listen_endpoint[1]}"
        )
        dock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        dock_socket.bind((self.listen_endpoint[0], self.listen_endpoint[1]))
        dock_socket.listen(5)

        while True:
            mig_socket, mig_address = dock_socket.accept()
            print(
                f"==== migration request from {mig_address}:{self.listen_endpoint[1]}"
            )
            start_time = time()

            data = mig_socket.recv(1024)
            log(f"migration info: {data}")
            new_endpoint = data.decode()
            new_endpoint_address, new_endpoint_port = new_endpoint.split(":")
            new_endpoint_port = int(new_endpoint_port)

            with open(WIREGUARD_CONFIG_LOCATION, "rb") as f:
                old_config = f.read()

            splitted_config = old_config.decode().split("Peer")
            lines_in_peer = splitted_config[1].split("\n")
            for i in range(len(lines_in_peer)):
                line = lines_in_peer[i]
                if "PublicKey" in line:
                    pass
                    # NOTE: We can add public key replacement here as well.
                if "Endpoint" in line:
                    splitted_line = line.split("=")
                    splitted_line[1] = new_endpoint
                    lines_in_peer[i] = "= ".join(splitted_line)
            new_config = "Peer".join([splitted_config[0], "\n".join(lines_in_peer)])
            with open(WIREGUARD_CONFIG_LOCATION, "w") as f:
                f.write(new_config)

            # subprocess.run(f'wg syncconf {WIREGUARD_INTERFACE_NAME} <(wg-quick strip {WIREGUARD_INTERFACE_NAME})', shell=True)
            subprocess.run(f"wg-quick down wg0", shell=True)
            subprocess.run(f"wg-quick up wg0", shell=True)
            global client_socket, host, port
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.connect((host, port))
            log(f"Connected to {new_endpoint_address}:{new_endpoint_port}")
            # with open(MIGRATION_DURATION_LOG_PATH, 'a+') as f:
            #     f.write(str(time() - start_time))
            #     f.write('\n')
            # url = f'http://{CONTROLLER_IP_ADDRESS}:8000/assignments/postavgclient'
            # data = {"avg": time() - start_time}
            # response = requests.post(url, json=data)


def tcp_client(host, port):
    try:
        global client_socket
        client_socket.connect((host, port))
        log(f"Connected to {host}:{port}")

        while True:
            message = input("Enter a message (or 'exit' to quit): ")
            if message.lower() == "exit":
                break

            client_socket.send(message.encode("utf-8"))

            data = client_socket.recv(1024)
            log(f"Received from server: {data.decode('utf-8')}")

    except ConnectionRefusedError:
        log("Connection to the server failed. Make sure the server is running.")

    finally:
        client_socket.close()
        log("Connection closed.")

def get_and_set_wireguard_ip():
    try:
        response = requests.get(f'http://{CONTROLLER_IP_ADDRESS}:8000/assignments/getnew')
        if response.status_code == 200:
            wireguard_ip = response.json()['wireguard_ip']
            
            # Read current config
            with open(WIREGUARD_CONFIG_LOCATION, 'r') as f:
                config = f.read()
            
            # Replace or add Address line
            if 'Address' in config:
                config = re.sub(r'Address = .*', f'Address = {wireguard_ip}/32', config)
            else:
                # Add after [Interface] section
                config = config.replace('[Interface]', f'[Interface]\nAddress = {wireguard_ip}/32')
            
            # Write updated config
            with open(WIREGUARD_CONFIG_LOCATION, 'w') as f:
                f.write(config)
            
            # Restart WireGuard interface
            subprocess.run("wg-quick down wg0", shell=True)
            subprocess.run("wg-quick up wg0", shell=True)
            
            log(f"Successfully set WireGuard IP to {wireguard_ip}")
            return wireguard_ip
        else:
            log(f"Failed to get WireGuard IP: {response.text}")
            return None
    except Exception as e:
        log(f"Error getting/setting WireGuard IP: {e}")
        return None

def efficacy_test_bulk_download(host, port, migration, test_duration=300):
    global client_socket
    client_socket.connect((host, port))
    log(f"Connected to {host}:{port}")
    start_time = time()
    measure_thread = TrafficGetterThread(start_time=start_time, duration=300)
    measure_thread.start()
    measure_thread_2 = TrafficMeasurementPythonThread(
        start_time=start_time, duration=test_duration
    )
    measure_thread_2.start()
    # if migration:
    #     testing_migration_senderr = TestingMigrationSenderThread(start_time=start_time, duration=test_duration)
    #     testing_migration_senderr.start()
    i = 0
    amount_of_data_gathered = 0
    while time() - start_time < test_duration:
        try:
            while time() - start_time < test_duration:
                message = f"BEEGMode {amount_of_data_gathered}"
                client_socket.send(message.encode("utf-8"))
                bs = client_socket.recv(8)
                (length,) = unpack(">Q", bs)
                data = b""
                while len(data) < length:
                    to_read = length - len(data)
                    client_socket.settimeout(0.2)
                    new_data = client_socket.recv(4096 if to_read > 4096 else to_read)
                    data += new_data
                    amount_of_data_gathered += len(new_data)

                    if time() - start_time > i * 20:
                        log(f"here at {20*i}s, got {len(data)}data", pr=True)
                        i += 1
                # Note: We might have to add this back later
                # sleep(0.1)
        except ConnectionRefusedError:
            log("Connection to the server failed. Make sure the server is running.")

        except ConnectionResetError:
            log("migrating...")

        except Exception as e:
            log("the pipe is not ready yet, sleeping for 0.01 sec")
            log(f"error: {e}")
            sleep(0.01)
    log(f"test is done, total time was: {time() - start_time} secs")


def efficacy_test_wikipedia(host, port, migration, test_duration=999999):
    last_ack = -1
    global client_socket
    client_socket.connect((host, port))
    log(f"Connected to {host}:{port}")
    start_time = time()
    measure_thread = TrafficGetterThread(start_time=start_time, duration=test_duration)
    measure_thread.start()
    measure_thread_2 = TrafficMeasurementPythonThread(
        start_time=start_time, duration=test_duration
    )
    measure_thread_2.start()
    # if migration:
    #     testing_migration_senderr = TestingMigrationSenderThread(
    #         start_time=start_time, duration=test_duration
    #     )
    #     testing_migration_senderr.start()
    i = 0
    while time() - start_time < test_duration:
        try:
            while time() - start_time < test_duration:
                message = "https://www.wikipedia.org/"
                client_socket.send(message.encode("utf-8"))
                bs = client_socket.recv(8)
                (length,) = unpack(">Q", bs)
                data = b""
                while len(data) < length:
                    to_read = length - len(data)
                    new_data = client_socket.recv(4096 if to_read > 4096 else to_read)
                    data += new_data

                    if time() - start_time > i * 20:
                        log(f"here at {20*i}s, got {len(data)}data", pr=True)
                        i += 1

                sleep(0.1)
        except ConnectionRefusedError:
            log("Connection to the server failed. Make sure the server is running.")

        except ConnectionResetError:
            log("migrating...")

        except Exception as e:
            log("the pipe is not ready yet, sleeping for 0.01 sec")
            log(f"error: {e}")
            sleep(0.01)
    log(f"test is done, total time was: {time() - start_time} secs", pr=True)


def efficacy_test_kv_store(host, port, migration, test_duration=300):
    last_ack = -1
    global client_socket
    client_socket.connect((host, port))
    log(f"Connected to {host}:{port}")
    start_time = time()
    measure_thread = TrafficGetterThread(start_time=start_time, duration=test_duration)
    measure_thread.start()
    measure_thread_2 = TrafficMeasurementPythonThread(
        start_time=start_time, duration=test_duration
    )
    measure_thread_2.start()
    # if migration:
    #     testing_migration_senderr = TestingMigrationSenderThread(start_time=start_time, duration=test_duration)
    #     testing_migration_senderr.start()
    i = 0
    while time() - start_time < test_duration:
        try:
            while time() - start_time < test_duration:
                message = "GET testing_key"
                client_socket.send(message.encode("utf-8"))
                bs = client_socket.recv(8)
                (length,) = unpack(">Q", bs)
                data = b""
                while len(data) < length:
                    to_read = length - len(data)
                    new_data = client_socket.recv(4096 if to_read > 4096 else to_read)
                    data += new_data
                    if time() - start_time > i * 20:
                        log(f"here at {20*i}s, got {len(data)}data", pr=True)
                        i += 1

                sleep(0.1)
        except ConnectionRefusedError:
            log("Connection to the server failed. Make sure the server is running.")

        except ConnectionResetError:
            log("migrating...")

        except Exception as e:
            log("the pipe is not ready yet, sleeping for 0.01 sec")
            log(f"error: {e}")
            sleep(0.01)
    log(f"test is done, total time was: {time() - start_time} secs", pr=True)


def mass_test_simple_client(host, port, test_duration=1500):
    last_ack = -1
    global client_socket
    print(f"trying to connect to ({host}, {port})")
    client_socket.connect((host, port))
    log(f"Connected to {host}:{port}", pr=True)
    start_time = time()
    # testing_data_sender = TestingDataSenderThread(start_time=start_time, duration=test_duration)
    # testing_data_sender.start()
    i = 0
    while time() - start_time < test_duration:
        try:
            while time() - start_time < test_duration:
                message = "https://www.wikipedia.org/"
                client_socket.send(message.encode("utf-8"))
                bs = client_socket.recv(8)
                (length,) = unpack(">Q", bs)
                data = b""
                while len(data) < length:
                    to_read = length - len(data)
                    new_data = client_socket.recv(4096 if to_read > 4096 else to_read)
                    data += new_data

                    if time() - start_time > i * 20:
                        log(f"here at {20*i}s, got {len(data)}data", pr=True)
                        i += 1

                sleep(0.5)
        except ConnectionRefusedError:
            log("Connection to the server failed. Make sure the server is running.")

        except ConnectionResetError:
            log("migrating...")

        except Exception as e:
            log("the pipe is not ready yet, sleeping for 0.01 sec")
            log(f"error: {e}")
            sleep(0.01)
    log(f"test is done, total time was: {time() - start_time} secs")
    sleep(10)


if __name__ == "__main__":
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    host = "10.27.0.20"
    port = 8088
    if len(sys.argv) > 1:
        my_id = int(sys.argv[1])
        num1 = my_id // 200
        num2 = (my_id % 200) + 22
        my_ip = f"10.27.{num1}.{num2}"
        migration_endpoint = (my_ip, 8089)
        handler = MigrationHandler(listen_endpoint=migration_endpoint)
        handler.start()
        mass_test_simple_client(host, port)
    else:
        migration_endpoint = ("10.27.0.2", 8089)
        handler = MigrationHandler(listen_endpoint=migration_endpoint)
        handler.start()
        client_socket.connect((host, port))
        log(f"Connected to {host}:{port}")
        while True:
            url = input("Enter a URL to browse (or 'exit' to quit): ")
            if url.lower() == 'exit':
                break
            result = browse_url(url)
            if result:
                print(f"Received content from {url}:\n{result[:500]}...")
        client_socket.close()
        #efficacy_test_wikipedia(host, port, migration=True)
        # NOTE: Code for all the previous tests
        # choice = input(
        #     "the format is False: no mig - True: with mig. \n0 and 1 for wiki, 2 and 3 for bulk, 4 and 5 for kv.\nstart? "
        # ).strip()
        # if choice == "0":
        #     efficacy_test_wikipedia(host, port, migration=False)
        # elif choice == "1":
        #     efficacy_test_wikipedia(host, port, migration=True)
        # elif choice == "2":
        #     efficacy_test_bulk_download(host, port, migration=False)
        # elif choice == "3":
        #     efficacy_test_bulk_download(host, port, migration=True)
        # elif choice == "4":
        #     efficacy_test_kv_store(host, port, migration=False)
        # elif choice == "5":
        #     efficacy_test_kv_store(host, port, migration=True)
        # else:
        #     tcp_client(host, port)
