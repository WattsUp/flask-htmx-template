"""Encryption provider using AES encyrption."""

from __future__ import annotations

import base64
import hashlib
import secrets
from typing import override, TYPE_CHECKING

import Cryptodome.Random
from Cryptodome.Cipher import AES
from Cryptodome.Hash import SHA256

from flask_htmx_template import exceptions as exc
from flask_htmx_template.encryption import base

if TYPE_CHECKING:
    from Cryptodome.Cipher._mode_cbc import CbcMode


class EncryptionAES(base.EncryptionInterface):
    """Encryption provider.

    Uses AES encryption for encryption and decryption
    """

    def __init__(self, key: bytes | str, config: bytes | str) -> None:
        """Initialize EncryptionAES.

        Args:
            key: encryption key
            config: Encryption config string

        Raises:
            UnknownEncryptionVersionError: If encryption version is unknown

        """
        super().__init__(key, config)
        key = key.encode() if isinstance(key, str) else bytes(key)
        config = config.encode() if isinstance(config, str) else bytes(config)
        config_parts = config.split(b":")

        key_version = config_parts[0]
        if key_version != b"1":
            raise exc.UnknownEncryptionVersionError
        salt = config_parts[1]

        self._hased_key = hashlib.sha256(key + salt).digest()

    @classmethod
    @override
    def create(cls, key: bytes | str) -> tuple[EncryptionAES, bytes]:
        salt = secrets.token_urlsafe(32).encode()
        config = b":".join((b"1", salt))
        return EncryptionAES(key, config), config

    @property
    @override
    def hashed_key(self) -> bytes:
        return self._hased_key

    def _digest_key(self) -> bytes:
        """Get digest key.

        Hashes the key to get a fixed length key

        Returns:
            bytes hashed key

        """
        return SHA256.new(self._hased_key).digest()

    def _get_aes(self, iv: bytes) -> CbcMode:
        """Get AES cipher from digest key and initialization vector.

        Args:
            iv: Initialization vector

        Returns:
            AES cipher object

        """
        return AES.new(self._digest_key(), AES.MODE_CBC, iv)

    @override
    def encrypt(self, secret: bytes | str) -> str:
        secret_b = secret.encode() if isinstance(secret, str) else bytes(secret)

        # Generate a random initialization vector
        iv = Cryptodome.Random.new().read(AES.block_size)
        aes = self._get_aes(iv)

        # Add padding the secret to fit in whole blocks
        # Always adds at least 1 byte of padding
        padding = AES.block_size - len(secret_b) % AES.block_size
        secret_b += bytes([padding]) * padding

        # Prepend initialization vector to encrypted secret
        data = iv + aes.encrypt(secret_b)

        return base64.b64encode(data).decode()

    @override
    def decrypt(self, enc_secret: str) -> bytes:
        # Un-stringify bytes
        enc_secret_b = base64.b64decode(enc_secret)

        # Get the AES cipher from the included initialization vector
        iv = enc_secret_b[: AES.block_size]
        aes = self._get_aes(iv)

        # Decrypt secret and get length of padding
        data = aes.decrypt(enc_secret_b[AES.block_size :])
        padding = data[-1]

        # Validate padding is unchanged
        if data[-padding:] != bytes([padding]) * padding:  # pragma: no cover
            # Cannot guarantee this gets covered by a bad key test
            # Some bad keys decrypt with valid padding but the decoded secret is wrong
            msg = "Invalid padding"
            raise ValueError(msg)

        return data[:-padding]

    @override
    def decrypt_s(self, enc_secret: str) -> str:
        return self.decrypt(enc_secret).decode()
