"""Derived exceptions."""

from __future__ import annotations

from sqlalchemy.exc import (
    DatabaseError,
    IntegrityError,
    MultipleResultsFound,
    NoResultFound,
    UnboundExecutionError,
)
from werkzeug import exceptions as http

__all__ = [
    "DatabaseError",
    "DuplicateURLError",
    "EvaluationError",
    "IntegrityError",
    "InvalidBackupTarError",
    "InvalidEndpointError",
    "InvalidKeyError",
    "InvalidORMValueError",
    "InvalidURIError",
    "MigrationRequiredError",
    "MultipleResultsFound",
    "NoKeywordArgumentsError",
    "NoResultFound",
    "NoURIError",
    "NotEncryptedError",
    "ProtectedObjectNotFoundError",
    "UnboundExecutionError",
    "UnknownEncryptionVersionError",
    "UnlockingError",
    "WrongURITypeError",
    "http",
]


class NotEncryptedError(Exception):
    """Error when encryption operation is called on a unencrypted database."""

    def __init__(self) -> None:
        """Initialize NotEncryptedError."""
        msg = "Database is not encrypted"
        super().__init__(msg)


class InvalidBackupTarError(Exception):
    """Error when a backup tar does not have expected contents."""


class InvalidKeyError(Exception):
    """Error when a key does not meet minimum requirements."""


class InvalidEndpointError(Exception):
    """Error when an endpoint is not constructed properly."""


class DuplicateURLError(Exception):
    """Error when a URL already exists with a endpoint."""

    def __init__(self, url: str, endpoint: str) -> None:  # pragma: no cover
        """Initialize DuplicateURLError.

        Args:
            url: Duplicate URL
            endpoint: Attempted endpoint

        """
        msg = f"Already have a route on {url}, cannot add {endpoint}"
        super().__init__(msg)


class UnknownEncryptionVersionError(Exception):
    """Error when encryption config has an unknown version."""

    def __init__(self) -> None:
        """Initialize UnknownEncryptionVersionError."""
        msg = "Encryption config has an unrecognized version"
        super().__init__(msg)


class UnlockingError(Exception):
    """Error when database fails to unlock."""


class ProtectedObjectNotFoundError(Exception):
    """Error when a protected object (non-deletable) could not be found."""


class NoURIError(Exception):
    """Error when a URI is requested for a model without one."""


class WrongURITypeError(Exception):
    """Error when a URI is decoded for a different model."""


class InvalidURIError(Exception):
    """Error when object does not match expected URI format."""


class InvalidORMValueError(Exception):
    """Error when validation fails for an ORM column."""


class EvaluationError(Exception):
    """Error encountered when evaluating expression."""


class MigrationRequiredError(Exception):
    """Error when a migration is needed to operate."""


class NoKeywordArgumentsError(Exception):
    """Error when function is given kwargs when not expected."""
