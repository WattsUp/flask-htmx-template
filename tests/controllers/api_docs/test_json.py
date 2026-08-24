from __future__ import annotations

from typing import cast, TYPE_CHECKING

if TYPE_CHECKING:
    from flask_htmx_template.controllers.api_docs.ctx import _APIDocsJSON
    from tests.controllers.conftest import WebClient


def test_json_api_includes_documented_urls(web_client: WebClient) -> None:
    raw, _ = web_client.GET_J("api_docs.json_api")
    result = cast("_APIDocsJSON", raw)

    assert "/j/items" in result["urls"]


def test_json_api_enums_includes_item_category(web_client: WebClient) -> None:
    result, _ = web_client.GET_J("api_docs.json_api_enums")

    assert result["item category"] == ["general", "special"]


def test_json_api_has_one_common_error_response(web_client: WebClient) -> None:
    # Act
    raw, _ = web_client.GET_J("api_docs.json_api")
    result = cast("_APIDocsJSON", raw)

    # Assert
    assert set(result) == {"urls", "enums", "errors"}
    assert result["errors"]["schema"] == {"errors": ["string"]}
    assert result["errors"]["example"] == {"errors": ["a string of words"]}


def test_json_api_does_not_repeat_common_error_response(
    web_client: WebClient,
) -> None:
    # Act
    raw, _ = web_client.GET_J("api_docs.json_api")
    result = cast("_APIDocsJSON", raw)

    operations = [
        operation
        for methods in result["urls"].values()
        for operation in methods.values()
    ]

    # Assert
    assert operations
    assert all("4xx" not in operation["responses"] for operation in operations)
