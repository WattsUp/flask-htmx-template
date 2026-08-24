"""API documentation context builders.

Title: API documentation
"""

from __future__ import annotations

import ast
import datetime
import inspect
import json
import sys
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
    Literal,
    NamedTuple,
    NewType,
    NotRequired,
    Self,
    TYPE_CHECKING,
    TypedDict,
)

from pydantic import TypeAdapter

from flask_htmx_template import exceptions as exc
from flask_htmx_template import utils
from flask_htmx_template.controllers import base
from flask_htmx_template.models.base import BaseEnum

if TYPE_CHECKING:
    import types
    from collections.abc import Callable, Mapping

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


# NOTE: Every JSON API client error uses this response shape. Keep it outside the
# individual operations so the generated documentation does not repeat the
# same schema and example for every endpoint that accepts input.
ERROR_RESPONSE = _ResponseInfo(
    schema={"errors": ["string"]},
    example={"errors": ["a string of words"]},
)


def _extract_url_args(
    path: str,
    view: Callable[..., object],
) -> dict[str, str]:
    """Extract URL argument descriptions from a view's pydoc ``Args:`` section.

    Only args whose names appear as path parameters (e.g. ``<path:uri>``) are
    included; function-only parameters are ignored.

    Args:
        path: URL rule string, e.g. ``/j/items/i/<path:uri>``.
        view: View function whose docstring is parsed.

    Returns:
        Dict mapping each URL arg name to its description string.

    """
    url_arg_names = {
        segment.split(">")[0].split(":")[-1]
        for segment in path.split("<")[1:]
        if ">" in segment
    }
    if not url_arg_names:
        return {}

    raw_doc = inspect.getdoc(view) or ""
    in_args = False
    result: dict[str, str] = {}
    for line in raw_doc.splitlines():
        if line.startswith("Args:"):
            in_args = True
            continue
        if not in_args:
            continue
        if line and not line[0].isspace():
            break
        stripped = line.strip()
        if not stripped or ":" not in stripped:
            continue
        name, _, desc = stripped.partition(":")
        name = name.strip()
        if name in url_arg_names:
            result[name] = desc.strip()
    return result


def _is_named_tuple(t: object) -> bool:
    """Return whether *t* is a class created by ``typing.NamedTuple``.

    Returns:
        True for a ``NamedTuple`` class, otherwise False.

    """
    return (
        isinstance(t, type)
        and issubclass(t, tuple)
        and isinstance(getattr(t, "_fields", None), tuple)
        and hasattr(t, "__annotations__")
    )


def _resolve_ast_object(node: ast.AST, module: types.ModuleType) -> object | None:
    """Resolve a simple name or attribute expression from a view's module.

    Returns:
        The resolved object, or None when the expression cannot be resolved.

    """
    if isinstance(node, ast.Name):
        return getattr(module, node.id, None)
    if isinstance(node, ast.Attribute):
        parent = _resolve_ast_object(node.value, module)
        return getattr(parent, node.attr, None) if parent is not None else None
    return None


def _is_json_api_call(
    node: ast.AST,
    function_name: str,
    module: types.ModuleType,
) -> bool:
    """Return whether an AST function expression targets a JSON API helper.

    Qualified calls and direct imports with aliases are resolved to their
    module-level objects and checked against the helper's defining module and
    name.

    Args:
        node: AST function expression from a call.
        function_name: Expected JSON API helper name.
        module: Module containing the view.

    Returns:
        True when the expression refers to the requested helper.

    """
    if not isinstance(node, (ast.Name, ast.Attribute)):
        return False
    target = _resolve_ast_object(node, module)
    return (
        callable(target)
        and getattr(target, "__name__", None) == function_name
        and str(getattr(target, "__module__", "")).endswith(".json_api")
    )


def _extract_query_type(
    view: Callable[..., object],
) -> type[tuple[object, ...]] | None:
    """Find the ``NamedTuple`` passed to ``json_api.args`` in a view.

    The query model is the first positional argument.  Calls through a module
    alias and direct imports are both supported.

    Returns:
        The query ``NamedTuple`` class, or None when no parser call is found.

    """
    try:
        source = textwrap.dedent(inspect.getsource(view))
        tree = ast.parse(source)
    except (OSError, TypeError, SyntaxError):
        return None

    module = inspect.getmodule(view)
    if module is None:  # pragma: no cover
        return None

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not _is_json_api_call(func, "args", module) or not node.args:
            continue
        query_type = _resolve_ast_object(node.args[0], module)
        if _is_named_tuple(query_type):
            return cast("type[tuple[object, ...]]", query_type)
    return None


def _query_schema_label(schema: Mapping[str, object]) -> str:
    """Return a readable query type label from a pydantic JSON schema.

    Returns:
        Human-readable type label.

    """
    if isinstance(description := schema.get("description"), str):
        return description
    if isinstance(any_of := schema.get("anyOf"), list):
        arms = cast("list[object]", any_of)
        arm_schemas = [
            cast("dict[str, object]", arm) for arm in arms if isinstance(arm, dict)
        ]
        labels = [
            _query_schema_label(arm) for arm in arm_schemas if arm.get("type") != "null"
        ]
        return " or ".join(sorted(set(labels))) or "null"
    if isinstance(values := schema.get("enum"), list):
        return " or ".join(repr(value) for value in cast("list[object]", values))
    items = schema.get("items")
    if schema.get("type") == "array" and isinstance(items, dict):
        return f"list of {_query_schema_label(cast('dict[str, object]', items))}"
    schema_key = schema.get("format") or schema.get("type")
    return {
        "date": "ISO-8601 date string",
        "date-time": "ISO-8601 date & time string",
        "boolean": "boolean",
        "integer": "integer",
        "number": "number",
        "string": "string",
    }.get(cast("str", schema_key), "value")


def _query_schema_constraints(schema: Mapping[str, object]) -> list[str]:
    """Format pydantic JSON-schema bounds as a human-readable phrase.

    Returns:
        A list containing at most one human-readable constraint.

    """
    minimum = schema.get("minimum")
    exclusive_minimum = schema.get("exclusiveMinimum")
    maximum = schema.get("maximum")
    exclusive_maximum = schema.get("exclusiveMaximum")
    if minimum is not None and maximum is not None:
        text = f"between {minimum} and {maximum}"
    elif exclusive_minimum is not None and exclusive_maximum is not None:
        text = f"greater than {exclusive_minimum} and less than {exclusive_maximum}"
    elif minimum is not None:
        text = f"at least {minimum}"
    elif exclusive_minimum is not None:
        text = f"greater than {exclusive_minimum}"
    elif maximum is not None:
        text = f"at most {maximum}"
    elif exclusive_maximum is not None:
        text = f"less than {exclusive_maximum}"
    else:
        return []
    return [text]


def _query_args_from_named_tuple(
    query_type: type[tuple[object, ...]],
) -> dict[str, str]:
    """Build query argument descriptions from a ``NamedTuple`` declaration.

    Returns:
        Mapping of query parameter names to generated descriptions.

    """
    try:
        hints = get_type_hints(
            query_type,
            localns=_build_localns(getattr(query_type, "__module__", "")),
            include_extras=True,
        )
    except Exception:  # pragma: no cover
        return {}

    defaults = getattr(query_type, "_field_defaults", {})
    result: dict[str, str] = {}
    for name, annotation in hints.items():
        schema = TypeAdapter(annotation).json_schema()
        parts = [_query_schema_label(schema), *_query_schema_constraints(schema)]
        if name in defaults and defaults[name] is not None:
            parts.append(f"defaults to {defaults[name]}")
        elif name in defaults:
            parts.append("optional")
        result[name] = ", ".join(parts)
    return result


def _extract_query_args(view: Callable[..., object]) -> dict[str, str]:
    """Extract query argument descriptions from a query argument declaration.

    JSON views declare parsed query arguments by passing a ``NamedTuple`` to
    ``json_api.args``.  Its annotations, ``Field`` metadata, and
    defaults are the source of truth for generated documentation.  The
    docstring format remains supported for views that predate the parser.

    Args:
        view: View function whose docstring is parsed.

    Returns:
        Dict mapping each query arg name to its description string.

    """
    query_type = _extract_query_type(view)
    if query_type is not None:
        return _query_args_from_named_tuple(query_type)

    raw_doc = inspect.getdoc(view) or ""
    in_query_args = False
    result: dict[str, str] = {}
    for line in raw_doc.splitlines():
        if line.startswith("Query args:"):
            in_query_args = True
            continue
        if not in_query_args:
            continue
        if line and not line[0].isspace():
            break
        stripped = line.strip()
        if not stripped or ":" not in stripped:
            continue
        name, _, desc = stripped.partition(":")
        result[name.strip()] = desc.strip()
    return result


class _Operation(NamedTuple):
    url: str
    method: _Method
    description: list[str]
    url_args: dict[str, str]
    query_args: dict[str, str]
    request_schema: dict[str, object] | None
    request_example: dict[str, object] | None
    responses: dict[str, _ResponseInfo]
    enums: set[type[IntEnum]]

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
            if raw.startswith(("Args:", "Query args:", "Returns:", "Raises:")):
                break
            line = raw.strip()
            if not line:
                paragraphs.append("")
            else:
                paragraphs[-1] += " " + line
        desc = [p.strip() for p in paragraphs if p.strip()]

        url_args = _extract_url_args(path, view)
        query_args = _extract_query_args(view)
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
            if not _is_client_error_status(status)
        }

        enum_set: set[type[IntEnum]] = set()
        if request_td:
            _collect_enums_from_annotation(request_td, enum_set)
        for ann in response_anns.values():
            _collect_enums_from_annotation(ann, enum_set)

        return cls(
            path,
            method,
            desc,
            url_args,
            query_args,
            req_schema,
            req_example,
            responses,
            enum_set,
        )


class _Group(NamedTuple):
    name: str
    description: list[str]
    operations: list[_Operation]


class _ResponseInfoJSON(TypedDict):
    schema: object
    example: object


class _OperationJSON(TypedDict):
    description: list[str]
    url_args: dict[str, str]
    query_args: dict[str, str]
    request_schema: dict[str, object] | None
    request_example: dict[str, object] | None
    responses: dict[Status, _ResponseInfoJSON]


class _APIDocsJSON(TypedDict):
    urls: dict[URL, dict[Method, _OperationJSON]]
    enums: dict[str, list[str]]
    errors: _ResponseInfoJSON


GROUPS: list[_Group] = []
ENUMS: dict[str, list[str]] = {}


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
        # Treat dict[K, V] where V is not bare object as a documentable dict
        if dict_args and dict_args[-1] is not object:
            return cast("type[dict[str, object]]", t)

    # Expand Python 3.12 `type X = ...` aliases
    if v := getattr(t, "__value__", None):
        return _find_typed_dict(v)
    return None


def _collect_enums_from_annotation(
    ann: object,
    result: set[type[IntEnum]],
    _seen: set[int] | None = None,
) -> None:
    """Recursively collect IntEnum subclasses from a type annotation.

    Args:
        ann: Type annotation to scan.
        result: Set to add found IntEnum subclasses to.
        _seen: Set of already-visited annotation ids (cycle guard).

    """
    if _seen is None:
        _seen = set()
    key = id(ann)
    if key in _seen:
        return
    _seen.add(key)

    if isinstance(ann, type) and issubclass(ann, IntEnum):
        result.add(ann)
        return

    for arg in get_args(ann):
        _collect_enums_from_annotation(arg, result, _seen)

    if _is_typed_dict(cast("object", ann)):
        try:
            td_cls = cast("type[dict[str, object]]", ann)
            hints = get_type_hints(
                td_cls,
                localns=_build_localns(td_cls.__module__),
                include_extras=True,
            )
        except Exception:  # pragma: no cover
            return
        for hint in hints.values():
            _collect_enums_from_annotation(hint, result, _seen)


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


def _example_from_union(
    args: tuple[object, ...],
    field_name: str,
    *,
    skip_not_required: bool,
) -> object:
    """Return an example value for a union type annotation.

    Returns:
        The example for the first non-None arm.

    """
    non_none = [a for a in args if a is not NoneType]
    if not non_none:
        return None
    return _example_value(non_none[0], field_name, skip_not_required=skip_not_required)


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
        return _example_from_union(
            args,
            field_name,
            skip_not_required=skip_not_required,
        )

    prim = _PRIMITIVE_EXAMPLES.get(cast("type[object]", annotation))
    if prim is not None:
        return prim() if callable(prim) else prim

    if origin is Literal and args:
        return args[0]

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
        hints = get_type_hints(
            td,
            localns=_build_localns(getattr(td, "__module__", "")),
            include_extras=True,
        )
    except Exception:  # pragma: no cover
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


def _schema_scalar(annotation: object, origin: object, args: tuple[object, ...]) -> str:
    """Return a schema string for Literal, IntEnum, or unknown annotations.

    Returns:
        A human-readable schema type string.

    """
    if origin is Literal:
        parts = [f"'{a}'" if isinstance(a, str) else str(a) for a in args]
        return " or ".join(parts)
    if isinstance(annotation, type) and issubclass(annotation, IntEnum):
        name = utils.camel_to_snake(annotation.__name__).replace("_", " ")
        return f"{name} enum value"
    return "unknown"


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

    return _schema_scalar(annotation, origin, args)


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
        hints = get_type_hints(
            td,
            localns=_build_localns(getattr(td, "__module__", "")),
            include_extras=True,
        )
    except Exception:  # pragma: no cover
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


def _is_client_error_status(status: str) -> bool:
    """Return whether *status* describes an HTTP 4xx response.

    Returns:
        True for the generic 4xx marker or a concrete 4xx status code.

    """
    if status == "4xx":
        return True
    try:
        return base.HTTP_CODE_BAD_REQUEST <= int(status) < base.HTTP_CODE_INTERNAL_ERROR
    except ValueError:
        return False


def _build_localns(module_name: str) -> dict[str, object]:
    """Build a namespace that resolves type hints imported only while type checking.

    Args:
        module_name: Module that defines the annotated object.

    Returns:
        Namespace suitable for ``typing.get_type_hints``.

    """
    top = module_name.split(".", 1)[0]
    own_mod = sys.modules.get(module_name)
    # NOTE: Endpoint modules may import standard-library types only under
    # TYPE_CHECKING.  Keep the runtime namespace useful for annotations such as
    # ``datetime.date`` without requiring every endpoint module to duplicate
    # the import at runtime.
    localns: dict[str, object] = {"base": base, "datetime": datetime}
    for mod_name, mod in sys.modules.items():
        if mod is own_mod:
            continue
        if mod_name == top or mod_name.startswith(f"{top}."):
            localns.update(
                {
                    key: value
                    for key, value in vars(mod).items()
                    if not key.startswith("_")
                },
            )
    if own_mod is not None:
        localns.update(
            {
                key: value
                for key, value in vars(own_mod).items()
                if not key.startswith("_")
            },
        )
    return localns


def _extract_response_annotations(
    view_func: Callable[..., object],
) -> dict[str, object]:
    """Extract response type annotations keyed by HTTP status string.

    Returns:
        Dict mapping ``"200"``, ``"4xx"``, or specific status strings to type
        annotations. Empty if the return type cannot be resolved.

    """
    try:
        hints = get_type_hints(
            view_func,
            localns=_build_localns(view_func.__module__),
        )
    except Exception:  # pragma: no cover
        return {}
    ret = hints.get("return")
    if ret is None:
        return {}
    return _response_arms(ret)


def _extract_request_type(
    view_func: Callable[..., object],
) -> type[dict[str, object]] | None:
    """Find the TypedDict passed to ``json_api.body()`` in the source.

    Scans the AST for calls to ``body(SomeTypedDict, raw)`` and resolves
    *SomeTypedDict* from the view function's module globals.  The body helper
    may be accessed through any module alias.

    Returns:
        TypedDict class or None.

    """
    try:
        source = textwrap.dedent(inspect.getsource(view_func))
        tree = ast.parse(source)
    except (OSError, TypeError, SyntaxError):
        return None

    module = inspect.getmodule(view_func)
    if not module:  # pragma: no cover
        return None

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if _is_json_api_call(func, "body", module) and node.args:
            type_obj = _resolve_ast_object(node.args[0], module)
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
    on view functions and their ``json_api.body()`` calls.

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
        if not view:  # pragma: no cover
            continue
        group = str(rule.endpoint).split(".", 1)[0].replace("_", " ").capitalize()
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
        else:  # pragma: no cover
            title, desc = None, []
        name = title if title is not None else group_key
        groups.append(_Group(name, desc, ops))

    # globals shenanigans
    GROUPS.clear()
    GROUPS.extend(sorted(groups, key=lambda g: g.name.lower()))

    all_enums: set[type[IntEnum]] = set()
    for group in GROUPS:
        for op in group.operations:
            all_enums.update(op.enums)
    ENUMS.clear()
    ENUMS.update(
        {
            utils.camel_to_snake(e.__name__).replace("_", " "): [
                m.name.lower() for m in e
            ]
            for e in sorted(all_enums, key=lambda e: e.__name__)
        },
    )

    # Patch the json_api_enums operation example to show actual enum values
    # (ENUMS is populated above; the example was generated before it was filled)
    for group in GROUPS:
        for i, op in enumerate(group.operations):
            if op.url == "/j/api/enums" and "200" in op.responses:
                resp = op.responses["200"]
                updated = dict(op.responses)
                updated["200"] = _ResponseInfo(schema=resp.schema, example=dict(ENUMS))
                group.operations[i] = op._replace(responses=updated)
                break


def api_enums() -> dict[str, list[str]]:
    """Build known enum values for JSON API fields.

    Returns:
        JSON response structured as ``{EnumName: [value, ...]}`` mapping each
        enum class name to its sorted list of lowercase member names.

    """
    return ENUMS


def api() -> _APIDocsJSON:
    """Build machine-readable API documentation.

    Returns:
        JSON response structured as ``{"urls": {url: {method: {info}}},
        "enums": {EnumName: [value, ...]}}`` where each info object contains
        the description, schema, and examples keyed by HTTP status code.

    """
    urls: dict[URL, dict[Method, _OperationJSON]] = {}
    for group in GROUPS:
        for op in group.operations:
            methods = urls.setdefault(URL(op.url), {})
            methods[Method(op.method.name)] = _OperationJSON(
                description=op.description,
                url_args=op.url_args,
                query_args=op.query_args,
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
    return {
        "urls": urls,
        "enums": dict(ENUMS),
        "errors": _ResponseInfoJSON(
            schema=ERROR_RESPONSE.schema,
            example=ERROR_RESPONSE.example,
        ),
    }
