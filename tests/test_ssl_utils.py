import datetime
import os
import ssl
import sys
import tempfile
from pathlib import Path
from typing import Tuple

import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

# Fix path for local imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ssl_utils import create_ssl_context  # noqa: E402


# Enhanced Test Fixtures
@pytest.fixture(scope="module")
def rsa_key_pair() -> Tuple[str, str]:
    """Generate RSA key pair for testing."""
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    return (
        key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode(),
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ).decode()
    )


@pytest.fixture
def temp_cert_key() -> Tuple[str, str]:
    """Use existing cert.pem and key.pem files from project root."""
    # Get the absolute path to the project root
    project_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), ".."))
    cert_path = os.path.join(project_root, "cert.pem")
    key_path = os.path.join(project_root, "key.pem")
    if not os.path.exists(cert_path):
        pytest.skip("cert.pem not found in project root directory")
    if not os.path.exists(key_path):
        pytest.skip("key.pem not found in project root directory")

    return cert_path, key_path


@pytest.fixture
def temp_ca_cert() -> str:
    """Generate temporary CA certificate."""
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Test CA"),
        x509.NameAttribute(NameOID.COMMON_NAME, "Test Root CA"),
    ])

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow())
        .not_valid_after(
            datetime.datetime.utcnow() + datetime.timedelta(days=365))
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=None),
            critical=True,
        )
        .sign(key, hashes.SHA256(), default_backend())
    )

    with tempfile.NamedTemporaryFile(mode="wb", delete=False) as ca_file:
        ca_file.write(cert.public_bytes(serialization.Encoding.PEM))
        ca_path = ca_file.name

    yield ca_path

    Path(ca_path).unlink(missing_ok=True)


# Test Cases
class TestSSLUtils:
    """Test suite for SSL utilities."""

    def test_create_ssl_context_success(self, temp_cert_key):
        """Test successful SSL context creation."""
        cert_path, key_path = temp_cert_key
        context = create_ssl_context(cert_path, key_path)

        assert isinstance(context, ssl.SSLContext)
        assert context.protocol == ssl.PROTOCOL_TLS_SERVER
        assert context.minimum_version in {
            ssl.TLSVersion.TLSv1_2, ssl.TLSVersion.TLSv1_3}
        assert (context.options & ssl.OP_NO_SSLv2) == ssl.OP_NO_SSLv2
        assert (context.options & ssl.OP_NO_SSLv3) == ssl.OP_NO_SSLv3
        assert (context.options & ssl.OP_NO_TLSv1) == ssl.OP_NO_TLSv1
        assert (context.options & ssl.OP_NO_TLSv1_1) == ssl.OP_NO_TLSv1_1

    def test_create_ssl_context_with_ca(self, temp_cert_key, temp_ca_cert):
        """Test SSL context creation with CA certificate."""
        cert_path, key_path = temp_cert_key
        context = create_ssl_context(cert_path, key_path, temp_ca_cert)

        assert context.verify_mode == ssl.CERT_REQUIRED
        assert len(context.get_ca_certs()) > 0

    def test_missing_cert_file(self):
        """Test handling of missing certificate file."""
        with pytest.raises(FileNotFoundError) as excinfo:
            create_ssl_context("nonexistent_cert.pem", "dummy.key")
        assert excinfo.value.errno == 2
        assert "nonexistent_cert.pem" in str(excinfo.value)

    def test_missing_key_file(self, temp_cert_key):
        """Test handling of missing key file."""
        cert_path, _ = temp_cert_key
        with pytest.raises(FileNotFoundError) as excinfo:
            create_ssl_context(cert_path, "nonexistent_key.pem")
        assert excinfo.value.errno == 2
        assert "nonexistent_key.pem" in str(excinfo.value)

    def test_invalid_cert_format(self, tmp_path):
        """Test handling of invalid certificate format."""
        cert = tmp_path / "invalid_cert.pem"
        key = tmp_path / "invalid_key.pem"
        cert.write_text("INVALID CERT DATA")
        key.write_text("INVALID KEY DATA")

        with pytest.raises(ValueError):
            create_ssl_context(str(cert), str(key))

    def test_mismatched_cert_key(self, temp_cert_key):
        """Test handling of mismatched certificate and key."""
        cert_path, key_path = temp_cert_key

        # Create a new key that doesn't match the cert
        new_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        new_key_pem = new_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ).decode()

        with tempfile.NamedTemporaryFile(mode="w",
                                         delete=False) as wrong_key_file:
            wrong_key_file.write(new_key_pem)
            wrong_key_path = wrong_key_file.name

        try:
            with pytest.raises(ssl.SSLError):
                create_ssl_context(cert_path, wrong_key_path)
        finally:
            Path(wrong_key_path).unlink(missing_ok=True)

    def test_expired_certificate(self, rsa_key_pair):
        """Test handling of expired certificate."""
        _, private_key_pem = rsa_key_pair
        key = serialization.load_pem_private_key(
            private_key_pem.encode(),
            password=None,
            backend=default_backend()
        )

        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "expired.local"),
        ])

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject) .issuer_name(issuer) .public_key(
                key.public_key()) .serial_number(
                x509.random_serial_number()) .not_valid_before(
                datetime.datetime.now(
                    datetime.timezone.utc) -
                datetime.timedelta(
                    days=2)) .not_valid_after(
                datetime.datetime.now(
                    datetime.timezone.utc) -
                datetime.timedelta(
                    days=1)) .sign(
                key,
                hashes.SHA256(),
                default_backend()))

        with tempfile.NamedTemporaryFile(mode="wb", delete=False) as cert_file:
            cert_file.write(cert.public_bytes(serialization.Encoding.PEM))
            cert_path = cert_file.name

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as key_file:
            key_file.write(private_key_pem)
            key_path = key_file.name

        try:
            # Expect either SSLError or ValueError depending on Python version
            with pytest.raises((ssl.SSLError, ValueError)) as excinfo:
                create_ssl_context(cert_path, key_path)

            # Verify the error contains appropriate message
            error_msg = str(excinfo.value).lower()
            assert any(
                term in error_msg for term in [
                    "expired",
                    "invalid",
                    "verify failed",
                    "not valid"])
        finally:
            Path(cert_path).unlink(missing_ok=True)
            Path(key_path).unlink(missing_ok=True)
