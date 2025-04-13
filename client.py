import socket
import time
import argparse


def query_server(
    query: str, host: str = "localhost", port: int = 5555, ssl: bool = False
):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if ssl:
                context = ssl.create_default_context()
                s = context.wrap_socket(s, server_hostname=host)

            s.connect((host, port))
            start = time.time()
            s.sendall(query.encode() + b"\x00")
            response = s.recv(1024).decode()
            elapsed = (time.time() - start) * 1000

            print(f"Response: {response.strip()}")
            print(f"Time: {elapsed:.2f}ms")
            return response, elapsed
    except Exception as e:
        print(f"Error: {e}")
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("query", help="String to search")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=5555)
    parser.add_argument("--ssl", action="store_true")
    args = parser.parse_args()

    query_server(args.query, args.host, args.port, args.ssl)
