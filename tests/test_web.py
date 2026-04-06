from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import flask
import pytest

from flask_htmx_template import exceptions as exc
from flask_htmx_template import web
from flask_htmx_template.encryption.top import ENCRYPTION_AVAILABLE
from flask_htmx_template.models.base import BaseEnum
from flask_htmx_template.models.config import Config, ConfigKey
from tests import conftest

if TYPE_CHECKING:
    import datetime
    from pathlib import Path

    from flask_htmx_template.database import Database


class Derived(BaseEnum):
    RED = 1
    BLUE = 2
    SEAFOAM_GREEN = 3


def test_create_app(empty_database: Database, flask_app: flask.Flask) -> None:
    with empty_database.begin_session():
        secret_key = Config.fetch(ConfigKey.SECRET_KEY)
    assert flask_app.secret_key == secret_key
    assert len(flask_app.before_request_funcs[None]) == 1

    assert web.db.path == empty_database.path


def test_no_secret_key(
    monkeypatch: pytest.MonkeyPatch,
    empty_database: Database,
) -> None:
    monkeypatch.setenv("DB_PATH", str(empty_database.path))
    with empty_database.begin_session():
        Config.query().where(Config.key == ConfigKey.SECRET_KEY).delete()

    with pytest.raises(exc.ProtectedObjectNotFoundError):
        web.create_app()


@pytest.mark.skipif(not ENCRYPTION_AVAILABLE, reason="No encryption available")
@pytest.mark.encryption
def test_create_app_encrypted(
    monkeypatch: pytest.MonkeyPatch,
    empty_database_encrypted: tuple[Database, str],
) -> None:
    d, key = empty_database_encrypted
    monkeypatch.setenv("DB_PATH", str(d.path))
    monkeypatch.setenv("DB_KEY", key)

    app = web.create_app()
    assert len(app.before_request_funcs[None]) == 2


@pytest.mark.skipif(not ENCRYPTION_AVAILABLE, reason="No encryption available")
@pytest.mark.encryption
def test_create_app_encrypted_key_file(
    monkeypatch: pytest.MonkeyPatch,
    empty_database_encrypted: tuple[Database, str],
    tmp_path: Path,
) -> None:
    d, key = empty_database_encrypted
    path_key = tmp_path / "key"
    path_key.write_text(key, "utf-8")
    monkeypatch.setenv("DB_PATH", str(d.path))
    monkeypatch.setenv("DB_KEY_PATH", str(path_key))

    app = web.create_app()
    assert len(app.before_request_funcs[None]) == 2


def test_getattr() -> None:
    with pytest.raises(AttributeError):
        _ = web.fake


@pytest.mark.parametrize(
    ("kwargs", "target"),
    [
        ({}, ""),
        ({"boolean": True}, "?boolean="),
        ({"boolean": False}, ""),
        ({"uri": None}, ""),
        ({"string": "abc"}, "?string=abc"),
        ({"string": ""}, ""),
        ({"integer": 0}, "?integer=0"),
        ({"integer": 1}, "?integer=1"),
    ],
    ids=conftest.id_func,
)
def test_url_for(
    flask_app: flask.Flask,
    kwargs: dict[str, object],
    target: str,
) -> None:
    with flask_app.test_request_context():
        result = flask_app.url_for(
            "static",
            filename="main.css",
            _anchor=None,
            _method=None,
            _scheme=None,
            _external=False,
            **kwargs,
        )
        assert result == "/static/main.css" + target


def test_flask_context(flask_app: flask.Flask, utc: datetime.datetime) -> None:
    with flask_app.app_context():
        assert (
            flask.render_template_string("{{ date }}")
            == utc.astimezone().date().isoformat()
        )


@pytest.mark.parametrize(
    ("value", "filt", "target"),
    [
        (Decimal("1000.100000"), "comma", "1,000.10"),
        (Decimal("1000.100000"), "qty", "1,000.100000"),
        (Decimal("1000.100000"), "input_value", "1000.1"),
        (Decimal("1000.000000"), "input_value", "1000"),
        (Decimal(), "input_value", ""),
        (14, "days", "2 weeks"),
        (14, "days_abv", "2 wks"),
        (Decimal("0.1234"), "percent", "12.34%"),
        (
            {
                "dict": {"k": (1, 2)},
                "list": [(1, 2)],
                "enum": Derived.SEAFOAM_GREEN,
            },
            "tojson",
            '{"dict":{"k":[1,2]},"list":[[1,2]],"enum":"seafoam_green"}',
        ),
    ],
    ids=conftest.id_func,
)
def test_jinja_filters(
    flask_app: flask.Flask,
    value: object,
    filt: str,
    target: str,
) -> None:
    with flask_app.test_request_context():
        result = flask.render_template_string(
            f"{{{{ value | {filt} | safe }}}}",
            value=value,
        )
        assert result == target


def test_add_routes() -> None:
    app = flask.Flask(__file__)
    app.debug = False
    web.FlaskExtension._add_routes(app)

    routes = app.url_map
    for rule in routes.iter_rules():
        assert not rule.endpoint.startswith("flask_htmx_template.controllers.")
        assert not rule.endpoint.startswith(".")
        assert rule.rule.startswith("/")
        assert not rule.rule.startswith("/d/")
        assert not (rule.rule != "/" and rule.rule.endswith("/"))
