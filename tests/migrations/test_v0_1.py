from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

from packaging.version import Version

from flask_htmx_template import sql
from flask_htmx_template.database import SQLiteDatabase
from flask_htmx_template.migrations.v0_1 import MigratorV0_1
from flask_htmx_template.models.config import Config
from flask_htmx_template.models.item import Item

if TYPE_CHECKING:
    from pathlib import Path


def test_version() -> None:
    assert MigratorV0_1().min_version() == Version("0.1.0")


def test_migrate(tmp_path: Path, data_path: Path) -> None:
    path_original = data_path / "old_versions" / "v0.0.0.db"
    path_db = tmp_path / "portfolio.new.db"
    shutil.copyfile(path_original, path_db)

    d = SQLiteDatabase(path_db, None, check_migration=False)
    m = MigratorV0_1()
    result = m.migrate(d)
    target = [
        "Created Item table",
    ]
    assert result == target

    assert Config in m.pending_schema_updates

    with d.begin_session():
        assert sql.count(Item.query()) == 0
