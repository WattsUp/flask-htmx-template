from __future__ import annotations

import inspect
import re
from pathlib import Path
from types import ModuleType

from flask_htmx_template import exceptions as exc


def test_all_exported() -> None:
    # Test every exception is in __all__
    exceptions = {
        "http",  # export http for usage: exc.http.HTTPException
    }
    for k in dir(exc):
        if k[0] == "_":
            continue
        obj = getattr(exc, k)
        if not inspect.isclass(obj):
            continue
        if isinstance(obj, ModuleType):
            continue

        assert issubclass(obj, Exception)
        exceptions.add(k)

        # Next checks are for flask_htmx_template custom exceptions only
        if obj.__module__ != exc.__name__:
            continue

        # Class is direct subclass of Exception so try/excepts only work with
        # the specific exception
        assert obj.__base__ is Exception
    assert set(exc.__all__) == exceptions


def test_all_used() -> None:
    # Coverage doesn't check if each Exception is used
    # See if every exception is tested by looking for the test case
    target = {
        "IntegrityError",  # sqlalchemy error: if constraint fails
        "UnboundExecutionError",  # sqlalchemy error: if object has no session
        "NoResultFound",  # sqlalchemy error: if query has no results
    }
    for k in dir(exc):
        if k[0] == "_":
            continue
        obj = getattr(exc, k)
        if not inspect.isclass(obj):
            continue
        if isinstance(obj, ModuleType):
            continue

        assert issubclass(obj, Exception)
        if obj.__module__ != exc.__name__:
            continue
        target.add(k)

    result = {
        "DuplicateURLError",  # DuplicateURLError only raised with bad endpoints
    }
    folder = Path(__file__).parent
    re_raises = re.compile(
        r"exc\.([^_]\w+)[,)]",
        re.MULTILINE,
    )
    for path in folder.glob("**/test_*.py"):
        buf = path.read_text("utf-8")
        result.update(re_raises.findall(buf))

    assert result == target
