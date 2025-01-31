import asyncio
from enum import Enum
import socket
import struct
import time
import requests
from scapy.all import AsyncSniffer, Raw, IP, TCP, UDP, sr1, conf
from scapy.layers.inet import ICMP
from typing import Dict, Tuple
import logging


logging.basicConfig(
    filename='/app/logs/app.log',
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

SYN = 0x02


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
        self.connections: Dict[str, ConnectionState] = {}


class ConnectionState(Enum):
    NEW = "NEW"
    ESTABLISHED = "ESTABLISHED"
    CLOSED = "CLOSED"


class TCPState:
    def __init__(self):
        self.seq = 0
        self.ack = 0
        self.established = False
        self.fin_sent = False
        self.fin_received = False
        self.last_activity = time.time()

    def update(self, tcp_packet: TCP):
        self.seq = tcp_packet.ack
        self.ack = tcp_packet.seq + len(tcp_packet.payload)
        self.last_activity = time.time()


class NATServer:
    def __init__(self) -> None:
        self.conn_manager = ConnectionManager()
        self.logger = logging.getLogger('NATServer')
        self.logger.info("Initializing NAT Server")
        self.loop = asyncio.get_event_loop()
        self.PUBLIC_IP = "54.90.59.253"
        self.cons = []

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
                pkt = IP(payload)
                self.logger.debug(
                    f"Packet details: src={pkt.src}, dst={pkt.dst}, proto={pkt.proto}, raw: {pkt.summary()}")
                if TCP in pkt:
                    tcp = pkt[TCP]
                    self.logger.debug(
                        f"TCP details: sport={tcp.sport}, dport={tcp.dport}, flags={tcp.flags}")
                    await self.handle_tcp_stream(payload, (pkt.dst, tcp.dport), writer)

                if UDP in pkt:
                    udp = pkt[UDP]
                    await self.handle_udp_packet(payload, (pkt.dst, udp.dport), writer)

        except Exception as e:
            self.logger.error(
                f"Client handler error for {peer}: {str(e)}", exc_info=True)
        finally:
            self.logger.info(f"Closing connection from {peer}")
            writer.close()
            await writer.wait_closed()

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

    async def handle_tcp_stream(self, payload,
                                target_addr: Tuple[str, int],
                                client_writer: asyncio.StreamWriter):
        peer = client_writer.get_extra_info('peername')
        self.logger.info(
            f"Handling TCP stream from proxy: {IP(payload).summary()}")

        org_pkt = IP(payload)
        tcp_layer = org_pkt[TCP]
        conn_key = f"{org_pkt[IP].src}:{org_pkt[TCP].sport} \
            :{org_pkt[IP].dst}:{org_pkt[TCP].dport}"
        self.conn_manager.connections[conn_key] = ConnectionState.NEW
        try:
            if tcp_layer.flags & SYN and self.conn_manager.connections[conn_key] == ConnectionState.NEW:
                self.logger.debug("Establishing new TCP connection")

                syn_packet = org_pkt.copy()
                del syn_packet[IP].src
                del syn_packet[TCP].sport
                del syn_packet[IP].chksum
                del syn_packet[TCP].chksum

                self.logger.debug(f"syn_pkt summary: {syn_packet.summary()}")
                syn_ans = sr1(syn_packet, timeout=3,
                              retry=3, verbose=True)
                if not syn_ans:
                    self.logger.error(
                        "No response received from target server")
                    raise Exception("No response from target")
                self.logger.debug(f"syn_ans is: {syn_ans.summary()}")
                if str(syn_ans[TCP].flags) == 'SA':
                    # TODO: Store connection state, Store ans pkt to resend it later
                    pass

                syn_ans[IP].dst = org_pkt.src
                syn_ans[TCP].dport = tcp_layer.sport
                del syn_ans[IP].chksum
                del syn_ans[TCP].chksum
                self.logger.debug(
                    f"sending this syn_ans is: {syn_ans.summary()}")
                await self.send_response(bytes(syn_ans), client_writer)

                self.conn_manager.connections[conn_key] = ConnectionState.ESTABLISHED
                state = TCPState()
                state.seq = tcp_layer.seq
                state.ack = tcp_layer.ack

            elif self.conn_manager.connections[conn_key] == ConnectionState.ESTABLISHED:
                self.logger.debug(f"NOT SYN pkt: {org_pkt.summary()}")
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
        finally:
            try:
                client_writer.close()
                await client_writer.wait_closed()
            except Exception as e:
                self.logger.warning(
                    f"Error closing client writer for {peer}: {str(e)}")

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
            self.logger.info(f"NAT server is running on {host}:{port}")
            await self.server.serve_forever()
