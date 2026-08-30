from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from flask_htmx_template import exceptions as exc
from flask_htmx_template import sql, web_theme
from flask_htmx_template.models.config import Config, ConfigKey

if TYPE_CHECKING:
    from sqlalchemy import orm

    from tests.conftest import RandomStringGenerator


@pytest.fixture
def delete_web_key(session: orm.Session) -> None:
    Config.query().where(Config.key == ConfigKey.WEB_KEY).delete()


def test_init_properties(rand_str: str, delete_web_key: None) -> None:
    d = {
        "key": ConfigKey.WEB_KEY,
        "value": rand_str,
    }

    c = Config.create(**d)

    assert c.key == d["key"]
    assert c.value == d["value"]


def test_duplicate_keys(
    rand_str_generator: RandomStringGenerator,
    delete_web_key: None,
) -> None:
    Config.create(key=ConfigKey.WEB_KEY, value=rand_str_generator())
    with pytest.raises(exc.IntegrityError):
        Config.create(key=ConfigKey.WEB_KEY, value=rand_str_generator())


def test_empty(delete_web_key: None) -> None:
    with pytest.raises(exc.IntegrityError):
        Config.create(key=ConfigKey.WEB_KEY, value="")


def test_short(delete_web_key: None) -> None:
    with pytest.raises(exc.InvalidORMValueError):
        Config.create(key=ConfigKey.WEB_KEY, value="a")


def test_set(rand_str: str, delete_web_key: None) -> None:
    Config.set_(ConfigKey.VERSION, rand_str)
    assert Config.fetch(ConfigKey.VERSION) == rand_str


def test_set_new(rand_str: str, delete_web_key: None) -> None:
    Config.set_(ConfigKey.WEB_KEY, rand_str)
    assert Config.fetch(ConfigKey.WEB_KEY) == rand_str


def test_fetch(delete_web_key: None) -> None:
    v = sql.scalar(Config.query(Config.value).where(Config.key == ConfigKey.VERSION))
    assert Config.fetch(ConfigKey.VERSION) == v


def test_fetch_missing(delete_web_key: None) -> None:
    with pytest.raises(exc.ProtectedObjectNotFoundError):
        Config.fetch(ConfigKey.WEB_KEY)


def test_fetch_missing_ok(delete_web_key: None) -> None:
    assert Config.fetch(ConfigKey.WEB_KEY, no_raise=True) is None


def test_db_version(delete_web_key: None) -> None:
    assert Config.fetch(ConfigKey.VERSION) == "1.0"


def test_web_theme_mood(delete_web_key: None) -> None:
    assert Config.web_theme_mood() == web_theme.DEFAULT_MOOD
