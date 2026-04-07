from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

from packaging.version import Version

from flask_htmx_template import web_theme
from flask_htmx_template.database import Database
from flask_htmx_template.migrations.v0_3 import MigratorV0_3
from flask_htmx_template.models.config import Config, ConfigKey

if TYPE_CHECKING:
    from pathlib import Path


def test_version() -> None:
    assert MigratorV0_3().min_version() == Version("0.3.0")


def test_migrate(tmp_path: Path, data_path: Path) -> None:
    path_original = data_path / "old_versions" / "v0.2.0.db"
    path_db = tmp_path / "portfolio.new.db"
    shutil.copyfile(path_original, path_db)

    d = Database(path_db, None, check_migration=False)
    m = MigratorV0_3()
    result = m.migrate(d)
    assert result == []

    assert not m.pending_schema_updates

    with d.begin_session():
        assert Config.fetch(ConfigKey.WEB_THEME_SWATCH) == web_theme.DEFAULT_SWATCH
        assert Config.fetch(ConfigKey.WEB_THEME_MOOD) == web_theme.DEFAULT_MOOD.name
