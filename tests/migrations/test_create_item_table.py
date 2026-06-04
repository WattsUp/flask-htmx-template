from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

from flask_htmx_template import sql
from flask_htmx_template.database import SQLiteDatabase
from flask_htmx_template.migrations.create_item_table import CreateItemTable
from flask_htmx_template.models.config import Config
from flask_htmx_template.models.item import Item

if TYPE_CHECKING:
    from pathlib import Path


def test_migrate(tmp_path: Path, data_path: Path) -> None:
    path_original = data_path / "old_versions" / "v0.0.0.db"
    path_db = tmp_path / "portfolio.new.db"
    shutil.copyfile(path_original, path_db)

    d = SQLiteDatabase(path_db, None, check_migration=False)
    m = CreateItemTable()
    result = m.migrate(d)
    target = [
        "Created Item table",
    ]
    assert result == target

    assert Config in m.pending_schema_updates

    with d.begin_session():
        assert sql.count(Item.query()) == 0
