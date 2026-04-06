from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tests.controllers.conftest import WebClient


def test_page_dashboard(web_client: WebClient) -> None:
    result, _ = web_client.GET("common.page_dashboard")
    assert "Dashboard" in result


def test_page_status(web_client: WebClient) -> None:
    result, _ = web_client.GET("common.page_status")
    assert result == "ok"

    result, _ = web_client.GET(
        "prometheus_metrics",
        content_type="text/plain; version=0.0.4; charset=utf-8",
    )
    if isinstance(result, bytes):
        result = result.decode()
    assert 'endpoint="common.page_status"' not in result


def test_page_style_test(web_client: WebClient) -> None:
    result, _ = web_client.GET("common.page_style_test")
    assert "Style test" in result


def test_favicon(web_client: WebClient) -> None:
    web_client.GET(
        "common.favicon",
        content_type="image/vnd.microsoft.icon",
    )
