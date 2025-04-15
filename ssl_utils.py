"""
SSL Context Management
"""
import os
import ssl
import datetime
from typing import Optional
from cryptography import x509
from cryptography.hazmat.backends import default_backend
import errno


def create_ssl_context(
        certfile: str,
        keyfile: str,
        cafile: Optional[str] = None) -> ssl.SSLContext:
    """Create and configure an SSL context with proper security settings.

    Args:
        certfile: Path to server certificate
        keyfile: Path to server private key
        cafile: Path to CA certificate for client verification (optional)

    Returns:
        Configured SSLContext object
    """

    if not os.path.exists(certfile):
        raise FileNotFoundError(
            errno.ENOENT, os.strerror(
                errno.ENOENT), certfile)
    if not os.path.exists(keyfile):
        raise FileNotFoundError(
            errno.ENOENT, os.strerror(
                errno.ENOENT), keyfile)

    # Check expiration manually
    with open(certfile, "rb") as f:
        cert_data = f.read()
    cert = x509.load_pem_x509_certificate(cert_data, default_backend())
    now = datetime.datetime.utcnow()
    if cert.not_valid_before > now or cert.not_valid_after < now:
        raise ssl.SSLError("Certificate is expired or not yet valid.")

    # SSL context setup
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certfile, keyfile)

    # Set strong security options
    context.options |= ssl.OP_NO_SSLv2
    context.options |= ssl.OP_NO_SSLv3
    context.options |= ssl.OP_NO_TLSv1
    context.options |= ssl.OP_NO_TLSv1_1
    context.minimum_version = ssl.TLSVersion.TLSv1_2

    # Configure client certificate verification if needed
    if cafile:
        context.verify_mode = ssl.CERT_REQUIRED
        context.load_verify_locations(cafile)

    return context
