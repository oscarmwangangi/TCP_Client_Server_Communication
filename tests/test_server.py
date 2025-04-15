import configparser
import datetime
import logging
import socket
import threading
from unittest.mock import MagicMock, mock_open, patch

import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from server import TCPServer


MOCK_CONFIG = {
    "SERVER": {
        "port": "5555",
        "max_allowed_time_ms": "1000",
        "reread_on_query": "False",
        "ssl_enabled": "False",
        "max_workers": "10"
    },
    "SSL": {
        "certfile": "",
        "keyfile": "",
        "cafile": ""
    },
    "PATHS": {
        "linuxpath": "test_data.txt"
    }
}

# Create a fixture to mock the config file


@pytest.fixture(autouse=True)
def mock_config():
    with patch('configparser.ConfigParser') as mock_configparser:
        mock_config = configparser.ConfigParser()
        mock_config.read_dict(MOCK_CONFIG)
        mock_configparser.return_value = mock_config
        yield


# Now import the server module after setting up the mocks

# Test data
TEST_DATA = """7;0;6;28;0;23;5;0;
10;0;1;26;0;8;3;0;
1;2;3;
"""


@pytest.fixture
def temp_cert_key(tmp_path):
    """Generate temporary SSL certificate and key for testing."""
    # Generate private key
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    key_path = tmp_path / "key.pem"
    with open(key_path, "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ))

    # Generate self-signed certificate
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, u"localhost"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow())
        .not_valid_after(
            datetime.datetime.utcnow() + datetime.timedelta(days=1)
        )
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(u"localhost")]),
            critical=False,
        )
        .sign(key, hashes.SHA256(), default_backend())
    )
    cert_path = tmp_path / "cert.pem"
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    return str(cert_path), str(key_path)


@pytest.fixture
def test_server():
    """Fixture providing a test server instance."""
    with patch("builtins.open", mock_open(read_data=TEST_DATA)):
        server = TCPServer()
        server.shutdown_flag = False
        yield server
        dummy_sock = MagicMock()
        server.cleanup(dummy_sock)

# Rest of your test functions remain the same...


def test_handle_client_normal_query(test_server, caplog):
    """Test handling of a normal client query."""
    caplog.set_level(logging.INFO)
    mock_conn = MagicMock()
    mock_conn.recv.side_effect = [b"7;0;6;28;0;23;5;0;\x00", b""]
    test_server.handle_client(mock_conn, ("127.0.0.1", 12345))
    mock_conn.sendall.assert_called_once_with(b"STRING EXISTS\n")
    logs = caplog.text
    assert "127.0.0.1" in logs
    assert "7;0;6;28;0;23;5;0;" in logs
    assert "FOUND" in logs


def test_handle_client_not_found(test_server, caplog):
    """Test handling of a not found query."""
    caplog.set_level(logging.INFO)
    mock_conn = MagicMock()
    mock_conn.recv.side_effect = [b"nonexistent_string\x00", b""]
    test_server.handle_client(mock_conn, ("127.0.0.1", 12345))
    mock_conn.sendall.assert_called_once_with(b"STRING NOT FOUND\n")
    assert "Result=NOT FOUND" in caplog.text


@pytest.mark.timeout(2)
def test_client_timeout_handling(test_server):
    """Test handling of client timeout."""
    mock_conn = MagicMock()
    mock_conn.recv.side_effect = [socket.timeout(), socket.timeout(), b""]
    test_server.handle_client(mock_conn, ("127.0.0.1", 12345))
    assert mock_conn.recv.call_count == 3
    assert mock_conn.close.call_count == 1
    assert not mock_conn.sendall.called


def test_client_disconnect_during_query(test_server):
    """Test handling of client disconnection."""
    mock_conn = MagicMock()
    mock_conn.recv.side_effect = ConnectionResetError()
    test_server.handle_client(mock_conn, ("127.0.0.1", 12345))
    mock_conn.close.assert_called_once()


def test_multiple_packets_received(test_server):
    """Test handling of multiple packet reception."""
    mock_conn = MagicMock()
    mock_conn.recv.side_effect = [b"7;0;6;28", b";0;23;5;0;\x00", b""]
    test_server.handle_client(mock_conn, ("127.0.0.1", 12345))
    mock_conn.sendall.assert_called_once_with(b"STRING EXISTS\n")


def test_empty_query(test_server):
    """Test handling of empty queries."""
    mock_conn = MagicMock()
    mock_conn.recv.side_effect = [b"\x00", b""]
    test_server.handle_client(mock_conn, ("127.0.0.1", 12345))
    mock_conn.sendall.assert_called_once_with(b"STRING NOT FOUND\n")


def test_multiple_simultaneous_connections(test_server):
    """Test handling of multiple simultaneous connections."""
    mock_conn1 = MagicMock()
    mock_conn2 = MagicMock()
    mock_conn1.recv.side_effect = [b"query1\x00", b""]
    mock_conn2.recv.side_effect = [b"query2\x00", b""]

    thread1 = threading.Thread(
        target=test_server.handle_client,
        args=(mock_conn1, ("127.0.0.1", 12345))
    )
    thread2 = threading.Thread(
        target=test_server.handle_client,
        args=(mock_conn2, ("127.0.0.1", 12346)))

    thread1.start()
    thread2.start()
    thread1.join()
    thread2.join()

    assert mock_conn1.sendall.called
    assert mock_conn2.sendall.called


def test_cleanup_with_active_connections(test_server):
    """Test cleanup with active connections."""
    mock_conn = MagicMock()
    test_server.active_connections.add(mock_conn)
    test_server.cleanup(MagicMock())
    mock_conn.close.assert_called_once()


def test_high_connection_load(test_server):
    """Test server under concurrent load."""
    def mock_client(query):
        mock_conn = MagicMock()
        mock_conn.recv.side_effect = [query.encode() + b"\x00", b""]
        test_server.handle_client(mock_conn, ("127.0.0.1", 12345))
        return mock_conn

    threads = []
    for i in range(100):
        t = threading.Thread(target=mock_client, args=(f"query_{i}",))
        threads.append(t)
        t.start()
    for t in threads:
        t.join()

    assert len(test_server.active_connections) == 0


if __name__ == "__main__":
    pytest.main(["-v", "--capture=no"])
