from __future__ import annotations

import urllib.parse
from typing import TYPE_CHECKING

import pytest

from flask_htmx_template.encryption.top import ENCRYPTION_AVAILABLE

if TYPE_CHECKING:
    from tests.controllers.conftest import WebClient, WebClientEncrypted


def test_page_login(web_client: WebClient) -> None:
    result, headers = web_client.GET("auth.page_login")
    assert "Login" in result
    assert "Location" not in headers


@pytest.mark.skipif(not ENCRYPTION_AVAILABLE, reason="No encryption available")
@pytest.mark.encryption
def test_unauth_redirect(web_client_encrypted: WebClientEncrypted) -> None:
    endpoint = "common.page_dashboard"
    result, headers = web_client_encrypted.GET(endpoint)
    assert not result

    url = web_client_encrypted.url_for(endpoint)
    login = web_client_encrypted.url_for("auth.page_login")
    # There's double quoting if given to url_for directly
    assert headers["HX-Redirect"] == f"{login}?next={urllib.parse.quote_plus(url)}"


@pytest.mark.skipif(not ENCRYPTION_AVAILABLE, reason="No encryption available")
@pytest.mark.encryption
def test_unauth_static(web_client_encrypted: WebClientEncrypted) -> None:
    result, _ = web_client_encrypted.GET(
        ("static", {"filename": "dist/main.css"}),
        content_type="text/css; charset=utf-8",
    )
    if isinstance(result, bytes):
        result = result.decode()
    assert "/*! tailwindcss" in result


@pytest.mark.skipif(not ENCRYPTION_AVAILABLE, reason="No encryption available")
@pytest.mark.encryption
def test_login(web_client_encrypted: WebClientEncrypted) -> None:
    web_client_encrypted.login()
    result, _ = web_client_encrypted.GET("common.page_dashboard")
    assert "Dashboard" in result


@pytest.mark.skipif(not ENCRYPTION_AVAILABLE, reason="No encryption available")
@pytest.mark.encryption
def test_page_login_already_logged_in(web_client_encrypted: WebClientEncrypted) -> None:
    web_client_encrypted.login()
    result, headers = web_client_encrypted.GET("auth.page_login")
    assert not result
    url = web_client_encrypted.url_for("common.page_dashboard")
    assert headers["HX-Redirect"] == url


def test_login_empty(web_client: WebClient) -> None:
    result, _ = web_client.POST("auth.login")
    assert "Password must not be blank" in result


@pytest.mark.skipif(not ENCRYPTION_AVAILABLE, reason="No encryption available")
@pytest.mark.encryption
def test_login_bad_password(web_client_encrypted: WebClientEncrypted) -> None:
    result, _ = web_client_encrypted.POST("auth.login", data={"password": "fake"})
    assert "Bad password" in result


@pytest.mark.skipif(not ENCRYPTION_AVAILABLE, reason="No encryption available")
@pytest.mark.encryption
def test_logout(web_client_encrypted: WebClientEncrypted) -> None:
    web_client_encrypted.login()
    result, headers = web_client_encrypted.POST("auth.logout")
    assert not result
    url = web_client_encrypted.url_for("auth.page_login")
    assert headers["HX-Redirect"] == url

    # Can't reach dashboard anymore
    test_unauth_redirect(web_client_encrypted)
