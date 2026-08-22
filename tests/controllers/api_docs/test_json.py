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
