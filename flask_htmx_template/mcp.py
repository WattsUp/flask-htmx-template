"""Flask HTMX Template Model Context Protocol server."""

from __future__ import annotations

import functools
import importlib
import pkgutil
from typing import NamedTuple, TYPE_CHECKING

import prometheus_client
from mcp.server.mcpserver import MCPServer

from flask_htmx_template import controllers
from flask_htmx_template.controllers import base
from flask_htmx_template.version import __version__

if TYPE_CHECKING:
    from collections.abc import Callable

    from flask_htmx_template.database import Database


class MCPMetrics(NamedTuple):
    """Prometheus metrics recorded for MCP tools."""

    call_count: prometheus_client.Counter
    duration: prometheus_client.Histogram


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
    server = MCPServer(
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
    tool: base.MCPTool[base.MCPResult_co],
    database: Database,
    metrics: MCPMetrics,
) -> Callable[[], base.MCPResult_co]:
    """Bind an MCP tool to the server's database.

    Args:
        tool: Database-dependent MCP tool
        database: Database to provide to the tool
        metrics: Prometheus metrics for the tool call

    Returns:
        Parameterless MCP tool function

    """

    @functools.wraps(tool)
    def bound_tool() -> base.MCPResult_co:
        """Call the MCP tool with its bound database.

        Returns:
            MCP tool result

        """
        metrics.call_count.labels(tool=tool.__name__).inc()
        with metrics.duration.labels(tool=tool.__name__).time():
            return tool(database)

    # The wrapper has no database argument, so the MCP SDK can inspect its
    # return type without trying to resolve the database's TYPE_CHECKING-only
    # annotation.  ``wraps`` preserves the original metadata for callers; its
    # ``__wrapped__`` link is removed so inspection does not expose the bound
    # database parameter.
    bound_tool.__dict__.pop("__wrapped__", None)
    bound_tool.__annotations__ = {"return": tool.mcp_return_type}
    return bound_tool
