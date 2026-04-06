"""Database of financial records."""

from __future__ import annotations

import base64
import contextlib
import datetime
import io
import operator
import re
import secrets
import shutil
import sys
import tarfile
from pathlib import Path
from typing import TYPE_CHECKING

import sqlalchemy
import tqdm
from packaging.version import Version
from sqlalchemy import func, orm

from flask_htmx_template import exceptions as exc
from flask_htmx_template import sql, utils
from flask_htmx_template.encryption.top import Encryption, ENCRYPTION_AVAILABLE
from flask_htmx_template.migrations.top import MIGRATORS
from flask_htmx_template.models.base import Base
from flask_htmx_template.models.base_uri import Cipher, load_cipher
from flask_htmx_template.models.config import Config, ConfigKey
from flask_htmx_template.version import __version__

if TYPE_CHECKING:
    from collections.abc import Iterator


class Database:
    """Database."""

    _ENCRYPTION_TEST_VALUE = "flask_htmx_template encryption test string"

    def __init__(
        self,
        path: str | Path,
        key: str | None,
        *,
        check_migration: bool = True,
    ) -> None:
        """Initialize Database.

        Args:
            path: Path to database file
            key: String password to unlock database encryption
            check_migration: True will check if migration is required

        Raises:
            FileNotFoundError: If database does not exist
            MigrationRequiredError: If migration is required

        """
        self._path_db = Path(path).resolve().with_suffix(".db")
        self._path_salt = self._path_db.with_suffix(".nacl")
        self._path_importers = self._path_db.with_suffix(".importers")
        if not self._path_db.exists():
            msg = f"Database at {self._path_db} does not exist, use Database.create()"
            raise FileNotFoundError(msg)
        self._path_importers.mkdir(exist_ok=True)  # Make if it doesn't exist

        if key is None:
            self._enc = None
        elif self._path_salt.exists():
            enc_config = self._path_salt.read_bytes()
            self._enc = Encryption(key, enc_config)
        else:
            msg = f"Database at {self._path_db} does not have salt file"
            raise FileNotFoundError(msg)
        self._session_maker = orm.sessionmaker(self.get_engine())
        configs = self._unlock()

        version_str = configs.get(ConfigKey.VERSION)
        if check_migration and (v := self.migration_required(version_str)):
            msg = f"Database requires migration to v{v}"
            raise exc.MigrationRequiredError(msg)

    @property
    def path(self) -> Path:
        """Path to Database database."""
        return self._path_db

    @property
    def path_salt(self) -> Path:
        """Path to Database salt database."""
        return self._path_salt

    @classmethod
    def is_encrypted_path(cls, path: str | Path) -> bool:
        """Check Database's config for encryption status.

        Args:
            path: Path to database file

        Returns:
            True if Database is encrypted

        Raises:
            FileNotFoundError: If database or configuration does not exist

        """
        path_db = Path(path)
        if not path_db.exists():
            msg = f"Database does not exist at {path_db}"
            raise FileNotFoundError(msg)
        path_salt = path_db.with_suffix(".nacl")
        return path_salt.exists()

    @property
    def is_encrypted(self) -> bool:
        """Check if database is encrypted."""
        return self._enc is not None

    @classmethod
    def create(cls, path: str | Path, key: str | None = None) -> Database:
        """Create a new Database.

        Saves database and configuration file

        Args:
            path: Path to database file
            key: String password to unlock database encryption

        Returns:
            Database linked to newly created database

        Raises:
            FileExistsError: If database already exists

        """
        path_db = Path(path).resolve()
        if path_db.exists():
            msg = f"Database already exists at {path_db}"
            raise FileExistsError(msg)
        path_salt = path_db.with_suffix(".nacl")
        path_importers = path_db.with_suffix(".importers")

        path_db.parent.mkdir(parents=True, exist_ok=True)
        path_importers.mkdir(exist_ok=True)

        enc = None
        enc_config = None
        if ENCRYPTION_AVAILABLE and key is not None:
            enc, enc_config = Encryption.create(key)
            path_salt.write_bytes(enc_config)
            path_salt.chmod(0o600)  # Only owner can read/write
        else:
            # Remove salt if unencrypted
            path_salt.unlink(missing_ok=True)

        cipher_bytes = Cipher.generate().to_bytes()
        cipher_b64 = base64.b64encode(cipher_bytes).decode()

        if enc is None:
            test_value = Database._ENCRYPTION_TEST_VALUE
        else:
            test_value = enc.encrypt(Database._ENCRYPTION_TEST_VALUE)

        engine = sql.get_engine(path_db, enc)
        with orm.Session(engine) as s, Base.set_session(s):
            with s.begin():
                Base.metadata_create_all()

            with s.begin():
                # If developing a migration, current version will be less
                # Set new database to max of __version__ and Migrator.all()
                versions = [
                    Version(__version__),
                    *[m.min_version() for m in MIGRATORS],
                ]
                v = versions[0] if len(versions) == 1 else max(versions)

                Config.set_(ConfigKey.VERSION, str(v))
                Config.set_(ConfigKey.ENCRYPTION_TEST, test_value)
                Config.set_(ConfigKey.CIPHER, cipher_b64)
                Config.set_(ConfigKey.SECRET_KEY, secrets.token_hex())

                if enc is not None and key is not None:
                    Config.set_(ConfigKey.WEB_KEY, enc.encrypt(key))
        path_db.chmod(0o600)  # Only owner can read/write

        return Database(path_db, key)

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
            msg = f"Failed to open database {self._path_db}"
            raise exc.UnlockingError(msg) from e

        value = configs.get(ConfigKey.ENCRYPTION_TEST)
        if value is None:
            msg = "Config.ENCRYPTION_TEST not found"
            raise exc.ProtectedObjectNotFoundError(msg)

        if self._enc is not None:
            try:
                value = self._enc.decrypt_s(value)
            except ValueError as e:
                msg = "Failed to decrypt root password"
                raise exc.UnlockingError(msg) from e

        if value != self._ENCRYPTION_TEST_VALUE:
            msg = "Test value did not match"
            raise exc.UnlockingError(msg)
        # Load Cipher
        cipher_b64 = configs.get(ConfigKey.CIPHER)
        if cipher_b64 is None:
            msg = "Config.CIPHER not found"
            raise exc.ProtectedObjectNotFoundError(msg)
        load_cipher(base64.b64decode(cipher_b64))
        # All good :)
        return configs

    def get_engine(self) -> sqlalchemy.Engine:
        """Get SQL Engine to the database.

        Returns:
            Engine

        """
        return sql.get_engine(self._path_db, self._enc)

    @contextlib.contextmanager
    def begin_session(self) -> Iterator[orm.Session]:
        """Get SQL Session to the database.

        Yields:
            Open Session

        """
        s = self._session_maker()
        with s, s.begin(), Base.set_session(s):
            yield s

    def encrypt(self, secret: bytes | str) -> str:
        """Encrypt a secret using the key.

        Args:
            secret: Secret object

        Returns:
            base64 encoded encrypted object

        Raises:
            NotEncryptedError: If database does not support encryption

        """
        if self._enc is None:
            raise exc.NotEncryptedError
        return self._enc.encrypt(secret)

    def decrypt(self, enc_secret: str) -> bytes:
        """Decrypt an encoded secret using the key.

        Args:
            enc_secret: base64 encoded encrypted object

        Returns:
            bytes decoded object

        Raises:
            NotEncryptedError: If database does not support encryption

        """
        if self._enc is None:
            raise exc.NotEncryptedError
        return self._enc.decrypt(enc_secret)

    def decrypt_s(self, enc_secret: str) -> str:
        """Decrypt an encoded secret using the key.

        Args:
            enc_secret: base64 encoded encrypted string

        Returns:
            decoded string

        """
        return self.decrypt(enc_secret).decode()

    def migration_required(self, version_str: str | None) -> Version | None:
        """Check if migration is required.

        Args:
            version_str: Config VERSION value, will skip extra query

        Returns:
            Version to migrate to or None if migration not required

        """
        if version_str is None:
            with self.begin_session():
                v_db = Config.db_version()
        else:
            v_db = Version(version_str)
        for m in MIGRATORS[::-1]:
            v_m = m.min_version()
            if v_db < v_m:
                return v_m
        return None

    def backup(self) -> tuple[Path, int]:
        """Back up database, duplicates files.

        Returns:
            (Path to newly created backup tar, backup version)

        """
        # Find latest backup file for this Database
        i = 0
        parent = self._path_db.parent
        name = self._path_db.with_suffix("").name
        re_filter = re.compile(rf"^{name}.backup(\d+).tar$")
        for file in parent.iterdir():
            m = re_filter.match(file.name)
            if m is not None:
                i = max(i, int(m.group(1)))
        tar_ver = i + 1

        path_backup = self._path_db.with_suffix(f".backup{tar_ver}.tar")

        with tarfile.open(path_backup, "w") as tar:
            files: list[Path] = [self._path_db]

            if self._path_salt.exists():
                files.append(self._path_salt)

            for file in files:
                tar.add(file, arcname=file.relative_to(parent))
            # Add a timestamp of when it was created
            info = tarfile.TarInfo("_timestamp")
            buf = datetime.datetime.now(datetime.UTC).isoformat().encode()
            info.size = len(buf)
            tar.addfile(info, io.BytesIO(buf))

        path_backup.chmod(0o600)  # Only owner can read/write
        return path_backup, tar_ver

    @classmethod
    def backups(cls, d: str | Path | Database) -> list[tuple[int, datetime.datetime]]:
        """Get a list of all backups for this database.

        Args:
            d: Path to database file, or Database which will get its path

        Returns:
            List[(tar_ver, created timestamp), ...]

        Raises:
            InvalidBackupTarError: If backup is missing timestamp

        """
        backups: list[tuple[int, datetime.datetime]] = []

        path_db = Path(d.path if isinstance(d, Database) else d)
        path_db = path_db.resolve().with_suffix(".db")
        parent = path_db.parent
        name = path_db.with_suffix("").name

        # Find latest backup file for this Database
        re_filter = re.compile(rf"^{name}.backup(\d+).tar$")
        for file in parent.iterdir():
            m = re_filter.match(file.name)
            if m is None:
                continue
            # tar archive preserved owner and mode so no need to set these
            with tarfile.open(file, "r") as tar:
                try:
                    file_ts = tar.extractfile("_timestamp")
                except KeyError as e:
                    # Backup file should always have timestamp file
                    msg = "Backup is missing timestamp"
                    raise exc.InvalidBackupTarError(msg) from e
                if file_ts is None:
                    # Backup file should always have timestamp file
                    msg = "Backup is missing timestamp"
                    raise exc.InvalidBackupTarError(msg)
                tar_ver = int(m[1])
                ts = datetime.datetime.fromisoformat(file_ts.read().decode())
                ts = ts.replace(tzinfo=datetime.UTC)
                backups.append((tar_ver, ts))
        return sorted(backups, key=operator.itemgetter(0))

    def clean(self) -> tuple[int, int]:
        """Delete any unused files, creates a new backup.

        Returns:
            Size of files in bytes:
            (database before, database after)

        """
        parent = self._path_db.parent
        name = self._path_db.with_suffix("").name

        # Create a backup before optimizations
        path_backup, _ = self.backup()
        size_before = self._path_db.stat().st_size

        # Optimize database
        with self.begin_session() as s:
            s.execute(sqlalchemy.text("VACUUM"))

        path_backup_optimized, _ = self.backup()
        size_after = self._path_db.stat().st_size

        # Delete all files that start with name except the fresh backups
        for file in parent.iterdir():
            if file in {path_backup, path_backup_optimized}:
                continue
            if file == self._path_importers:
                continue
            if file.name.startswith(f"{name}."):
                if file.is_dir():
                    shutil.rmtree(file)
                else:
                    file.unlink()

        # Move backup to i=1
        path_new = parent.joinpath(f"{name}.backup1.tar")
        shutil.move(path_backup, path_new)

        # Move optimized backup to i=2
        path_new = parent.joinpath(f"{name}.backup2.tar")
        shutil.move(path_backup_optimized, path_new)

        # Restore the optimized version
        Database.restore(self, tar_ver=2)

        # Delete optimized backup version since that is the live version
        path_new.unlink()

        return (size_before, size_after)

    @classmethod
    def restore(cls, d: str | Path | Database, tar_ver: int | None = None) -> None:
        """Restore Database from backup.

        Args:
            d: Path to database file, or Database which will get its path
            tar_ver: Backup version to restore, None will use latest

        Raises:
            FileNotFoundError: If backup does not exist
            InvalidBackupTarError: If backup is missing required files

        """
        path_db = Path(d.path if isinstance(d, Database) else d)
        path_db = path_db.resolve()
        parent = path_db.parent
        stem = path_db.stem

        tar_ver = tar_ver or cls._latest_backup_version(path_db)

        path_backup = parent.joinpath(f"{stem}.backup{tar_ver}.tar")
        if not path_backup.exists():
            msg = f"Backup does not exist {path_backup}"
            raise FileNotFoundError(msg)

        # tar archive preserved owner and mode so no need to set these
        with tarfile.open(path_backup, "r") as tar:
            required = {
                "_timestamp",
                re.sub(r"\.backup\d+.tar$", ".db", path_backup.name),
            }
            members = tar.getmembers()
            member_paths = [member.path for member in members]
            missing = [m for m in required if m not in member_paths]
            if missing:
                msg = f"Backup is missing required files: {missing}"
                raise exc.InvalidBackupTarError(msg)

            cls.delete_files(path_db)
            for member in members:
                if member.path == "_timestamp":
                    continue
                dest = parent.joinpath(member.path).resolve()
                if not dest.is_relative_to(parent):
                    # Dest should still be relative to parent else, path traversal
                    msg = "Backup contains a file outside of destination"
                    raise exc.InvalidBackupTarError(msg)

                if (
                    (3, 10, 12) <= sys.version_info < (3, 11)
                    or (3, 11, 4) <= sys.version_info < (3, 12)
                    or (3, 12) <= sys.version_info < (3, 14)
                ):  # pragma: no cover
                    # These versions add filter parameter
                    # Don't care which one gets covered
                    tar.extract(member, parent, filter="data")
                else:  # pragma: no cover
                    tar.extract(member, parent)

        # Reload Database
        if isinstance(d, Database):
            d._unlock()  # noqa: SLF001

    @classmethod
    def _latest_backup_version(cls, path_db: Path) -> int:
        """Get the latest backup version available.

        Args:
            path_db: Path to database

        Returns:
            latest version

        Raises:
            FileNotFoundError: if no backups exists

        """
        parent = path_db.parent
        stem = path_db.stem
        # Find latest backup file for this Database
        i = 0
        re_filter = re.compile(rf"^{stem}.backup(\d+).tar$")
        for file in parent.iterdir():
            if m := re_filter.match(file.name):
                i = max(i, int(m.group(1)))
        if i == 0:
            msg = f"No backup exists for {path_db}"
            raise FileNotFoundError(msg)
        return i

    @classmethod
    def delete_files(cls, path_db: Path) -> None:
        """Delete all files and folder for database.

        Args:
            path_db: Path to database

        """
        path_db.unlink(missing_ok=True)
        path_db.with_suffix(".nacl").unlink(missing_ok=True)

        path = path_db.with_suffix(".importers")
        if path.exists() and not path.is_symlink():
            shutil.rmtree(path)

    @staticmethod
    def _copy_tables(
        engine_src: sqlalchemy.Engine,
        engine_dst: sqlalchemy.Engine,
        exclude_tables: set[str],
    ) -> None:
        """Copy tables from source to destination engine, skipping excluded tables.

        Args:
            engine_src: Source database engine
            engine_dst: Destination database engine
            exclude_tables: Table names to skip

        """

        def filter_(tables: list[sqlalchemy.Table]) -> list[sqlalchemy.Table]:
            return [table for table in tables if table.name not in exclude_tables]

        with engine_src.connect() as conn_src, engine_dst.connect() as conn_dst:
            metadata_src = sqlalchemy.MetaData()
            metadata_src.reflect(bind=engine_src)
            metadata_dst = sqlalchemy.MetaData()
            metadata_dst.reflect(bind=engine_dst)

            # Drop destination tables in order of foreign keys
            for table in reversed(filter_(metadata_dst.sorted_tables)):
                table.drop(bind=engine_dst)
            metadata_dst.clear()
            metadata_dst.reflect(bind=engine_dst)

            # Create destination tables in order of foreign keys
            for table in filter_(metadata_src.sorted_tables):
                table.create(bind=engine_dst)
            metadata_dst.clear()
            metadata_dst.reflect(bind=engine_dst)

            # Count total number of rows for progress bar
            col = func.count(sqlalchemy.literal_column("*"))
            n = 0
            for table in filter_(metadata_src.sorted_tables):
                query = sqlalchemy.select(col).select_from(table)
                result = conn_src.execute(query).scalar_one()
                n += result

            # Copy each row, metadata is the same so order of columns is the same
            with tqdm.tqdm(desc="Copying rows", total=n) as bar:
                for table in filter_(metadata_dst.sorted_tables):
                    table_src = metadata_src.tables[table.name]
                    statement = table.insert()
                    select = conn_src.execute(table_src.select())
                    for row in select:
                        conn_dst.execute(statement.values(row))
                        bar.update()

            conn_dst.commit()

    def change_key(self, key: str) -> None:
        """Change database password.

        This also works to add encryption to an unencrypted database.

        Args:
            key: New database key

        Raises:
            InvalidKeyError: If key does not match minimum requirements

        """
        if len(key) < utils.MIN_PASS_LEN:
            msg = f"Password must be at least {utils.MIN_PASS_LEN} characters"
            raise exc.InvalidKeyError(msg)

        # Changing database password requires recreating it
        path_new = self._path_db.with_suffix(".new.db")
        dst = Database.create(path_new, key)

        engine_src = self.get_engine()
        engine_dst = dst.get_engine()

        self._copy_tables(engine_src, engine_dst, exclude_tables={"config"})

        # Use new encryption key
        with self.begin_session():
            value_encrypted = Config.fetch(ConfigKey.WEB_KEY, no_raise=True)
            value = key if value_encrypted is None else self.decrypt_s(value_encrypted)
        dst.change_web_key(value)

        # Move new database into existing
        shutil.copyfile(dst.path, self.path)
        shutil.copyfile(dst.path_salt, self.path_salt)

        # Test unlock
        self._enc = dst._enc  # noqa: SLF001
        self._session_maker = orm.sessionmaker(self.get_engine())
        self._unlock()

        # And delete temporary
        self.delete_files(dst.path)

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

        key_encrypted = self.encrypt(key)
        with self.begin_session():
            Config.set_(ConfigKey.WEB_KEY, key_encrypted)
