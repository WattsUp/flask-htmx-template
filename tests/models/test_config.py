from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from packaging.version import Version

from flask_htmx_template import exceptions as exc
from flask_htmx_template import sql, web_theme
from flask_htmx_template.migrations.top import MIGRATORS
from flask_htmx_template.models.config import Config, ConfigKey
from flask_htmx_template.version import __version__

if TYPE_CHECKING:
    from tests.conftest import RandomStringGenerator


def test_init_properties(rand_str: str) -> None:
    d = {
        "key": ConfigKey.WEB_KEY,
        "value": rand_str,
    }

    c = Config.create(**d)

    assert c.key == d["key"]
    assert c.value == d["value"]


def test_duplicate_keys(
    rand_str_generator: RandomStringGenerator,
) -> None:
    Config.create(key=ConfigKey.WEB_KEY, value=rand_str_generator())
    with pytest.raises(exc.IntegrityError):
        Config.create(key=ConfigKey.WEB_KEY, value=rand_str_generator())


def test_empty() -> None:
    with pytest.raises(exc.IntegrityError):
        Config.create(key=ConfigKey.WEB_KEY, value="")


def test_short() -> None:
    with pytest.raises(exc.InvalidORMValueError):
        Config.create(key=ConfigKey.WEB_KEY, value="a")


def test_set(rand_str: str) -> None:
    Config.set_(ConfigKey.VERSION, rand_str)
    assert Config.fetch(ConfigKey.VERSION) == rand_str


def test_set_new(rand_str: str) -> None:
    Config.set_(ConfigKey.WEB_KEY, rand_str)
    assert Config.fetch(ConfigKey.WEB_KEY) == rand_str


def test_fetch() -> None:
    v = sql.scalar(Config.query(Config.value).where(Config.key == ConfigKey.VERSION))
    assert Config.fetch(ConfigKey.VERSION) == v


def test_fetch_missing() -> None:
    with pytest.raises(exc.ProtectedObjectNotFoundError):
        Config.fetch(ConfigKey.WEB_KEY)


def test_fetch_missing_ok() -> None:
    assert Config.fetch(ConfigKey.WEB_KEY, no_raise=True) is None


def test_db_version() -> None:
    versions = [
        Version(__version__),
        *[m.min_version() for m in MIGRATORS],
    ]
    target = versions[0] if len(versions) == 1 else max(versions)
    assert Config.db_version() == target


def test_web_theme_mood() -> None:
    assert Config.web_theme_mood() == web_theme.DEFAULT_MOOD
