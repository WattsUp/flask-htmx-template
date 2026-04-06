from __future__ import annotations

import pytest

from flask_htmx_template import exceptions as exc
from flask_htmx_template.database import Database
from flask_htmx_template.encryption.top import ENCRYPTION_AVAILABLE
from flask_htmx_template.models.config import Config, ConfigKey
from flask_htmx_template.models.item import Item


@pytest.mark.skipif(not ENCRYPTION_AVAILABLE, reason="No encryption available")
@pytest.mark.encryption
def test_change_db_key(
    capsys: pytest.CaptureFixture[str],
    empty_database_encrypted: tuple[Database, str],
    rand_str: str,
    today_ord: int,
) -> None:
    new_key = rand_str
    d, old_key = empty_database_encrypted
    with d.begin_session():
        item = Item.create(name="Banana", date_ord=today_ord)
        web_key_enc = Config.fetch(ConfigKey.WEB_KEY)
    web_key = d.decrypt_s(web_key_enc)

    d.change_key(new_key)

    captured = capsys.readouterr()
    assert not captured.out
    # tqdm in here
    assert captured.err

    with d.begin_session():
        web_key_enc = Config.fetch(ConfigKey.WEB_KEY)
        item = Item.one()
        assert item.name == "Banana"
        assert item.date_ord == today_ord
    new_web_key = d.decrypt_s(web_key_enc)
    assert new_web_key == web_key
    assert new_web_key != new_key

    # Unlocking with new_key works
    Database(d.path, new_key)

    # Unlocking with key doesn't work
    with pytest.raises(exc.UnlockingError):
        Database(d.path, old_key)


def test_change_db_key_short(empty_database: Database) -> None:
    with pytest.raises(exc.InvalidKeyError):
        empty_database.change_key("a")


@pytest.mark.skipif(not ENCRYPTION_AVAILABLE, reason="No encryption available")
@pytest.mark.encryption
def test_change_web_key(
    empty_database_encrypted: tuple[Database, str],
    rand_str: str,
) -> None:
    new_key = rand_str
    d, db_key = empty_database_encrypted
    d.change_web_key(new_key)

    with d.begin_session():
        web_key_enc = Config.fetch(ConfigKey.WEB_KEY)
    web_key = d.decrypt_s(web_key_enc)
    assert web_key == new_key
    assert web_key != db_key


def test_change_web_key_short(empty_database: Database) -> None:
    with pytest.raises(exc.InvalidKeyError):
        empty_database.change_web_key("a")
