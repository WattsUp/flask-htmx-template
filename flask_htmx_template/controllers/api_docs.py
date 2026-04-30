"""Interactive JSON API documentation controller.

Title: API Documentation
"""

from __future__ import annotations

import ast
import datetime
import inspect
import json
import textwrap
import typing
from decimal import Decimal
from enum import IntEnum
from types import NoneType, UnionType
from typing import (
    cast,
    get_args,
    get_origin,
    get_type_hints,
    NamedTuple,
    NewType,
    NotRequired,
    Self,
    TYPE_CHECKING,
    TypedDict,
)

from flask_htmx_template import exceptions as exc
from flask_htmx_template import utils
from flask_htmx_template.controllers import base
from flask_htmx_template.models.base import BaseEnum

if TYPE_CHECKING:
    import types
    from collections.abc import Callable

    import flask


class _Method(BaseEnum):
    GET = 0
    POST = 1
    PUT = 2
    DELETE = 3

    @property
    def badge(self) -> str:
        return {
            _Method.GET: "bg-primary text-on-primary",
            _Method.POST: "bg-secondary text-on-secondary",
            _Method.PUT: "bg-tertiary text-on-tertiary",
            _Method.DELETE: "bg-error text-on-error",
        }[self]

    @property
    def container(self) -> str:
        return {
            _Method.GET: "bg-primary-container text-on-primary-container",
            _Method.POST: "bg-secondary-container text-on-secondary-container",
            _Method.PUT: "bg-tertiary-container text-on-tertiary-container",
            _Method.DELETE: "bg-error-container text-on-error-container",
        }[self]


URL = NewType("URL", str)
Method = NewType("Method", str)
Status = NewType("Status", str)


class _ResponseInfo(NamedTuple):
    schema: str | dict[str, object] | list[object]
    example: object

    @property
    def schema_json(self) -> str:
        """Serialized schema."""
        return json.dumps(self.schema, indent=2)

    @property
    def example_json(self) -> str:
        """Serialized example."""
        return json.dumps(self.example, indent=2)


class _Operation(NamedTuple):
    url: str
    method: _Method
    description: list[str]
    request_schema: dict[str, object] | None
    request_example: dict[str, object] | None
    responses: dict[str, _ResponseInfo]

    @property
    def request_schema_json(self) -> str | None:
        """Serialized request schema, or None if no request body."""
        if self.request_schema is None:
            return None
        return json.dumps(self.request_schema, indent=2)

    @property
    def request_example_json(self) -> str | None:
        """Serialized request example, or None if no request body."""
        if self.request_example is None:
            return None
        return json.dumps(self.request_example, indent=2)

    @classmethod
    def extract(cls, path: str, method: _Method, view: Callable[..., object]) -> Self:
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
        desc = [p.strip() for p in paragraphs if p.strip()]

        request_td = _extract_request_type(view)
        response_anns = _extract_response_annotations(view)

        if not response_anns:
            msg = f"{method.name} {path} is missing a response type"
            raise exc.InvalidEndpointError(msg)

        if request_td:
            req_schema = _schema_from_typed_dict(request_td, skip_not_required=True)
            req_example = cast(
                "dict[str, object]",
                utils.json_mutate(
                    _example_from_typed_dict(request_td, skip_not_required=True),
                ),
            )
        else:
            req_schema = None
            req_example = None

        responses: dict[str, _ResponseInfo] = {
            status: _ResponseInfo(
                _schema_type(ann),
                utils.json_mutate(_example_value(ann)),
            )
            for status, ann in response_anns.items()
        }
        return cls(path, method, desc, req_schema, req_example, responses)


class _Group(NamedTuple):
    name: str
    description: list[str]
    operations: list[_Operation]


class _ResponseInfoJSON(TypedDict):
    schema: object
    example: object


class _OperationJSON(TypedDict):
    description: list[str]
    request_schema: dict[str, object] | None
    request_example: dict[str, object] | None
    responses: dict[Status, _ResponseInfoJSON]


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

# NOTE: Dict-key examples provide meaningful seed values for NewType key aliases.
_KEY_EXAMPLES: dict[str, str] = {
    "url": "/j/api",
    "method": "GET",
    "status": "200",
}

_PRIMITIVE_EXAMPLES: dict[type, object | Callable[[], object]] = {
    object: dict,
    bool: False,
    str: "a string of words",
    int: 3,
    float: 3.1,
    Decimal: Decimal("3.14159"),
    datetime.date: lambda: datetime.datetime.now(datetime.UTC).date(),
    datetime.datetime: lambda: datetime.datetime.now(datetime.UTC),
}


def _is_typed_dict(t: object) -> bool:
    return (
        isinstance(t, type)
        and issubclass(t, dict)
        and hasattr(cast("type[dict[object, object]]", t), "__required_keys__")
    )


def _find_typed_dict(t: object) -> type[dict[str, object]] | None:
    """Find the first TypedDict in a (possibly union or generic) type annotation.

    Returns:
        TypedDict class or None.

    """
    if _is_typed_dict(t):
        return cast("type[dict[str, object]]", t)

    origin = get_origin(t)
    if origin is UnionType or origin is typing.Union:
        for arg in get_args(t):
            if found := _find_typed_dict(arg):
                return found

    # Recurse into the value type of dict[K, V] (e.g. dict[str, dict[str, TD]])
    if origin is dict:
        dict_args = get_args(t)
        if dict_args[1:] and (found := _find_typed_dict(dict_args[1])):
            return found

    # Expand Python 3.12 `type X = ...` aliases
    if v := getattr(t, "__value__", None):
        return _find_typed_dict(v)
    return None


def _example_value_for_type(
    annotation: object,
    *,
    skip_not_required: bool = False,
) -> object:
    """Generate example value for a non-primitive concrete type.

    Returns:
        Example value or None.

    """
    if isinstance(annotation, type) and issubclass(annotation, IntEnum):
        return next(iter(annotation)).name.lower()
    if _is_typed_dict(cast("object", annotation)):
        return _example_from_typed_dict(
            cast("type[dict[str, object]]", annotation),
            skip_not_required=skip_not_required,
        )
    return None


def _example_collection(
    origin: object,
    args: tuple[object, ...],
    *,
    skip_not_required: bool = False,
) -> object:
    """Return example for list/dict collection types, or None if not a collection.

    Returns:
        A list, dict, or None.

    """
    if origin is list and args:
        return [_example_value(args[0], skip_not_required=skip_not_required)]
    if origin is dict and args[1:]:
        if args[1] is object:
            return {}
        return {
            _key_example_value(args[0]): _example_value(
                args[1],
                skip_not_required=skip_not_required,
            ),
        }
    return None


def _example_value(
    annotation: object,
    field_name: str = "",
    *,
    skip_not_required: bool = False,
) -> object:
    """Generate a sane example value from a type annotation.

    Uses *_FIELD_HINTS* for known field names, otherwise derives a sensible
    default from the type itself.

    Args:
        annotation: Resolved type annotation.
        field_name: Name of the field (for hint lookup).
        skip_not_required: Passed through to nested TypedDict expansion.

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
        return _example_value(
            non_none[0],
            field_name,
            skip_not_required=skip_not_required,
        )

    prim = _PRIMITIVE_EXAMPLES.get(cast("type[object]", annotation))
    if prim is not None:
        return prim() if callable(prim) else prim

    if result := _example_collection(origin, args, skip_not_required=skip_not_required):
        return result

    return _example_value_for_type(annotation, skip_not_required=skip_not_required)


def _example_from_typed_dict(
    td: type[dict[str, object]],
    *,
    skip_not_required: bool = False,
) -> dict[str, object]:
    """Build an example dict from a TypedDict's field annotations.

    Args:
        td: TypedDict class.
        skip_not_required: When True, omit fields annotated with NotRequired.

    Returns:
        Example dict.

    """
    try:
        hints = get_type_hints(td, include_extras=True)
    except Exception:  # noqa: BLE001
        return {}
    result: dict[str, object] = {}
    for k, v in hints.items():
        if skip_not_required and get_origin(v) is NotRequired:
            continue
        # Unwrap NotRequired[X] -> X before generating example value
        annotation = get_args(v)[0] if get_origin(v) is NotRequired else v
        result[k] = _example_value(annotation, k, skip_not_required=skip_not_required)
    return result


_JSON_TYPE_NAMES: dict[type[object], str] = {
    NoneType: "null",
    object: "object",
    bool: "boolean",
    str: "string",
    int: "number",
    float: "number",
    Decimal: "number or number string",
    datetime.date: "ISO-8601 date string",
    datetime.datetime: "ISO-8601 date & time string",
}


def _key_schema_label(key_type: object) -> str:
    """Return a schema placeholder like ``<url>`` for a NewType key, or ``<key>``.

    Returns:
        Placeholder string for use as a dict key in a schema.

    """
    name = getattr(key_type, "__name__", None)
    if name and name not in {"str", "int", "object"}:
        return f"<{name.lower()}>"
    return "<key>"


def _key_example_value(key_type: object) -> str:
    """Return an example value for a dict key type.

    Looks up ``_KEY_EXAMPLES`` for known NewType key names, falls back to a
    ``<name>`` placeholder, or ``<example_key>`` for plain built-in types.

    Returns:
        Example string for use as a dict key.

    """
    name = getattr(key_type, "__name__", None)
    if not name or name in {"str", "int", "object"}:
        return "<example_key>"
    return _KEY_EXAMPLES.get(name.lower(), f"<{name.lower()}>")


def _schema_collection(
    origin: object,
    args: tuple[object, ...],
    *,
    skip_not_required: bool = False,
) -> str | list[object] | dict[str, object] | None:
    """Return schema for list/dict collection types, or None if not a collection.

    Returns:
        A string, list, dict, or None.

    """
    if origin is list:
        item = (
            _schema_type(args[0], skip_not_required=skip_not_required)
            if args
            else "unknown"
        )
        return [item]
    if origin is dict and args[1:]:
        if args[1] is object:
            return "object"
        return {
            _key_schema_label(args[0]): _schema_type(
                args[1],
                skip_not_required=skip_not_required,
            ),
        }
    return None


def _schema_type(
    annotation: object,
    *,
    skip_not_required: bool = False,
) -> str | dict[str, object] | list[object]:
    """Return a JSON-verbiage type description for a type annotation.

    Returns:
        String, nested dict (TypedDict), or single-element list (array type).

    """
    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin is UnionType or origin is typing.Union:
        non_none = [a for a in args if a is not NoneType]
        has_none = any(a is NoneType for a in args)
        schemas = [
            _schema_type(a, skip_not_required=skip_not_required) for a in non_none
        ]
        str_parts = [s for s in schemas if isinstance(s, str)]
        base = " or ".join(str_parts) if str_parts else "null"
        return f"{base} or null" if has_none and base != "null" else base

    if name := _JSON_TYPE_NAMES.get(cast("type[object]", annotation)):
        return name

    if result := _schema_collection(origin, args, skip_not_required=skip_not_required):
        return result

    if _is_typed_dict(annotation):
        return _schema_from_typed_dict(
            cast("type[dict[str, object]]", annotation),
            skip_not_required=skip_not_required,
        )

    if isinstance(annotation, type) and issubclass(annotation, IntEnum):
        return "string"

    return "unknown"


def _schema_from_typed_dict(
    td: type[dict[str, object]],
    *,
    skip_not_required: bool = False,
) -> dict[str, object]:
    """Build a JSON-schema-style dict from a TypedDict's field annotations.

    Args:
        td: TypedDict class.
        skip_not_required: When True, omit fields annotated with NotRequired.

    Returns:
        Dict mapping field names to type description strings or nested dicts.

    """
    try:
        hints = get_type_hints(td, include_extras=True)
    except Exception:  # noqa: BLE001
        return {}
    result: dict[str, object] = {}
    for k, v in hints.items():
        optional = get_origin(v) is NotRequired
        if skip_not_required and optional:
            continue
        inner = get_args(v)[0] if optional else v
        type_schema = _schema_type(inner, skip_not_required=skip_not_required)
        result[k] = type_schema
    return result


def _response_arms(t: object) -> dict[str, object]:
    """Map HTTP status strings to type annotations for all response arms.

    Returns:
        Dict mapping ``"200"``, ``"4xx"``, or a literal status string to the
        type annotation for that response branch.

    """
    # Expand Python 3.12 `type X = ...` aliases
    if v := getattr(t, "__value__", None):
        return _response_arms(v)

    origin = get_origin(t)
    args = get_args(t)

    if origin is UnionType or origin is typing.Union:
        result: dict[str, object] = {}
        for arm in args:
            result.update(_response_arms(arm))
        return result

    if origin is tuple and args:
        # Error arm: tuple[ErrorJSON, int] or tuple[ErrorJSON, Literal[422]]
        td = _find_typed_dict(args[0])
        if td is not None:
            status_literals = get_args(args[1]) if args[1:] else ()
            key = (
                str(status_literals[0])
                if status_literals and isinstance(status_literals[0], int)
                else "4xx"
            )
            return {key: td}
        return {}

    # Success arm: return the full annotation so callers get dict[str,X] etc.
    if _find_typed_dict(t) is not None:
        return {"200": t}
    return {}


def _extract_response_annotations(
    view_func: Callable[..., object],
) -> dict[str, object]:
    """Extract response type annotations keyed by HTTP status string.

    Returns:
        Dict mapping ``"200"``, ``"4xx"``, or specific status strings to type
        annotations. Empty if the return type cannot be resolved.

    """
    try:
        # NOTE: Some controllers import base under TYPE_CHECKING only, so
        # get_type_hints() can't resolve "base.JSONResponse" from module
        # globals.  Supplying base explicitly fixes the NameError.
        hints = get_type_hints(view_func, localns={"base": base})
    except Exception:  # noqa: BLE001
        return {}
    ret = hints.get("return")
    if ret is None:
        return {}
    return _response_arms(ret)


def _extract_request_type(
    view_func: Callable[..., object],
) -> type[dict[str, object]] | None:
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
        if is_validate and len(node.args) >= min_validate_args:
            type_arg = node.args[1]
            if isinstance(type_arg, ast.Name):
                type_obj = getattr(module, type_arg.id, None)
                if type_obj and _is_typed_dict(type_obj):
                    return cast("type[dict[str, object]]", type_obj)
    return None


def _parse_module_doc(
    module: types.ModuleType,
) -> tuple[str | None, list[str]]:
    """Extract title override and description paragraphs from a module docstring.

    Parses the module's docstring the same way view pydocs are parsed:
    blank lines separate paragraphs, and standard section headers
    (``Args:``, ``Returns:``, ``Raises:``) terminate parsing.

    If a ``Title: <text>`` line appears, it is captured as the name override
    and excluded from the description paragraphs.

    Args:
        module: Module whose ``__doc__`` string is parsed.

    Returns:
        Tuple of ``(title_or_None, description_paragraphs)``.

    """
    raw_doc = inspect.getdoc(module) or ""
    title: str | None = None
    paragraphs: list[str] = [""]
    for raw in raw_doc.splitlines():
        if raw.startswith(("Args:", "Returns:", "Raises:")):
            break
        if raw.startswith("Title:"):
            title = raw[len("Title:") :].strip()
            continue
        line = raw.strip()
        if not line:
            paragraphs.append("")
        else:
            paragraphs[-1] += " " + line
    desc = [p.strip() for p in paragraphs if p.strip()]
    return title, desc


def get_operations(
    app: flask.Flask,
) -> dict[str, tuple[types.ModuleType | None, list[_Operation]]]:
    """Scan /j/ routes and build operation documentation.

    Generates request/response examples by introspecting TypedDict annotations
    on view functions and their ``validate_json()`` calls.

    Args:
        app: Flask application whose URL map is scanned.

    Returns:
        Dict mapping group key to ``(module, operations)`` pairs, unordered.

    Raises:
        InvalidJSONRouteError: If multiple method on same view
            without a match statement

    """
    groups: dict[str, tuple[types.ModuleType | None, list[_Operation]]] = {}

    for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
        path = str(rule.rule)
        if not path.startswith("/j/"):
            continue
        view = app.view_functions.get(rule.endpoint)
        if not view:
            continue
        group = str(rule.endpoint).split(".", 1)[0].capitalize()
        methods = (rule.methods or set()) - {"HEAD", "OPTIONS"}

        module = inspect.getmodule(view)
        group_module, ops = groups.get(group, (module, []))
        groups[group] = (group_module, ops)

        if len(methods) == 1:
            method = _Method(next(iter(methods)))
            ops.append(_Operation.extract(path, method, view))
            continue

        view_name = view.__name__
        for s in methods:
            method = _Method(s)
            # Each method should have its own view
            method_view_name = f"{view_name}_{method.name.lower()}"
            try:
                method_view = getattr(module, method_view_name)
            except AttributeError as e:
                msg = f"JSON routes require dedicated view: {method_view_name}"
                raise exc.InvalidJSONRouteError(msg) from e
            ops.append(_Operation.extract(path, method, method_view))

    return groups


def init_docs(app: flask.Flask) -> None:
    """Populate the docs cache at startup.

    Called once from web.FlaskExtension.init_app() after all routes are
    registered.

    Args:
        app: Flask application to scan.

    """
    groups: list[_Group] = []
    for group_key, (module, ops_unsorted) in get_operations(app).items():
        ops = sorted(ops_unsorted, key=lambda op: (op.url.lower(), op.method))
        if module is not None:
            title, desc = _parse_module_doc(module)
        else:
            title, desc = None, []
        name = title if title is not None else group_key
        groups.append(_Group(name, desc, ops))

    # globals shenanigans
    GROUPS.clear()
    GROUPS.extend(sorted(groups, key=lambda g: g.name.lower()))


def json_api() -> dict[URL, dict[Method, _OperationJSON]]:
    """GET machine-readable API documentation.

    Returns:
        JSON response structured as ``{url: {method: {info}}}`` where each
        info object contains the description, schema, and examples keyed by
        HTTP status code.

    """
    result: dict[URL, dict[Method, _OperationJSON]] = {}
    for group in GROUPS:
        for op in group.operations:
            methods = result.setdefault(URL(op.url), {})
            methods[Method(op.method.name)] = _OperationJSON(
                description=op.description,
                request_schema=op.request_schema,
                request_example=op.request_example,
                responses={
                    Status(status): _ResponseInfoJSON(
                        schema=resp.schema,
                        example=resp.example,
                    )
                    for status, resp in op.responses.items()
                },
            )
    return result


ROUTES: base.Routes = {
    "/api": (page, ["GET"]),
    "/j/api": (cast("base.RouteCallable", json_api), ["GET"]),
}
# TODO (Bradley): #0 Describe URL args
