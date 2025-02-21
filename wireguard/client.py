import logging
import socks  # pip install pysocks

logging.basicConfig(level=logging.INFO)


def connect_through_proxy():
    # Configure proxy settings
    s = socks.socksocket()
    s.set_proxy(socks.HTTP, "127.0.0.1", 8080)

    try:
        logging.info("Connecting to Google through mitmproxy...")
        s.connect(("142.250.186.142", 80))
        logging.info("Connected!")

        # Send HTTP request
        request = (
            b"GET / HTTP/1.1\r\n"
            b"Host: 142.250.186.142\r\n"
            b"Connection: close\r\n"
            b"\r\n"
        )
        s.send(request)

        # Receive response
        response = s.recv(4096)
        logging.info(f"Received: {response}")

    except Exception as e:
        logging.error(f"Error: {e}")
    finally:
        s.close()
        logging.info("Connection closed")


if __name__ == "__main__":
    connect_through_proxy()
