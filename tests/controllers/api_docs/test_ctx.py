from __future__ import annotations

import datetime
import types
from typing import Any, cast, Literal, NotRequired, TYPE_CHECKING, TypedDict

import flask
import pytest

from flask_htmx_template import exceptions as exc
from flask_htmx_template import utils
from flask_htmx_template.controllers.api_docs import ctx as api_docs
from flask_htmx_template.controllers.items.ctx import ItemCategory

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.controllers.conftest import WebClient


# ---------------------------------------------------------------------------
# Module-level helpers used by _extract_request_type tests
# ---------------------------------------------------------------------------


class _NotATypedDict:
    pass


def _view_with_non_td_validate() -> api_docs._ResponseInfo:
    utils.validate_json(dict[str, Any](), _NotATypedDict)
    return api_docs._ResponseInfo({}, {})


def _view_with_attr_validate() -> api_docs._ResponseInfo:
    utils.validate_json(dict[str, Any](), api_docs._Method)
    return api_docs._ResponseInfo({}, {})


class _SimpleTypedDict(TypedDict):
    """Minimal response type for API-doc tests."""

    key: str


class _TypedDictWithOptional(TypedDict):
    """Request type with an optional field."""

    name: str
    count: NotRequired[int]


def _view_with_valid_td() -> _SimpleTypedDict:
    """Create a response after validating a typed request body.

    Returns:
        Minimal response context.

    """
    utils.validate_json(dict[str, Any](), _SimpleTypedDict)
    return {"key": "value"}


def _json_multi() -> _SimpleTypedDict:
    """Dispatch an endpoint shared by multiple HTTP methods."""
    raise NotImplementedError


def _json_multi_get() -> _SimpleTypedDict:
    """Return the GET response for the multi-method endpoint.

    Returns:
        Minimal response context.

    """
    return {"key": "get"}


def _json_multi_put() -> _SimpleTypedDict:
    """Return the PUT response for the multi-method endpoint.

    Returns:
        Minimal response context.

    """
    return {"key": "put"}


def _minimal_app(
    rules: dict[str, Callable[..., Any] | tuple[Callable[..., Any], list[str]]],
) -> flask.Flask:
    app = flask.Flask(__name__)
    bp = flask.Blueprint("test_bp", __name__)
    for url, spec in rules.items():
        if callable(spec):
            bp.add_url_rule(url, view_func=spec)
        else:
            view_func, methods = spec
            bp.add_url_rule(url, view_func=view_func, methods=methods)
    app.register_blueprint(bp)
    return app


# ---------------------------------------------------------------------------
# _parse_module_doc
# ---------------------------------------------------------------------------


def test_parse_module_doc_title() -> None:
    m = types.ModuleType("test")
    m.__doc__ = "First paragraph.\n\nTitle: My title\n\nSecond paragraph."
    title, desc = api_docs._parse_module_doc(m)
    assert title == "My title"
    assert desc == ["First paragraph.", "Second paragraph."]


def test_parse_module_doc_no_title() -> None:
    m = types.ModuleType("test")
    m.__doc__ = "Just a description."
    title, desc = api_docs._parse_module_doc(m)
    assert title is None
    assert desc == ["Just a description."]


def test_parse_module_doc_stops_at_args() -> None:
    m = types.ModuleType("test")
    m.__doc__ = "Description.\n\nArgs:\n    x: something"
    _, desc = api_docs._parse_module_doc(m)
    assert desc == ["Description."]


# ---------------------------------------------------------------------------
# _extract_url_args
# ---------------------------------------------------------------------------


def test_extract_url_args_single() -> None:
    def view(uri: str) -> None:
        """Do something.

        Args:
            uri: Item URI

        """

    result = api_docs._extract_url_args("/j/items/i/<path:uri>", view)
    assert result == {"uri": "Item URI"}


def test_extract_url_args_multiple() -> None:
    def view(group: str, name: str) -> None:
        """Do something.

        Args:
            group: Group slug
            name: Item name
            other: Not a URL arg

        """

    result = api_docs._extract_url_args("/j/<group>/<name>", view)
    assert result == {"group": "Group slug", "name": "Item name"}


def test_extract_url_args_none() -> None:
    def view() -> None:
        """No URL args."""

    result = api_docs._extract_url_args("/j/items", view)
    assert result == {}


# ---------------------------------------------------------------------------
# _extract_query_args
# ---------------------------------------------------------------------------


def test_extract_query_args_multiple() -> None:
    def view() -> None:
        """Get resources.

        Query args:
            before: ISO-8601 date upper bound, optional
            category: category name, optional

        Returns:
            Resources before the upper bound.

        """

    result = api_docs._extract_query_args(view)

    assert result == {
        "before": "ISO-8601 date upper bound, optional",
        "category": "category name, optional",
    }


def test_extract_query_args_none() -> None:
    def view() -> None:
        """Get resources without filters."""

    result = api_docs._extract_query_args(view)

    assert result == {}


# ---------------------------------------------------------------------------
# get_operations — error cases
# ---------------------------------------------------------------------------


def test_get_operations_missing_response_type() -> None:
    def no_return_view():  # ruff: ignore[missing-return-type-private-function]
        """Have no return type annotation."""

    app = _minimal_app({"/j/test": no_return_view})
    with pytest.raises(exc.InvalidEndpointError):
        api_docs.get_operations(app)


def test_get_operations_multi_method_no_dispatch() -> None:
    def shared_view() -> str:
        """Share incorrectly across multiple HTTP methods.

        Returns:
            string HTML response

        """
        return ""

    app = _minimal_app({"/j/test": (shared_view, ["GET", "POST"])})
    with pytest.raises(exc.InvalidJSONRouteError):
        api_docs.get_operations(app)


# ---------------------------------------------------------------------------
# JSON API endpoint
# ---------------------------------------------------------------------------


def test_json_api_structure(web_client: WebClient) -> None:
    result, _ = web_client.GET_J("api_docs.json_api")
    assert isinstance(result, dict)
    urls = result["urls"]
    assert isinstance(urls, dict)
    for url, methods in urls.items():
        assert isinstance(url, str)
        assert url.startswith("/j/")
        assert isinstance(methods, dict)
        for method, info in methods.items():
            assert method in {"GET", "POST", "PUT", "DELETE"}
            assert isinstance(info, dict)
            assert "description" in info
            assert "url_args" in info
            assert "query_args" in info
            assert "responses" in info


def test_json_api_url_args(web_client: WebClient) -> None:
    result, _ = web_client.GET_J("api_docs.json_api")
    assert isinstance(result, dict)
    urls = result["urls"]
    assert isinstance(urls, dict)
    url_ops = urls["/j/items/i/<path:uri>"]
    assert isinstance(url_ops, dict)
    item_get = url_ops["GET"]
    assert isinstance(item_get, dict)
    assert item_get["url_args"] == {"uri": "Item URI"}


def test_json_api_query_args(web_client: WebClient) -> None:
    result, _ = web_client.GET_J("api_docs.json_api")

    assert isinstance(result, dict)
    urls = result["urls"]
    assert isinstance(urls, dict)
    url_ops = urls["/j/items"]
    assert isinstance(url_ops, dict)
    item_get = url_ops["GET"]
    assert isinstance(item_get, dict)
    assert item_get["query_args"] == {
        "before": "filter items that appear before this date, optional",
    }


# ---------------------------------------------------------------------------
# _Operation properties
# ---------------------------------------------------------------------------


def test_operation_request_example_json_none() -> None:
    op = api_docs._Operation(
        url="/j/test",
        method=api_docs._Method.GET,
        description=["Test"],
        url_args={},
        query_args={},
        request_schema=None,
        request_example=None,
        responses={},
        enums=set(),
    )
    assert op.request_example_json is None
    assert op.request_schema_json is None


# ---------------------------------------------------------------------------
# _find_typed_dict — union arm
# ---------------------------------------------------------------------------


def test_find_typed_dict_union() -> None:
    # _SimpleTypedDict | str: first arg is TypedDict, found immediately
    result = api_docs._find_typed_dict(_SimpleTypedDict | str)
    assert result is _SimpleTypedDict


def test_find_typed_dict_union_second_arg() -> None:
    # str | _SimpleTypedDict: str is processed first (None), loop continues (280->279),
    # then _SimpleTypedDict is found (279 exhausts on hit)
    result = api_docs._find_typed_dict(str | _SimpleTypedDict)
    assert result is _SimpleTypedDict


def test_find_typed_dict_union_none_found() -> None:
    # str | int: no TypedDict in union → loop exhausts (279->284) → returns None
    result = api_docs._find_typed_dict(str | int)
    assert result is None


def test_find_typed_dict_type_alias() -> None:
    # Object with __value__ attribute simulates a Python 3.12 type alias
    class _MockAlias:
        __value__ = _SimpleTypedDict

    result = api_docs._find_typed_dict(_MockAlias)
    assert result is _SimpleTypedDict


# ---------------------------------------------------------------------------
# _example_value / _example_collection / _example_value_for_type
# ---------------------------------------------------------------------------


def test_example_value_intenum() -> None:
    result = api_docs._example_value(api_docs._Method)
    assert isinstance(result, str)


def test_example_value_literal_string() -> None:
    result = api_docs._example_value(Literal["a word"])
    assert result == "a word"


def test_example_value_literal_ints() -> None:
    result = api_docs._example_value(Literal[1, 2, 3])
    assert result == 1


def test_example_collection_dict_object() -> None:
    result = api_docs._example_collection(dict, (str, object))
    assert result == {}


def test_example_value_union_non_none() -> None:
    # str | int has no NoneType → falls through to return non-None example
    result = api_docs._example_value(str | int)
    assert result == "a string of words"


def test_example_value_union_optional_prefers_non_none() -> None:
    annotation = str | None

    result = api_docs._example_value(annotation)

    assert result == "a string of words"


def test_example_from_union_all_none() -> None:
    result = api_docs._example_from_union(
        (types.NoneType,),
        "",
        skip_not_required=False,
    )
    assert result is None


def test_example_value_for_type_unknown() -> None:
    # datetime.date is not an IntEnum or TypedDict → returns None
    result = api_docs._example_value_for_type(datetime.date)
    assert result is None


# ---------------------------------------------------------------------------
# _schema_type
# ---------------------------------------------------------------------------


def test_schema_type_intenum() -> None:
    assert api_docs._schema_type(ItemCategory) == "item category enum value"


def test_schema_type_literal_strings() -> None:
    assert api_docs._schema_type(Literal["a word"]) == "'a word'"


def test_schema_type_literal_ints() -> None:
    assert api_docs._schema_type(Literal[1, 2, 3]) == "1 or 2 or 3"


def test_schema_type_unknown() -> None:
    assert api_docs._schema_type(bytes) == "unknown"


# ---------------------------------------------------------------------------
# _response_arms — tuple with no TypedDict
# ---------------------------------------------------------------------------


def test_response_arms_tuple_no_typed_dict() -> None:
    # tuple[str, int] has no TypedDict first arg → empty dict
    result = api_docs._response_arms(tuple[str, int])
    assert result == {}


# ---------------------------------------------------------------------------
# _extract_request_type — non-TypedDict name branch
# ---------------------------------------------------------------------------


def test_extract_request_type_non_typed_dict_name() -> None:
    # _NotATypedDict is not a TypedDict → _is_typed_dict returns False → None
    result = api_docs._extract_request_type(_view_with_non_td_validate)
    assert result is None


def test_extract_request_type_attribute_type_arg() -> None:
    # _view_with_attr_validate uses api_docs._Method as type arg (ast.Attribute,
    # not ast.Name) → isinstance(type_arg, ast.Name) is False → 658->649 branch
    result = api_docs._extract_request_type(_view_with_attr_validate)
    assert result is None


# ---------------------------------------------------------------------------
# _collect_enums_from_annotation
# ---------------------------------------------------------------------------


def test_collect_enums_from_annotation_direct() -> None:
    result: set[type] = set()
    api_docs._collect_enums_from_annotation(api_docs._Method, result)
    assert api_docs._Method in result


def test_collect_enums_from_annotation_nested_in_typed_dict() -> None:
    result: set[type] = set()
    api_docs._collect_enums_from_annotation(_SimpleTypedDict, result)
    assert not result  # _SimpleTypedDict has no enum fields


def test_collect_enums_from_annotation_cycle_guard() -> None:
    result: set[type] = set()
    seen: set[int] = set()
    api_docs._collect_enums_from_annotation(str, result, seen)
    api_docs._collect_enums_from_annotation(str, result, seen)
    assert not result


# ---------------------------------------------------------------------------
# /j/api/enums endpoint
# ---------------------------------------------------------------------------


def test_json_api_enums_structure(web_client: WebClient) -> None:
    result, _ = web_client.GET_J("api_docs.json_api_enums")
    assert isinstance(result, dict)
    for enum_name, values in result.items():
        assert isinstance(enum_name, str)
        assert isinstance(values, list)
        assert all(isinstance(v, str) for v in values)


def test_json_api_enums_contains_item_category(web_client: WebClient) -> None:
    result, _ = web_client.GET_J("api_docs.json_api_enums")
    assert "item category" in result
    assert result["item category"] == ["general", "special"]


def test_json_api_includes_enums(web_client: WebClient) -> None:
    result, _ = web_client.GET_J("api_docs.json_api")
    assert "enums" in result
    assert result["enums"] == web_client.GET_J("api_docs.json_api_enums")[0]


def test_json_api_enums_example_matches_actual(web_client: WebClient) -> None:
    enums_result, _ = web_client.GET_J("api_docs.json_api_enums")
    api_result, _ = web_client.GET_J("api_docs.json_api")
    assert isinstance(api_result, dict)
    urls = api_result["urls"]
    assert isinstance(urls, dict)
    enums_op = urls["/j/api/enums"]
    assert isinstance(enums_op, dict)
    get_op = enums_op["GET"]
    assert isinstance(get_op, dict)
    responses = get_op["responses"]
    assert isinstance(responses, dict)
    response_200 = responses["200"]
    assert isinstance(response_200, dict)
    example = response_200["example"]
    assert example == enums_result


# ---------------------------------------------------------------------------
# _find_typed_dict — non-object dict value branch
# ---------------------------------------------------------------------------


def test_find_typed_dict_dict_non_object_value() -> None:
    # dict[str, list[str]] has a non-object value type → treated as documentable
    result = api_docs._find_typed_dict(dict[str, list[str]])
    assert result is not None


def test_find_typed_dict_dict_typed_dict_value() -> None:
    # dict[str, _SimpleTypedDict]: value is TypedDict → recurse finds it (line 310)
    result = api_docs._find_typed_dict(dict[str, _SimpleTypedDict])
    assert result is _SimpleTypedDict


def test_find_typed_dict_dict_object_value() -> None:
    # dict[str, object] has bare object as value → not treated as documentable
    result = api_docs._find_typed_dict(dict[str, object])
    assert result is None


# ---------------------------------------------------------------------------
# Request body schemas
# ---------------------------------------------------------------------------


def test_example_from_typed_dict_skips_not_required_fields() -> None:
    result = api_docs._example_from_typed_dict(
        cast("type[dict[str, object]]", _TypedDictWithOptional),
        skip_not_required=True,
    )

    assert result == {"name": "Example item"}


def test_schema_from_typed_dict_skips_not_required_fields() -> None:
    result = api_docs._schema_from_typed_dict(
        cast("type[dict[str, object]]", _TypedDictWithOptional),
        skip_not_required=True,
    )

    assert result == {"name": "string"}


def test_operation_serializes_request_schema_and_example() -> None:
    operation = api_docs._Operation(
        url="/j/test",
        method=api_docs._Method.GET,
        description=["Test"],
        url_args={},
        query_args={},
        request_schema={"key": "string"},
        request_example={"key": "value"},
        responses={},
        enums=set(),
    )

    schema_json = operation.request_schema_json
    example_json = operation.request_example_json

    assert schema_json is not None
    assert "key" in schema_json
    assert example_json is not None
    assert "key" in example_json


def test_extract_request_type_finds_typed_dict() -> None:
    result = api_docs._extract_request_type(_view_with_valid_td)

    assert result is _SimpleTypedDict


def test_get_operations_includes_request_body_schema_and_example() -> None:
    app = _minimal_app({"/j/test": (_view_with_valid_td, ["POST"])})

    groups = api_docs.get_operations(app)

    _, operations = next(iter(groups.values()))
    assert operations[0].request_schema is not None
    assert operations[0].request_example is not None


# ---------------------------------------------------------------------------
# Response annotations and multi-method dispatch
# ---------------------------------------------------------------------------


def test_response_arms_expands_type_alias() -> None:
    class _MockAlias:
        """Minimal Python 3.12 type-alias stand-in."""

        __value__ = _SimpleTypedDict

    result = api_docs._response_arms(_MockAlias)

    assert "200" in result


def test_response_arms_combines_union_arms() -> None:
    result = api_docs._response_arms(_SimpleTypedDict | str)

    assert "200" in result


def test_response_arms_uses_default_error_status() -> None:
    result = api_docs._response_arms(tuple[_SimpleTypedDict, int])

    assert "4xx" in result


def test_response_arms_uses_literal_error_status() -> None:
    result = api_docs._response_arms(tuple[_SimpleTypedDict, Literal[422]])

    assert "422" in result


def test_response_arms_ignores_undocumented_type() -> None:
    result = api_docs._response_arms(str)

    assert result == {}


def test_extract_response_annotations_without_package_module() -> None:
    def view() -> _SimpleTypedDict:
        """Get a resource.

        Returns:
            Minimal response context.

        """
        return {"key": "value"}

    view.__module__ = "toplevelmod"

    result = api_docs._extract_response_annotations(view)

    assert "200" in result


def test_get_operations_dispatches_each_method() -> None:
    assert callable(_json_multi_get)
    assert callable(_json_multi_put)
    app = _minimal_app({"/j/test": (_json_multi, ["GET", "PUT"])})

    groups = api_docs.get_operations(app)

    _, operations = next(iter(groups.values()))
    assert len(operations) == 2
