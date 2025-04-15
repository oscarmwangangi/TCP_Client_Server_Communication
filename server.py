import atexit
import configparser
import concurrent.futures
import logging
import queue
import signal
import socket
import ssl
import sys
import threading
import time
from typing import Dict, Optional, Set, Tuple

from search import Searcher
from ssl_utils import create_ssl_context


class TCPServer:
    def __init__(self, max_workers: int = 10):
        """Initialize the TCP server with thread pool support."""
        self.shutdown_flag = False
        self.active_connections: Set[socket.socket] = set()
        self.lock = threading.Lock()
        self.connection_queue = queue.Queue(maxsize=100)
        self.thread_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="TCPWorker"
        )
        
        self.connection_stats: Dict[Tuple[str, int], Dict[str, float]] = {}

        # Load configuration
        self.config = configparser.ConfigParser()
        self.config.read("config.ini")

        # Validate configuration
        self._validate_config()

        # Initialize server parameters
        self.port = int(self.config["SERVER"]["port"])
        self.max_allowed_time_ms = int(
            self.config["SERVER"]["max_allowed_time_ms"])
        self.reread_on_query = self.config.getboolean(
            "SERVER", "reread_on_query")
        self.ssl_enabled = self.config.getboolean("SERVER", "ssl_enabled")
        self.file_path = self.config["PATHS"]["linuxpath"]
        self.cert_file = self.config["SSL"]["certfile"]
        self.key_file = self.config["SSL"]["keyfile"]
        self.ca_file = self.config.get("SSL", "cafile", fallback=None)

        # Initialize searcher
        self.searcher = Searcher(
            self.file_path,
            reread_on_query=self.reread_on_query)

        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s",
            handlers=[
                logging.FileHandler("server.log"),
                logging.StreamHandler(sys.stdout),
            ],
        )

    def _validate_config(self) -> None:
        """Validate the required configuration sections and options."""
        required_sections = {
            "SERVER": [
                "port",
                "max_allowed_time_ms",
                "reread_on_query",
                "ssl_enabled"],
            "PATHS": ["linuxpath"],
            "SSL": [
                "certfile",
                "keyfile"]}

        for section, options in required_sections.items():
            if not self.config.has_section(section):
                logging.error(
                    f"Missing required configuration section: {section}")
                sys.exit(1)

            for option in options:
                if not self.config.has_option(section, option):
                    logging.error(
                        f"Missing required option "
                        f"'{option}' in section '{section}'")
                    sys.exit(1)

    def _update_connection_stats(
            self, address: Tuple[str, int], duration: float) -> None:
        """Thread-safe update of connection statistics."""
        with self.lock:
            if address not in self.connection_stats:
                self.connection_stats[address] = {
                    'count': 0,
                    'total_time': 0.0,
                    'last_connected': time.time()
                }
            self.connection_stats[address]['count'] += 1
            self.connection_stats[address]['total_time'] += duration
            self.connection_stats[address]['last_connected'] = time.time()

    def handle_client(self, conn: socket.socket,
                      address: Tuple[str, int]) -> None:
        """Handle client connection and search requests."""
        thread_name = threading.current_thread().name
        logging.info(f"[{thread_name}] Handling connection from {address}")

        try:
            with self.lock:
                self.active_connections.add(conn)

            conn.settimeout(1.0)
            buffer = b""
            total_queries = 0

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
                            total_queries += 1
                            self._update_connection_stats(address, duration_ms)

                            if duration_ms > self.max_allowed_time_ms:
                                logging.warning(
                                    f"[{thread_name}]"
                                    f" Slow query from {address}: "
                                    f"'{query[:20]}...' took "
                                    f"{duration_ms:.2f}ms "
                                    f"(limit "
                                    f"{self.max_allowed_time_ms}ms)"
                                )

                            response = ("STRING EXISTS\n"
                                        if exists else "STRING NOT FOUND\n")
                            conn.sendall(response.encode())

                            logging.info(
                                f"[{thread_name}] "
                                f"Query='{query[:20]}...' from {address[0]} "
                                f"Result={'FOUND'
                                          if exists else 'NOT FOUND'} "
                                f"({duration_ms:.2f}ms)"
                            )

                        except UnicodeDecodeError:
                            logging.warning(
                                f"[{thread_name}] "
                                f"Invalid UTF-8 from {address}")
                            conn.sendall(b"STRING NOT FOUND\n")

                except socket.timeout:
                    continue
                except ssl.SSLError as e:
                    logging.error(
                        f"[{thread_name}] SSL error with {address}: {e}")
                    break
        except (ConnectionResetError, BrokenPipeError) as e:
            logging.warning(
                f"[{thread_name}] Client {address} disconnected: {e}")
        except Exception as e:
            logging.exception(
                f"[{thread_name}] Unexpected error with {address}: {e}")
        finally:
            try:
                conn.shutdown(socket.SHUT_RDWR)
                conn.close()
            except Exception as e:
                logging.debug(f"[{thread_name}] "
                              f"Connection close error: {e}")
            finally:
                with self.lock:
                    self.active_connections.discard(conn)
                logging.info(f"[{thread_name}] "
                             f"Closed connection from {address} "
                             f"(processed {total_queries} queries)")

    def start(self) -> None:
        """Start the TCP server with thread pool management."""
        if threading.current_thread() == threading.main_thread():
            def handler(signum, frame) -> None:
                logging.info(
                    f"Received signal {signum}, initiating shutdown...")
                self.shutdown_flag = True

            signal.signal(signal.SIGINT, handler)
            signal.signal(signal.SIGTERM, handler)

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", self.port))
        sock.listen(100)  # Increased backlog
        sock.settimeout(1.0)

        context = None
        if self.ssl_enabled:
            try:
                context = create_ssl_context(
                    self.cert_file, self.key_file, self.ca_file)
                logging.info("SSL enabled with certificate verification")
            except ssl.SSLError as e:
                logging.error(f"SSL setup failed: {e}")
                sys.exit(1)

        logging.info(
            f"Server started on port {
                self.port} with {
                self.thread_pool._max_workers} worker threads")
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
                                do_handshake_on_connect=True,
                                suppress_ragged_eofs=True
                            )
                            if self.ca_file:
                                cert = conn.getpeercert()
                                if not cert:
                                    logging.error(
                                        f"No client certificate"
                                        f" provided from {addr}")
                                    conn.close()
                                    continue
                        except ssl.SSLError as e:
                            logging.error(
                                f"SSL handshake failed with {addr}: {e}")
                            conn.close()
                            continue

                    future = self.thread_pool.submit(
                        self.handle_client, conn, addr)
                    future.add_done_callback(
                        lambda f: logging.debug(
                            f"Client handling completed with {f.exception()}"
                            if f.exception() else "Client"
                            " handling completed successfully"
                        )
                    )
                except socket.timeout:
                    continue
                except ssl.SSLError as e:
                    logging.error(f"SSL error: {e}")
                except OSError as e:
                    if not self.shutdown_flag:
                        logging.error(f"Socket error: {e}")
        except KeyboardInterrupt:
            logging.info("Received keyboard interrupt, shutting down...")
        finally:
            self.cleanup(sock)

    def cleanup(self, sock: Optional[socket.socket] = None) -> None:
        """Clean up server resources with graceful shutdown."""
        logging.info("Initiating graceful shutdown...")
        self.shutdown_flag = True

        # Shutdown thread pool first
        self.thread_pool.shutdown(wait=True, cancel_futures=False)

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
                    self.active_connections.discard(conn)

        # Close main socket
        if sock:
            try:
                sock.close()
            except Exception as e:
                logging.debug(f"Socket close error: {e}")

        # Log connection statistics
        logging.info("Connection statistics:")
        for addr, stats in self.connection_stats.items():
            avg_time = stats['total_time'] / \
                stats['count'] if stats['count'] > 0 else 0
            logging.info(
                f"  {addr[0]}:{addr[1]} - "
                f"Queries: {stats['count']}, "
                f"Avg Time: {avg_time:.2f}ms, "
                f"Last: {time.ctime(stats['last_connected'])}"
            )

        logging.info("Server shutdown complete")


def main() -> None:
    """Main entry point for the server application."""
    # Read max_workers from config or use default
    config = configparser.ConfigParser()
    config.read("config.ini")
    max_workers = config.getint("SERVER", "max_workers", fallback=20)

    server = TCPServer(max_workers=max_workers)

    def handler(signum, frame) -> None:
        logging.info(f"Received signal {signum}")
        server.shutdown_flag = True

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)

    server.start()


if __name__ == "__main__":
    main()
