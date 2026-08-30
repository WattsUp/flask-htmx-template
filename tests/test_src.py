from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import override

import pytest

import flask_htmx_template
import tests
import tools
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

    Flags any ``tuple[...]`` annotation with 3+ type args - those always
    warrant a ``NamedTuple``. Two-element tuples are considered trivial.

    Args:
        source: source string

    Returns:
        Dict of violations.

    """
    violations: dict[int, str] = {}
    # Tuples whose every arg is a bare TypeVar name or ellipsis are generic
    # overloads - allowed.
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


def _find_hardcoded_url_violations(source: str) -> dict[int, str]:
    """Return ``{line_number: literal}`` for hardcoded URL literals.

    Args:
        source: Python source to inspect.

    Returns:
        Dict of URL-policy violations.

    """
    allowed_url_prefixes: set[str] = set()
    http_methods = {
        "DELETE",
        "GET",
        "HEAD",
        "OPTIONS",
        "PATCH",
        "POST",
        "PUT",
        "delete",
        "get",
        "head",
        "options",
        "patch",
        "post",
        "put",
    }
    http_clients = {"c", "client", "requests", "web_client"}
    violations: dict[int, str] = {}
    tree = ast.parse(source)
    docstring_ids = {
        id(container.body[0].value)
        for container in ast.walk(tree)
        if isinstance(
            container,
            (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        )
        and container.body
        and isinstance(container.body[0], ast.Expr)
        and isinstance(container.body[0].value, ast.Constant)
        and isinstance(container.body[0].value.value, str)
    }

    class URLVisitor(ast.NodeVisitor):
        """Collect hardcoded URL literals and HTTP client paths."""

        EXTERNAL_SCHEMES = ("http://", "https://")

        @override
        def visit_Constant(self, node: ast.Constant) -> None:
            if (
                id(node) not in docstring_ids
                and isinstance(node.value, str)
                and node.value.startswith(self.EXTERNAL_SCHEMES)
                and node.value not in self.EXTERNAL_SCHEMES
                and not any(
                    node.value.startswith(prefix) for prefix in allowed_url_prefixes
                )
            ):
                violations[node.lineno] = node.value

        @override
        def visit_Call(self, node: ast.Call) -> None:
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in http_methods
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in http_clients
            ):
                for arg in node.args:
                    if (
                        isinstance(arg, ast.Constant)
                        and isinstance(arg.value, str)
                        and arg.value.startswith("/")
                    ):
                        violations[arg.lineno] = arg.value
            self.generic_visit(node)

    URLVisitor().visit(tree)
    return violations


_SOURCE_PATHS = sorted(
    [
        *Path(flask_htmx_template.__file__).parent.glob("**/*.py"),
        *Path(tests.__file__).parent.glob("**/*.py"),
        *Path(tools.__file__).parent.glob("**/*.py"),
    ],
)


@pytest.mark.parametrize("path", _SOURCE_PATHS, ids=id_func)
def test_ruff_ignore(path: Path) -> None:
    lines = path.read_text("utf-8").splitlines()

    if "tests" in path.parts:
        allowed_noqa = {
            "call-datetime-without-tzinfo",
            "comparison-with-itself",
            "hardcoded-password-func-arg",
            "hardcoded-password-string",
            "missing-return-type-private-function",
            "private-member-access",
            "subprocess-without-shell-equals-true",
        }
    elif "tools" in path.parts:
        allowed_noqa = {"subprocess-without-shell-equals-true"}
    else:
        allowed_noqa = {
            "hardcoded-sql-expression",
            "typing-only-standard-library-import",
        }

    re_noqa = re.compile(r"ruff: (?:file-)?ignore\[([\w, -]+)\]")
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


@pytest.mark.parametrize("path", _SOURCE_PATHS, ids=id_func)
def test_no_hardcoded_url(path: Path) -> None:
    """Require URL generation instead of hardcoded HTTP paths."""
    lines = path.read_text("utf-8").splitlines()
    ignore = "# flask-htmx-template: ignore[url]"
    violations = _find_hardcoded_url_violations("\n".join(lines))

    errors: list[str] = []
    for i, line in enumerate(lines):
        line_no = i + 1
        ignored = line.rstrip().endswith(ignore)
        if line_no in violations:
            if not ignored:
                errors.append(
                    f"{path}:{line_no}: hardcoded URL literal: "
                    f"{violations[line_no]}, replace with url_for",
                )
        elif ignored:
            errors.append(
                f"{path}:{line_no}: Use of unnecessary '{ignore}'",
            )

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
