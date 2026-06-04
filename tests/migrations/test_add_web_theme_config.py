from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

from flask_htmx_template import web_theme
from flask_htmx_template.database import SQLiteDatabase
from flask_htmx_template.migrations.add_web_theme_config import AddWebThemeConfig
from flask_htmx_template.models.config import Config, ConfigKey

if TYPE_CHECKING:
    from pathlib import Path


def test_migrate(tmp_path: Path, data_path: Path) -> None:
    path_original = data_path / "old_versions" / "v0.2.0.db"
    path_db = tmp_path / "portfolio.new.db"
    shutil.copyfile(path_original, path_db)

    d = SQLiteDatabase(path_db, None, check_migration=False)
    m = AddWebThemeConfig()
    result = m.migrate(d)
    assert result == []

    assert not m.pending_schema_updates

    with d.begin_session():
        assert Config.fetch(ConfigKey.WEB_THEME_SWATCH) == web_theme.DEFAULT_SWATCH
        assert Config.fetch(ConfigKey.WEB_THEME_MOOD) == web_theme.DEFAULT_MOOD.name
