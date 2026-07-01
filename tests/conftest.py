from __future__ import annotations

import datetime
import functools
import random
import shutil
import string
from collections.abc import Iterable
from decimal import Decimal
from pathlib import Path
from typing import cast, NamedTuple, override, TYPE_CHECKING

import flask
import psycopg
import pytest
import sqlalchemy
from pytest_postgresql.factories import postgresql_proc
from sqlalchemy import orm, pool

from flask_htmx_template import sql, web
from flask_htmx_template.database import PostgresDatabase, SQLiteDatabase
from flask_htmx_template.models import base_uri
from flask_htmx_template.models.base import Base
from flask_htmx_template.models.item import Item

if TYPE_CHECKING:
    from collections.abc import Generator

    import time_machine
    from pytest_postgresql.executor import PostgreSQLExecutor

    from flask_htmx_template.database import Database


def id_func(val: object) -> str | None:
    if isinstance(val, datetime.date):
        return val.isoformat()
    if isinstance(val, Iterable | Decimal | Path):
        return str(cast("Iterable[object] | Decimal | Path", val))
    if callable(val):
        return val.__name__
    return None


class RandomStringGenerator:

    @classmethod
    def __call__(cls, length: int = 20) -> str:
        return "".join(random.choice(string.ascii_letters) for _ in range(length))


@pytest.fixture(scope="session")
def rand_str_generator() -> RandomStringGenerator:
    """Return a random string generator.

    Returns:
        RandomStringGenerator

    """
    return RandomStringGenerator()


@pytest.fixture
def rand_str(rand_str_generator: RandomStringGenerator) -> str:
    """Return a random string.

    Returns:
        Random string with 20 characters

    """
    return rand_str_generator()


class RandomRealGenerator:

    @classmethod
    def __call__(
        cls,
        low: str | float | Decimal = 0.1,
        high: str | float | Decimal = 1,
        precision: int = 6,
    ) -> Decimal:
        d_low = round(Decimal(low), precision)
        d_high = round(Decimal(high), precision)
        x = random.uniform(float(d_low), float(d_high))
        return min(max(round(Decimal(x), precision), d_low), d_high)


@pytest.fixture(scope="session")
def rand_real_generator() -> RandomRealGenerator:
    """Return a random decimal generator.

    Returns:
        RandomRealGenerator

    """
    return RandomRealGenerator()


@pytest.fixture
def rand_real(rand_real_generator: RandomRealGenerator) -> Decimal:
    """Return a random decimal [0, 1].

    Returns:
        Real number between [0, 1] with 6 digits

    """
    return rand_real_generator()


@pytest.fixture(autouse=True)
def sql_engine_args() -> None:
    """Change all engines to NullPool so timing isn't an issue."""
    # Needed specifically for DatabaseIntegrity test
    sql._ENGINE_ARGS["poolclass"] = pool.NullPool


class EmptyDatabaseGenerator:

    def __init__(
        self,
        tmp_path_factory: pytest.TempPathFactory,
        rand_str_generator: RandomStringGenerator,
    ) -> None:
        # Create the database once, then copy the file each time called
        self._path = tmp_path_factory.mktemp("data") / "database.db"
        self._rand_str_generator = rand_str_generator
        SQLiteDatabase.create(self._path)

    def __call__(self) -> SQLiteDatabase:
        tmp_path = self._path.with_name(f"{self._rand_str_generator()}.db")
        shutil.copyfile(self._path, tmp_path)
        return SQLiteDatabase(tmp_path)


@pytest.fixture(scope="session")
def empty_database_generator(
    tmp_path_factory: pytest.TempPathFactory,
    rand_str_generator: RandomStringGenerator,
) -> EmptyDatabaseGenerator:
    """Return an empty database generator.

    Returns:
        EmptyDatabase generator

    """
    return EmptyDatabaseGenerator(tmp_path_factory, rand_str_generator)


@pytest.fixture
def empty_database(
    empty_database_generator: EmptyDatabaseGenerator,
) -> SQLiteDatabase:
    """Return an empty database.

    Returns:
        Database

    """
    return empty_database_generator()


@pytest.fixture(autouse=True)
def session(empty_database: SQLiteDatabase) -> Generator[orm.Session]:
    """Create SQL session.

    Yields:
        Session

    """
    s = orm.Session(sql.get_engine(empty_database.path))
    with Base.set_session(s):
        yield s


@pytest.fixture(autouse=True, scope="session")
def uri_cipher() -> None:
    """Generate a URI cipher."""
    base_uri._cipher = base_uri.Cipher.generate()


@pytest.fixture(scope="session")
def today() -> datetime.date:
    """Get today's date.

    Returns:
        today datetime.date

    """
    return datetime.datetime.now(datetime.UTC).date()


@pytest.fixture(scope="session")
def today_ord(today: datetime.date) -> int:
    """Get today's date ordinal.

    Returns:
        today as ordinal

    """
    return today.toordinal()


@pytest.fixture(scope="session")
def tomorrow(today: datetime.date) -> datetime.date:
    """Get tomorrow's date.

    Returns:
        tomorrow datetime.date

    """
    return today + datetime.timedelta(days=1)


@pytest.fixture(scope="session")
def tomorrow_ord(tomorrow: datetime.date) -> int:
    """Get tomorrow's date ordinal.

    Returns:
        tomorrow as ordinal

    """
    return tomorrow.toordinal()


@pytest.fixture(scope="session")
def month(today: datetime.date) -> datetime.date:
    """Get today's month.

    Returns:
        month datetime.date

    """
    return today.replace(day=1)


@pytest.fixture(scope="session")
def month_ord(month: datetime.date) -> int:
    """Get today's month ordinal.

    Returns:
        month as ordinal

    """
    return month.toordinal()


@pytest.fixture(scope="session")
def data_path() -> Path:
    """Get path to data directory.

    Returns:
        Path to test data

    """
    return Path(__file__).with_name("data")


@pytest.fixture
def utc() -> datetime.datetime:
    """Get current time in UTC.

    Returns:
        datetime

    """
    return datetime.datetime.now(datetime.UTC)


@pytest.fixture
def utc_frozen(
    utc: datetime.datetime,
    time_machine: time_machine.TimeMachineFixture,
) -> datetime.datetime:
    """Get current time in UTC and freeze it.

    Returns:
        datetime

    """
    time_machine.move_to(utc, tick=False)
    return utc


class FlaskAppGenerator:

    def __init__(
        self,
        generator: EmptyDatabaseGenerator,
    ) -> None:
        class MockExtension(web.FlaskExtension):
            @override
            @classmethod
            def _open_db(cls, config: dict[str, object]) -> Database:
                return generator()

        self._ext = MockExtension()

        path_root = Path(web.__file__).parent.resolve()
        self._flask_app = flask.Flask(__name__, root_path=str(path_root))
        self._flask_app.debug = True
        self._flask_app.testing = True
        self._ext.init_app(self._flask_app)

        # Needed by test_change_redirect
        self._flask_app.add_url_rule(
            "/redirect",
            "redirect",
            functools.partial(flask.redirect, "/"),
        )

    def __call__(self, d: Database) -> flask.Flask:
        # Just swap out database reference, quicker than making a new app
        # Since all use the same empty_database_generator,
        # the SECRET_KEY will be identical
        web.ext._db = d
        return self._flask_app


@pytest.fixture(scope="session")
def flask_app_generator(
    empty_database_generator: EmptyDatabaseGenerator,
) -> FlaskAppGenerator:
    """Return an flask app generator.

    Returns:
        FlaskAppGenerator

    """
    return FlaskAppGenerator(empty_database_generator)


@pytest.fixture
def flask_app(
    flask_app_generator: FlaskAppGenerator,
    empty_database: Database,
) -> flask.Flask:
    """Create flask app for EmptyDatabase.

    Returns:
        Flask

    """
    return flask_app_generator(empty_database)


@pytest.fixture
def item(session: orm.Session, today_ord: int) -> Item:
    """Create an Item.

    Returns:
        Checking Item

    """
    with session.begin_nested():
        return Item.create(
            name="Bananas",
            date_ord=today_ord,
        )


# ---------------------------------------------------------------------------
# Postgres fixtures — spin up a fresh cluster; no system setup needed
# ---------------------------------------------------------------------------

_pg_proc = postgresql_proc(
    executable="/usr/lib/postgresql/16/bin/pg_ctl",
    host="127.0.0.1",
    user="postgres",
    password="pgpassword",  # noqa: S106
    postgres_options="-c listen_addresses='127.0.0.1'",
)


class PostgresDatabaseGenerator:
    """Drop all application tables and recreate the schema for each test."""

    def __init__(self, pg_url: str) -> None:
        self._pg_url = pg_url

    @property
    def url(self) -> str:
        """Postgres URL for this database.

        Returns:
            postgres URL string

        """
        return self._pg_url

    def drop(self) -> None:
        """Drop all application tables, leaving a clean postgres database."""
        norm = sql.normalize_postgres_url(self._pg_url)
        engine = sqlalchemy.create_engine(
            norm,
            connect_args={"sslmode": "disable"},
            poolclass=pool.NullPool,
        )
        with engine.begin() as conn:
            Base.metadata.drop_all(conn)
        engine.dispose()

    def __call__(self) -> PostgresDatabase:
        """Drop all tables and recreate the schema, returning a fresh Database.

        Returns:
            Freshly created postgres Database

        """
        self.drop()
        return PostgresDatabase.create(self._pg_url)


@pytest.fixture(scope="session", autouse=True)
def disable_ssl() -> Generator[None]:
    """Disable SSL for local test postgres (no TLS cert configured)."""
    original = sql._POSTGRES_SSL_MODE
    sql._POSTGRES_SSL_MODE = "disable"
    yield
    sql._POSTGRES_SSL_MODE = original


@pytest.fixture(scope="session")
def pg_proc(_pg_proc: PostgreSQLExecutor) -> PostgreSQLExecutor:
    """Expose the postgres process under a stable name.

    Returns:
        PostgreSQL process executor

    """
    return _pg_proc


class PGCredentials(NamedTuple):
    """Postgres database credentials."""

    host: str
    port: int
    dbname: str
    user: str
    password: str


@pytest.fixture(scope="session")
def pg_credentials(pg_proc: PostgreSQLExecutor) -> PGCredentials:
    """Create a dedicated test user/database.

    Returns:
        Tuple of (host, port, dbname, user, password)

    """
    host = pg_proc.host
    port = pg_proc.port
    user = "testuser"
    password = "testpass"  # noqa: S105
    dbname = "testdb"

    with (
        psycopg.connect(
            host=host,
            port=port,
            user="postgres",
            password="pgpassword",  # noqa: S106
            dbname="postgres",
            autocommit=True,
        ) as conn,
        conn.cursor() as cur,
    ):
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (user,))
        if cur.fetchone() is None:
            cur.execute(
                f"CREATE ROLE {user} WITH LOGIN PASSWORD '{password}'",
            )
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
        if cur.fetchone() is None:
            cur.execute(f"CREATE DATABASE {dbname} OWNER {user}")

    return PGCredentials(host, port, dbname, user, password)


@pytest.fixture(scope="session")
def pg_url(pg_credentials: PGCredentials) -> str:
    """Return a postgres URL with credentials for the test database.

    Returns:
        postgresql://user:password@host:port/dbname

    """
    host, port, dbname, user, password = pg_credentials
    return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"


@pytest.fixture(scope="session")
def postgres_database_generator(pg_url: str) -> PostgresDatabaseGenerator:
    """Return a generator that resets the postgres database for each test.

    Returns:
        PostgresDatabaseGenerator instance

    """
    return PostgresDatabaseGenerator(pg_url)


@pytest.fixture
def postgres_database(
    postgres_database_generator: PostgresDatabaseGenerator,
) -> PostgresDatabase:
    """Drop all application tables and recreate the schema.

    Returns:
        Fresh postgres Database

    """
    return postgres_database_generator()
