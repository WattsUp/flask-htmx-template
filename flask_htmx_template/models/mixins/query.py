"""Query mix-in for active-record models."""

from __future__ import annotations

from typing import overload, Self, TYPE_CHECKING

from flask_htmx_template import exceptions as exc
from flask_htmx_template import sql
from flask_htmx_template.models.mixins.session import SessionMixIn

if TYPE_CHECKING:
    import sqlalchemy.sql.roles as sql_roles
    from sqlalchemy import orm


class QueryMixIn(SessionMixIn):
    """Mix-in that provides a query interface to the type."""

    @classmethod
    def create(cls, **kwargs: object) -> Self:
        """Create a new instance.

        Args:
            kwargs: Passed to init

        Returns:
            New instance

        """
        instance = cls(**kwargs)
        session = cls.session()
        session.add(instance)  # flask_htmx_template: ignore[mixins]
        session.flush()
        return instance

    def delete(self) -> None:
        """Delete an instance."""
        session = self.session()
        session.delete(self)
        session.flush()

    def refresh(self) -> None:
        """Refresh an instance."""
        self.session().refresh(self)

    @overload
    @classmethod
    def query(cls) -> orm.Query[Self]: ...

    @overload
    @classmethod
    def query[T0](
        cls,
        c0: sql_roles.TypedColumnsClauseRole[T0],
    ) -> orm.query.RowReturningQuery[tuple[T0]]: ...

    @overload
    @classmethod
    def query[T0, T1](
        cls,
        c0: sql_roles.TypedColumnsClauseRole[T0],
        c1: sql_roles.TypedColumnsClauseRole[T1],
    ) -> orm.query.RowReturningQuery[tuple[T0, T1]]: ...

    @overload
    @classmethod
    def query[T0, T1, T2](
        cls,
        c0: sql_roles.TypedColumnsClauseRole[T0],
        c1: sql_roles.TypedColumnsClauseRole[T1],
        c2: sql_roles.TypedColumnsClauseRole[T2],
    ) -> orm.query.RowReturningQuery[tuple[T0, T1, T2]]: ...

    @overload
    @classmethod
    def query[T0, T1, T2, T3](
        cls,
        c0: sql_roles.TypedColumnsClauseRole[T0],
        c1: sql_roles.TypedColumnsClauseRole[T1],
        c2: sql_roles.TypedColumnsClauseRole[T2],
        c3: sql_roles.TypedColumnsClauseRole[T3],
    ) -> orm.query.RowReturningQuery[tuple[T0, T1, T2, T3]]: ...

    @overload
    @classmethod
    def query[T0, T1, T2, T3, T4](
        cls,
        c0: sql_roles.TypedColumnsClauseRole[T0],
        c1: sql_roles.TypedColumnsClauseRole[T1],
        c2: sql_roles.TypedColumnsClauseRole[T2],
        c3: sql_roles.TypedColumnsClauseRole[T3],
        c4: sql_roles.TypedColumnsClauseRole[T4],
    ) -> orm.query.RowReturningQuery[tuple[T0, T1, T2, T3, T4]]: ...

    @overload
    @classmethod
    def query[T0, T1, T2, T3, T4, T5](
        cls,
        c0: sql_roles.TypedColumnsClauseRole[T0],
        c1: sql_roles.TypedColumnsClauseRole[T1],
        c2: sql_roles.TypedColumnsClauseRole[T2],
        c3: sql_roles.TypedColumnsClauseRole[T3],
        c4: sql_roles.TypedColumnsClauseRole[T4],
        c5: sql_roles.TypedColumnsClauseRole[T5],
    ) -> orm.query.RowReturningQuery[tuple[T0, T1, T2, T3, T4, T5]]: ...

    @classmethod
    def query[T](
        cls,
        *columns: sql_roles.TypedColumnsClauseRole[object],
        **kwargs: T,
    ) -> orm.Query[Self] | orm.Query[T]:
        """Create a new query.

        Returns:
            Query of table

        Raises:
            NoKeywordArgumentsError: if kwargs are provided

        """
        if kwargs:
            raise exc.NoKeywordArgumentsError
        query: orm.Query[Self] = cls.session().query(cls)
        if columns:
            return query.with_entities(*columns)  # flask_htmx_template: ignore[mixins]
        return query

    @classmethod
    def all(cls) -> list[Self]:
        """Fetch all rows.

        Returns:
            List of each row object

        """
        return list(sql.yield_(cls.query()))

    @classmethod
    def one(cls) -> Self:
        """Fetch one rows.

        Returns:
            Only row

        """
        return sql.one(cls.query())

    @classmethod
    def first(cls) -> Self | None:
        """Fetch first rows.

        Returns:
            First row

        """
        return cls.query().first()

    @classmethod
    def count(cls) -> int:
        """Count number of rows.

        Returns:
            Number of rows

        """
        return sql.count(cls.query())
