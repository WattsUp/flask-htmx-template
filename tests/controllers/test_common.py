from __future__ import annotations

from typing import TYPE_CHECKING

from flask_htmx_template import web_theme

if TYPE_CHECKING:
    from tests.controllers.conftest import WebClient


def _set_cookies(web_client: WebClient, swatch: str, mood: str) -> None:
    web_client._client.set_cookie("theme_swatch", swatch)
    web_client._client.set_cookie("theme_mood", mood)


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


def test_theme_css(web_client: WebClient) -> None:
    result, _ = web_client.GET(
        "common.theme_css",
        content_type="text/css; charset=utf-8",
    )
    css = result.decode()
    assert css.startswith("@layer theme {")
    assert ":root {" in css
    assert "@layer base {" in css
    assert "--color-primary:" in css
    assert "--color-primary-fixed:" in css
    assert "html:where(.dark, .dark *) {" in css
    assert css.endswith("}\n")


def test_theme_css_query_args(web_client: WebClient) -> None:
    swatch_and_mood = {"swatch": "#ff5500", "mood": web_theme.Mood.VIBRANT.name}
    result, _ = web_client.GET(
        ("common.theme_css", swatch_and_mood),
        content_type="text/css; charset=utf-8",
    )
    assert "--color-primary:" in result.decode()


def test_theme_css_cookies(web_client: WebClient) -> None:
    _set_cookies(web_client, "#ff5500", web_theme.Mood.EXPRESSIVE.name)
    result, _ = web_client.GET(
        "common.theme_css",
        content_type="text/css; charset=utf-8",
    )
    assert "--color-primary:" in result.decode()


def test_theme_css_swatch_from_cookie_mood_from_config(web_client: WebClient) -> None:
    web_client._client.set_cookie("theme_swatch", "#ff5500")
    result, _ = web_client.GET(
        "common.theme_css",
        content_type="text/css; charset=utf-8",
    )
    assert "--color-primary:" in result.decode()


def test_theme_css_mood_from_cookie_swatch_from_config(web_client: WebClient) -> None:
    web_client._client.set_cookie("theme_mood", web_theme.Mood.VIBRANT.name)
    result, _ = web_client.GET(
        "common.theme_css",
        content_type="text/css; charset=utf-8",
    )
    assert "--color-primary:" in result.decode()


def test_theme_css_invalid_mood_falls_back(web_client: WebClient) -> None:
    result, _ = web_client.GET(
        ("common.theme_css", {"swatch": "#3f6837", "mood": "INVALID"}),
        content_type="text/css; charset=utf-8",
    )
    assert "--color-primary:" in result.decode()


def test_theme_edit(web_client: WebClient) -> None:
    result, _ = web_client.GET("common.theme")
    assert "Theme" in result
    assert "theme-hue" in result
    assert "theme-mood-select" in result


def test_theme_edit_uses_cookies(web_client: WebClient) -> None:
    _set_cookies(web_client, "#ff5500", web_theme.Mood.VIBRANT.name)
    result, _ = web_client.GET("common.theme")
    assert web_theme.Mood.VIBRANT.name in result


def test_theme_edit_swatch_from_cookie_mood_from_config(web_client: WebClient) -> None:
    web_client._client.set_cookie("theme_swatch", "#ff5500")
    result, _ = web_client.GET("common.theme")
    assert "theme-hue" in result


def test_theme_edit_mood_from_cookie_swatch_from_config(web_client: WebClient) -> None:
    web_client._client.set_cookie("theme_mood", web_theme.Mood.VIBRANT.name)
    result, _ = web_client.GET("common.theme")
    assert web_theme.Mood.VIBRANT.name in result


def test_theme_edit_invalid_mood_in_cookie_falls_back(web_client: WebClient) -> None:
    _set_cookies(web_client, "#3f6837", "INVALID")
    result, _ = web_client.GET("common.theme")
    assert web_theme.DEFAULT_MOOD.name in result


def test_theme_save(web_client: WebClient) -> None:
    swatch = "#1a2b3c"
    mood = web_theme.Mood.EXPRESSIVE.name
    _, headers = web_client.PUT(
        "common.theme",
        data={"swatch": swatch, "mood": mood},
    )
    all_cookies = " ".join(headers.get_all("Set-Cookie"))
    assert swatch in all_cookies
    assert mood in all_cookies


def test_theme_save_invalid_swatch(web_client: WebClient) -> None:
    web_client.PUT(
        "common.theme",
        data={"swatch": "notacolor", "mood": web_theme.Mood.TONAL_SPOT.name},
    )


def test_theme_save_invalid_mood(web_client: WebClient) -> None:
    web_client.PUT(
        "common.theme",
        data={"swatch": "#3f6837", "mood": "INVALID"},
    )
