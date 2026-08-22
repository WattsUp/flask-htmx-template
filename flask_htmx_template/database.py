"""Database of financial records."""

from __future__ import annotations

import base64
import contextlib
import datetime
import secrets
from abc import ABC, abstractmethod
from pathlib import Path
from typing import override, Self, TYPE_CHECKING

import sqlalchemy
from sqlalchemy import orm

from flask_htmx_template import exceptions as exc
from flask_htmx_template import sql, utils, web_theme
from flask_htmx_template.migrations.top import _MIGRATORS, collect
from flask_htmx_template.models.applied_migration import AppliedMigration
from flask_htmx_template.models.base import Base
from flask_htmx_template.models.base_uri import Cipher, load_cipher
from flask_htmx_template.models.config import Config, ConfigKey

if TYPE_CHECKING:
    from collections.abc import Generator


class Database(ABC):
    """Database base class."""

    @abstractmethod
    def __init__(
        self,
        path: str | Path,
        *,
        check_migration: bool = True,
    ) -> None:
        """Initialize Database.

        Args:
            path: Path to database file, or postgres connection URL
            check_migration: True will check if migration is required

        Raises:
            FileNotFoundError: If SQLite database does not exist
            MigrationRequiredError: If migration is required

        """
        super().__init__()
        self._postgres_url: str

        self._engine = self.get_engine()
        self._session_maker = orm.sessionmaker(self._engine)
        self._unlock()

        if check_migration and self.migration_required():
            msg = "Database requires migration"
            raise exc.MigrationRequiredError(msg)

    @classmethod
    def create(cls, path: str | Path) -> Self:
        """Create a new Database.

        For SQLite, saves database and configuration file.
        For postgres, creates tables in the existing server.

        Args:
            path: Path to database file, or postgres connection URL

        Returns:
            Database linked to newly created database

        Raises:
            FileExistsError: If database already exists

        """
        raise NotImplementedError

    @property
    @abstractmethod
    def is_postgres(self) -> bool:
        """Check if database is postgres."""
        raise NotImplementedError

    def _unlock(self) -> dict[ConfigKey, str]:
        """Unlock the database.

        Returns:
            Configuration properties

        Raises:
            UnlockingError: If database file fails to open
            ProtectedObjectNotFoundError: If URI cipher is missing

        """
        try:
            with self.begin_session():
                query = Config.query(Config.key, Config.value)
                configs: dict[ConfigKey, str] = sql.to_dict(query)
        except exc.DatabaseError as e:
            msg = f"Failed to open database {self}"
            raise exc.UnlockingError(msg) from e

        # Load Cipher
        cipher_b64 = configs.get(ConfigKey.CIPHER)
        if cipher_b64 is None:
            msg = "Config.CIPHER not found"
            raise exc.ProtectedObjectNotFoundError(msg)
        load_cipher(base64.b64decode(cipher_b64))
        # Verify VERSION is present
        if configs.get(ConfigKey.VERSION) is None:
            msg = "Config.VERSION not found"
            raise exc.ProtectedObjectNotFoundError(msg)
        # All good :)
        return configs

    @abstractmethod
    def get_engine(self) -> sqlalchemy.Engine:
        """Get SQL Engine to the database.

        Returns:
            Engine

        """
        raise NotImplementedError

    def dispose(self) -> None:
        """Dispose of the connection pool.

        Must be called in each worker process after forking (e.g. gunicorn
        post_fork) to prevent workers from sharing inherited SSL connections.

        """
        self._engine.dispose()

    @contextlib.contextmanager
    def begin_session(self) -> Generator[orm.Session]:
        """Get SQL Session to the database.

        Yields:
            Open Session

        """
        s = self._session_maker()
        with s, s.begin(), Base.set_session(s):
            yield s

    def migration_required(self) -> bool:
        """Check if migration is required.

        Returns:
            True if migration is required

        """
        return bool(collect(self))

    def change_web_key(self, key: str) -> None:
        """Change password used to access web.

        Args:
            key: New web key

        Raises:
            InvalidKeyError: If key does not match minimum requirements

        """
        if len(key) < utils.MIN_PASS_LEN:
            msg = f"Password must be at least {utils.MIN_PASS_LEN} characters"
            raise exc.InvalidKeyError(msg)

        with self.begin_session():
            Config.set_(ConfigKey.WEB_KEY, key)


class SQLiteDatabase(Database):
    """SQLite-backed database."""

    @override
    def __init__(
        self,
        path: str | Path,
        *,
        check_migration: bool = True,
    ) -> None:
        path_str = str(path)
        if sql.is_postgres_url(path_str):
            msg = "Can only create a SQLiteDatabase with a file path"
            raise exc.UnlockingError(msg)

        self._path_db = Path(path).resolve().with_suffix(".db")
        if not self._path_db.exists():
            msg = f"Database at {self._path_db} does not exist, use Database.create()"
            raise FileNotFoundError(msg)

        super().__init__(path=path, check_migration=check_migration)

    @override
    @classmethod
    def create(cls, path: str | Path) -> Self:
        path_db = Path(path).resolve()
        if path_db.exists():
            msg = f"Database already exists at {path_db}"
            raise FileExistsError(msg)

        path_db.parent.mkdir(parents=True, exist_ok=True)

        cipher_bytes = Cipher.generate().to_bytes()
        cipher_b64 = base64.b64encode(cipher_bytes).decode()

        engine = sql.get_engine(path_db)
        with orm.Session(engine) as s, Base.set_session(s):
            with s.begin():
                Base.metadata_create_all()

            with s.begin():
                # NOTE: Keep DB version at 1.0 unless a BIG change happens
                Config.set_(ConfigKey.VERSION, "1.0")
                Config.set_(ConfigKey.CIPHER, cipher_b64)
                Config.set_(ConfigKey.SECRET_KEY, secrets.token_hex())
                Config.set_(ConfigKey.WEB_KEY, secrets.token_hex())
                Config.set_(ConfigKey.API_BEARER_TOKEN, secrets.token_urlsafe(32))

                Config.set_(ConfigKey.WEB_THEME_SWATCH, web_theme.DEFAULT_SWATCH)
                Config.set_(ConfigKey.WEB_THEME_MOOD, web_theme.DEFAULT_MOOD.name)

                # New databases have all migrations pre-applied
                now = datetime.datetime.now(datetime.UTC)
                for m_class in _MIGRATORS:
                    AppliedMigration.create(name=m_class.__name__, applied_at_utc=now)
        path_db.chmod(0o600)  # Only owner can read/write

        return cls(path_db)

    @property
    @override
    def is_postgres(self) -> bool:
        return False

    @override
    def get_engine(self) -> sqlalchemy.Engine:
        return sql.get_engine(self._path_db)

    @override
    def __str__(self) -> str:
        return f"<SQLiteDatabase@{self.path}>"

    @property
    def path(self) -> Path:
        """Path to SQLite database file."""
        return self._path_db


class PostgresDatabase(Database):
    """Postgres-backed database."""

    @override
    def __init__(
        self,
        path: str | Path,
        *,
        check_migration: bool = True,
    ) -> None:
        path_str = str(path)
        if not sql.is_postgres_url(path_str):
            msg = "Can only create a PostgresDatabase with a postgres URL"
            raise exc.UnlockingError(msg)

        self._postgres_url = sql.normalize_postgres_url(path_str)

        super().__init__(path=path, check_migration=check_migration)

    @override
    @classmethod
    def create(cls, path: str | Path) -> Self:
        url = sql.normalize_postgres_url(str(path))

        cipher_bytes = Cipher.generate().to_bytes()
        cipher_b64 = base64.b64encode(cipher_bytes).decode()

        engine = sql.get_engine_postgres(url)
        with orm.Session(engine) as s, Base.set_session(s):
            with s.begin():
                Base.metadata_create_all()

            with s.begin():
                existing = Config.first()
                if existing is not None:
                    msg = "Postgres database is already initialized"
                    raise FileExistsError(msg)

                # NOTE: Keep DB version at 1.0 unless a BIG change happens
                Config.set_(ConfigKey.VERSION, "1.0")
                Config.set_(ConfigKey.CIPHER, cipher_b64)
                Config.set_(ConfigKey.SECRET_KEY, secrets.token_hex())
                Config.set_(ConfigKey.WEB_KEY, secrets.token_hex())
                Config.set_(ConfigKey.API_BEARER_TOKEN, secrets.token_urlsafe(32))

                Config.set_(ConfigKey.WEB_THEME_SWATCH, web_theme.DEFAULT_SWATCH)
                Config.set_(ConfigKey.WEB_THEME_MOOD, web_theme.DEFAULT_MOOD.name)

                now = datetime.datetime.now(datetime.UTC)
                for m_class in _MIGRATORS:
                    AppliedMigration.create(name=m_class.__name__, applied_at_utc=now)

        return cls(url)

    @property
    @override
    def is_postgres(self) -> bool:
        return True

    @override
    def get_engine(self) -> sqlalchemy.Engine:
        return sql.get_engine_postgres(self._postgres_url)

    @override
    def __str__(self) -> str:
        url = sqlalchemy.engine.make_url(self._postgres_url)
        return f"<PostgresDatabase@{url.render_as_string(hide_password=True)}>"
