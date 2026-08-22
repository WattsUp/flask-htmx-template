"""Flask HTMX Template Model Context Protocol server."""

from __future__ import annotations

from typing import NamedTuple, TYPE_CHECKING

import prometheus_client
from mcp.server.mcpserver import MCPServer

from flask_htmx_template.controllers.items import mcp as items_mcp
from flask_htmx_template.version import __version__

if TYPE_CHECKING:
    from collections.abc import Callable

    from flask_htmx_template.controllers import base
    from flask_htmx_template.database import Database


class MCPMetrics(NamedTuple):
    """Prometheus metrics recorded for MCP tools."""

    call_count: prometheus_client.Counter
    duration: prometheus_client.Histogram


_METRICS: dict[prometheus_client.CollectorRegistry, MCPMetrics] = {}

_TOOLS = [*items_mcp.TOOLS]


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
    server = MCPServer(
        "Flask HTMX Template",
        description="Read-only item information from Flask HTMX Template.",
        version=__version__,
    )

    for tool in _TOOLS:
        bound_tool = _bind_database(tool, database, _get_metrics(registry))
        server.add_tool(
            bound_tool,
            description=tool.mcp_description,
            annotations=tool.mcp_annotations,
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
                ["tool"],
                registry=registry,
            ),
            prometheus_client.Histogram(
                "flask_htmx_template_mcp_tool_duration_seconds",
                "Duration of MCP tool calls in seconds.",
                ["tool"],
                registry=registry,
            ),
        )
    return _METRICS[registry]


def _bind_database(
    tool: base.MCPTool,
    database: Database,
    metrics: MCPMetrics,
) -> Callable[[], str]:
    """Bind an MCP tool to the server's database.

    Args:
        tool: Database-dependent MCP tool
        database: Database to provide to the tool
        metrics: Prometheus metrics for the tool call

    Returns:
        Parameterless MCP tool function

    """

    def bound_tool() -> str:
        """Call the MCP tool with its bound database.

        Returns:
            MCP tool result

        """
        metrics.call_count.labels(tool=tool.__name__).inc()
        with metrics.duration.labels(tool=tool.__name__).time():
            return tool(database)

    bound_tool.__name__ = tool.__name__
    return bound_tool
