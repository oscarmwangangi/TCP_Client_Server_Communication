import ssl
import os
import tempfile
from typing import Optional

import datetime
import pytest

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


# SSL Utilities Implementation
def create_ssl_context(
        certfile: str,
        keyfile: str
) -> Optional[ssl.SSLContext]:
    """Create and configure SSL context with certificate verification."""
    if not os.path.exists(certfile):
        raise FileNotFoundError(f"Certificate file not found: {certfile}")
    if not os.path.exists(keyfile):
        raise FileNotFoundError(f"Key file not found: {keyfile}")

    try:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile, keyfile)
        context.verify_mode = ssl.CERT_REQUIRED
        context.check_hostname = True
        return context
    except ssl.SSLError as e:
        raise ValueError(f"Invalid certificate or key: {e}")


# Test Fixtures and Cases
@pytest.fixture
def temp_cert_key():
    """Generate temporary valid certificate and key files."""
    # Generate private key
    key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )

    # Generate self-signed certificate
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "California"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Test Company"),
            x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
        ]
    )

    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.UTC))
        .not_valid_after(
            datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1)
        )
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("localhost")]),
            critical=False,
        )
        .sign(key, hashes.SHA256(), default_backend())
    )

    # Write to temporary files
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pem") as cert_file:
        cert_file.write(cert.public_bytes(serialization.Encoding.PEM))
        cert_path = cert_file.name

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pem") as key_file:
        key_file.write(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        key_path = key_file.name

    yield cert_path, key_path

    # Cleanup
    os.unlink(cert_path)
    os.unlink(key_path)


def test_ssl_context_creation(temp_cert_key):
    """Test successful SSL context creation."""
    cert_path, key_path = temp_cert_key
    context = create_ssl_context(cert_path, key_path)
    assert context is not None
    assert isinstance(context, ssl.SSLContext)
    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED


def test_missing_cert_file():
    """Test handling of missing certificate file."""
    with pytest.raises(FileNotFoundError):
        create_ssl_context("missing_cert.pem", "dummy.key")


def test_missing_key_file(temp_cert_key):
    """Test handling of missing key file."""
    cert_path, _ = temp_cert_key
    with pytest.raises(FileNotFoundError):
        create_ssl_context(cert_path, "missing_key.pem")


def test_invalid_cert_file(tmp_path):
    """Test handling of invalid certificate format."""
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    cert.write_text("INVALID CERT")
    key.write_text("INVALID KEY")

    with pytest.raises(ValueError):
        create_ssl_context(str(cert), str(key))


if __name__ == "__main__":
    # Run tests when executed directly
    pytest.main(["-v", "--capture=no"])
