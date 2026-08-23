from __future__ import annotations

import datetime
import decimal
from types import NoneType
from typing import Annotated, cast, NamedTuple, TypedDict

import flask
import pytest
from pydantic import Field
from werkzeug.datastructures import MultiDict

from flask_htmx_template import utils
from flask_htmx_template.controllers import json_api
from flask_htmx_template.models.base import BaseEnum
from tests import conftest


class Derived(BaseEnum):
    """Enum used to exercise JSON validation."""

    RED = 1
    BLUE = 2
    SEAFOAM_GREEN = 3


class QueryArgs(NamedTuple):
    """Query arguments used to exercise ``args``."""

    before: datetime.date | None = None
    limit: Annotated[int, Field(ge=1, le=100)] = 50
    offset: Annotated[int, Field(ge=0)] = 0


class RequiredQueryArgs(NamedTuple):
    """Query arguments with one required value."""

    name: str
    amount: Annotated[int, Field(ge=1)]


class ScalarQueryArgs(NamedTuple):
    """Query arguments covering scalar and exclusive-bound validation."""

    ratio: float
    enabled: bool
    above: Annotated[int, Field(gt=0)]
    below: Annotated[int, Field(lt=10)]


class MaximumQueryArgs(NamedTuple):
    """Query arguments with an upper bound and no lower bound."""

    value: Annotated[int, Field(le=10)]


def test_args_uses_defaults_and_converts_values() -> None:
    app = flask.Flask(__name__)
    request_path = "/?before=2026-08-22&limit=2&offset=1"

    with app.test_request_context(request_path):
        result, errors = json_api.args(QueryArgs)

    assert result == QueryArgs(datetime.date(2026, 8, 22), 2, 1)
    assert errors == []


def test_args_preserves_explicit_empty_query_args() -> None:
    app = flask.Flask(__name__)

    with app.test_request_context("/?limit=2"):
        result, errors = json_api.args(QueryArgs, MultiDict())

    assert result == QueryArgs(None, 50, 0)
    assert errors == []


def test_args_collects_all_validation_errors() -> None:
    app = flask.Flask(__name__)
    request_path = "/?before=invalid&limit=0&offset=-1&unknown=value"

    with app.test_request_context(request_path):
        result, errors = json_api.args(QueryArgs)

    assert tuple(result) == (None, None, None)
    assert errors == [
        "before must be an ISO 8601 date string",
        "limit must be between 1 and 100",
        "offset must be at least 0",
        "unknown is not recognized",
    ]


def test_args_reports_missing_required_values() -> None:
    app = flask.Flask(__name__)

    with app.test_request_context("/?amount=0"):
        result, errors = json_api.args(RequiredQueryArgs)

    assert tuple(result) == (None, None)
    assert errors == ["name is missing", "amount must be at least 1"]


def test_args_reports_scalar_and_exclusive_bound_errors() -> None:
    app = flask.Flask(__name__)
    request_path = "/?ratio=invalid&enabled=invalid&above=0&below=10"

    with app.test_request_context(request_path):
        result, errors = json_api.args(ScalarQueryArgs)

    assert tuple(result) == (None, None, None, None)
    assert errors == [
        "ratio must be a number",
        "enabled must be a boolean",
        "above must be greater than 0",
        "below must be less than 10",
    ]


def test_args_reports_upper_bound_without_lower_bound() -> None:
    app = flask.Flask(__name__)

    with app.test_request_context("/?value=11"):
        result, errors = json_api.args(MaximumQueryArgs)

    assert tuple(result) == (None,)
    assert errors == ["value must be at most 10"]


def test_query_bound_error_ignores_other_error_types() -> None:
    error_type = "string_too_short"

    message = json_api._query_bound_error(error_type, {}, {})

    assert message is None


def test_args_requires_named_tuple() -> None:
    invalid_type = cast("type[tuple[object, ...]]", tuple)

    with pytest.raises(TypeError, match="must be a NamedTuple subclass"):
        json_api.args(invalid_type)


class Top(TypedDict):
    """Nested JSON object used to exercise TypedDict validation."""

    bool: bool
    list: list[bool]
    none: None
    object: Top | None


@pytest.mark.parametrize(
    ("obj", "type_", "target"),
    [
        (True, NoneType, ["json should be null, not a boolean"]),
        ([], NoneType, ["json should be null, not an array"]),
        ({}, NoneType, ["json should be null, not an object"]),
        (
            {},
            Top,
            [
                "json.bool is missing",
                "json.list is missing",
                "json.none is missing",
                "json.object is missing",
            ],
        ),
        (None, NoneType, []),
        (None, bool, ["json should be a boolean, not null"]),
        (True, bool, []),
        (None, int, ["json should be an integer, not null"]),
        (0.0, int, ["json should be an integer, not a number"]),
        (0, int, []),
        (None, float, ["json should be a number, not null"]),
        (0, float, []),
        (0.0, float, []),
        (None, list, ["json should be an array, not null"]),
        ([None], list, []),
        ([None], list[bool], ["json[0] should be a boolean, not null"]),
        (None, list[bool] | None, []),
        ([True], list[bool] | None, []),
        ([None], list[bool] | None, ["json[0] should be a boolean, not null"]),
        (
            [0, None, True],
            list[bool | int],
            ["json[1] should be a boolean or an integer, not null"],
        ),
        (None, dict, ["json should be an object, not null"]),
        ({"k": None}, dict, []),
        ({"k": None}, dict[str, bool], ["json.k should be a boolean, not null"]),
        (
            {"k": None},
            dict[str, bool] | None,
            ["json.k should be a boolean, not null"],
        ),
        ({"k": None}, dict[str, bool | None] | None, []),
        (
            {"k": None},
            dict[str, bool | int],
            ["json.k should be a boolean or an integer, not null"],
        ),
        (None, str, ["json should be a string, not null"]),
        ("", str, []),
        (None, int | float, ["json should be an integer or a number, not null"]),
        (None, int | float | None, []),
        (
            {},
            int | float | None,
            ["json should be an integer or a number or null, not an object"],
        ),
    ],
    ids=conftest.id_func,
)
def test_body(obj: object, type_: type, target: list[str]) -> None:
    app = flask.Flask(__name__)
    with app.test_request_context(
        "/",
        data="null",
        content_type="application/json",
    ):
        obj_upgraded, errors = (
            json_api.body(type_) if obj is None else json_api.body(type_, raw=obj)
        )
    assert errors == target
    if not target:
        assert obj_upgraded == obj


@pytest.mark.parametrize(
    ("obj", "type_", "target"),
    [
        (datetime.date(2026, 4, 6), datetime.date, []),
        (datetime.date(2026, 4, 6), datetime.date | None, []),
        (
            0,
            datetime.date | None,
            ["json should be an ISO 8601 date string or null, not an integer"],
        ),
        (
            "4/6/2026",
            datetime.date,
            ["json should be an ISO 8601 date string, not a string"],
        ),
        (
            datetime.datetime(2026, 4, 6, 15, 47, 1, tzinfo=datetime.UTC),
            datetime.datetime,
            [],
        ),
        (
            datetime.datetime(  # ruff: ignore[call-datetime-without-tzinfo]
                2026,
                4,
                6,
                15,
                47,
                1,
            ),
            datetime.datetime,
            ["json should be an ISO 8601 date time string with TZ, not a string"],
        ),
        (Derived.SEAFOAM_GREEN, Derived, []),
        (
            "1",
            Derived,
            ['json should be "red" or "blue" or "seafoam_green", not a string'],
        ),
        (
            1,
            Derived,
            ['json should be "red" or "blue" or "seafoam_green", not an integer'],
        ),
        (decimal.Decimal(), decimal.Decimal, []),
        (decimal.Decimal("1234.5"), decimal.Decimal, []),
        ("abc", decimal.Decimal, ["json should be a number, not a string"]),
    ],
    ids=conftest.id_func,
)
def test_body_upgrade(obj: object, type_: type, target: list[str]) -> None:
    obj_upgraded, errors = json_api.body(type_, raw=utils.json_mutate(obj))
    assert errors == target
    if not target:
        assert obj_upgraded == obj


def test_body_nested() -> None:
    j: dict[str, object] = {
        "bool": False,
        "none": None,
        "list": [],
        "object": {
            "bool": False,
            "none": None,
            "list": [True, False],
            "object": None,
        },
    }
    assert not json_api.body(Top, raw=j)[1]


def test_body_preserves_explicit_empty_body() -> None:
    app = flask.Flask(__name__)

    with app.test_request_context("/", json={"bool": True}):
        _, errors = json_api.body(Top, raw={})

    assert errors == [
        "json.bool is missing",
        "json.list is missing",
        "json.none is missing",
        "json.object is missing",
    ]


def test_body_nested_error() -> None:
    j: dict[str, object] = {
        "list": [None],
        "none": True,
        "object": {
            "bool": None,
            "list": [True, {}],
            "object": [True, False],
        },
        "fake": None,
    }
    assert json_api.body(Top, raw=j)[1] == [
        "json.bool is missing",
        "json.list[0] should be a boolean, not null",
        "json.none should be null, not a boolean",
        "json.object.bool should be a boolean, not null",
        "json.object.list[1] should be a boolean, not an object",
        "json.object.none is missing",
        "json.object.object should be an object or null, not an array",
        "json.fake is not recognized",
    ]
