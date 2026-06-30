from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from flask_htmx_template import exceptions as exc
from flask_htmx_template.models.config import Config, ConfigKey

if TYPE_CHECKING:
    from flask_htmx_template.database import SQLiteDatabase


def test_change_web_key(
    empty_database: SQLiteDatabase,
    rand_str: str,
) -> None:
    new_key = rand_str
    empty_database.change_web_key(new_key)

    with empty_database.begin_session():
        web_key = Config.fetch(ConfigKey.WEB_KEY)
    assert web_key == new_key


def test_change_web_key_short(empty_database: SQLiteDatabase) -> None:
    with pytest.raises(exc.InvalidKeyError):
        empty_database.change_web_key("a")
