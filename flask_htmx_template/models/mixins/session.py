"""Session binding mix-in for active-record models."""

from __future__ import annotations

import contextlib
from contextvars import ContextVar
from typing import ClassVar, TYPE_CHECKING

from flask_htmx_template import exceptions as exc

if TYPE_CHECKING:
    from collections.abc import Generator

    from sqlalchemy import orm


class SessionMixIn:
    """Mix-in that provides a session reference to the type."""

    _active_session: ClassVar[ContextVar[orm.Session | None]] = ContextVar(
        "active_orm_session",
        default=None,
    )

    @classmethod
    @contextlib.contextmanager
    def set_session(cls, s: orm.Session) -> Generator[None]:
        """Set session used by active record.

        Yields:
            SQL session

        """
        token = cls._active_session.set(s)
        try:
            yield
        finally:
            # NOTE: The token restores nested contexts without crossing task boundaries.
            cls._active_session.reset(token)

    @classmethod
    def session(cls) -> orm.Session:
        """Get scoped session.

        Returns:
            SQL session

        Raises:
            UnboundExecutionError: set_session has not been called yet

        """
        session = cls._active_session.get()
        if session is None:
            raise exc.UnboundExecutionError
        return session
