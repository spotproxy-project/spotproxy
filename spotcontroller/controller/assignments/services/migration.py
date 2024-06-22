from assignments.models import Proxy
import socket


def send_migration_notice(proxy1: Proxy, proxy2: Proxy):
    BROKER_PORT = 8121
    ip = proxy1.ip

    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect((ip, BROKER_PORT))

    message = f"migrate {proxy2.ip}"
    client_socket.send(message.encode("utf-8"))
