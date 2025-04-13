import atexit
import configparser
import logging
import signal
import socket
import ssl
import sys
import threading
import time

from search import Searcher
from ssl_utils import create_ssl_context


# Load configuration
config = configparser.ConfigParser()
config.read("config.ini")

PORT = int(config["SERVER"]["port"])
MAX_ALLOWED_TIME_MS = int(config["SERVER"]["max_allowed_time_ms"])
REREAD_ON_QUERY = config.getboolean("SERVER", "reread_on_query")
SSL_ENABLED = config.getboolean("SERVER", "ssl_enabled")
FILE_PATH = config["PATHS"]["linuxpath"]
CERT_FILE = config["SSL"]["certfile"]
KEY_FILE = config["SSL"]["keyfile"]

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("server.log"),
        logging.StreamHandler(sys.stdout),
    ],
)


class TCPServer:
    def __init__(self):
        self.shutdown_flag = False
        self.active_connections = set()
        self.lock = threading.Lock()
        self.searcher = Searcher(FILE_PATH, reread_on_query=REREAD_ON_QUERY)
        if (not config.has_section('SERVER') or
                not config.has_option('SERVER', 'port')):
            logging.error("Missing required SERVER configuration.")
            sys.exit(1)

    def handle_client(
            self,
            conn: socket.socket,
            address: tuple[str, int]
    ) -> None:
        """Handle client connection and search requests."""
        with self.lock:
            self.active_connections.add(conn)
        try:
            logging.info(f"Connection from {address}")
            conn.settimeout(1)
            buffer = b""

            while not self.shutdown_flag:
                try:
                    data = conn.recv(1024)
                    if not data:
                        break

                    buffer += data
                    if b"\x00" in buffer:
                        query_part, _, buffer = buffer.partition(b"\x00")
                        try:
                            query = query_part.decode("utf-8").strip()
                            start_time = time.perf_counter()
                            exists = self.searcher.search(query)
                            end_time = time.perf_counter()

                            duration_ms = (end_time - start_time) * 1000

                            if duration_ms > MAX_ALLOWED_TIME_MS:
                                logging.warning(
                                    f"Slow query detected: '{query[:20]}...'"
                                    f"from {address[0]}, "
                                    f"took {duration_ms:.2f}ms "
                                    f"(limit {MAX_ALLOWED_TIME_MS}ms)"
                                )

                            response = (
                                "STRING EXISTS\n" if exists
                                else "STRING NOT FOUND\n"
                            )
                            conn.sendall(response.encode())

                            logging.info(
                                f"Query='{query[:20]}...' from {address[0]} "
                                f"Result={'FOUND' if exists else 'NOT FOUND'} "
                                f"({duration_ms:.2f}ms)"
                            )

                        except UnicodeDecodeError:
                            logging.warning("Invalid UTF-8 from %s", address)
                            conn.sendall(b"STRING NOT FOUND\n")

                except socket.timeout:
                    continue
                except ssl.SSLError as e:
                    logging.exception(f"SSL error with {address}: {e}")
                    break
        except (ConnectionResetError, BrokenPipeError) as e:
            logging.warning(f"Client {address} disconnected: {e}")
        except Exception as e:
            logging.exception(f"Unexpected error with {address}: {e}")
        finally:
            try:
                conn.close()
            except Exception:
                pass
            with self.lock:
                self.active_connections.discard(conn)
            logging.info(f"Closed connection from {address}")

    def start(self):
        """Start the TCP server with optional SSL."""
        if threading.current_thread() == threading.main_thread():
            def handler(signum, frame):
                logging.info(f"Received signal {signum}")
                self.shutdown_flag = True
            signal.signal(signal.SIGINT, handler)
            signal.signal(signal.SIGTERM, handler)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", PORT))
        sock.listen(5)
        sock.settimeout(1)
        context = None
        if SSL_ENABLED:
            try:
                context = create_ssl_context(CERT_FILE, KEY_FILE)
                context.verify_mode = ssl.CERT_REQUIRED
                context.load_verify_locations(CERT_FILE)
                logging.info("SSL enabled with certificate verification")
            except ssl.SSLError as e:
                logging.error(f"SSL setup failed: {e}")
                sys.exit(1)

        logging.info(f"Server started on port {PORT}")

        atexit.register(self.cleanup, sock)

        try:
            while not self.shutdown_flag:
                try:
                    conn, addr = sock.accept()
                    if context:
                        try:
                            conn = context.wrap_socket(
                                conn,
                                server_side=True,
                                do_handshake_on_connect=True
                            )
                        except ssl.SSLError as e:
                            logging.error(f"SSL handshake failed: {e}")
                            conn.close()
                            continue
                    thread = threading.Thread(
                        target=self.handle_client,
                        args=(conn, addr),
                        daemon=True
                    )
                    thread.start()
                except socket.timeout:
                    continue
                except ssl.SSLError as e:
                    logging.error(f"SSL error: {e}")
        except KeyboardInterrupt:
            logging.info("Received shutdown signal")
        finally:
            self.cleanup(sock)

    def cleanup(self, sock=None):
        """Clean up server resources."""
        logging.info("Shutting down server...")
        self.shutdown_flag = True

        # Close all active connections
        with self.lock:
            connections = list(self.active_connections)
            for conn in connections:
                try:
                    conn.shutdown(socket.SHUT_RDWR)
                    conn.close()
                except Exception as e:
                    logging.debug(f"Connection close error: {e}")
                finally:
                    self.active_connections.remove(conn)

        # Close main socket
        if sock:
            try:
                sock.close()
            except Exception as e:
                logging.debug(f"Socket close error: {e}")

        logging.info("Server shutdown complete")


def main():
    server = TCPServer()

    def handler(signum, frame):
        logging.info(f"Received signal {signum}")
        server.shutdown_flag = True

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)

    server.start()


if __name__ == "__main__":
    main()
