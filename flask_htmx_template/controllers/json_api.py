"""JSON API validation helpers."""

from __future__ import annotations

import contextlib
import datetime
import decimal
from enum import Enum
from types import GenericAlias, NoneType, UnionType
from typing import (
    Annotated,
    cast,
    get_args,
    get_origin,
    get_type_hints,
    NotRequired,
    TYPE_CHECKING,
)

import flask
from pydantic import TypeAdapter, ValidationError

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping


_JSON_TYPES: dict[type, str] = {
    list: "an array",
    bool: "a boolean",
    NoneType: "null",
    int: "an integer",
    float: "a number",
    decimal.Decimal: "a number",
    dict: "an object",
    str: "a string",
    datetime.date: "an ISO 8601 date string",
    datetime.datetime: "an ISO 8601 date time string with TZ",
}

_QUERY_PARSE_ERROR_MESSAGES = {
    "int_parsing": "must be an integer",
    "int_type": "must be an integer",
    "float_parsing": "must be a number",
    "float_type": "must be a number",
    "decimal_parsing": "must be a number",
    "bool_parsing": "must be a boolean",
    "bool_type": "must be a boolean",
    "date_parsing": "must be an ISO 8601 date string",
    "date_from_datetime_parsing": "must be an ISO 8601 date string",
}


def _pretty_json_type(t: type[Enum | object]) -> str:
    if issubclass(t, Enum):
        return " or ".join(f'"{e.name.lower()}"' for e in t)
    return _JSON_TYPES.get(t, t.__name__)


def _parse_annotations(
    type_: type | UnionType | GenericAlias,
    *,
    no_typed_dict: bool = False,
) -> tuple[type, ...]:
    if isinstance(type_, UnionType):
        return tuple(
            _parse_annotations(t, no_typed_dict=no_typed_dict)[0]
            for t in type_.__args__
        )
    if isinstance(type_, GenericAlias):
        origin = type_.__origin__
        if not isinstance(origin, type):
            raise TypeError
        return _parse_annotations(origin, no_typed_dict=no_typed_dict)
    if no_typed_dict and issubclass(type_, dict):
        return (dict,)
    return (type_,)


def body[T: object](
    type_: type[T],
    raw: object | None = None,
) -> tuple[T, list[str]]:
    """Validate a JSON request body against an expected type.

    Args:
        type_: Type that the JSON body is expected to match.
        raw: JSON value to validate. If omitted, the value is read from the
            current Flask request. An explicitly supplied empty object is
            validated as-is.

    Returns:
        Tuple containing the upgraded value and validation errors.

    """
    obj = flask.request.json if raw is None else raw
    return _validate_json(cast("T", obj), type_)


def _validate_json[T: object](
    obj: T,
    type_: type | UnionType | GenericAlias,
    *,
    key: str = "",
) -> tuple[T, list[str]]:
    """Validate a JSON value against an expected type.

    Args:
        obj: JSON value to test.
        type_: Type to compare against.
        key: Name of the path to the sub-item in the JSON value.

    Returns:
        tuple(validated object, list of errors)

    """
    key = key or "json"

    to_test = _parse_annotations(type_, no_typed_dict=True)
    if decimal.Decimal in to_test and isinstance(obj, (str, float, int)):
        with contextlib.suppress(decimal.InvalidOperation):
            return cast("T", decimal.Decimal(obj)), []

    if isinstance(obj, str):
        for t in to_test:
            obj_upgrade, errors = _validate_json_str(obj, t, key=key)
            if not errors:
                return obj_upgrade, errors

    if not isinstance(obj, to_test) and not (isinstance(obj, int) and float in to_test):
        pretty_exp = " or ".join(_pretty_json_type(t) for t in to_test)
        return obj, [
            f"{key} should be {pretty_exp}, not {_pretty_json_type(type(obj))}",
        ]
    if isinstance(obj, list):
        return _validate_json_list(
            obj,  # type: ignore[attr-defined]
            type_,
            key=key,
        )
    if isinstance(obj, dict):
        return _validate_json_dict(
            obj,  # type: ignore[attr-defined]
            type_,
            key=key,
        )
    return obj, []


def _query_bound_error(
    error_type: object,
    context: Mapping[str, object],
    bounds: dict[str, object],
) -> str | None:
    """Convert a Pydantic bound error to the API error style.

    Args:
        error_type: Pydantic error type.
        context: Values attached to the Pydantic error.
        bounds: Numeric bounds declared by the parameter's ``Field``.

    Returns:
        Human-readable validation error, or None for a different error type.

    """
    message: str | None = None
    if error_type == "greater_than_equal":
        minimum = context.get("ge", context.get("gt"))
        if "maximum" in bounds:
            message = f"must be between {minimum} and {bounds['maximum']}"
        else:
            message = f"must be at least {minimum}"
    elif error_type == "greater_than":
        message = f"must be greater than {context.get('gt')}"
    elif error_type == "less_than_equal":
        maximum = context.get("le", context.get("lt"))
        if "minimum" in bounds:
            message = f"must be between {bounds['minimum']} and {maximum}"
        else:
            message = f"must be at most {maximum}"
    elif error_type == "less_than":
        message = f"must be less than {context.get('lt')}"
    return message


def _query_error(
    name: str,
    error: Mapping[str, object],
    bounds: dict[str, object],
) -> str:
    """Convert a Pydantic query-parameter error to the API error style.

    Args:
        name: Query parameter name.
        error: One error entry returned by Pydantic.
        bounds: Numeric bounds declared by the parameter's ``Field``.

    Returns:
        Human-readable validation error.

    """
    error_type = error.get("type")
    context = cast("dict[str, object]", error.get("ctx", {}))
    message = _QUERY_PARSE_ERROR_MESSAGES.get(cast("str", error_type))
    message = message or _query_bound_error(error_type, context, bounds)
    message = message or str(error.get("msg", "is invalid"))
    return f"{name} {message}"


def _query_bounds(annotation: object) -> dict[str, object]:
    """Extract numeric bounds from an annotated query parameter type.

    Args:
        annotation: Resolved query parameter annotation.

    Returns:
        Mapping containing any declared minimum and maximum values.

    """
    bounds: dict[str, object] = {}
    metadata = get_args(annotation)[1:] if get_origin(annotation) is Annotated else ()
    for item in metadata:
        for constraint in getattr(item, "metadata", (item,)):
            if (minimum := getattr(constraint, "ge", None)) is not None or (
                minimum := getattr(constraint, "gt", None)
            ) is not None:
                bounds["minimum"] = minimum
            if (maximum := getattr(constraint, "le", None)) is not None or (
                maximum := getattr(constraint, "lt", None)
            ) is not None:
                bounds["maximum"] = maximum
    return bounds


def args[T: tuple[object, ...]](
    type_: type[T],
    query_args: Mapping[str, str] | None = None,
) -> tuple[T, list[str]]:
    """Parse query arguments into a ``NamedTuple``.

    Args:
        type_: ``NamedTuple`` subclass describing the query arguments.
        query_args: Query arguments to parse, or None to use the current
            Flask request.

    Returns:
        Populated ``NamedTuple`` and all validation errors.

    Raises:
        TypeError: If ``type_`` is not a ``NamedTuple`` subclass.

    """
    if not hasattr(type_, "_fields") or not hasattr(type_, "_field_defaults"):
        msg = "type_ must be a NamedTuple subclass"
        raise TypeError(msg)

    namespace = vars(type_)
    fields = cast("tuple[str, ...]", namespace["_fields"])
    defaults = cast("dict[str, object]", namespace["_field_defaults"])
    hints = get_type_hints(
        type_,
        localns={"datetime": datetime},
        include_extras=True,
    )
    query_args = flask.request.args if query_args is None else query_args
    values: dict[str, object] = {}
    errors: list[str] = []

    # NOTE: Invalid fields use None placeholders so every field can be validated.
    # Callers must return the collected errors before using the result.
    for name in fields:
        if name not in query_args:
            if name in defaults:
                values[name] = defaults[name]
            else:
                values[name] = None
                errors.append(f"{name} is missing")
            continue

        raw_value = query_args.get(name)
        try:
            values[name] = TypeAdapter(hints[name]).validate_python(raw_value)
        except ValidationError as error:
            values[name] = None
            errors.extend(
                _query_error(name, entry, _query_bounds(hints[name]))
                for entry in error.errors()
            )

    errors.extend(
        f"{name} is not recognized" for name in sorted(query_args) if name not in fields
    )
    constructor = cast("Callable[..., T]", type_)
    return constructor(**values), errors


def _validate_json_str(
    obj: str,
    type_: type,
    *,
    key: str = "",
) -> tuple[object, list[str]]:
    if type_ == datetime.date:
        with contextlib.suppress(ValueError):
            return datetime.date.fromisoformat(obj), []
    elif type_ == datetime.datetime:
        with contextlib.suppress(ValueError):
            d = datetime.datetime.fromisoformat(obj)
            if d.tzinfo is None:
                return obj, [f"{key} is missing time zone"]
            return d, []
    elif issubclass(type_, Enum):
        with contextlib.suppress(ValueError):
            return type_(obj), []
    return obj, ["unknown"]


def _validate_json_list[V: object](
    obj: list[V],
    type_: type[list[V]] | UnionType | GenericAlias,
    *,
    key: str = "",
) -> tuple[list[V], list[str]]:
    errors: list[str] = []
    obj_upgrade: list[V] = []
    if isinstance(type_, GenericAlias):
        # Check all elements are of sub_type
        sub_type: type = type_.__args__[0]
        for i, v in enumerate(obj):
            sub_obj, sub_errors = _validate_json(v, sub_type, key=f"{key}[{i}]")
            obj_upgrade.append(sub_obj)
            errors.extend(sub_errors)
        return obj_upgrade, errors
    if isinstance(type_, UnionType):
        # Check if any of them work
        for t in type_.__args__:
            if t is list or isinstance(t, GenericAlias):
                obj_upgrade, errors = _validate_json_list(obj, t, key=key)
                if not errors:
                    return obj_upgrade, []

    return obj, errors


def _validate_typed_dict_hints[V: object](
    obj: dict[str, V],
    hints: dict[str, object],
    key: str,
) -> tuple[dict[str, V], list[str]]:
    errors: list[str] = []
    obj_upgrade: dict[str, V] = {}
    obj_copy: dict[str, V] = obj.copy()
    for k, sub_type in sorted(hints.items()):
        is_not_required = get_origin(sub_type) is NotRequired
        if k in obj_copy:
            v = obj_copy.pop(k)
            sub_obj, sub_errors = _validate_json(
                v,
                (
                    cast("type", get_args(sub_type)[0])
                    if is_not_required
                    else cast("type", sub_type)
                ),
                key=f"{key}.{k}",
            )
            obj_upgrade[k] = sub_obj
            errors.extend(sub_errors)
        elif not is_not_required:
            errors.append(f"{key}.{k} is missing")
    errors.extend(f"{key}.{k} is not recognized" for k in obj_copy)
    return obj_upgrade, errors


def _validate_json_dict[V: object](
    obj: dict[str, V],
    type_: type[dict[str, V]] | UnionType | GenericAlias,
    *,
    key: str = "",
) -> tuple[dict[str, V], list[str]]:
    errors: list[str] = []
    obj_upgrade: dict[str, V] = {}
    if isinstance(type_, GenericAlias):
        # Check all elements are of sub_type
        sub_type: type = type_.__args__[1]
        for k, v in sorted(obj.items()):
            sub_obj, sub_errors = _validate_json(v, sub_type, key=f"{key}.{k}")
            obj_upgrade[k] = sub_obj
            errors.extend(sub_errors)
        return obj_upgrade, errors
    if isinstance(type_, UnionType):
        # Check if any of them work
        union_errors: list[str] = []
        for t in type_.__args__:
            if (isinstance(t, type) and issubclass(t, dict)) or isinstance(
                t,
                GenericAlias,
            ):
                obj_upgrade, union_errors = _validate_json_dict(
                    obj,
                    cast("type[dict[str, V]] | GenericAlias", t),
                    key=key,
                )
                if not union_errors:
                    return obj_upgrade, errors
        errors.extend(union_errors)
        return obj, errors
    # NOTE: Some endpoint context modules import annotation-only types under
    # TYPE_CHECKING. Keep those modules lightweight at runtime while still
    # resolving their annotations during JSON validation.
    hints = get_type_hints(
        type_,
        localns={"datetime": datetime},
        include_extras=True,
    )
    if not hints:
        return obj, errors
    return _validate_typed_dict_hints(obj, hints, key)
