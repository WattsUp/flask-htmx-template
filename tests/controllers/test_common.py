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
    assert 'endpoint="common.page_status"' not in result.decode()


def test_page_style_test(web_client: WebClient) -> None:
    result, _ = web_client.GET("common.page_style_test")
    assert "Style test" in result


def test_favicon(web_client: WebClient) -> None:
    web_client.GET(
        "common.favicon",
        content_type="image/vnd.microsoft.icon",
    )


def test_theme(web_client: WebClient) -> None:
    result, _ = web_client.GET("common.theme", content_type="text/css; charset=utf-8")
    css = result.decode()
    assert css.startswith("@layer theme {")
    assert ":root {" in css
    assert "@layer base {" in css
    assert "--color-primary:" in css
    assert "--color-primary-fixed:" in css
    assert "html:where(.dark, .dark *) {" in css
    assert css.endswith("}\n")
