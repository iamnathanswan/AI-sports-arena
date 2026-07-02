"""Verify the Kalshi request signature is a valid RSA-PSS-SHA256 signature
over timestamp+METHOD+path, base64-encoded."""

import base64

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from arena.kalshi.client import sign_request


def test_signature_verifies_with_public_key():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()

    ts = 1751904000000
    path = "/trade-api/v2/portfolio/orders"
    signature = sign_request(pem, ts, "post", path)

    key.public_key().verify(
        base64.b64decode(signature),
        f"{ts}POST{path}".encode(),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=hashes.SHA256.digest_size),
        hashes.SHA256(),
    )  # raises InvalidSignature on failure
