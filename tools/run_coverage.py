#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK
"""Run isolated tests and combine their per-file coverage results."""

from __future__ import annotations

import argparse
import json
import os
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import cast, NamedTuple, TYPE_CHECKING, TypedDict

import argcomplete

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
SOURCE_ROOT = Path("flask_htmx_template")
TEST_ROOT = Path("tests")
REQUIRED_COVERAGE_PERCENT = 100.0
BRANCH_ARC_LENGTH = 2


class CoverageSummary(TypedDict):
    """Coverage JSON summary fields used by the combined report."""

    num_statements: int
    missing_lines: int
    num_branches: int
    num_partial_branches: int
    percent_covered: float
    percent_covered_display: str


class FileCoverage(TypedDict):
    """Coverage JSON fields used for one source file."""

    summary: CoverageSummary
    executed_lines: list[int]
    missing_lines: list[int]
    missing_branches: list[list[int]]


class CoverageJson(TypedDict):
    """Relevant structure of a Coverage JSON report."""

    files: dict[str, FileCoverage]


class CoverageCase(NamedTuple):
    """One source file and the tests selected to cover it."""

    source_path: Path
    test_path: Path


class CoverageRow(NamedTuple):
    """One row in the combined per-file coverage table."""

    name: str
    statements: int
    missing: int
    branches: int
    partial_branches: int
    cover: str
    missing_description: str
    percent_covered: float


def normalize_source_path(raw_path: Path) -> Path:
    """Normalize and validate a source path.

    Args:
        raw_path: User-provided source file or directory.

    Returns:
        A normalized path rooted under the source package.

    Raises:
        ValueError: If the path is outside the source package or does not exist.

    """
    source_path = Path(os.path.normpath(raw_path))
    source_parents = {source_path, *source_path.parents}
    if source_path.is_absolute() or SOURCE_ROOT not in source_parents:
        message = f"Source path must begin with {SOURCE_ROOT}/: {raw_path}"
        raise ValueError(message)
    if not (REPOSITORY_ROOT / source_path).exists():
        message = f"Source path does not exist: {source_path}"
        raise ValueError(message)
    return source_path


def expand_source_paths(raw_paths: Sequence[Path]) -> list[Path]:
    """Expand source directories into individual Python files.

    Args:
        raw_paths: User-provided source paths, or an empty sequence for all sources.

    Returns:
        Source files in argument and directory traversal order without duplicates.

    Raises:
        ValueError: If a source directory contains no Python files.

    """
    source_paths: list[Path] = []
    seen_paths: set[Path] = set()
    for raw_path in raw_paths or (SOURCE_ROOT,):
        source_path = normalize_source_path(raw_path)
        absolute_source_path = REPOSITORY_ROOT / source_path
        expanded_paths = (
            [
                path.relative_to(REPOSITORY_ROOT)
                for path in absolute_source_path.rglob("*.py")
            ]
            if absolute_source_path.is_dir()
            else [source_path]
        )
        if not expanded_paths:
            message = f"Source directory contains no Python files: {source_path}"
            raise ValueError(message)
        for expanded_path in expanded_paths:
            if expanded_path not in seen_paths and expanded_path.name not in {
                "__init__.py",
                "version.py",
            }:
                seen_paths.add(expanded_path)
                source_paths.append(expanded_path)
    return sorted(source_paths)


def find_test_path(source_path: Path) -> Path:
    """Find the narrowest test target associated with a source file.

    Args:
        source_path: Python source file under the package root.

    Returns:
        The closest matching test file or directory.

    Raises:
        ValueError: If no corresponding test target exists.

    """
    source_relative = source_path.relative_to(SOURCE_ROOT)
    test_parent = TEST_ROOT / source_relative.parent
    candidates = (
        test_parent / f"test_{source_path.name}",
        TEST_ROOT / source_relative.with_suffix(""),
        test_parent,
    )
    for candidate in candidates:
        if (REPOSITORY_ROOT / candidate).exists():
            return candidate
    message = f"Could not find a targeted test for source path: {source_path}"
    raise ValueError(message)


def find_target_test_path(source_path: Path) -> Path:
    """Find the test target for a source file or directory.

    Args:
        source_path: Source file or directory under the package root.

    Returns:
        The narrowest corresponding test file or directory.

    Raises:
        ValueError: If no corresponding test target exists.

    """
    absolute_source_path = REPOSITORY_ROOT / source_path
    if absolute_source_path.is_file():
        return find_test_path(source_path)
    source_relative = source_path.relative_to(SOURCE_ROOT)
    test_path = TEST_ROOT / source_relative
    if (REPOSITORY_ROOT / test_path).is_dir():
        return test_path
    message = f"Could not find a targeted test for source path: {source_path}"
    raise ValueError(message)


def make_cases(source_paths: Sequence[Path]) -> list[CoverageCase]:
    """Pair source files with their closest test targets.

    Args:
        source_paths: Individual Python source files.

    Returns:
        Coverage cases in source path order.

    """
    return [CoverageCase(path, find_test_path(path)) for path in source_paths]


def format_missing(file_coverage: FileCoverage) -> str:
    """Format missing lines and partial branches for one coverage row.

    Args:
        file_coverage: Parsed Coverage JSON data for one file.

    Returns:
        Coverage-style missing line and branch descriptions.

    """
    missing_lines = file_coverage["missing_lines"]
    ranges: list[str] = []
    if missing_lines:
        range_start = range_end = missing_lines[0]
        for line in missing_lines[1:]:
            if line == range_end + 1:
                range_end = line
                continue
            ranges.append(
                (
                    str(range_start)
                    if range_start == range_end
                    else f"{range_start}-{range_end}"
                ),
            )
            range_start = range_end = line
        ranges.append(
            (
                str(range_start)
                if range_start == range_end
                else f"{range_start}-{range_end}"
            ),
        )

    arcs: dict[int, list[int]] = defaultdict(list)
    for branch in file_coverage["missing_branches"]:
        if len(branch) == BRANCH_ARC_LENGTH:
            arcs[branch[0]].append(branch[1])
    missing_line_set = set(missing_lines)
    for source_line, destinations in arcs.items():
        if source_line in missing_line_set:
            continue
        for destination_line in destinations:
            destination = "exit" if destination_line < 0 else str(destination_line)
            ranges.append(f"{source_line}->{destination}")
    return ", ".join(ranges)


def row_from_json(source_path: Path, json_path: Path) -> CoverageRow:
    """Load one source file's result from a Coverage JSON report.

    Args:
        source_path: Source file represented by the report.
        json_path: Coverage JSON output path.

    Returns:
        A formatted combined-table row.

    Raises:
        ValueError: If the report does not contain the requested source file.

    """
    with json_path.open(encoding="utf-8") as file_obj:
        report = cast("CoverageJson", json.load(file_obj))
    file_coverage = report["files"].get(source_path.as_posix())
    if file_coverage is None:
        message = f"Coverage JSON contains no result for: {source_path}"
        raise ValueError(message)
    summary = file_coverage["summary"]
    return CoverageRow(
        name=source_path.as_posix(),
        statements=summary["num_statements"],
        missing=summary["missing_lines"],
        branches=summary["num_branches"],
        partial_branches=summary["num_partial_branches"],
        cover=f'{summary["percent_covered_display"]}%',
        missing_description=format_missing(file_coverage),
        percent_covered=summary["percent_covered"],
    )


def make_table_lines(rows: Sequence[CoverageRow]) -> list[str]:
    """Build a combined Coverage-style table.

    Args:
        rows: Per-file coverage rows.

    Returns:
        Header, separator, data, and closing separator lines.

    """
    name_width = max(len("Name"), *(len(row.name) for row in rows))
    cover_width = max(len("Cover"), *(len(row.cover) for row in rows))

    def make_line(values: Mapping[str, str]) -> str:
        """Format one table line.

        Args:
            values: Display value for each coverage column.

        Returns:
            One aligned table line.

        """
        return (
            f'{values["name"]:<{name_width}}  {values["statements"]:>5}  '
            f'{values["missing"]:>4}  {values["branches"]:>6}  '
            f'{values["partial"]:>6}  {values["cover"]:>{cover_width}}  '
            f'{values["missing_description"]}'
        ).rstrip()

    header = make_line(
        {
            "name": "Name",
            "statements": "Stmts",
            "missing": "Miss",
            "branches": "Branch",
            "partial": "BrPart",
            "cover": "Cover",
            "missing_description": "Missing",
        },
    )
    lines = [header, "-" * len(header)]
    lines.extend(
        make_line(
            {
                "name": row.name,
                "statements": str(row.statements),
                "missing": str(row.missing),
                "branches": str(row.branches),
                "partial": str(row.partial_branches),
                "cover": row.cover,
                "missing_description": row.missing_description,
            },
        )
        for row in rows
    )
    lines.append("-" * len(header))
    return lines


def run_command(
    command: Sequence[str],
    environment: Mapping[str, str],
) -> subprocess.CompletedProcess[str]:
    """Run a captured subprocess.

    Args:
        command: Executable and command-line arguments.
        environment: Complete subprocess environment.

    Returns:
        The completed subprocess result.

    """
    return subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
        command,
        check=False,
        cwd=REPOSITORY_ROOT,
        env=environment,
        stderr=subprocess.STDOUT,
        stdout=subprocess.PIPE,
        text=True,
    )


def run_live_command(command: Sequence[str]) -> int:
    """Run a subprocess with output connected to the terminal.

    Args:
        command: Executable and command-line arguments.

    Returns:
        The subprocess exit status.

    """
    result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
        command,
        check=False,
        cwd=REPOSITORY_ROOT,
    )
    return result.returncode


def run_standard(source_arguments: Sequence[Path]) -> int:
    """Run full or combined targeted coverage.

    Args:
        source_arguments: Source paths to target, or an empty sequence for all tests.

    Returns:
        The first failing Coverage or pytest exit status, otherwise zero.

    """
    if not source_arguments:
        commands = (
            ("coverage", "erase"),
            ("coverage", "run"),
            ("coverage", "report"),
        )
    else:
        source_paths = [normalize_source_path(path) for path in source_arguments]
        test_paths = sorted(
            {find_target_test_path(path) for path in source_paths},
        )
        report_paths = sorted(set(expand_source_paths(source_paths)))
        commands = (
            ("coverage", "erase"),
            ("coverage", "run", "-m", "pytest", *(str(path) for path in test_paths)),
            ("coverage", "report", *(str(path) for path in report_paths)),
        )
    for command in commands:
        status = run_live_command(command)
        if status != 0:
            return status
    return 0


def run_cases(cases: Sequence[CoverageCase]) -> int:
    """Run isolated tests and print their combined coverage table.

    Args:
        cases: Source/test pairs to run independently.

    Returns:
        Zero if all tests pass with complete coverage, otherwise one.

    """
    rows: list[CoverageRow] = []
    failed = False
    with tempfile.TemporaryDirectory(prefix="run-coverage-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        for index, case in enumerate(cases):
            print(f"=== {case.source_path} (tests: {case.test_path}) ===", flush=True)
            environment = os.environ.copy()
            environment["COVERAGE_FILE"] = str(temp_dir / f"coverage-{index}")
            test_result = run_command(
                ("coverage", "run", "-m", "pytest", str(case.test_path)),
                environment,
            )
            if test_result.returncode != 0:
                failed = True
                ending = "" if test_result.stdout.endswith("\n") else "\n"
                print(test_result.stdout, end=ending)

            json_path = temp_dir / f"coverage-{index}.json"
            json_result = run_command(
                (
                    "coverage",
                    "json",
                    "--fail-under=0",
                    f"--include={case.source_path}",
                    "-o",
                    str(json_path),
                ),
                environment,
            )
            if json_result.returncode != 0:
                failed = True
                print(json_result.stdout, file=sys.stderr, end="")
                continue
            try:
                row = row_from_json(case.source_path, json_path)
            except (
                KeyError,
                OSError,
                TypeError,
                ValueError,
                json.JSONDecodeError,
            ) as error:
                failed = True
                print(error, file=sys.stderr)
                continue
            rows.append(row)
            if row.percent_covered < REQUIRED_COVERAGE_PERCENT:
                failed = True

    if rows:
        print()
        print(*make_table_lines(rows), sep="\n")
    return int(failed)


def main(command_line: list[str] | None = None) -> int:
    """Run full, targeted, or per-file coverage.

    Args:
        command_line: Command-line arguments, or None for sys.argv.

    Returns:
        Zero if the selected coverage workflow succeeds, otherwise nonzero.

    """
    parser = argparse.ArgumentParser(
        description="Run full, targeted, or isolated per-file coverage.",
    )
    parser.add_argument(
        "--per-file",
        action="store_true",
        help="run each source file's tests and coverage independently",
    )
    parser.add_argument(
        "source_paths",
        nargs="*",
        type=Path,
        metavar="SOURCE_PATH",
        help=f"source file or directory under {SOURCE_ROOT} (default: all)",
    )
    argcomplete.autocomplete(parser)
    arguments = parser.parse_args(command_line)
    try:
        if not arguments.per_file:
            return run_standard(arguments.source_paths)
        source_paths = expand_source_paths(arguments.source_paths)
        return run_cases(make_cases(source_paths))
    except ValueError as error:
        parser.error(str(error))


if __name__ == "__main__":
    sys.exit(main())
