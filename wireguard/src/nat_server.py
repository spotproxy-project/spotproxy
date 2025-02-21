from json import dump
import logging
from sys import flags
from typing import Awaitable, Dict, Literal, Tuple
from scapy.layers.inet import ICMP
from scapy.all import AsyncSniffer, Raw, IP, TCP, UDP, sr1, conf
import requests
import struct
import socket
from enum import Enum
import asyncio
import hashlib
import time

logging.basicConfig(
    filename='/app/logs/app.log',
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


def generate_isn(source_ip: str, dest_ip: str, source_port: int, dest_port: int) -> int:
    """Generate a TCP Initial Sequence Number (ISN) based on a hash of connection parameters."""
    timestamp = int(time.time() * 1000)  # Milliseconds precision

    data = f"{timestamp}:{source_ip}:{dest_ip}:{source_port}:{dest_port}".encode()

    hash_value = hashlib.md5(data).digest()

    isn = struct.unpack("!I", hash_value[:4])[0]

    return isn


def get_public_ip():
    try:
        response = requests.get("https://httpbin.org/ip")

        if response.status_code == 200:
            public_ip = response.json()["origin"]
            print(public_ip)
            return public_ip
        else:
            print(
                f"Failed to retrieve public IP. Status code: {response.status_code}")

    except requests.RequestException as e:
        print(f"Request error: {e}")

    return None


class ConnectionManager:
    def __init__(self):
        self.connections: Dict[str, Connection] = {}


FIN = 0x01   # Finish (Connection Termination)
SYN = 0x02   # Synchronize (Connection Establishment)
RST = 0x04   # Reset (Abort Connection)
PSH = 0x08   # Push (Immediate Delivery)
ACK = 0x10   # Acknowledge (Confirms Receipt)
URG = 0x20   # Urgent (Priority Data)
ECE = 0x40   # Explicit Congestion Notification Echo
CWR = 0x80
SYN_ACK = SYN | ACK
FIN_ACK = FIN | ACK
PSH_ACK = PSH | ACK
RST_ACK = RST | ACK


class TCPFlags(Enum):
    FIN = (0x01, 'F')   # Finish (Connection Termination)
    SYN = (0x02, 'S')   # Synchronize (Connection Establishment)
    RST = (0x04, 'R')   # Reset (Abort Connection)
    PSH = (0x08, 'P')   # Push (Immediate Delivery)
    ACK = (0x10, 'A')   # Acknowledge (Confirms Receipt)
    URG = (0x20, 'U')   # Urgent (Priority Data)
    ECE = (0x40, 'E')   # Explicit Congestion Notification Echo
    CWR = (0x80, 'C')   # Congestion Window Reduced

    # Common Combinations
    SYN_ACK = (SYN[0] | ACK[0], 'SA')
    FIN_ACK = (FIN[0] | ACK[0], 'FA')
    PSH_ACK = (PSH[0] | ACK[0], 'PA')
    RST_ACK = (RST[0] | ACK[0], 'RA')

    def __init__(self, value, short_name):
        self._value_ = value
        self.short_name = short_name

    @classmethod
    def from_value(cls, value):
        """ Returns a list of matching flags from a given integer value. """
        return [flag for flag in cls if flag.value & value]

    @classmethod
    def to_string(cls, value):
        """ Converts a flag value into a human-readable string like 'SA' or 'PA'. """
        return ''.join(flag.short_name for flag in cls.from_value(value))

    @classmethod
    def from_string(cls, string):
        """ Converts a short string representation like 'SA' into the combined flag value. """
        value = sum(flag.value for flag in cls if flag.short_name in string)
        return value


class ConnectionState(Enum):
    NEW = "NEW"
    STARTING = "STARTING"
    ESTABLISHED = "ESTABLISHED"
    CLOSED = "CLOSED"
    SYN_RECEIVED = "SYN_RECEIVED"


class TCPState:
    flag: TCPFlags

    def __init__(self):
        self.seq = 0
        self.ack = 0
        self.established = False
        self.fin_sent = False
        self.fin_received = False

    def set(self, tcp_packet: TCP):
        self.seq = tcp_packet.ack
        self.ack = tcp_packet.seq + len(tcp_packet.payload)

# TODO: base class Connection(TCP Connection, UDP Connection)


class Connection:
    server_reader: asyncio.StreamReader
    nat_writer: asyncio.StreamWriter
    state: ConnectionState
    tcp_state: TCPState
    initial_seq: int

    def __init__(self, ) -> None:
        self.state = ConnectionState.STARTING
        self.expected_seq = 0


class NATServer:
    def __init__(self) -> None:
        self.tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.conn_manager = ConnectionManager()
        self.logger = logging.getLogger('NATServer')
        self.logger.info("Initializing NAT Server")
        self.loop = asyncio.get_event_loop()
        self.PUBLIC_IP = "54.90.59.253"
        self.cons = []

    def _initialize_socket(self, host: str, port: int):
        self.tcp_sock.setsockopt(
            socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        self.tcp_sock.bind((host, port))
        self.tcp_sock.listen(100)

    async def decapsulate(self, reader: asyncio.StreamReader):
        try:
            payload_len_data = await reader.read(4)
            payload_len = struct.unpack('>I', payload_len_data)[0]
            payload = await reader.read(payload_len)
            return payload
        except Exception as e:
            self.logger.error(f"error decapsulating the pkt {e}")

    async def connection_loop(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle individual client connection"""
        peer = writer.get_extra_info('peername')
        self.logger.info(f"New client connection from {peer}")
        try:
            while True:
                payload = await self.decapsulate(reader)
                if not payload:
                    self.logger.debug("PAYLOAD is empty, ingnoring")
                    continue
                pkt = IP(payload)
                if TCP in pkt:
                    tcp = pkt[TCP]
                    await self.handle_tcp(payload, (pkt.dst, tcp.dport), writer)

                if UDP in pkt:
                    udp = pkt[UDP]
                    await self.handle_udp_packet(payload, (pkt.dst, udp.dport), writer)

        except Exception as e:
            self.logger.error(
                f"Client handler error for {peer}: {str(e)}", exc_info=True)

    async def send_response(self, packet_data: bytes, client_writer: asyncio.StreamWriter):
        try:
            complete_message = struct.pack(
                '>I', len(packet_data)) + packet_data

            client_writer.write(complete_message)

            await client_writer.drain()

            self.logger.debug(
                "Response sent successfully",
                extra={
                    'packet_length': len(packet_data)
                }
            )

        except asyncio.TimeoutError:
            self.logger.warning("Drain timeout - connection might be slow")
        except ConnectionResetError as e:
            self.logger.error(f"Connection reset while sending response: {e}")
        except Exception as e:
            self.logger.error(
                f"Failed to send response: {str(e)}",
                extra={
                    'packet_length': len(packet_data)
                },
                exc_info=True
            )
            raise

    async def handle_tcp(self, payload: bytes,
                         target: Tuple[str, int],
                         client_writer: asyncio.StreamWriter):
        org_pkt = IP(payload)
        tcp_layer = org_pkt[TCP]
        conn_key = f"{org_pkt[IP].src}:{org_pkt[TCP].sport}:{org_pkt[IP].dst}:{org_pkt[TCP].dport}"
        self.logger.debug(
            f"----comming conn: {org_pkt.summary()} with flags: {tcp_layer.flags}----")
        if conn_key in self.conn_manager.connections.keys():
            connection = self.conn_manager.connections[conn_key]
        else:
            connection = Connection()
            connection.initial_seq = generate_isn(
                org_pkt[IP].src, org_pkt[IP].dst, org_pkt[TCP].sport, org_pkt[TCP].dport)
            self.conn_manager.connections[conn_key] = connection

        # if connection is starting: OPEN_CONNECTION, SEND SYN-ACK, STATE->NEW, save state
        # if connection in NEW state, send SYN-ACK update state
        # if conncetion in STARTING and sending ACK, STATE->ESTABLISHED, update state
        # if connection in ESTABLISHED and sending data, write to connection, update sate, send back response in PSH-ACK
        try:
            if tcp_layer.flags & SYN:
                if connection.state == ConnectionState.STARTING:
                    connection.state = ConnectionState.NEW
                    # TODO: create connection, send response, handle TCPState
                    self.logger.debug("Establishing new TCP connection")
                    server_reader, nat_writer = await asyncio.open_connection(
                        target[0],
                        target[1]
                    )
                    connection.nat_writer = nat_writer
                    connection.server_reader = server_reader
                    syn_ack = IP(
                        src=org_pkt[IP].dst,
                        dst=org_pkt[IP].src
                    )/TCP(
                        sport=org_pkt[TCP].dport,
                        dport=org_pkt[TCP].sport,
                        flags='SA',
                        seq=connection.initial_seq,
                        ack=org_pkt[TCP].seq+1,
                        window=org_pkt[TCP].window)
                    del syn_ack[IP].chksum
                    del syn_ack[TCP].chksum
                    self.logger.debug(
                        f"syn_ack pack: {syn_ack.summary()}")
                    await self.send_response(bytes(syn_ack), client_writer)
                elif connection.state == ConnectionState.NEW:
                    self.logger.debug(
                        f"GOT repeated SYNs {org_pkt.summary()}")
                    # updating TCP_state, send SYN-ACK
                    syn_ack = IP(
                        src=org_pkt[IP].dst,
                        dst=org_pkt[IP].src
                    )/TCP(
                        sport=org_pkt[TCP].dport,
                        dport=org_pkt[TCP].sport,
                        flags='SA',
                        seq=connection.initial_seq,
                        ack=org_pkt[TCP].seq+1,
                        window=org_pkt[TCP].window)

                    del syn_ack[IP].chksum
                    del syn_ack[TCP].chksum
                    self.logger.debug(
                        f"repeated syn_ack pack: {syn_ack.summary()}")
                    await self.send_response(bytes(syn_ack), client_writer)
            elif org_pkt[TCP].seq < connection.expected_seq:
                self.logger.debug(
                    f"Duplicate/retransmitted packet detected: {org_pkt.summary()}")
                # Resend last ACK to prevent stalls
                ack_pkt = IP(src=org_pkt[IP].dst, dst=org_pkt[IP].src)/TCP(
                    sport=org_pkt[TCP].dport, dport=org_pkt[TCP].sport, flags='A',
                    seq=connection.initial_seq, ack=connection.expected_seq, window=org_pkt[
                        TCP].window
                )
                del ack_pkt[IP].chksum
                del ack_pkt[TCP].chksum
                await self.send_response(bytes(ack_pkt), client_writer)
            elif tcp_layer.flags == 'A':
                self.logger.debug("Acking TCP Connection")
                # Handle TCPState
                connection.expected_seq = org_pkt[TCP].seq
                self.conn_manager.connections[conn_key].state = ConnectionState.ESTABLISHED
            elif (tcp_layer.flags == 'R') or (tcp_layer.flags == 'F'):
                self.logger.debug(
                    f"got FIN or RST pkt from client: {org_pkt.summary()}")
                pass
            elif tcp_layer.flags == 'FA':
                self.logger.debug("GOT FA from client")
                connection.expected_seq = org_pkt[TCP].seq

                # Respond with ACK first
                fin_ack = IP(src=org_pkt[IP].dst, dst=org_pkt[IP].src)/TCP(
                    sport=org_pkt[TCP].dport, dport=org_pkt[TCP].sport, flags='FA',
                    seq=connection.initial_seq, ack=org_pkt[TCP].seq + 1, window=org_pkt[TCP].window
                )
                del fin_ack[IP].chksum
                del fin_ack[TCP].chksum
                self.logger.debug(
                    f"FIN-ACK sent to client: {fin_ack.summary()}")
                await self.send_response(bytes(fin_ack), client_writer)

                # Close connection after timeout (to allow for final ACK)
                await asyncio.sleep(2)
                connection.state = ConnectionState.CLOSED
                del self.conn_manager.connections[conn_key]
                self.logger.debug("Connection closed successfully.")
            elif tcp_layer.flags == 'PA':
                self.logger.debug("IN PSH_ACK")
                if connection and connection.state == ConnectionState.ESTABLISHED:
                    connection.expected_seq = org_pkt[TCP].seq
                    # TODO: modify the packet header(IP,PORT)
                    data = bytes(org_pkt[TCP].payload)
                    connection.nat_writer.write(data=data)
                    await connection.nat_writer.drain()

                    # Not Sure About This Number
                    res = await connection.server_reader.read(65535)
                    data_length = len(res)
                    ip_layer = IP(src=org_pkt[IP].dst, dst=org_pkt[IP].src)
                    tcp_layer = TCP(sport=tcp_layer.dport,
                                    dport=tcp_layer.sport, flags='PA',
                                    seq=connection.initial_seq + data_length,
                                    ack=org_pkt[TCP].seq +
                                    len(org_pkt[TCP].payload),
                                    window=org_pkt[TCP].window)
                    res_pkt = ip_layer/tcp_layer/Raw(res)
                    del res_pkt[IP].chksum
                    del res_pkt[TCP].chksum

                    self.logger.debug(
                        f"sending res to client {res_pkt.summary()}")
                    await self.send_response(bytes(res_pkt), client_writer)

        except Exception:
            pass

    async def handle_tcp_stream(self, payload,
                                target_addr: Tuple[str, int],
                                client_writer: asyncio.StreamWriter):
        peer = client_writer.get_extra_info('peername')
        sniffer = AsyncSniffer(prn=lambda x: self.logger.info(x.summary()),
                               store=False, filter="tcp")
        self.logger.info(
            f"Handling TCP stream from proxy: {IP(payload).summary()}")

        org_pkt = IP(payload)
        tcp_layer = org_pkt[TCP]
        conn_key = f"{org_pkt[IP].src}:{org_pkt[TCP].sport}:{org_pkt[IP].dst}:{org_pkt[TCP].dport}"
        if conn_key not in self.conn_manager.connections.keys():
            self.conn_manager.connections[conn_key] = ConnectionState.NEW
        self.logger.debug(f"conn_key: {conn_key}")
        try:
            if self.conn_manager.connections[conn_key] == ConnectionState.NEW:
                if tcp_layer.flags & SYN:
                    self.logger.debug("Establishing new TCP connection")

                    syn_packet = org_pkt.copy()
                    del syn_packet[IP].src
                    del syn_packet[IP].chksum
                    del syn_packet[TCP].chksum

                    self.logger.debug(
                        f"syn_pkt summary: {syn_packet.summary()}")
                    self.logger.debug(
                        f"syn_pkt sport:{syn_packet[TCP].sport} dport:{syn_packet[TCP].dport}")
                    syn_ans = sr1(syn_packet, timeout=3,
                                  retry=3, verbose=True)
                    if not syn_ans:
                        self.logger.error(
                            "No response received from target server")
                        raise Exception("No response from target")
                    self.logger.debug(f"syn_ans is: {syn_ans.summary()}")
                    if str(syn_ans[TCP].flags) == 'SA':
                        self.conn_manager.connections[conn_key] = ConnectionState.SYN_RECEIVED

                    syn_ans[IP].dst = org_pkt.src
                    syn_ans[TCP].dport = tcp_layer.sport
                    del syn_ans[IP].chksum
                    del syn_ans[TCP].chksum
                    self.logger.debug(
                        f"sending this syn_ans is: {syn_ans.summary()}")
                    self.logger.debug(
                        f"syn_pkt sport:{syn_ans[TCP].sport} dport:{syn_ans[TCP].dport}")

                    await self.send_response(bytes(syn_ans), client_writer)

            elif self.conn_manager.connections[conn_key] == ConnectionState.SYN_RECEIVED:
                if tcp_layer.flags & ACK:
                    self.logger.debug("ACKing an open connection")

                    sniffer.start()
                    syn_packet = org_pkt.copy()
                    del syn_packet[IP].src
                    del syn_packet[IP].chksum
                    del syn_packet[TCP].chksum

                    self.logger.debug(
                        f"syn_pkt summary: {syn_packet.summary()}")
                    self.logger.debug(
                        f"syn_pkt sport:{syn_packet[TCP].sport} dport:{syn_packet[TCP].dport}")
                    syn_ans = sr1(syn_packet, timeout=3,
                                  retry=3, verbose=True)
                    sniffer.stop()
                    if not syn_ans:
                        self.logger.error(
                            "No response received from target server")
                        raise Exception("No response from target")
                    self.logger.debug(f"syn_ans is: {syn_ans.summary()}")

                    syn_ans[IP].dst = org_pkt.src
                    syn_ans[TCP].dport = tcp_layer.sport
                    del syn_ans[IP].chksum
                    del syn_ans[TCP].chksum
                    self.logger.debug(
                        f"sending this syn_ans is: {syn_ans.summary()}")
                    self.logger.debug(
                        f"syn_pkt sport:{syn_ans[TCP].sport} dport:{syn_ans[TCP].dport}")
                    await self.send_response(bytes(syn_ans), client_writer)

                    if str(syn_ans[TCP].flags) == 'R':
                        self.conn_manager.connections[conn_key] = ConnectionState.CLOSED
                    else:
                        self.conn_manager.connections[conn_key] = ConnectionState.ESTABLISHED
                    self.logger.debug(
                        f"changed the connection state: {self.conn_manager.connections[conn_key]}")
                else:
                    self.logger.debug("DROPING dup SYN pkt")

            elif self.conn_manager.connections[conn_key] == ConnectionState.ESTABLISHED:
                self.logger.debug(f"AFTER 3WAY HAND pkt: {org_pkt.summary()}")
                pkt = org_pkt.copy()
                pkt[IP].src = org_pkt[IP].src
                ans = sr1(pkt)
                if not ans:
                    raise Exception()

                self.logger.debug(f"ans is: {ans.summary()}")
                ans[IP].dst = org_pkt[IP].src
                ans[TCP].dport = tcp_layer.sport
                await self.send_response(bytes(ans), client_writer)

        except asyncio.TimeoutError:
            self.logger.error(
                f"Timeout occurred while handling TCP stream from {peer} to {target_addr}")
        except ConnectionRefusedError:
            self.logger.error(
                f"Connection refused to target {target_addr} from {peer}")
        except Exception as e:
            self.logger.error(
                f"Unhandled error in TCP stream handling: {str(e)}", exc_info=True)
#        finally:
#            try:
#                client_writer.close()
#                await client_writer.wait_closed()
#            except Exception as e:
#                self.logger.warning(
#                    f"Error closing client writer for {peer}: {str(e)}")

    async def handle_udp_packet(self, pkt,
                                target_addr: Tuple[str, int],
                                client_writer: asyncio.StreamWriter):
        """Handle UDP packet"""
        peer = client_writer.get_extra_info('peername')
        self.logger.info(f"Handling UDP stream from {peer} to {target_addr}")

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)

        try:
            org_pkt = IP(pkt)
            udp_payload = bytes(org_pkt[UDP].payload)

            await self.loop.sock_sendto(sock, udp_payload, target_addr)

            data, addr = await self.loop.sock_recvfrom(sock, 65535)

            response_packet = IP(
                src=addr[0],
                dst=org_pkt.src,
                proto=socket.IPPROTO_UDP
            )/UDP(
                sport=addr[1],
                dport=org_pkt[UDP].sport
            )/Raw(load=data)

            await self.send_response(bytes(response_packet), client_writer)
            self.logger.info("UDP response forwarded back successfully", extra={
                'bytes_forwarded': len(bytes(response_packet)),
                'source_addr': addr,
                'destination': peer
            })

        finally:
            sock.close()

    async def handle_icmp_packet(self, payload: bytes,
                                 target_addr: Tuple[str, int],
                                 client_writer: asyncio.StreamWriter):
        """Handle ICMP packet with proper packet reconstruction"""

        org_pkt = IP(payload)
        icmp_layer = org_pkt[ICMP]

        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_RAW,
            socket.IPPROTO_ICMP
        )
        sock.setblocking(False)

        try:
            await self.loop.sock_sendto(
                sock,
                bytes(icmp_layer),
                (target_addr[0], 0)
            )

            data, addr = await self.loop.sock_recvfrom(sock, 65535)

            response_packet = IP(
                src=addr[0],
                dst=org_pkt.dst,
                proto=socket.IPPROTO_ICMP
            )/ICMP(data)

            complete_packet = bytes(response_packet)
            await self.send_response(complete_packet, client_writer)

        finally:
            sock.close()

    async def start_server(self, host: str, port: int):
        self.logger.debug(f"interfaces: {conf.ifaces}")
        self.server = await asyncio.start_server(
            self.connection_loop, host, port)

        async with self.server:
            self.logger.info(f"[✔] NAT server is running on {host}:{port}")
            await self.server.serve_forever()
