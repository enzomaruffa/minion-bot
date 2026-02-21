"""MCP server lifecycle manager for Playwright, Beads, and user-configured servers."""

import logging

from agno.tools.mcp import MCPTools

from src.config import settings

logger = logging.getLogger(__name__)

_mcp_connections: list[MCPTools] = []


async def init_mcp_servers() -> list[MCPTools]:
    """Start and connect to all configured MCP servers."""
    servers: list[MCPTools] = []

    # Playwright MCP (browser automation)
    try:
        playwright = MCPTools(command="npx @playwright/mcp@latest --headless")
        await playwright.initialize()
        servers.append(playwright)
        logger.info("Playwright MCP server connected")
    except Exception as e:
        logger.warning(f"Failed to start Playwright MCP: {e}")

    # Beads MCP (task tracking) — use uvx to run from PyPI
    try:
        beads = MCPTools(command="uvx beads-mcp")
        await beads.initialize()
        servers.append(beads)
        logger.info("Beads MCP server connected")
    except Exception as e:
        logger.warning(f"Failed to start Beads MCP (fallback CLI tools available): {e}")

    # Additional user-configured MCP servers
    for cmd in settings.mcp_server_commands:
        try:
            mcp = MCPTools(command=cmd)
            await mcp.initialize()
            servers.append(mcp)
            logger.info(f"Custom MCP server connected: {cmd}")
        except Exception as e:
            logger.warning(f"Failed to start MCP server '{cmd}': {e}")

    _mcp_connections.extend(servers)
    return servers


async def close_mcp_servers() -> None:
    """Shutdown all MCP connections."""
    for mcp in _mcp_connections:
        try:
            await mcp.close()
        except Exception as e:
            logger.warning(f"Error closing MCP connection: {e}")
    _mcp_connections.clear()
    logger.info("All MCP servers closed")
