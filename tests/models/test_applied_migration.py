from __future__ import annotations

from typing import TYPE_CHECKING

from flask_htmx_template.models.applied_migration import AppliedMigration

if TYPE_CHECKING:
    import datetime

    from sqlalchemy import orm

    from tests.conftest import RandomStringGenerator


def test_init_properties(
    rand_str_generator: RandomStringGenerator,
    session: orm.Session,
    utc: datetime.datetime,
) -> None:
    d = {
        "name": rand_str_generator(),
        "applied_at_utc": utc,
    }
    obj = AppliedMigration.create(**d)

    assert obj.name == d["name"]
    assert obj.applied_at_utc == d["applied_at_utc"]
