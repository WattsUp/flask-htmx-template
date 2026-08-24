"""Flask HTMX Template Model Context Protocol server."""

from __future__ import annotations

import functools
import importlib
import json
import logging
import pkgutil
import time
from enum import IntEnum
from typing import NamedTuple, TYPE_CHECKING

import prometheus_client
from mcp.server import MCPServer
from mcp.shared.exceptions import MCPError
from mcp_types import (
    CallToolResult,
)
from mcp_types import INTERNAL_ERROR as MCP_INTERNAL_ERROR
from mcp_types import INVALID_PARAMS as MCP_INVALID_PARAMS
from mcp_types import METHOD_NOT_FOUND as MCP_METHOD_NOT_FOUND
from mcp_types import (
    TextContent,
)

from flask_htmx_template import controllers
from flask_htmx_template.controllers import base
from flask_htmx_template.version import __version__

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any

    from mcp.server.context import CallNext, HandlerResult, ServerRequestContext

    from flask_htmx_template.database import Database


class MCPErrorCode(IntEnum):
    """Safe JSON-RPC error codes returned for MCP tool failures."""

    INVALID_PARAMS = MCP_INVALID_PARAMS
    METHOD_NOT_FOUND = MCP_METHOD_NOT_FOUND
    INTERNAL_ERROR = MCP_INTERNAL_ERROR


_MCP_ERROR_MESSAGES: dict[MCPErrorCode, str] = {
    MCPErrorCode.INVALID_PARAMS: "MCP tool arguments are invalid.",
    MCPErrorCode.METHOD_NOT_FOUND: "MCP tool was not found.",
    MCPErrorCode.INTERNAL_ERROR: "MCP tool execution failed.",
}

_LOGGER = logging.getLogger(__name__)
_CALL_TOOL_METHOD = "tools/call"

_SERVER_NAME = "Flask HTMX Template"
_SERVER_DESCRIPTION = "Read and write item information from Flask HTMX Template."
_METADATA_SCHEMA_VERSION = 1
METADATA_RESOURCE_URI = "flask-htmx-template://metadata/server"
CAPABILITIES_RESOURCE_URI = "flask-htmx-template://metadata/capabilities"
_RESOURCE_URIS = (
    METADATA_RESOURCE_URI,
    CAPABILITIES_RESOURCE_URI,
)


def _metadata_resource() -> str:
    """Return stable application identity and version metadata.

    Returns:
        JSON-encoded application metadata

    """
    return json.dumps(
        {
            "schema_version": _METADATA_SCHEMA_VERSION,
            "name": _SERVER_NAME,
            "description": _SERVER_DESCRIPTION,
            "version": __version__,
        },
        sort_keys=True,
    )


def _capabilities_resource() -> str:
    """Return the stable MCP capability manifest.

    Returns:
        JSON-encoded capability metadata

    """
    return json.dumps(
        {
            "schema_version": _METADATA_SCHEMA_VERSION,
            "transport": "streamable-http",
            "authentication": "bearer",
            "tools": sorted(tool.__name__ for tool in base.get_mcp_tools()),
            "resources": list(_RESOURCE_URIS),
        },
        sort_keys=True,
    )


def _error_result(code: MCPErrorCode) -> CallToolResult:
    """Build an MCP tool error without exposing server-side details.

    Args:
        code: Safe protocol error code for the failure

    Returns:
        Sanitized MCP tool error result

    """
    return CallToolResult(
        content=[TextContent(text=_MCP_ERROR_MESSAGES[code])],
        is_error=True,
        _meta={"errorCode": int(code)},
    )


class _SafeToolErrors:
    """Sanitize errors returned by database-backed MCP tools."""

    def __init__(self, tool_names: frozenset[str]) -> None:
        """Initialize the middleware.

        Args:
            tool_names: Names of tools registered with the server

        """
        self._tool_names = tool_names

    async def __call__(
        self,
        ctx: ServerRequestContext[Any, Any],
        call_next: CallNext,
    ) -> HandlerResult:
        """Call the next handler and sanitize MCP tool failures.

        Args:
            ctx: Current MCP request context
            call_next: Remaining server middleware and request handler

        Returns:
            MCP handler result with safe tool errors

        """
        if ctx.method != _CALL_TOOL_METHOD:
            return await call_next(ctx)

        tool_name = ctx.params.get("name") if ctx.params is not None else None
        if isinstance(tool_name, str) and tool_name not in self._tool_names:
            return _error_result(MCPErrorCode.METHOD_NOT_FOUND)
        try:
            result = await call_next(ctx)
        except MCPError as error:
            try:
                code = MCPErrorCode(error.code)
            except ValueError:
                code = MCPErrorCode.INTERNAL_ERROR
            return _error_result(code)
        # NOTE: Unexpected handler failures must not expose server details.
        except Exception:
            _LOGGER.exception("Unexpected MCP tool handler failure")
            return _error_result(MCPErrorCode.INTERNAL_ERROR)

        # NOTE: Registered tools translate argument validation failures into an
        # error result, so sanitize that result after the public handler runs.
        if isinstance(result, dict) and result.get("isError") is True:
            safe_result = _error_result(MCPErrorCode.INVALID_PARAMS).model_dump(
                by_alias=True,
                mode="json",
                exclude_none=True,
            )
            if "resultType" in result:
                safe_result["resultType"] = result["resultType"]
            result_meta = result.get("_meta")
            if isinstance(result_meta, dict):
                safe_result["_meta"] = {
                    **result_meta,
                    **safe_result["_meta"],
                }
            return safe_result
        return result


class MCPMetrics(NamedTuple):
    """Prometheus metrics recorded for MCP tools."""

    call_count: prometheus_client.Counter
    duration: prometheus_client.Histogram


_MCP_CALL_SUCCESS = "success"
_MCP_CALL_ERROR = "error"
_MCP_ERROR_NONE = "none"
_MCP_ERROR_INTERNAL = "internal"


_METRICS: dict[prometheus_client.CollectorRegistry, MCPMetrics] = {}


def _load_tools() -> None:
    """Import MCP controller modules into the central tool registry."""
    modules = sorted(
        pkgutil.walk_packages(
            controllers.__path__,
            f"{controllers.__name__}.",
        ),
        key=lambda module: module.name,
    )
    for module in modules:
        if module.name.rpartition(".")[2] == "mcp":
            importlib.import_module(module.name)


_load_tools()


def create_server(
    registry: prometheus_client.CollectorRegistry,
    database: Database,
) -> MCPServer:
    """Create an MCP server for a Flask HTMX Template database.

    Args:
        registry: Prometheus registry shared with the web application
        database: Database to expose through MCP

    Returns:
        MCP server with template tools

    """
    tool_names = frozenset(tool.__name__ for tool in base.get_mcp_tools())
    server = MCPServer(
        _SERVER_NAME,
        description=_SERVER_DESCRIPTION,
        version=__version__,
        middleware=[_SafeToolErrors(tool_names)],
    )

    server.resource(
        METADATA_RESOURCE_URI,
        name="server_metadata",
        title="Server metadata",
        description="Stable application identity and version metadata.",
        mime_type="application/json",
    )(_metadata_resource)
    server.resource(
        CAPABILITIES_RESOURCE_URI,
        name="server_capabilities",
        title="Server capabilities",
        description=(
            "Stable MCP transport, authentication, tool, and resource metadata."
        ),
        mime_type="application/json",
    )(_capabilities_resource)

    for tool in base.get_mcp_tools():
        bound_tool = _bind_database(tool, database, _get_metrics(registry))
        server.add_tool(
            bound_tool,
            description=tool.mcp_description,
            annotations=tool.mcp_annotations,
            structured_output=True,
        )

    return server


def _get_metrics(registry: prometheus_client.CollectorRegistry) -> MCPMetrics:
    """Get the MCP metrics registered with a Prometheus registry.

    Args:
        registry: Prometheus registry shared with the web application

    Returns:
        MCP tool metrics for the registry

    """
    if registry not in _METRICS:
        _METRICS[registry] = MCPMetrics(
            prometheus_client.Counter(
                "flask_htmx_template_mcp_tool_calls",
                "Number of MCP tool calls.",
                ["tool", "status", "error_code"],
                registry=registry,
            ),
            prometheus_client.Histogram(
                "flask_htmx_template_mcp_tool_duration_seconds",
                "Duration of MCP tool calls in seconds.",
                ["tool", "status", "error_code"],
                registry=registry,
            ),
        )
    return _METRICS[registry]


def _bind_database(
    tool: base.MCPTool[base.MCPResult_co],
    database: Database,
    metrics: MCPMetrics,
) -> Callable[..., base.MCPResult_co]:
    """Bind an MCP tool to the server's database.

    Args:
        tool: Database-dependent MCP tool
        database: Database to provide to the tool
        metrics: Prometheus metrics for the tool call

    Returns:
        MCP tool function without its database parameter

    """

    @functools.wraps(tool)
    def bound_tool(*args: object, **kwargs: object) -> base.MCPResult_co:
        """Call the MCP tool with its bound database.

        Returns:
            MCP tool result

        Raises:
            MCPError: If the tool fails during execution

        """
        started_at = time.perf_counter()
        try:
            result = tool(database, *args, **kwargs)
        except Exception as error:
            _LOGGER.exception("MCP tool %s failed", tool.__name__)
            _record_metrics(
                metrics,
                tool.__name__,
                _MCP_CALL_ERROR,
                _MCP_ERROR_INTERNAL,
                time.perf_counter() - started_at,
            )
            raise MCPError(
                code=MCPErrorCode.INTERNAL_ERROR,
                message=_MCP_ERROR_MESSAGES[MCPErrorCode.INTERNAL_ERROR],
            ) from error

        _record_metrics(
            metrics,
            tool.__name__,
            _MCP_CALL_SUCCESS,
            _MCP_ERROR_NONE,
            time.perf_counter() - started_at,
        )
        return result

    # NOTE: The explicit signature hides the TYPE_CHECKING-only Database type while
    # preserving typed tool arguments for MCP SDK schema generation.
    bound_tool.__dict__.pop("__wrapped__", None)
    bound_tool.__dict__["__signature__"] = tool.mcp_signature
    return bound_tool


def _record_metrics(
    metrics: MCPMetrics,
    tool_name: str,
    status: str,
    error_code: str,
    duration_seconds: float,
) -> None:
    """Record the outcome and duration of one MCP tool call.

    Args:
        metrics: Prometheus metrics for MCP tool calls
        tool_name: MCP tool name
        status: Safe success or error status label
        error_code: Safe error code label
        duration_seconds: Elapsed tool execution time in seconds

    """
    labels = {
        "tool": tool_name,
        "status": status,
        "error_code": error_code,
    }
    metrics.call_count.labels(**labels).inc()
    metrics.duration.labels(**labels).observe(duration_seconds)
