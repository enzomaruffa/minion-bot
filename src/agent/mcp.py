"""MCP server lifecycle for Agno agents.

Connects to external MCP servers (Playwright, Beads, user-configured) and
returns MCPTools instances that can be passed to Agent(tools=[...]).
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any

from agno.tools.mcp import MCPTools
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from src.config import settings

logger = logging.getLogger(__name__)

# Active MCP connections — kept alive for the process lifetime
_active_connections: list[tuple[MCPTools, Any, Any]] = []


def _get_server_configs() -> dict[str, StdioServerParameters]:
    """Return MCP server configs for external servers."""
    servers: dict[str, StdioServerParameters] = {}

    servers["playwright"] = StdioServerParameters(
        command="npx",
        args=["@playwright/mcp@latest", "--headless"],
    )

    servers["beads"] = StdioServerParameters(
        command="uvx",
        args=["beads-mcp"],
    )

    for i, cmd in enumerate(settings.mcp_server_commands):
        parts = cmd.split()
        if parts:
            servers[f"custom_{i}"] = StdioServerParameters(
                command=parts[0],
                args=parts[1:],
            )

    return servers


async def init_mcp_servers() -> list[MCPTools]:
    """Connect to all configured MCP servers and return MCPTools instances.

    Each MCPTools instance can be passed directly to Agent(tools=[...]).
    """
    configs = _get_server_configs()
    mcp_tools_list: list[MCPTools] = []

    for name, params in configs.items():
        try:
            # stdio_client returns an async context manager that gives (read, write)
            transport = stdio_client(params)
            streams = await transport.__aenter__()
            read_stream, write_stream = streams

            session = ClientSession(read_stream, write_stream)
            await session.__aenter__()

            mcp_tools = MCPTools(session=session)
            await mcp_tools.initialize()

            _active_connections.append((mcp_tools, session, transport))
            mcp_tools_list.append(mcp_tools)
            logger.info(f"MCP server '{name}' connected")
        except Exception as e:
            logger.warning(f"MCP server '{name}' failed to connect: {e}")

    logger.info(f"MCP init complete: {len(mcp_tools_list)}/{len(configs)} servers connected")
    return mcp_tools_list


async def close_mcp_servers() -> None:
    """Gracefully close all MCP connections."""
    for _tools, session, transport in _active_connections:
        with contextlib.suppress(Exception):
            await session.__aexit__(None, None, None)
        with contextlib.suppress(Exception):
            await transport.__aexit__(None, None, None)

    count = len(_active_connections)
    _active_connections.clear()
    logger.info(f"Closed {count} MCP connections")
