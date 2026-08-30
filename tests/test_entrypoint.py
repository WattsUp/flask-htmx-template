from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Sequence


class EntrypointRunner:
    """Run the container entrypoint with temporary command stubs."""

    def __init__(self, tmp_path: Path) -> None:
        self._root = tmp_path
        self._bin = tmp_path / "bin"
        self._bin.mkdir()
        self._log = tmp_path / "commands.log"
        self.sqlite_path = tmp_path / "database.db"
        source = Path(__file__).resolve().parents[1] / "docker" / "entrypoint.sh"
        self._entrypoint = tmp_path / "entrypoint.sh"
        script = source.read_text(encoding="utf-8")
        script = script.replace(
            "/home/python/.local/bin/flask_htmx_template",
            str(self._bin / "flask_htmx_template"),
        )
        script = script.replace(
            "/home/python/.local/bin/gunicorn",
            str(self._bin / "gunicorn"),
        )
        self._entrypoint.write_text(script, encoding="utf-8")
        self._entrypoint.chmod(0o755)
        for command in ("flask_htmx_template", "gunicorn"):
            self._write_command(command)

    def _write_command(self, command: str) -> None:
        script = """#!/bin/sh
printf '%s' "$(basename "$0")" >> "$COMMAND_LOG"
for arg in "$@"; do
  printf '\\t%s' "$arg" >> "$COMMAND_LOG"
done
printf '\\n' >> "$COMMAND_LOG"
if [ "${3:-}" = "create" ]; then
  case "${CREATE_RESULT:-success}" in
  success) exit 0 ;;
  already-initialized)
    printf '%s\\n' 'database already initialized' >&2
    exit 2
    ;;
  failure)
    printf '%s\\n' 'postgres connection failed' >&2
    exit 1
    ;;
  esac
fi
exit 0
"""
        path = self._bin / command
        path.write_text(script, encoding="utf-8")
        path.chmod(
            stat.S_IRUSR
            | stat.S_IWUSR
            | stat.S_IXUSR
            | stat.S_IRGRP
            | stat.S_IXGRP
            | stat.S_IROTH
            | stat.S_IXOTH,
        )

    def run(
        self,
        database: Path | str,
        *,
        create_result: str = "success",
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment.update(
            {
                "COMMAND_LOG": str(self._log),
                "CREATE_RESULT": create_result,
                "DB_PATH": str(database),
                "DB_WEB_KEY": "test-web-key",
                "PROMETHEUS_MULTIPROC_DIR": str(self._root / "prometheus"),
            },
        )
        return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
            ["/bin/sh", str(self._entrypoint)],
            capture_output=True,
            check=False,
            cwd=self._root,
            env=environment,
            shell=False,
            text=True,
        )

    @property
    def commands(self) -> list[list[str]]:
        """Command invocations recorded by the stubs."""
        if not self._log.exists():
            return []
        return [line.split("\t") for line in self._log.read_text().splitlines()]


@pytest.fixture
def entrypoint_runner(tmp_path: Path) -> EntrypointRunner:
    """Create a runner for the temporary entrypoint test environment.

    Returns:
        Runner configured with temporary command stubs

    """
    return EntrypointRunner(tmp_path)


@pytest.mark.parametrize(
    ("database_kind", "existing", "create_result", "expected_actions"),
    [
        ("sqlite", False, "success", ["create", "change-password", "migrate"]),
        ("sqlite", True, "success", ["migrate"]),
        ("postgres", False, "success", ["create", "change-password", "migrate"]),
        ("postgresql", True, "already-initialized", ["create", "migrate"]),
        (
            "postgresql+psycopg",
            False,
            "success",
            ["create", "change-password", "migrate"],
        ),
    ],
    ids=[
        "new-sqlite",
        "existing-sqlite",
        "new-postgres",
        "existing-postgres",
        "new-postgres-driver-url",
    ],
)
def test_entrypoint_initializes_database(
    entrypoint_runner: EntrypointRunner,
    database_kind: str,
    existing: bool,
    create_result: str,
    expected_actions: Sequence[str],
) -> None:
    # Arrange
    database: Path | str = (
        entrypoint_runner.sqlite_path
        if database_kind == "sqlite"
        else f"{database_kind}://test:test@localhost/test"
    )
    if existing and database_kind == "sqlite":
        assert isinstance(database, Path)
        database.touch()

    # Act
    result = entrypoint_runner.run(database, create_result=create_result)

    # Assert
    assert result.returncode == 0
    cli_calls = [
        call for call in entrypoint_runner.commands if call[0] == "flask_htmx_template"
    ]
    assert [call[3] for call in cli_calls] == list(expected_actions)
    assert all(call[2] == str(database) for call in cli_calls)
    password_calls = [call for call in cli_calls if call[3] == "change-password"]
    if "change-password" in expected_actions:
        assert password_calls == [
            [
                "flask_htmx_template",
                "--database",
                str(database),
                "change-password",
                "--new-pass",
                "test-web-key",
            ],
        ]
    else:
        assert not password_calls
    assert entrypoint_runner.commands[-1][0] == "gunicorn"


def test_entrypoint_stops_on_postgres_creation_failure(
    entrypoint_runner: EntrypointRunner,
) -> None:
    # Arrange
    database = "postgres://test:test@localhost/test"

    # Act
    result = entrypoint_runner.run(database, create_result="failure")

    # Assert
    assert result.returncode == 1
    assert entrypoint_runner.commands == [
        ["flask_htmx_template", "--database", database, "create"],
    ]
