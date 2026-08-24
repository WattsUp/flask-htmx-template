"""Flask HTMX Template Model Context Protocol server."""

from __future__ import annotations

import functools
import importlib
import logging
import pkgutil
import time
from enum import IntEnum
from typing import NamedTuple, TYPE_CHECKING

import prometheus_client
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.context import Context
from mcp.server.mcpserver.exceptions import ToolError
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

    from mcp.server.context import LifespanContextT, ServerRequestContext
    from mcp_types import CallToolRequestParams, InputRequiredResult

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


class _SafeMCPServer(MCPServer):
    """MCP server that sanitizes errors returned by database-backed tools."""

    async def _handle_call_tool(
        self,
        ctx: ServerRequestContext[LifespanContextT],
        params: CallToolRequestParams,
    ) -> CallToolResult | InputRequiredResult:
        """Call a tool and return a safe, protocol-compatible error result.

        Returns:
            MCP tool result or input request

        """
        context = Context(
            request_context=ctx,
            mcp_server=self,
            input_params=params,
            subscriptions=self._subscriptions,
        )
        if not any(tool.name == params.name for tool in await self.list_tools()):
            return _error_result(MCPErrorCode.METHOD_NOT_FOUND)
        try:
            result = await self.call_tool(params.name, params.arguments or {}, context)
        except MCPError as error:
            try:
                code = MCPErrorCode(error.code)
            except ValueError:
                code = MCPErrorCode.INTERNAL_ERROR
            return _error_result(code)
        except ToolError:
            return _error_result(MCPErrorCode.INVALID_PARAMS)
        # NOTE: Unexpected handler failures must not expose server details.
        except Exception:
            _LOGGER.exception("Unexpected MCP tool handler failure")
            return _error_result(MCPErrorCode.INTERNAL_ERROR)
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
    server = _SafeMCPServer(
        "Flask HTMX Template",
        description="Read-only item information from Flask HTMX Template.",
        version=__version__,
    )

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
