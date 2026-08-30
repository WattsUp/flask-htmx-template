from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from tools import run_coverage

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


def _write_coverage_json(output_path: Path, source_path: Path) -> None:
    """Write a complete synthetic Coverage JSON result."""
    report = {
        "files": {
            source_path.as_posix(): {
                "summary": {
                    "num_statements": 9,
                    "missing_lines": 0,
                    "num_branches": 0,
                    "num_partial_branches": 0,
                    "percent_covered": 100.0,
                    "percent_covered_display": "100.00",
                },
                "executed_lines": [1, 2, 3],
                "missing_lines": [],
                "missing_branches": [],
            },
        },
    }
    output_path.write_text(json.dumps(report), encoding="utf-8")


@pytest.fixture
def live_commands(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, ...]]:
    """Capture commands sent through the live subprocess runner.

    Returns:
        A mutable list populated with each command.

    """
    commands: list[tuple[str, ...]] = []

    def run_live_command(command: Sequence[str]) -> int:
        """Record one successful command.

        Returns:
            Zero to represent a successful subprocess.

        """
        commands.append(tuple(command))
        return 0

    monkeypatch.setattr(run_coverage, "run_live_command", run_live_command)
    return commands


@pytest.mark.parametrize(
    ("pytest_return_code", "pytest_output_visible"),
    [(0, False), (1, True)],
)
def test_run_cases_only_prints_failed_pytest_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    pytest_return_code: int,
    pytest_output_visible: bool,
) -> None:
    source_path = Path("flask_htmx_template/controllers/api_docs/json.py")
    coverage_case = run_coverage.CoverageCase(
        source_path,
        Path("tests/controllers/api_docs/test_json.py"),
    )

    def run_command(
        command: Sequence[str],
        environment: Mapping[str, str],
    ) -> subprocess.CompletedProcess[str]:
        """Return synthetic pytest and Coverage JSON subprocess results.

        Returns:
            A completed result matching the requested coverage subcommand.

        """
        assert "COVERAGE_FILE" in environment
        if command[1] == "run":
            return subprocess.CompletedProcess(
                command,
                pytest_return_code,
                stdout="PYTEST DETAILS\n",
            )
        output_path = Path(command[command.index("-o") + 1])
        _write_coverage_json(output_path, source_path)
        return subprocess.CompletedProcess(command, 0, stdout="JSON DETAILS\n")

    monkeypatch.setattr(run_coverage, "run_command", run_command)

    result = run_coverage.run_cases([coverage_case])

    output = capsys.readouterr().out
    assert ("PYTEST DETAILS" in output) is pytest_output_visible
    assert "JSON DETAILS" not in output
    assert "flask_htmx_template/controllers/api_docs/json.py" in output
    assert result == pytest_return_code


def test_make_table_lines_uses_longest_filename_width() -> None:
    rows = [
        run_coverage.CoverageRow("short.py", 1, 0, 0, 0, "100.00%", "", 100.0),
        run_coverage.CoverageRow(
            "directory/long_filename.py",
            10,
            1,
            2,
            1,
            "91.67%",
            "12",
            91.67,
        ),
    ]

    lines = run_coverage.make_table_lines(rows)

    statements_column = lines[0].index("Stmts")
    assert lines[2].index("1") == statements_column + len("Stmts") - 1
    assert lines[3].index("10") == statements_column + len("Stmts") - 2


def test_format_missing_collapses_lines_and_adds_partial_branches() -> None:
    file_coverage: run_coverage.FileCoverage = {
        "summary": {
            "num_statements": 5,
            "missing_lines": 3,
            "num_branches": 2,
            "num_partial_branches": 1,
            "percent_covered": 50.0,
            "percent_covered_display": "50.00",
        },
        "executed_lines": [1, 4],
        "missing_lines": [2, 3, 8],
        "missing_branches": [[4, 7], [8, 9]],
    }

    missing = run_coverage.format_missing(file_coverage)

    assert missing == "2-3, 8, 4->7"


def test_run_standard_without_paths_uses_configured_coverage_command(
    live_commands: list[tuple[str, ...]],
) -> None:
    result = run_coverage.run_standard([])

    assert live_commands == [
        ("coverage", "erase"),
        ("coverage", "run"),
        ("coverage", "report"),
    ]
    assert result == 0


def test_run_standard_maps_targeted_files_and_directories(
    live_commands: list[tuple[str, ...]],
) -> None:
    result = run_coverage.run_standard(
        [
            Path("flask_htmx_template/asgi.py"),
            Path("flask_htmx_template/controllers/api_docs"),
        ],
    )

    assert live_commands[0] == ("coverage", "erase")
    assert live_commands[1] == (
        "coverage",
        "run",
        "-m",
        "pytest",
        "tests/controllers/api_docs",
        "tests/test_asgi.py",
    )
    assert live_commands[2][:2] == ("coverage", "report")
    assert live_commands[2][2:] == (
        "flask_htmx_template/asgi.py",
        "flask_htmx_template/controllers/api_docs/ctx.py",
        "flask_htmx_template/controllers/api_docs/html.py",
        "flask_htmx_template/controllers/api_docs/json.py",
    )
    assert result == 0


def test_run_standard_targets_tools_with_source_override(
    live_commands: list[tuple[str, ...]],
) -> None:
    source_arguments = [Path("tools")]

    result = run_coverage.run_standard(source_arguments)

    assert live_commands == [
        ("coverage", "erase"),
        (
            "coverage",
            "run",
            "--source=tools",
            "-m",
            "pytest",
            "tests/tools",
        ),
        ("coverage", "report", "tools/mcp_connect.py", "tools/run_coverage.py"),
    ]
    assert result == 0


def test_run_cases_targets_tools_with_source_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = Path("tools/run_coverage.py")
    commands: list[tuple[str, ...]] = []

    def run_command(
        command: Sequence[str],
        environment: Mapping[str, str],
    ) -> subprocess.CompletedProcess[str]:
        """Return successful synthetic coverage subprocess results.

        Returns:
            A successful completed subprocess result.

        """
        commands.append(tuple(command))
        assert "COVERAGE_FILE" in environment
        if command[1] == "json":
            output_path = Path(command[command.index("-o") + 1])
            _write_coverage_json(output_path, source_path)
        return subprocess.CompletedProcess(command, 0, stdout="")

    monkeypatch.setattr(run_coverage, "run_command", run_command)
    coverage_case = run_coverage.CoverageCase(
        source_path,
        Path("tests/tools/test_run_coverage.py"),
    )

    result = run_coverage.run_cases([coverage_case])

    assert commands[0] == (
        "coverage",
        "run",
        "--source=tools",
        "-m",
        "pytest",
        "tests/tools/test_run_coverage.py",
    )
    assert result == 0
