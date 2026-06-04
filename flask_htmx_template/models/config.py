"""Config model for storing a key/value pair."""

from __future__ import annotations

from typing import Literal, overload

from sqlalchemy import orm

from flask_htmx_template import exceptions as exc
from flask_htmx_template import sql, web_theme
from flask_htmx_template.models.base import (
    Base,
    BaseEnum,
    ORMStr,
    SQLEnum,
    string_column_args,
)


class ConfigKey(BaseEnum):
    """Configuration keys."""

    VERSION = 1
    ENCRYPTION_TEST = 2
    CIPHER = 3
    SECRET_KEY = 4
    WEB_KEY = 5

    WEB_THEME_SWATCH = 6
    WEB_THEME_MOOD = 7


class Config(Base):
    """Config model for storing a key/value pair.

    Attributes:
        key: Key of config pair
        value: Value of config pair

    """

    __tablename__ = "config"
    __table_id__ = None

    key: orm.Mapped[ConfigKey] = orm.mapped_column(SQLEnum(ConfigKey), unique=True)
    value: ORMStr

    __table_args__ = (*string_column_args("value"),)

    @orm.validates("value")
    def validate_strings(self, key: str, field: str | None) -> str | None:
        """Validate string fields satisfy constraints.

        Args:
            key: Field being updated
            field: Updated value

        Returns:
            field

        """
        return self.clean_strings(key, field)

    @classmethod
    def set_(cls, key: ConfigKey, value: str) -> None:
        """Set a Configuration value.

        Args:
            key: ConfigKey to query
            value: Value to set

        """
        if Config.query().where(Config.key == key).update({"value": value}):
            return
        Config.create(key=key, value=value)

    @overload
    @classmethod
    def fetch(
        cls,
        key: ConfigKey,
        *,
        no_raise: Literal[False] = False,
    ) -> str: ...

    @overload
    @classmethod
    def fetch(
        cls,
        key: ConfigKey,
        *,
        no_raise: Literal[True],
    ) -> str | None: ...

    @classmethod
    def fetch(
        cls,
        key: ConfigKey,
        *,
        no_raise: bool = False,
    ) -> str | None:
        """Fetch a Configuration value.

        Args:
            key: ConfigKey to query
            no_raise: True will return None if missing

        Returns:
            string value

        Raises:
            ProtectedObjectNotFoundError: If key is not found

        """
        try:
            return sql.one(cls.query(cls.value).where(cls.key == key))
        except exc.NoResultFound as e:
            if no_raise:
                return None
            msg = f"Config.{key} not found"
            raise exc.ProtectedObjectNotFoundError(msg) from e

    @classmethod
    def web_theme_mood(cls) -> web_theme.Mood:
        """Query the database web theme mood.

        Returns:
            Mood of theme

        """
        return web_theme.Mood[Config.fetch(ConfigKey.WEB_THEME_MOOD)]
