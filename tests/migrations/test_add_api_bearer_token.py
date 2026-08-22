from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

from flask_htmx_template.database import SQLiteDatabase
from flask_htmx_template.migrations.add_api_bearer_token import AddAPIBearerToken
from flask_htmx_template.models.config import Config, ConfigKey

if TYPE_CHECKING:
    from pathlib import Path


def test_migrate(tmp_path: Path, data_path: Path) -> None:
    path_original = data_path / "old_versions" / "v0.2.0.db"
    path_db = tmp_path / "database.new.db"
    shutil.copyfile(path_original, path_db)
    d = SQLiteDatabase(path_db, check_migration=False)

    result = AddAPIBearerToken().migrate(d)

    assert result == []
    with d.begin_session():
        assert Config.fetch(ConfigKey.API_BEARER_TOKEN)
