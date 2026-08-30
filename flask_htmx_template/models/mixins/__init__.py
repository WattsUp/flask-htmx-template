# ruff: file-ignore[non-empty-init-module]

"""Reusable ORM mix-ins."""

from __future__ import annotations

from flask_htmx_template.models.mixins.query import QueryMixIn
from flask_htmx_template.models.mixins.session import SessionMixIn

__all__ = ["QueryMixIn", "SessionMixIn"]
