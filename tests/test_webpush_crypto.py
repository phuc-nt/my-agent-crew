import json
import struct

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from my_agent_crew.webpush import crypto

# RFC 8291 §5, the worked example.
PLAINTEXT = b"When I grow up, I want to be a watermelon"
AS_PRIVATE = "yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"
UA_PRIVATE = "q1dXpw3UpT5VOmu_cf_v6ih07Aems3njxI-JWgLcM94"
UA_PUBLIC = (
    "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4"
)
AUTH = "BTBZMqHH6r4Tts7J_aSIgg"
SALT = "DGv6ra1nlYgDCS1FRnbzlw"


def _hkdf(salt: bytes, ikm: bytes, info: bytes, length: int) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(ikm)


def decrypt(body: bytes, ua_private: str, auth: str) -> bytes:
    """What the browser does with the body: an independent reading of RFC 8291."""
    salt, (rs, idlen) = body[:16], struct.unpack("!IB", body[16:21])
    as_public = body[21 : 21 + idlen]
    assert rs == crypto.RECORD_SIZE
    ua = crypto.private_from(ua_private)
    ua_public = crypto.unb64url(crypto.public_raw(ua))
    peer = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_public)
    shared = ua.exchange(ec.ECDH(), peer)
    info = b"WebPush: info\x00" + ua_public + as_public
    ikm = _hkdf(crypto.unb64url(auth), shared, info, 32)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    plain = AESGCM(cek).decrypt(nonce, body[21 + idlen :], None)
    assert plain.endswith(b"\x02")
    return plain[:-1]


def test_the_rfc_example_encrypts_to_the_rfc_body():
    body = crypto.encrypt(
        PLAINTEXT,
        UA_PUBLIC,
        AUTH,
        salt=crypto.unb64url(SALT),
        sender=crypto.private_from(AS_PRIVATE),
    )
    assert body[:16] == crypto.unb64url(SALT)
    assert decrypt(body, UA_PRIVATE, AUTH) == PLAINTEXT
    # The RFC's own ciphertext: the record after the header.
    assert crypto.b64url(body[86:]) == (
        "8pfeW0KbunFT06SuDKoJH9Ql87S1QUrdirN6GcG7sFz1y1sqLgVi1VhjVkHsUoEsbI_0LpXMuGvnzQ"
    )


def test_a_fresh_message_round_trips_and_never_repeats():
    ua = crypto.new_key()
    auth = crypto.b64url(b"0123456789abcdef")
    first = crypto.encrypt(b'{"title":"x"}', crypto.public_raw(ua), auth)
    second = crypto.encrypt(b'{"title":"x"}', crypto.public_raw(ua), auth)
    assert first != second
    assert decrypt(first, crypto.private_raw(ua), auth) == b'{"title":"x"}'


def test_a_key_survives_its_raw_form():
    key = crypto.new_key()
    again = crypto.private_from(crypto.private_raw(key))
    assert crypto.public_raw(again) == crypto.public_raw(key)
    assert len(crypto.unb64url(crypto.public_raw(key))) == 65


def test_the_vapid_claim_names_the_push_service_and_verifies():
    key = crypto.new_key()
    header = crypto.vapid_header(
        "https://push.example.net/send/abc", key, "https://crew.example", now=1000
    )
    token, public = header.removeprefix("vapid t=").split(", k=")
    assert public == crypto.public_raw(key)
    head, body, signature = token.split(".")
    claims = json.loads(crypto.unb64url(body))
    assert claims == {
        "aud": "https://push.example.net",
        "exp": 1000 + crypto.CLAIM_SECONDS,
        "sub": "https://crew.example",
    }
    assert json.loads(crypto.unb64url(head)) == {"typ": "JWT", "alg": "ES256"}
    raw = crypto.unb64url(signature)
    der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
    key.public_key().verify(der, f"{head}.{body}".encode(), ec.ECDSA(hashes.SHA256()))
