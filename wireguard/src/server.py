from proxy import Proxy
import subprocess
from settings import *
import sys
from logger import log
import logging

nat_endpoint = NAT_ENDPOINT

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    stream=sys.stdout
)


if len(sys.argv) > 1:
    nat_host, nat_port = sys.argv[1].split(":")
    nat_endpoint = (nat_host, int(nat_port))
    log(f"nat endpoint set to: {nat_host}:{nat_port}", pr=True)

proxy = Proxy(
    WIREGUARD_INTERFACE_NAME,
    WIREGUARD_ENDPOINT,
    nat_endpoint,
    BROKER_ENDPOINT,
    MIGRATION_ENDPOINT,
    POLLING_ENDPOINT,
)
def log_network_config():
    try:
        routes = subprocess.check_output(["ip", "route"]).decode()
        interfaces = subprocess.check_output(["ip", "addr"]).decode()
        iptables = subprocess.check_output(["sudo", "iptables", "-L", "-n", "-v"]).decode()
        logging.info("Current network configuration:")
        logging.info(f"Routes:\n{routes}")
        logging.info(f"Interfaces:\n{interfaces}")
        logging.info(f"IPTables rules:\n{iptables}")
    except Exception as e:
        logging.error(f"Error getting network configuration: {e}")

log_network_config()
proxy.run()
