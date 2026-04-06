"""Migrators."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask_htmx_template.migrations.v0_1 import MigratorV0_1

if TYPE_CHECKING:
    from flask_htmx_template.migrations.base import Migrator

MIGRATORS: list[type[Migrator]] = [
    MigratorV0_1,
]
