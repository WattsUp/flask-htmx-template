"""Interactive JSON API documentation controller."""

from __future__ import annotations

import ast
import inspect
import json
import textwrap
import typing
from collections import defaultdict
from decimal import Decimal
from enum import IntEnum
from types import NoneType, UnionType
from typing import (
    cast,
    get_args,
    get_origin,
    get_type_hints,
    NamedTuple,
    TYPE_CHECKING,
)

from flask_htmx_template import exceptions as exc
from flask_htmx_template import utils
from flask_htmx_template.controllers import base
from flask_htmx_template.models.base import BaseEnum

if TYPE_CHECKING:
    from collections.abc import Callable

    import flask


class _Method(BaseEnum):
    GET = 0
    POST = 1
    PUT = 2
    DELETE = 3

    @property
    def style(self) -> str:
        return {
            _Method.GET: "bg-primary text-on-primary",
            _Method.POST: "bg-secondary text-on-secondary",
            _Method.PUT: "bg-tertiary text-on-tertiary",
            _Method.DELETE: "bg-error text-on-error",
        }[self]


class _Path(NamedTuple):
    name: str
    description: list[str]
    methods: list[_Method]
    request_example: str | None
    response_example: str | None


class _Group(NamedTuple):
    name: str
    paths: list[_Path]


GROUPS: list[_Group] = []


def page() -> flask.Response:
    """GET interactive JSON API documentation page.

    Returns:
        HTML page

    """
    return base.page("api/page.jinja", "API", groups=GROUPS)


# NOTE: Field-name overrides provide meaningful seed values for common fields
# that would otherwise be empty strings or None.
_FIELD_HINTS: dict[str, object] = {
    "name": "Example item",
    "note": "A short note",
    "uri": "1a32f309",
}

_PRIMITIVE_EXAMPLES: dict[type, object] = {
    bool: False,
    str: "",
    int: 0,
    float: 0.0,
    Decimal: Decimal(),
}


def _is_typed_dict(t: type[dict] | object) -> bool:
    return (
        isinstance(t, type) and issubclass(t, dict) and hasattr(t, "__required_keys__")
    )


def _find_typed_dict(t: type[dict] | object) -> type[dict] | None:
    """Find the first TypedDict in a (possibly union) type annotation.

    Returns:
        TypedDict class or None.

    """
    if _is_typed_dict(t):
        return cast("type[dict]", t)

    origin = get_origin(t)
    if origin is UnionType or origin is typing.Union:
        for arg in get_args(t):
            if found := _find_typed_dict(arg):
                return found

    # Expand Python 3.12 `type X = ...` aliases
    if v := getattr(t, "__value__", None):
        return _find_typed_dict(v)
    return None


def _example_value_for_type(annotation: type) -> object:
    """Generate example value for a non-primitive concrete type.

    Returns:
        Example value or None.

    """
    if issubclass(annotation, IntEnum):
        return next(iter(annotation)).name.lower()
    if _is_typed_dict(annotation):
        return _example_from_typed_dict(annotation)
    return None


def _example_value(annotation: type, field_name: str = "") -> object:
    """Generate a sane example value from a type annotation.

    Uses *_FIELD_HINTS* for known field names, otherwise derives a sensible
    default from the type itself.

    Args:
        annotation: Resolved type annotation.
        field_name: Name of the field (for hint lookup).

    Returns:
        A JSON-serialisable example value.

    """
    if field_name in _FIELD_HINTS:
        return _FIELD_HINTS[field_name]

    origin = get_origin(annotation)
    args = get_args(annotation)

    # Unwrap unions (str | None, etc.)
    if origin is UnionType or origin is typing.Union:
        non_none = [a for a in args if a is not NoneType]
        if not non_none or any(a is NoneType for a in args):
            return None
        return _example_value(non_none[0], field_name)

    if annotation in _PRIMITIVE_EXAMPLES:
        return _PRIMITIVE_EXAMPLES[cast("type", annotation)]

    if origin is list:
        return [_example_value(args[0])]

    return _example_value_for_type(annotation)


def _example_from_typed_dict(td: type) -> dict[str, object]:
    """Build an example dict from a TypedDict's field annotations.

    Returns:
        Example dict.

    """
    try:
        hints = get_type_hints(td)
    except Exception:  # noqa: BLE001
        return {}
    return {k: _example_value(v, k) for k, v in hints.items()}


def _extract_response_type(view_func: Callable[..., object]) -> type[dict] | None:
    """Extract the TypedDict from a view function's return annotation.

    Returns:
        TypedDict class or None.

    """
    try:
        # NOTE: Some controllers import base under TYPE_CHECKING only, so
        # get_type_hints() can't resolve "base.JSONResponse" from module
        # globals.  Supplying base explicitly fixes the NameError.
        hints = get_type_hints(view_func, localns={"base": base})
    except Exception:  # noqa: BLE001
        return None
    ret = hints.get("return")
    if ret is None:
        return None
    return _find_typed_dict(ret)


def _extract_request_type(view_func: Callable[..., object]) -> type[dict] | None:
    """Find the TypedDict passed to ``validate_json()`` in the function source.

    Scans the AST for ``validate_json(data, SomeTypedDict)`` and resolves
    *SomeTypedDict* from the view function's module globals.

    Returns:
        TypedDict class or None.

    """
    try:
        source = textwrap.dedent(inspect.getsource(view_func))
        tree = ast.parse(source)
    except (OSError, TypeError, SyntaxError):
        return None

    module = inspect.getmodule(view_func)
    if not module:
        return None

    min_validate_args = 2
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_validate = (
            isinstance(func, ast.Attribute) and func.attr == "validate_json"
        ) or (isinstance(func, ast.Name) and func.id == "validate_json")
        # TODO (WattsUp): #0 remove unused keys (uri, today)
        if is_validate and len(node.args) >= min_validate_args:
            type_arg = node.args[1]
            if isinstance(type_arg, ast.Name):
                type_obj = getattr(module, type_arg.id, None)
                if type_obj and _is_typed_dict(type_obj):
                    return cast("type[dict]", type_obj)
    return None


def get_paths(app: flask.Flask) -> dict[str, list[_Path]]:
    """Scan /j/ routes and build operation documentation.

    Generates request/response examples by introspecting TypedDict annotations
    on view functions and their ``validate_json()`` calls.

    Args:
        app: Flask application whose URL map is scanned.

    Returns:
        List of all paths by groups, unordered and flat

    Raises:
        InvalidEndpointError: If an endpoint is missing type annotations

    """
    groups: dict[str, list[_Path]] = defaultdict(list)

    for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
        path = str(rule.rule)
        if not path.startswith("/j/"):
            continue
        view = app.view_functions.get(rule.endpoint)
        if not view:
            continue

        paragraphs: list[str] = [""]
        raw_doc = inspect.getdoc(view) or "The devs forgot pydocs, grr"
        for raw in raw_doc.splitlines():
            if raw.startswith(("Args:", "Returns:", "Raises:")):
                break
            line = raw.strip()
            if not line:
                paragraphs.append("")
            else:
                paragraphs[-1] += " " + line
        desc = [p for p in paragraphs if p]

        group = str(rule.endpoint).split(".", 1)[0].capitalize()
        methods = (rule.methods or set()) - {"HEAD", "OPTIONS"}

        request_td = _extract_request_type(view)
        response_td = _extract_response_type(view)

        if response_td is None:
            msg = f"{rule.endpoint} is missing a response type"
            raise exc.InvalidEndpointError(msg)

        # TODO (WattsUp): #0 Format request_td as schema AND example
        # TODO (WattsUp): #0 separate out each method. So get/put shows no body for get

        request_json = (
            json.dumps(
                utils.json_mutate(_example_from_typed_dict(request_td)),
                indent=2,
            )
            if request_td
            else None
        )
        response_json = json.dumps(
            utils.json_mutate(_example_from_typed_dict(response_td)),
            indent=2,
        )
        groups[group].append(
            _Path(
                path,
                desc,
                sorted(_Method(m) for m in methods),
                request_json,
                response_json,
            ),
        )

    return groups


def init_docs(app: flask.Flask) -> None:
    """Populate the docs cache at startup.

    Called once from web.FlaskExtension.init_app() after all routes are
    registered.

    Args:
        app: Flask application to scan.

    """
    groups: list[_Group] = []
    for group, paths_unsorted in get_paths(app).items():
        paths = sorted(paths_unsorted, key=lambda path: path.name.lower())
        groups.append(_Group(group, paths))

    # globals shenanigans
    GROUPS.clear()
    GROUPS.extend(sorted(groups, key=lambda g: g.name.lower()))


ROUTES: base.Routes = {
    "/api": (page, ["GET"]),
    # TODO (WattsUp): #0 Add json endpoint to get the same info
}
