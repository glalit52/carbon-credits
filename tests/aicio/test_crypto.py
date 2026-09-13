"""ChaCha20-Poly1305, against RFC 8439's own test vectors.

A cipher implemented in this repository has to be verified against the
specification's vectors, not against itself. These are the published ones.
"""

from __future__ import annotations

import pytest

from aicio.crypto import (
    CryptoError, SealedBox, chacha20, decrypt, derive_key, encrypt, poly1305,
)

# RFC 8439 §2.4.2
KEY = bytes(range(32))
NONCE = bytes.fromhex("000000000000004a00000000")
PLAINTEXT = (
    b"Ladies and Gentlemen of the class of '99: If I could offer you only one "
    b"tip for the future, sunscreen would be it."
)
CIPHERTEXT = bytes.fromhex(
    "6e2e359a2568f98041ba0728dd0d6981e97e7aec1d4360c20a27afccfd9fae0bf91b65c5"
    "524733ab8f593dabcd62b3571639d624e65152ab8f530c359f0861d807ca0dbf500d6a61"
    "56a38e088a22b65e52bc514d16ccf806818ce91ab77937365af90bbf74a35be6b40b8eed"
    "f2785e42874d"
)

# RFC 8439 §2.5.2
POLY_KEY = bytes.fromhex(
    "85d6be7857556d337f4452fe42d506a8"      # r
    "0103808afb0db2fd4abff6af4149f51b"      # s
)
POLY_MESSAGE = b"Cryptographic Forum Research Group"
POLY_TAG = bytes.fromhex("a8061dc1305136c6c22b8baf0c0127a9")

# RFC 8439 §2.8.2
AEAD_KEY = bytes.fromhex(
    "808182838485868788898a8b8c8d8e8f909192939495969798999a9b9c9d9e9f"
)
AEAD_NONCE = bytes.fromhex("070000004041424344454647")
AEAD_AAD = bytes.fromhex("50515253c0c1c2c3c4c5c6c7")
AEAD_TAG = bytes.fromhex("1ae10b594f09e26a7e902ecbd0600691")


def test_chacha20_matches_rfc8439():
    assert chacha20(KEY, NONCE, PLAINTEXT, counter=1) == CIPHERTEXT


def test_chacha20_is_its_own_inverse():
    assert chacha20(KEY, NONCE, CIPHERTEXT, counter=1) == PLAINTEXT


def test_poly1305_matches_rfc8439():
    assert poly1305(POLY_KEY, POLY_MESSAGE) == POLY_TAG


def test_aead_matches_rfc8439():
    sealed = encrypt(AEAD_KEY, PLAINTEXT, aad=AEAD_AAD, nonce=AEAD_NONCE)
    assert sealed[-16:] == AEAD_TAG
    assert decrypt(AEAD_KEY, sealed, aad=AEAD_AAD) == PLAINTEXT


def test_a_modified_ciphertext_fails_rather_than_decrypting_to_rubbish():
    sealed = bytearray(encrypt(AEAD_KEY, b"a statement", aad=b"documents"))
    sealed[20] ^= 0x01
    with pytest.raises(CryptoError, match="authentication failed"):
        decrypt(AEAD_KEY, bytes(sealed), aad=b"documents")


def test_wrong_associated_data_fails():
    sealed = encrypt(AEAD_KEY, b"a token", aad=b"connector_tokens")
    with pytest.raises(CryptoError):
        decrypt(AEAD_KEY, sealed, aad=b"documents")


def test_nonces_are_not_reused():
    first = encrypt(AEAD_KEY, b"x")
    second = encrypt(AEAD_KEY, b"x")
    assert first[:12] != second[:12]
    assert first != second


def test_truncated_input_is_rejected():
    with pytest.raises(CryptoError):
        decrypt(AEAD_KEY, b"too short")


def test_key_derivation_is_deterministic_and_salt_sensitive():
    salt = b"0123456789abcdef"
    assert derive_key("secret", salt=salt) == derive_key("secret", salt=salt)
    assert derive_key("secret", salt=salt) != derive_key("secret", salt=b"fedcba9876543210")
    assert derive_key("secret", salt=salt) != derive_key("secret", salt=salt, context="other")


def test_short_salts_are_refused():
    with pytest.raises(CryptoError):
        derive_key("secret", salt=b"short")


def test_sealed_box_round_trips_json():
    box = SealedBox.from_secret("hunter2", salt=b"0123456789abcdef", purpose="documents")
    sealed = box.seal_json({"folio": "12345", "units": 120.5})
    assert box.open_json(sealed)["folio"] == "12345"


def test_a_sealed_token_cannot_be_substituted_for_a_sealed_document():
    """Cross-purpose substitution is the attack that one-key-for-everything
    invites, so the purpose is part of the authentication."""
    documents = SealedBox.from_secret("k", salt=b"0123456789abcdef", purpose="documents")
    tokens = SealedBox(documents.key, "connector_tokens")
    sealed = documents.seal(b"a statement")
    with pytest.raises(CryptoError):
        tokens.open(sealed)


def test_key_fingerprint_identifies_without_revealing():
    box = SealedBox.from_secret("k", salt=b"0123456789abcdef")
    assert len(box.fingerprint()) == 16
    assert box.key.hex() not in box.fingerprint()


def test_environment_refuses_to_invent_a_key(monkeypatch):
    """A deployment with no key configured must fail loudly rather than write
    plaintext and discover it during an audit."""
    monkeypatch.delenv("AICIO_SECRET_KEY", raising=False)
    monkeypatch.delenv("AICIO_SECRET_SALT", raising=False)
    with pytest.raises(CryptoError):
        SealedBox.from_environment()
