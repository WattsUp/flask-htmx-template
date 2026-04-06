"""Base Migrator."""

from __future__ import annotations

import re
import textwrap
from abc import ABC, abstractmethod
from typing import override, TYPE_CHECKING

import sqlalchemy
from packaging.version import Version
from sqlalchemy.schema import CreateTable

from flask_htmx_template import sql
from flask_htmx_template.models.base import Base
from flask_htmx_template.models.utils import dump_table_configs, get_constraints

if TYPE_CHECKING:
    from flask_htmx_template.database import Database


class Migrator(ABC):
    """Base Migrator."""

    _VERSION: str

    def __init__(self) -> None:
        """Initialize Migrator."""
        super().__init__()
        self.pending_schema_updates: set[type[Base]] = set()

    @abstractmethod
    def migrate(self, d: Database) -> list[str]:
        """Run migration.

        Args:
            d: Database to migrate

        Returns:
            List of comments to display to user

        """

    @classmethod
    def min_version(cls) -> Version:
        """Minimum version that satisfies migrator.

        Returns:
            Version

        """
        return Version(cls._VERSION)

    def add_column(
        self,
        model: type[Base],
        column: sql.Column,
        initial_value: object | None = None,
    ) -> None:
        """Add a column to a table.

        Args:
            model: Table to modify
            column: Column to add
            initial_value: Value to set all rows to

        """
        s = model.session()
        engine = s.get_bind().engine

        col_name = sql.escape(column.name)
        col_type = column.type.compile(dialect=engine.dialect)
        stmt = f'ALTER TABLE "{model.__tablename__}" ADD {col_name} {col_type}'
        s.execute(sqlalchemy.text(stmt))

        if initial_value is not None:
            model.query().update({column: initial_value})

        self.pending_schema_updates.add(model)

    def rename_column(
        self,
        model: type[Base],
        old_name: str,
        new_name: str,
    ) -> None:
        """Rename a column in a table.

        Args:
            model: Table to modify
            old_name: Current name of column
            new_name: New name of column

        """
        old_name = sql.escape(old_name)
        new_name = sql.escape(new_name)
        stmt = f'ALTER TABLE "{model.__tablename__}" RENAME {old_name} TO {new_name}'
        model.session().execute(sqlalchemy.text(stmt))

        # RENAME modifies column references but not constraint names
        # Need to update schema to update those
        self.pending_schema_updates.add(model)

    def drop_column(
        self,
        model: type[Base],
        col_name: str,
    ) -> None:
        """Rename a column in a table.

        Args:
            model: Table to modify
            col_name: Name of column to drop

        """
        constraints = get_constraints(model)
        if any(col_name in sql_text for _, sql_text in constraints):
            self.recreate_table(model, drop={col_name})
        else:
            # Able to drop directly
            col_name = sql.escape(col_name)
            stmt = f'ALTER TABLE "{model.__tablename__}" DROP {col_name}'
            model.session().execute(sqlalchemy.text(stmt))

        # DROP does not need updated schema

    def recreate_table(
        self,
        model: type[Base],
        *,
        drop: set[str] | None = None,
        create_stmt: str | None = None,
    ) -> None:
        """Rebuild table, optionally dropping columns.

        Args:
            model: Table to modify
            drop: Set of column names to drop
            create_stmt: Statement to execute to create new table,
                None will modify existing config

        """
        s = model.session()
        drop = drop or set()
        # In SQLite we can do the hacky way or recreate the table
        # Opt for recreate
        table: sqlalchemy.Table = model.sql_table()
        name: str = model.__tablename__

        if create_stmt:
            new_config = create_stmt.splitlines()
        else:
            # Edit table config, dropping any columns
            old_config = dump_table_configs(model)
            new_config: list[str] = []
            re_column = re.compile(r" +([a-z_]+) [A-Z ]+")
            re_constraint = re.compile(r' +[A-Z ]+(?:"[^\"]+" [A-Z ]+)?\(([^\)]+)\)')
            for line in old_config:
                if (m := re_column.match(line)) or (m := re_constraint.match(line)):
                    sql_text = m.group(1)
                    if all(col not in sql_text for col in drop):
                        new_config.append(line)
                else:
                    new_config.append(line)
        new_config[0] = new_config[0].replace(name, "migration_temp")
        new_config[-2] = new_config[-2].rstrip(", ")

        stmt = "PRAGMA foreign_keys = OFF"
        s.execute(sqlalchemy.text(stmt))

        # Create new table
        s.execute(sqlalchemy.text("\n".join(new_config)))

        # Copy data
        columns = ", ".join(
            sql.escape(c.name) for c in table.columns if c.name not in drop
        )
        stmt = textwrap.dedent(
            f"""\
            INSERT INTO "migration_temp" ({columns})
                SELECT {columns}
                FROM "{name}";""",  # noqa: S608
        )
        s.execute(sqlalchemy.text(stmt))

        # Drop old table
        self.drop_table(name)

        # Rename new into old
        stmt = f'ALTER TABLE "migration_temp" RENAME TO "{name}"'
        s.execute(sqlalchemy.text(stmt))

        # Reset PRAGMAs
        stmt = "PRAGMA foreign_keys = ON"
        s.execute(sqlalchemy.text(stmt))

        self.pending_schema_updates.add(model)

    @staticmethod
    def drop_table(table_name: str) -> None:
        """Drop a table.

        Args:
            table_name: Name of table to drop

        """
        stmt = f'DROP TABLE "{table_name}"'
        Base.session().execute(sqlalchemy.text(stmt))


class SchemaMigrator(Migrator):
    """Migrator to update schema of pending tables."""

    def __init__(self, pending_schema_updates: set[type[Base]]) -> None:
        """Initialize SchemaMigrator.

        Args:
            pending_schema_updates: Models to update schema for

        """
        super().__init__()
        self.pending_schema_updates = pending_schema_updates

    @override
    def migrate(self, d: Database) -> list[str]:
        for model in self.pending_schema_updates:
            with d.begin_session() as s:
                table: sqlalchemy.Table = model.sql_table()
                create_stmt = CreateTable(table).compile(s.get_bind()).string.strip()
                self.recreate_table(model, create_stmt=create_stmt)
        return []
