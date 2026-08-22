from __future__ import annotations

import urllib.parse
from typing import TYPE_CHECKING

import pytest

from flask_htmx_template.models.config import Config, ConfigKey

if TYPE_CHECKING:
    from collections.abc import Generator

    import flask

    from tests.controllers.conftest import WebClient


@pytest.fixture
def auth_enabled(flask_app: flask.Flask) -> Generator[str]:
    """Enable auth and yield the web key.

    Yields:
        Web key

    """
    web_key = Config.fetch(ConfigKey.WEB_KEY)
    flask_app.testing = False
    try:
        yield web_key
    finally:
        flask_app.testing = True


def test_page_login(web_client: WebClient) -> None:
    result, headers = web_client.GET("auth.page_login")
    assert "Login" in result
    assert "Location" not in headers


def test_unauth_redirect(web_client: WebClient, auth_enabled: str) -> None:
    endpoint = "common.page_dashboard"
    result, headers = web_client.GET(endpoint)
    assert not result

    url = web_client.url_for(endpoint)
    login = web_client.url_for("auth.page_login")
    # There's double quoting if given to url_for directly
    assert headers["HX-Redirect"] == f"{login}?next={urllib.parse.quote_plus(url)}"


def test_unauth_static(web_client: WebClient) -> None:
    result, _ = web_client.GET(
        ("static", {"filename": "dist/main.css"}),
        content_type="text/css; charset=utf-8",
    )
    assert "/*! tailwindcss" in result.decode()


def test_login(web_client: WebClient, auth_enabled: str) -> None:
    web_client.login(auth_enabled)
    result, _ = web_client.GET("common.page_dashboard")
    assert "Dashboard" in result


def test_page_login_already_logged_in(web_client: WebClient, auth_enabled: str) -> None:
    web_client.login(auth_enabled)
    result, headers = web_client.GET("auth.page_login")
    assert not result
    url = web_client.url_for("common.page_dashboard")
    assert headers["HX-Redirect"] == url


def test_login_empty(web_client: WebClient) -> None:
    result, _ = web_client.POST("auth.login")
    assert "Password must not be blank" in result


def test_login_bad_password(web_client: WebClient) -> None:
    result, _ = web_client.POST("auth.login", data={"password": "fake"})
    assert "Bad password" in result


def test_logout(web_client: WebClient, auth_enabled: str) -> None:
    web_client.login(auth_enabled)
    result, headers = web_client.POST("auth.logout")
    assert not result
    url = web_client.url_for("auth.page_login")
    assert headers["HX-Redirect"] == url

    # Can't reach dashboard anymore
    endpoint = "common.page_dashboard"
    result, headers = web_client.GET(endpoint)
    assert not result
    dashboard_url = web_client.url_for(endpoint)
    login_url = web_client.url_for("auth.page_login")
    assert (
        headers["HX-Redirect"]
        == f"{login_url}?next={urllib.parse.quote_plus(dashboard_url)}"
    )
