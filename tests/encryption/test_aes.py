from __future__ import annotations

import base64
import hashlib
from typing import TYPE_CHECKING

import pytest

from flask_htmx_template import exceptions as exc

if TYPE_CHECKING:
    from flask_htmx_template.encryption.base import EncryptionInterface
    from tests.conftest import RandomStringGenerator

try:
    from flask_htmx_template.encryption.aes import EncryptionAES as Encryption
except ImportError:
    no_encryption = True
    from flask_htmx_template.encryption.base import NoEncryption as Encryption
else:
    no_encryption = False

NO_ENCRYPTION = no_encryption


@pytest.fixture
def key(rand_str_generator: RandomStringGenerator) -> str:
    """Generate a random key.

    Returns:
        key

    """
    return rand_str_generator()


@pytest.fixture
def secret(rand_str_generator: RandomStringGenerator) -> str:
    """Generate a random secret.

    Returns:
        secret

    """
    return rand_str_generator()


@pytest.fixture
def encryption(key: str) -> tuple[EncryptionInterface, bytes]:
    """Generate an encryption object.

    Returns:
        tuple(Encryption, Encryption config)

    """
    return Encryption.create(key)


@pytest.fixture
def secret_encrypted(encryption: tuple[EncryptionInterface, bytes], secret: str) -> str:
    """Encrypt a secret.

    Returns:
        Encrypted secret

    """
    return encryption[0].encrypt(secret)


@pytest.mark.skipif(NO_ENCRYPTION, reason="No encryption available")
@pytest.mark.encryption
def test_encrypt(secret: str, secret_encrypted: str) -> None:
    assert secret_encrypted != secret
    assert base64.b64decode(secret_encrypted) != secret


@pytest.mark.skipif(NO_ENCRYPTION, reason="No encryption available")
@pytest.mark.encryption
def test_decrypt(
    encryption: tuple[EncryptionInterface, bytes],
    secret: str,
    secret_encrypted: str,
) -> None:
    decrypted = encryption[0].decrypt_s(secret_encrypted)
    assert decrypted == secret


@pytest.mark.skipif(NO_ENCRYPTION, reason="No encryption available")
@pytest.mark.encryption
def test_key_hash(encryption: tuple[EncryptionInterface, bytes], key: str) -> None:
    enc, enc_config = encryption
    assert key != enc.hashed_key
    assert hashlib.sha256(key.encode()).digest() != enc.hashed_key
    assert key.encode() not in enc.hashed_key
    assert key.encode() not in enc_config


@pytest.mark.skipif(NO_ENCRYPTION, reason="No encryption available")
@pytest.mark.encryption
def test_load_config(
    encryption: tuple[EncryptionInterface, bytes],
    key: str,
    secret: str,
    secret_encrypted: str,
) -> None:
    # Load from enc_config
    enc_loaded = Encryption(key, encryption[1])
    decrypted = enc_loaded.decrypt_s(secret_encrypted)
    assert decrypted == secret


@pytest.mark.skipif(NO_ENCRYPTION, reason="No encryption available")
@pytest.mark.encryption
def test_load_config_bad_version() -> None:
    with pytest.raises(exc.UnknownEncryptionVersionError):
        Encryption("", b"a:bc")


@pytest.mark.skipif(NO_ENCRYPTION, reason="No encryption available")
@pytest.mark.encryption
def test_bad_key(
    rand_str_generator: RandomStringGenerator,
    encryption: tuple[EncryptionInterface, bytes],
    key: str,
    secret: str,
    secret_encrypted: str,
) -> None:
    bad_key = key + rand_str_generator()
    enc_bad = Encryption(bad_key, encryption[1])

    try:
        secret_bad = enc_bad.decrypt_s(secret_encrypted)
    except ValueError:
        pass  # Expected mismatch of padding
    else:
        # Sometimes decrypting is valid but yields wrong secret
        assert secret_bad != secret
