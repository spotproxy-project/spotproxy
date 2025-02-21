import socket
import threading
from scapy.all import *


def dummy_server():
    """Dummy server to prevent kernel from sending RST packets."""
    dummy_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    dummy_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    dummy_sock.bind(("0.0.0.0", 8081))
    dummy_sock.listen(5)
    while True:
        conn, _ = dummy_sock.accept()
        conn.close()


def three_way_handshake():
    target_ip = "142.250.186.142"  # Google's IP
    target_port = 443  # HTTPS port

    # Create SYN packet
    syn_packet = IP(dst=target_ip)/TCP(sport=8081,
                                       dport=target_port, flags='S')

    print("\nSending SYN...")
    syn_packet.show2()

    # Send SYN and receive SYN-ACK
    syn_ack = sr1(syn_packet, timeout=2)

    if syn_ack and syn_ack.haslayer(TCP) and syn_ack[TCP].flags == 'SA':
        print("\nReceived SYN-ACK:")
        syn_ack.show2()

        # Create ACK packet
        ack_packet = IP(dst=target_ip)/TCP(
            sport=8081,
            dport=target_port,
            seq=syn_ack.ack,
            ack=syn_ack.seq + 1,
            flags='A'
        )

        print("\nSending ACK...")
        ack_packet.show2()

        # Send ACK
        send(ack_packet)

        print("\nHandshake completed.")
    else:
        print("Did not receive SYN-ACK")


if __name__ == "__main__":
    # Start the dummy server in a separate thread
    threading.Thread(target=dummy_server, daemon=True).start()
    three_way_handshake()
