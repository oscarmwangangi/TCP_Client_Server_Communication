import socket
import time
import argparse
import ssl
from typing import Tuple, Optional


def query_server(
    query: str,
    host: str = "localhost",
    port: int = 5555,
    ssl_mode: bool = False,
    certfile: str = None,
    timeout: float = 5.0
) -> Tuple[Optional[str], Optional[float]]:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)

            if ssl_mode:
                context = ssl.create_default_context()
                context.check_hostname = False

                if certfile:
                    context.load_verify_locations(cafile=certfile)
                    context.verify_mode = ssl.CERT_REQUIRED

                try:
                    secure_sock = context.wrap_socket(
                        sock, server_hostname=host)
                    secure_sock.connect((host, port))
                    sock = secure_sock
                except ssl.SSLError as e:
                    print(f"SSL Error: {e}")
                    return None, None
            else:
                try:
                    sock.connect((host, port))
                except ConnectionRefusedError:
                    print("Connection failed - "
                          "Is the server running with SSL?")
                    return None, None

            # Send query
            sock.sendall(query.encode() + b"\x00")

            # Get response
            start = time.time()
            response = sock.recv(1024)
            elapsed = (time.time() - start) * 1000

            if not response:
                return None, None

            response_str = response.decode().strip()
            print(f"Response: {response_str}")
            print(f"Time: {elapsed:.2f}ms")
            return response_str, elapsed

    except socket.timeout:
        print("Error: Connection timed out")
        return None, None
    except Exception as e:
        print(f"Error: {e}")
        return None, None


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("query", help="String to search")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=5555)
    parser.add_argument(
        "--ssl",
        action="store_true",
        help="Use SSL connection")
    parser.add_argument("--cert", help="CA certificate file path")
    parser.add_argument("--timeout", type=float, default=5.0,
                        help="Connection timeout in seconds")

    args = parser.parse_args()
    query_server(
        args.query,
        args.host,
        args.port,
        args.ssl,
        args.cert,
        args.timeout
    )
