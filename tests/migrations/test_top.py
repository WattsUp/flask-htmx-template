from __future__ import annotations

from typing import TYPE_CHECKING

from flask_htmx_template.database import SQLiteDatabase
from flask_htmx_template.migrations import top

if TYPE_CHECKING:
    from pathlib import Path


def test_collect_without_applied_migration_table(
    data_path: Path,
) -> None:
    path = data_path / "old_versions" / "v0.0.0.db"
    database = SQLiteDatabase(path, check_migration=False)

    migrators = top.collect(database)

    assert migrators == top._MIGRATORS
