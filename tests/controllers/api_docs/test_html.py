from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tests.controllers.conftest import WebClient


def test_page(web_client: WebClient) -> None:
    result, _ = web_client.GET("api_docs.page")
    assert "API" in result


def test_page_includes_query_parameters(web_client: WebClient) -> None:
    result, _ = web_client.GET("api_docs.page")

    assert "Query parameters" in result
    assert "before" in result
    assert "ISO-8601 date string, optional" in result
