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
    "DuplicateMCPToolError",
    "DuplicateURLError",
    "EvaluationError",
    "IntegrityError",
    "InvalidCipherBoxError",
    "InvalidCipherError",
    "InvalidDateError",
    "InvalidEndpointError",
    "InvalidJSONRouteError",
    "InvalidKeyError",
    "InvalidORMValueError",
    "InvalidTableError",
    "InvalidTimeoutError",
    "InvalidURIError",
    "MigrationRequiredError",
    "MultipleResultsFound",
    "NoKeywordArgumentsError",
    "NoResultFound",
    "NoURIError",
    "ProtectedObjectNotFoundError",
    "UnboundExecutionError",
    "UnlockingError",
    "WrongURITypeError",
    "http",
]


class InvalidKeyError(Exception):
    """Error when a key does not meet minimum requirements."""


class InvalidEndpointError(Exception):
    """Error when an endpoint is not constructed properly."""


class DuplicateMCPToolError(Exception):
    """Error when an MCP tool name is already registered."""


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


class InvalidCipherBoxError(Exception):
    """Error when a cipher substitution or permutation box is invalid."""


class InvalidCipherError(Exception):
    """Error when serialized cipher data is invalid."""


class InvalidDateError(Exception):
    """Error when a date cannot be parsed or violates date limits."""


class InvalidORMValueError(Exception):
    """Error when validation fails for an ORM column."""


class InvalidTableError(Exception):
    """Error when tabular data cannot be formatted."""


class InvalidTimeoutError(Exception):
    """Error when a timeout value is invalid."""


class EvaluationError(Exception):
    """Error encountered when evaluating expression."""


class MigrationRequiredError(Exception):
    """Error when a migration is needed to operate."""


class NoKeywordArgumentsError(Exception):
    """Error when function is given kwargs when not expected."""


class InvalidJSONRouteError(Exception):
    """Error when a dedicated route function does not exist per method."""
