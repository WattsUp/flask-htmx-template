from collections.abc import Callable, Iterator
from pathlib import Path

from _pytest.fixtures import FixtureRequest
from _pytest.tmpdir import TempPathFactory
from pytest_postgresql.executor import PostgreSQLExecutor

def postgresql_proc(
    executable: str | None = ...,
    host: str | None = ...,
    port: int | None = ...,
    user: str | None = ...,
    password: str | None = ...,
    dbname: str | None = ...,
    options: str = ...,
    startparams: str | None = ...,
    unixsocketdir: str | None = ...,
    postgres_options: str | None = ...,
    load: list[Callable[..., object] | str | Path] | None = ...,
) -> Callable[[FixtureRequest, TempPathFactory], Iterator[PostgreSQLExecutor]]: ...
