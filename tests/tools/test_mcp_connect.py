from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import pytest

from tools import mcp_connect

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


_METADATA_URI = "flask-htmx-template://metadata/server"
_BEARER = "test-bearer"


class FakeResult:
    """MCP result with JSON serialization behavior."""

    def __init__(self, value: mcp_connect.JSONObject) -> None:
        """Initialize a fake result.

        Args:
            value: JSON object returned by model serialization

        """
        self._value = value

    def model_dump(self, *, by_alias: bool, mode: str) -> mcp_connect.JSONObject:
        """Return the configured JSON object.

        Args:
            by_alias: Whether field aliases should be used
            mode: Pydantic serialization mode

        Returns:
            Configured JSON object

        """
        assert by_alias
        assert mode == "json"
        return self._value


class FakeClient:
    """MCP client that returns deterministic resource results."""

    def __init__(self) -> None:
        """Initialize an unused-resource marker."""
        self.listed_resources = False
        self.read_uri: str | None = None

    async def list_resources(self) -> FakeResult:
        """Return a resource listing.

        Returns:
            Fake MCP resource listing

        """
        self.listed_resources = True
        return FakeResult({"resources": [{"uri": _METADATA_URI}]})

    async def read_resource(self, uri: str) -> FakeResult:
        """Return resource contents.

        Args:
            uri: Resource URI to record

        Returns:
            Fake MCP resource contents

        """
        self.read_uri = uri
        return FakeResult(
            {
                "contents": [
                    {
                        "mimeType": "application/json",
                        "text": '{"schema_version": 1}',
                        "uri": uri,
                    },
                ],
            },
        )


@pytest.fixture
def mcp_client(
    monkeypatch: pytest.MonkeyPatch,
) -> FakeClient:
    """Replace the network connection with a fake MCP client.

    Returns:
        Fake client yielded by the patched connection

    """
    client = FakeClient()

    @asynccontextmanager
    async def connect(url: str, token: str) -> AsyncGenerator[FakeClient]:
        """Yield the fake client for expected connection settings.

        Yields:
            Fake MCP client

        """
        assert url == mcp_connect.DEFAULT_URL
        assert token == _BEARER
        yield client

    monkeypatch.setattr(mcp_connect, "connect", connect)
    monkeypatch.setenv(mcp_connect.DEFAULT_ENV, _BEARER)
    return client


def test_list_resources_command_prints_resource_listing(
    mcp_client: FakeClient,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = mcp_connect.main(["list-resources"])

    assert result == 0
    assert mcp_client.listed_resources
    assert json.loads(capsys.readouterr().out) == {
        "resources": [{"uri": _METADATA_URI}],
    }


def test_read_resource_command_prints_resource_contents(
    mcp_client: FakeClient,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = mcp_connect.main(["read-resource", _METADATA_URI])

    assert result == 0
    assert mcp_client.read_uri == _METADATA_URI
    assert json.loads(capsys.readouterr().out) == {
        "contents": [
            {
                "mimeType": "application/json",
                "text": '{"schema_version": 1}',
                "uri": _METADATA_URI,
            },
        ],
    }
