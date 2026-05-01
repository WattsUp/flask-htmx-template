from __future__ import annotations

import re
from pathlib import Path

import pytest

import flask_htmx_template
import tests
from flask_htmx_template import commands, main
from tests.conftest import id_func


@pytest.mark.parametrize(
    "path",
    sorted(
        [
            *Path(flask_htmx_template.__file__).parent.glob("**/*.py"),
            *Path(tests.__file__).parent.glob("**/*.py"),
        ],
    ),
    ids=id_func,
)
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
