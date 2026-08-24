from __future__ import annotations

import re
from typing import TYPE_CHECKING

from flask_htmx_template import web
from flask_htmx_template.models.config import Config, ConfigKey

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


def test_page_explains_when_four_xx_responses_are_possible(
    web_client: WebClient,
) -> None:
    result, _ = web_client.GET("api_docs.page")
    explanation = " ".join(re.sub(r"<[^>]+>", " ", result).lower().split())

    assert "no url, query, or body inputs" in explanation
    assert "never return a 4xx" in explanation
    assert "may return a 4xx" in explanation


def test_page_renders_configured_bearer_token(web_client: WebClient) -> None:
    configured_value = "configured-test-bearer-token"
    with web.db.begin_session():
        Config.set_(ConfigKey.API_BEARER_TOKEN, configured_value)

    result, _ = web_client.GET("api_docs.page")

    assert 'id="api-bearer-token"' in result
    assert configured_value in result


def test_page_includes_api_usage_instructions(web_client: WebClient) -> None:
    with web.db.begin_session():
        token = Config.fetch(ConfigKey.API_BEARER_TOKEN)

    result, _ = web_client.GET("api_docs.page")

    assert "Calling the API" in result
    assert "BEARER_TOKEN" in result
    assert "Authorization: Bearer ${BEARER_TOKEN}" in result
    assert "X-Indent: 2" in result
    assert "blur-sm" in result
    assert "hover:blur-none" in result
    assert "focus:blur-none" in result
    assert "api-bearer-token" in result
    assert 'onclick="apiDocs.copyBearerToken(event)"' in result
    assert token in result
