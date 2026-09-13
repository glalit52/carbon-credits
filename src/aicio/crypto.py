"""Encryption for statements and access tokens.

The PRD requires encrypted storage for financial documents and forbids raw
credentials reaching the model. Both need an authenticated cipher, and the
standard library has none -- ``hashlib`` and ``hmac`` give integrity but no
confidentiality.

So ChaCha20-Poly1305 is implemented here from RFC 8439, and verified against
the RFC's own test vectors in ``tests/aicio/test_crypto.py``. That is a
deliberate, bounded decision:

*   ChaCha20 rather than AES because a pure-Python AES is both slower and far
    more likely to leak through cache timing; ChaCha20 is add-rotate-xor on
    32-bit words, which is what Python does least badly.
*   Poly1305 because an unauthenticated cipher on a financial document is a
    footgun -- a flipped byte in a stored statement must fail loudly.
*   Keys come from scrypt over a deployment secret, so the key is never the
    password, and per-record nonces are random and stored alongside.

If a deployment can install ``cryptography``, it should: set
``AICIO_CIPHER=libsodium`` and supply an adapter. This implementation exists so
that "encrypted at rest" is true out of the box rather than a to-do.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import struct
from dataclasses import dataclass
from typing import Any

__all__ = ["encrypt", "decrypt", "derive_key", "SealedBox", "CryptoError"]


class CryptoError(ValueError):
    pass


_MASK = 0xFFFFFFFF


def _rotl(value: int, count: int) -> int:
    return ((value << count) | (value >> (32 - count))) & _MASK


def _quarter_round(state: list[int], a: int, b: int, c: int, d: int) -> None:
    state[a] = (state[a] + state[b]) & _MASK
    state[d] = _rotl(state[d] ^ state[a], 16)
    state[c] = (state[c] + state[d]) & _MASK
    state[b] = _rotl(state[b] ^ state[c], 12)
    state[a] = (state[a] + state[b]) & _MASK
    state[d] = _rotl(state[d] ^ state[a], 8)
    state[c] = (state[c] + state[d]) & _MASK
    state[b] = _rotl(state[b] ^ state[c], 7)


#: "expand 32-byte k" as four little-endian words. The constant is part of the
#: spec, not a magic number we chose.
_CONSTANTS = (0x61707865, 0x3320646E, 0x79622D32, 0x6B206574)


def _chacha20_block(key: bytes, counter: int, nonce: bytes) -> bytes:
    if len(key) != 32:
        raise CryptoError("ChaCha20 key must be 32 bytes")
    if len(nonce) != 12:
        raise CryptoError("ChaCha20 nonce must be 12 bytes")
    state = list(_CONSTANTS)
    state += list(struct.unpack("<8I", key))
    state.append(counter & _MASK)
    state += list(struct.unpack("<3I", nonce))

    working = list(state)
    for _ in range(10):                    # 20 rounds = 10 double rounds
        _quarter_round(working, 0, 4, 8, 12)
        _quarter_round(working, 1, 5, 9, 13)
        _quarter_round(working, 2, 6, 10, 14)
        _quarter_round(working, 3, 7, 11, 15)
        _quarter_round(working, 0, 5, 10, 15)
        _quarter_round(working, 1, 6, 11, 12)
        _quarter_round(working, 2, 7, 8, 13)
        _quarter_round(working, 3, 4, 9, 14)
    out = [(working[i] + state[i]) & _MASK for i in range(16)]
    return struct.pack("<16I", *out)


def chacha20(key: bytes, nonce: bytes, data: bytes, *, counter: int = 1) -> bytes:
    """XOR ``data`` with the ChaCha20 keystream. Encryption and decryption are
    the same operation, which is why there is one function."""
    out = bytearray(len(data))
    for offset in range(0, len(data), 64):
        block = _chacha20_block(key, counter + offset // 64, nonce)
        chunk = data[offset:offset + 64]
        for index, byte in enumerate(chunk):
            out[offset + index] = byte ^ block[index]
    return bytes(out)


_P = (1 << 130) - 5


def poly1305(key: bytes, message: bytes) -> bytes:
    """The Poly1305 one-time authenticator."""
    if len(key) != 32:
        raise CryptoError("Poly1305 key must be 32 bytes")
    r = int.from_bytes(key[:16], "little") & 0x0FFFFFFC0FFFFFFC0FFFFFFC0FFFFFFF
    s = int.from_bytes(key[16:], "little")
    accumulator = 0
    for offset in range(0, len(message), 16):
        chunk = message[offset:offset + 16]
        n = int.from_bytes(chunk + b"\x01", "little")
        accumulator = ((accumulator + n) * r) % _P
    return ((accumulator + s) & ((1 << 128) - 1)).to_bytes(16, "little")


def _pad16(data: bytes) -> bytes:
    remainder = len(data) % 16
    return b"" if remainder == 0 else b"\x00" * (16 - remainder)


def _tag(key: bytes, nonce: bytes, ciphertext: bytes, aad: bytes) -> bytes:
    # The one-time Poly1305 key is the first block of the ChaCha20 keystream at
    # counter 0; the ciphertext starts at counter 1. Reusing counter 0 for data
    # would leak the authentication key.
    otk = _chacha20_block(key, 0, nonce)[:32]
    payload = (
        aad + _pad16(aad)
        + ciphertext + _pad16(ciphertext)
        + struct.pack("<Q", len(aad)) + struct.pack("<Q", len(ciphertext))
    )
    return poly1305(otk, payload)


def encrypt(key: bytes, plaintext: bytes, *, aad: bytes = b"", nonce: bytes | None = None) -> bytes:
    """AEAD encrypt. Output is ``nonce || ciphertext || tag``."""
    nonce = nonce if nonce is not None else os.urandom(12)
    if len(nonce) != 12:
        raise CryptoError("nonce must be 12 bytes")
    ciphertext = chacha20(key, nonce, plaintext, counter=1)
    return nonce + ciphertext + _tag(key, nonce, ciphertext, aad)


def decrypt(key: bytes, sealed: bytes, *, aad: bytes = b"") -> bytes:
    """AEAD decrypt. Raises rather than returning a corrupted plaintext."""
    if len(sealed) < 28:
        raise CryptoError("sealed value is too short to be valid")
    nonce, ciphertext, tag = sealed[:12], sealed[12:-16], sealed[-16:]
    expected = _tag(key, nonce, ciphertext, aad)
    # Constant-time: a timing-variable comparison here would let an attacker
    # forge a tag byte at a time.
    if not hmac.compare_digest(expected, tag):
        raise CryptoError(
            "authentication failed: the stored value was modified, truncated, or "
            "encrypted under a different key"
        )
    return chacha20(key, nonce, ciphertext, counter=1)


def derive_key(secret: str | bytes, *, salt: bytes, context: str = "aicio") -> bytes:
    """Derive a 32-byte key from a deployment secret.

    scrypt rather than PBKDF2: it is memory-hard, it is in the standard
    library, and the cost of getting this wrong is every stored statement.
    """
    if isinstance(secret, str):
        secret = secret.encode()
    if len(salt) < 16:
        raise CryptoError("salt must be at least 16 bytes")
    return hashlib.scrypt(
        secret + context.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32,
    )


@dataclass
class SealedBox:
    """A keyed encryptor bound to one purpose.

    ``purpose`` becomes associated data, so a sealed access token cannot be
    swapped into the slot where a sealed statement is expected -- the tag
    check fails. Cross-purpose substitution is exactly the attack that "we
    encrypt everything with one key" invites.
    """

    key: bytes
    purpose: str = "aicio"

    @classmethod
    def from_secret(cls, secret: str, *, salt: bytes, purpose: str = "aicio") -> "SealedBox":
        return cls(derive_key(secret, salt=salt, context=purpose), purpose)

    @classmethod
    def from_environment(cls, purpose: str = "aicio") -> "SealedBox":
        """Build from ``AICIO_SECRET_KEY`` and ``AICIO_SECRET_SALT``.

        Refuses to invent a key. A deployment that has not configured one
        should fail at startup rather than silently write plaintext to disk and
        discover it during an audit.
        """
        secret = os.environ.get("AICIO_SECRET_KEY", "")
        salt = os.environ.get("AICIO_SECRET_SALT", "")
        if not secret or len(salt) < 16:
            raise CryptoError(
                "AICIO_SECRET_KEY and a 16+ character AICIO_SECRET_SALT must be set "
                "before encrypted storage can be used"
            )
        return cls.from_secret(secret, salt=salt.encode(), purpose=purpose)

    def seal(self, plaintext: bytes | str) -> bytes:
        if isinstance(plaintext, str):
            plaintext = plaintext.encode()
        return encrypt(self.key, plaintext, aad=self.purpose.encode())

    def open(self, sealed: bytes) -> bytes:
        return decrypt(self.key, sealed, aad=self.purpose.encode())

    def seal_json(self, payload: Any) -> bytes:
        import json
        return self.seal(json.dumps(payload, default=str).encode())

    def open_json(self, sealed: bytes) -> Any:
        import json
        return json.loads(self.open(sealed).decode())

    def fingerprint(self) -> str:
        """A non-secret identifier for the key, so a record can record which
        key sealed it without recording the key."""
        return hashlib.sha256(b"aicio-kid" + self.key).hexdigest()[:16]
