"""Encryption providers."""

from __future__ import annotations

import logging

from flask_htmx_template.encryption.base import NoEncryption

try:
    from flask_htmx_template.encryption.aes import EncryptionAES
except ImportError:
    logger = logging.getLogger(__name__)
    logger.warning(
        "Could not import flask_htmx_template.encryption, encryption not available",
    )
    logger.warning("Install libsqlcipher: apt install libsqlcipher-dev")
    logger.warning("Install encrypt extra: pip install flask_htmx_template[encrypt]")
    Encryption = NoEncryption
    encryption_available = False
else:
    Encryption = EncryptionAES
    encryption_available = True
ENCRYPTION_AVAILABLE = encryption_available
