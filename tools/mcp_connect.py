#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK
"""Inspect and call the template's Streamable HTTP MCP server."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from contextlib import asynccontextmanager
from typing import cast, TYPE_CHECKING

import argcomplete
import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


_DEFAULT_SCHEME = "http"
_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 5000
_DEFAULT_PATH = "/mcp"
DEFAULT_URL = f"{_DEFAULT_SCHEME}://{_DEFAULT_HOST}:{_DEFAULT_PORT}{_DEFAULT_PATH}"
DEFAULT_ENV = "BEARER_TOKEN"

type JSONValue = str | int | float | bool | list[JSONValue] | JSONObject | None
type JSONObject = dict[str, JSONValue]


@asynccontextmanager
async def connect(url: str, token: str) -> AsyncGenerator[Client]:
    """Connect an authenticated client to a Streamable HTTP MCP server.

    Args:
        url: Streamable HTTP MCP endpoint
        token: API bearer token

    Yields:
        Connected MCP client

    """
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx2.AsyncClient(headers=headers) as http_client:
        transport = streamable_http_client(url, http_client=http_client)
        async with Client(transport) as client:
            yield client


async def list_tools(url: str, token: str) -> JSONObject:
    """List tools exposed by an MCP server.

    Args:
        url: Streamable HTTP MCP endpoint
        token: API bearer token

    Returns:
        MCP tools/list result

    """
    async with connect(url, token) as client:
        result = await client.list_tools()
    return cast("JSONObject", result.model_dump(by_alias=True, mode="json"))


async def list_resources(url: str, token: str) -> JSONObject:
    """List resources exposed by an MCP server.

    Args:
        url: Streamable HTTP MCP endpoint
        token: API bearer token

    Returns:
        MCP resources/list result

    """
    async with connect(url, token) as client:
        result = await client.list_resources()
    return cast("JSONObject", result.model_dump(by_alias=True, mode="json"))


async def read_resource(url: str, token: str, uri: str) -> JSONObject:
    """Read a resource exposed by an MCP server.

    Args:
        url: Streamable HTTP MCP endpoint
        token: API bearer token
        uri: URI of the resource to read

    Returns:
        MCP resources/read result

    """
    async with connect(url, token) as client:
        result = await client.read_resource(uri)
    return cast("JSONObject", result.model_dump(by_alias=True, mode="json"))


async def call_tool(
    url: str,
    token: str,
    name: str,
    arguments: JSONObject,
) -> JSONObject:
    """Call a tool exposed by an MCP server.

    Args:
        url: Streamable HTTP MCP endpoint
        token: API bearer token
        name: Tool name
        arguments: Tool arguments

    Returns:
        MCP tools/call result

    """
    async with connect(url, token) as client:
        result = await client.call_tool(name, arguments)
    return cast("JSONObject", result.model_dump(by_alias=True, mode="json"))


def main(command_line: list[str] | None = None) -> int:
    """Execute the MCP inspection command.

    Args:
        command_line: Command-line arguments, None for sys.argv

    Returns:
        0 on success

    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help=f"Streamable HTTP endpoint (default: {DEFAULT_URL})",
    )
    parser.add_argument(
        "--token-env",
        default=DEFAULT_ENV,
        metavar="NAME",
        help=(
            "environment variable containing the bearer token "
            f"(default: {DEFAULT_ENV})"
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list-tools", help="list MCP tools")
    commands.add_parser("list-resources", help="list MCP resources")
    read = commands.add_parser("read-resource", help="read an MCP resource")
    read.add_argument("uri", help="resource URI")
    call = commands.add_parser("call", help="call an MCP tool")
    call.add_argument("name", help="tool name")
    call.add_argument(
        "--arguments",
        default="{}",
        help="JSON object of tool arguments (default: {})",
    )
    argcomplete.autocomplete(parser)
    args = parser.parse_args(command_line)

    # NOTE: Keep the credential in the environment instead of shell history or argv.
    token = os.getenv(args.token_env)
    if not token:
        parser.error(f"environment variable {args.token_env!r} is not set")

    if args.command == "list-tools":
        result = asyncio.run(list_tools(args.url, token))
    elif args.command == "list-resources":
        result = asyncio.run(list_resources(args.url, token))
    elif args.command == "read-resource":
        result = asyncio.run(read_resource(args.url, token, args.uri))
    else:
        try:
            arguments_raw = json.loads(args.arguments)
        except json.JSONDecodeError as error:
            parser.error(f"invalid --arguments JSON: {error.msg}")
        if not isinstance(arguments_raw, dict):
            parser.error("--arguments must be a JSON object")
        arguments = cast("JSONObject", arguments_raw)
        result = asyncio.run(call_tool(args.url, token, args.name, arguments))

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
