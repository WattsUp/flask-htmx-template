"""Encryption provider interface."""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from typing import override


class EncryptionInterface(ABC):
    """Encryption provider interface."""

    def __init__(self, key: bytes | str, config: bytes | str) -> None:
        """Initialize Encryption.

        Args:
            key: encryption key
            config: Encryption config string

        """
        key = key.encode() if isinstance(key, str) else bytes(key)
        config = config.encode() if isinstance(config, str) else bytes(config)
        self._hashed_key = hashlib.sha256(key).digest()
        self._config = config

    @classmethod
    @abstractmethod
    def create(cls, key: bytes | str) -> tuple[EncryptionInterface, bytes]:
        """Create a new encryption object with config.

        Args:
            key: encryption key

        Returns:
            (Encryption object, encryption config string)

        """
        raise NotImplementedError

    @property
    @abstractmethod
    def hashed_key(self) -> bytes:
        """Get the hashed salted key."""
        raise NotImplementedError

    @abstractmethod
    def encrypt(self, secret: bytes | str) -> str:
        """Encrypt a secret using the key.

        Args:
            secret: Object to encrypt

        Returns:
            base64 encoded encrypted object

        """
        raise NotImplementedError

    @abstractmethod
    def decrypt(self, enc_secret: str) -> bytes:
        """Decrypt an encoded secret using the key.

        Args:
            enc_secret: base64 encoded encrypted object

        Returns:
            bytes decoded object

        """
        raise NotImplementedError

    @abstractmethod
    def decrypt_s(self, enc_secret: str) -> str:
        """Decrypt an encoded secret using the key.

        Args:
            enc_secret: base64 encoded encrypted string

        Returns:
            decoded string

        """
        raise NotImplementedError


class NoEncryption(EncryptionInterface):
    """No encryption provide, all methods raise NotImplementedError."""

    @classmethod
    @override
    def create(cls, key: bytes | str) -> tuple[EncryptionInterface, bytes]:
        raise NotImplementedError

    @property
    @override
    def hashed_key(self) -> bytes:
        raise NotImplementedError

    @override
    def encrypt(self, secret: bytes | str) -> str:
        raise NotImplementedError

    @override
    def decrypt(self, enc_secret: str) -> bytes:
        raise NotImplementedError

    @override
    def decrypt_s(self, enc_secret: str) -> str:
        raise NotImplementedError
