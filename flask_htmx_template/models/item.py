"""Item model for storing a thing."""

from __future__ import annotations

import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, orm

from flask_htmx_template.models.base import (
    Base,
    Decimal6,
    ORMInt,
    ORMIntOpt,
    ORMReal,
    ORMStr,
    ORMStrOpt,
    string_column_args,
)


class Item(Base):
    """Item model for storing a thing.

    Attributes:
        uri: Item unique identifier
        name: Item name

    """

    __tablename__ = "item"
    __table_id__ = 0x00000000

    name: ORMStr = orm.mapped_column(unique=True)
    date_ord: ORMInt
    value: ORMReal = orm.mapped_column(Decimal6, default=Decimal())
    note: ORMStrOpt

    other_id: ORMIntOpt = orm.mapped_column(ForeignKey("item.id_"))

    __table_args__ = (
        *string_column_args("name"),
        *string_column_args("note"),
    )

    @orm.validates("name", "note")
    def validate_strings(self, key: str, field: str | None) -> str | None:
        """Validate string fields satisfy constraints.

        Args:
            key: Field being updated
            field: Updated value

        Returns:
            field

        """
        return self.clean_strings(key, field)

    @orm.validates("value")
    def validate_decimals(self, key: str, field: Decimal | None) -> Decimal | None:
        """Validate decimal fields satisfy constraints.

        Args:
            key: Field being updated
            field: Updated value

        Returns:
            field

        """
        return self.clean_decimals(key, field)

    @property
    def date(self) -> datetime.date:
        """Date on which Transaction occurred."""
        return datetime.date.fromordinal(self.date_ord)
