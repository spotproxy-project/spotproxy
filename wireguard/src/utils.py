import subprocess
import threading
import socket
import psutil
import requests
from time import time, sleep

from settings import *
from logger import log


def run_script_in_background(script_path="../scripts/measure.sh"):
    try:
        process = subprocess.Popen(["bash", script_path])

        log(f"Shell script '{script_path}' is running in the background.")
        return process
    except Exception as e:
        log(f"Error running the shell script: {e}")
        return None


def get_traffic(interface):
    command = ["bash", "../scripts/get_traffic.sh", interface]
    result = subprocess.run(command, capture_output=True, text=True)
    return result.stdout.strip()


def get_traffic_python(interface):
    initial_stats = psutil.net_io_counters(pernic=True)[interface]
    sleep(1)  # Wait for 1 second
    # Get the current network statistics after 1 second
    current_stats = psutil.net_io_counters(pernic=True)[interface]

    # Calculate throughput in bytes per second
    bytes_per_second_in = current_stats.bytes_recv - initial_stats.bytes_recv
    bytes_per_second_out = current_stats.bytes_sent - initial_stats.bytes_sent
    return bytes_per_second_in, bytes_per_second_out


class TrafficGetterThread(threading.Thread):
    def __init__(self, start_time, duration):
        threading.Thread.__init__(self)
        self.start_time = start_time
        self.duration = duration

    def run(self):
        interface = "wg0"
        initial = get_traffic(interface)
        initial_arr = initial.split()
        initial_rx = int(initial_arr[1])

        with open("throughput.txt", "w"):
            pass

        right_now = time() - self.start_time
        while right_now < self.duration:
            try:
                current = get_traffic(interface)
                current_arr = current.split()
                current_rx = int(current_arr[1])
                if current_rx == 0:
                    print("this thing was zero!")
            except:
                sleep(0.01)
                log("traffic getter sensed migration...")
                continue

            with open("throughput.txt", "a") as file:
                file.write(str(current_rx - initial_rx) + "\n")

            initial_rx = current_rx
            right_now = time() - self.start_time
            sleep(1)
        log("traffic collection thread finished!")


class TrafficMeasurementPythonThread(threading.Thread):
    def __init__(self, start_time, duration):
        threading.Thread.__init__(self)
        self.start_time = start_time
        self.duration = duration

    def run(self):
        interface = "wg0"

        with open("throughput_p_i.txt", "w"):
            pass

        with open("throughput_p_o.txt", "w"):
            pass

        # old_stats = psutil.net_io_counters(pernic=True)[interface]
        # right_now = time() - self.start_time

        # while right_now < self.duration:
        #     sleep(1)
        #     current_stats = psutil.net_io_counters(pernic=True)[interface]

        #     bytes_per_second_in = current_stats.bytes_recv - old_stats.bytes_recv
        #     bytes_per_second_out = current_stats.bytes_sent - old_stats.bytes_sent

        #     with open("throughput_p_i.txt", "a") as file:
        #         file.write(str(bytes_per_second_in) + "\n")

        #     with open("throughput_p_o.txt", "a") as file:
        #         file.write(str(bytes_per_second_out) + "\n")

        #     old_stats = current_stats
        #     right_now = time() - self.start_time

        old_stats = psutil.net_io_counters(pernic=True)[interface]

        while time() - self.start_time < self.duration:
            try:
                current_stats = psutil.net_io_counters(pernic=True)[interface]
            except:
                sleep(0.01)
                continue
            bytes_per_second_in = current_stats.bytes_recv - old_stats.bytes_recv
            bytes_per_second_out = current_stats.bytes_sent - old_stats.bytes_sent

            with open("throughput_p_i.txt", "a") as file:
                file.write(str(bytes_per_second_in) + "\n")

            with open("throughput_p_o.txt", "a") as file:
                file.write(str(bytes_per_second_out) + "\n")

            old_stats = current_stats
            sleep(1)

        log("python-based traffic collection thread finished!", pr=True)


class TestingMigrationSenderThread(threading.Thread):
    def __init__(self, start_time, duration):
        threading.Thread.__init__(self)
        self.start_time = start_time
        self.duration = duration

    def run(self):
        log(f"==== test migration sender running...")
        counters = [0] * len(TESTING_MIGRATION_TIMES)
        is_done = 0
        while True:
            right_now = time() - self.start_time

            for i in range(len(TESTING_MIGRATION_TIMES) - 1, -1, -1):
                if TESTING_MIGRATION_TIMES[i] < right_now and counters[i] == 0:
                    # TESTING_MIGRATION_DESTS
                    log(f"sending to {i} to migrate to {i+1}")
                    ip_src = TESTING_MIGRATION_DESTS[i]
                    ip_dest = TESTING_MIGRATION_DESTS[i + 1]

                    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    client_socket.connect((ip_src, BROKER_PORT))

                    message = f"migrate {ip_dest}"
                    client_socket.send(message.encode("utf-8"))
                    client_socket.close()

                    counters[i] = 1
                    is_done += 1
            if is_done == len(TESTING_MIGRATION_TIMES):
                break
        log("migration work is done.")


class TestingDataSenderThread(threading.Thread):
    def __init__(self, start_time, duration):
        threading.Thread.__init__(self)
        self.start_time = start_time
        self.duration = duration

    def run(self):
        right_now = time() - self.start_time
        while right_now < self.duration + 1:
            right_now = time() - self.start_time
            sleep(1)

        log("test should be done.")
        with open(MIGRATION_DURATION_LOG_PATH) as f:
            lines = f.readlines()

        sum = 0
        count = 0
        for line in lines:
            if not line.strip():
                break
            sum += float(line.strip())
            count += 1
        avg_mig_time = sum / count

        url = f"http://{CONTROLLER_IP_ADDRESS}:8000/assignments/postavgclient"

        data = {"avg": avg_mig_time}

        response = requests.post(url, json=data)

        if response.status_code == 200:
            log("sent data successfully. Done here", pr=True)
