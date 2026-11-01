"""What a Web Push message is made of: its body encrypted for one browser (RFC 8291,
`aes128gcm`), and the server's signed claim that it may push there (VAPID, RFC 8292).

The push service in between (Apple's, Google's, Mozilla's) carries the body without being
able to read it; only the browser that subscribed holds the key."""

from __future__ import annotations

import base64
import json
import os
import struct
import time
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

RECORD_SIZE = 4096
# A claim lives at most a day (RFC 8292 §2); twelve hours leaves room for a skewed clock.
CLAIM_SECONDS = 12 * 3600
_POINT = serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64url(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def new_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


def private_raw(key: ec.EllipticCurvePrivateKey) -> str:
    return b64url(key.private_numbers().private_value.to_bytes(32, "big"))


def private_from(raw: str) -> ec.EllipticCurvePrivateKey:
    return ec.derive_private_key(int.from_bytes(unb64url(raw), "big"), ec.SECP256R1())


def public_raw(key: ec.EllipticCurvePrivateKey) -> str:
    """The key a page hands `pushManager.subscribe` as `applicationServerKey`."""
    return b64url(key.public_key().public_bytes(*_POINT))


def _hkdf(salt: bytes, ikm: bytes, info: bytes, length: int) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(ikm)


def encrypt(
    payload: bytes,
    p256dh: str,
    auth: str,
    salt: bytes | None = None,
    sender: ec.EllipticCurvePrivateKey | None = None,
) -> bytes:
    """The body for one subscription, as one record. `salt` and `sender` are fresh for
    every message; a test passes its own to check against the RFC's worked example."""
    ua_public = unb64url(p256dh)
    sender = sender or new_key()
    as_public = sender.public_key().public_bytes(*_POINT)
    peer = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public)
    shared = sender.exchange(ec.ECDH(), peer)
    ikm = _hkdf(unb64url(auth), shared, b"WebPush: info\x00" + ua_public + as_public, 32)
    salt = salt or os.urandom(16)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    # The 0x02 marks the last (here the only) record; no padding follows it.
    sealed = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)
    header = salt + struct.pack("!IB", RECORD_SIZE, len(as_public)) + as_public
    return header + sealed


def vapid_header(
    endpoint: str, key: ec.EllipticCurvePrivateKey, subject: str, now: float | None = None
) -> str:
    """The `Authorization` value that tells the push service this server holds the key the
    browser subscribed with. `subject` is how its operator reaches the sender: an https URL
    or a mailto."""
    parts = urlsplit(endpoint)
    claims = {
        "aud": f"{parts.scheme}://{parts.netloc}",
        "exp": int((now if now is not None else time.time()) + CLAIM_SECONDS),
        "sub": subject,
    }
    head = b64url(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    body = b64url(json.dumps(claims, separators=(",", ":")).encode())
    signed = f"{head}.{body}".encode()
    r, s = decode_dss_signature(key.sign(signed, ec.ECDSA(hashes.SHA256())))
    signature = b64url(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
    return f"vapid t={head}.{body}.{signature}, k={public_raw(key)}"
