"""Beads CLI fallback tools — for when MCP isn't running or for synchronous contexts."""

import logging
import subprocess

logger = logging.getLogger(__name__)


def _run_bd(args: list[str]) -> str:
    """Run a bd CLI command and return output."""
    try:
        result = subprocess.run(
            ["bd"] + args,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout.strip()
        if result.stderr:
            output += f"\n{result.stderr.strip()}"
        return output or "(no output)"
    except FileNotFoundError:
        return "Error: bd CLI not found. Install beads: pip install beads"
    except subprocess.TimeoutExpired:
        return "Error: bd command timed out"
    except Exception as e:
        return f"Error running bd: {e}"


def beads_create(title: str, description: str | None = None, priority: int = 1) -> str:
    """Create a Beads issue for tracking a work item.

    Args:
        title: Issue title.
        description: Optional description.
        priority: 1 (high) to 3 (low).

    Returns:
        Creation confirmation with issue ID.
    """
    args = ["create", title, "--priority", str(priority)]
    if description:
        args.extend(["--description", description])
    return _run_bd(args)


def beads_list(status: str | None = None) -> str:
    """List Beads issues, optionally filtered by status.

    Args:
        status: Filter by status (open, in_progress, closed).

    Returns:
        Formatted list of issues.
    """
    args = ["list"]
    if status:
        args.extend(["--status", status])
    return _run_bd(args)


def beads_ready() -> str:
    """List unblocked Beads issues ready to work on.

    Returns:
        List of issues with no blocking dependencies.
    """
    return _run_bd(["ready"])
