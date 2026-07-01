from __future__ import annotations

import re
from pathlib import Path

import pytest

import flask_htmx_template
import tests
from flask_htmx_template import commands, main
from tests.conftest import id_func


def _strip_inline_comment(fragment: str) -> str:
    """Strip a Python inline comment (``# ...``) from a type-arg fragment.

    Args:
        fragment: raw arg fragment, possibly containing a ``#`` comment

    Returns:
        fragment with comment removed

    """
    depth = 0
    for i, ch in enumerate(fragment):
        if ch in {"[", "("}:
            depth += 1
        elif ch in {"]", ")"}:
            depth -= 1
        elif ch == "#" and depth == 0:
            return fragment[:i].strip()
    return fragment


def _parse_tuple_args(inner: str) -> list[str]:
    """Split the top-level comma-separated type args from inside ``tuple[...]``.

    Correctly ignores commas nested inside ``[`` / ``(`` brackets.

    Args:
        inner: source inside a tuple annotation

    Returns:
        List of fragments inside annotation

    """
    args: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in inner:
        if ch in {"[", "("}:
            depth += 1
            current.append(ch)
        elif ch in {"]", ")"}:
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            arg = _strip_inline_comment(" ".join("".join(current).split()))
            if arg:
                args.append(arg)
            current = []
        else:
            current.append(ch)
    last = _strip_inline_comment(" ".join("".join(current).split()))
    if last:
        args.append(last)
    return args


def _find_anon_tuple_violations(source: str) -> dict[int, str]:
    """Return ``{line_number: annotation}`` for non-trivial anonymous tuples.

    Flags any ``tuple[...]`` annotation with 3+ type args — those always
    warrant a ``NamedTuple``. Two-element tuples are considered trivial.

    Args:
        source: source string

    Returns:
        dict of violations

    """
    violations: dict[int, str] = {}
    # Tuples whose every arg is a bare TypeVar name or ellipsis are generic
    # overloads — allowed.
    re_typevar = re.compile(r"^[A-Z][0-9A-Z]*$")
    marker = "tuple["
    i = 0
    while True:
        idx = source.find(marker, i)
        if idx == -1:
            break
        if source[idx - 1] == '"':
            # matching the marker line above lol
            i = idx + 1
            continue
        start = idx + len(marker)
        depth = 1
        j = start
        while j < len(source) and depth > 0:
            if source[j] == "[":
                depth += 1
            elif source[j] == "]":
                depth -= 1
            j += 1
        inner = source[start : j - 1]
        args = _parse_tuple_args(inner)
        if all(re_typevar.match(a) for a in args):
            i = idx + 1
            continue
        if len(args) >= 3:
            line_no = source[:idx].count("\n") + 1
            violations[line_no] = f"tuple[{inner}]"
        i = idx + 1
    return violations


_SOURCE_PATHS = sorted(
    [
        *Path(flask_htmx_template.__file__).parent.glob("**/*.py"),
        *Path(tests.__file__).parent.glob("**/*.py"),
    ],
)


@pytest.mark.parametrize("path", _SOURCE_PATHS, ids=id_func)
def test_noqa(path: Path) -> None:
    lines = path.read_text("utf-8").splitlines()

    allowed_noqa = (
        {
            "ANN202",
            "DTZ001",
            "PLR0124",
            "S105",
            "S106",
            "S603",
            "SLF001",
        }
        if "tests" in path.parts
        else {"S608", "PLR0913"}
    )

    re_noqa = re.compile(r"noqa: ([\w, ]+)")

    errors: list[str] = []

    for i, line in enumerate(lines):
        m = re_noqa.search(line)
        if not m:
            continue
        checks = m.group(1).split(", ")
        errors.extend(
            f"{path}:{i + 1}: disabling {c} is not allowed"
            for c in checks
            if c not in allowed_noqa
        )

    print("\n".join(errors))
    assert not errors


@pytest.mark.parametrize("path", _SOURCE_PATHS, ids=id_func)
def test_anonymous_tuples(path: Path) -> None:
    violations = _find_anon_tuple_violations(path.read_text("utf-8"))
    errors = [
        f"{path}:{line}: non-trivial anonymous tuple: {ann}"
        for line, ann in violations.items()
    ]
    print("\n".join(errors))
    assert not errors


@pytest.mark.parametrize(
    "path",
    sorted(
        [
            Path(main.__file__),
            *Path(commands.__file__).parent.glob("**/*.py"),
        ],
    ),
    ids=id_func,
)
def test_top_imports(path: Path) -> None:
    lines = path.read_text("utf-8").splitlines()

    allowed_imports = {
        "__future__",
        "abc",
        "argcomplete",
        "argparse",
        "colorama",
        "datetime",
        "flask_htmx_template.version",
        "flask_htmx_template.commands",
        "pathlib",
        "sys",
        "typing",
    }

    re_imports = re.compile(r"^(from|import) ([^ ]+)")

    imports: set[str] = set()
    for line in lines:
        if m := re_imports.match(line):
            module = m.group(2)
            if not any(module.startswith(m) for m in allowed_imports):
                imports.add(module)

    assert not imports, "only minimum top level imports allowed for fast time-to-main"
