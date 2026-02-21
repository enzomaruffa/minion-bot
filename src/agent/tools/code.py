"""Code and shell execution tools — runs directly on host (Docker container)."""

import logging
import subprocess
import tempfile
from pathlib import Path

from src.config import settings

logger = logging.getLogger(__name__)

_MAX_OUTPUT = 4000


def run_python_code(code: str, packages: str | None = None) -> str:
    """Execute Python code on the host. Returns stdout+stderr.

    Args:
        code: Python code to execute.
        packages: Optional space-separated pip packages to install first.

    Returns:
        Combined stdout and stderr output, truncated to 4000 chars.
    """
    timeout = settings.code_execution_timeout

    # Install packages if requested
    if packages:
        try:
            subprocess.run(
                ["pip", "install"] + packages.split(),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return f"Package installation timed out after {timeout}s"
        except Exception as e:
            return f"Package installation failed: {e}"

    # Write code to temp file and execute
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        tmp_path = f.name

    try:
        result = subprocess.run(
            ["python", tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr}"
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"
    except subprocess.TimeoutExpired:
        output = f"Execution timed out after {timeout}s"
    except Exception as e:
        output = f"Execution failed: {e}"
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    if len(output) > _MAX_OUTPUT:
        output = output[:_MAX_OUTPUT] + f"\n... (truncated, {len(output)} total chars)"
    return output or "(no output)"


def run_shell_command(command: str) -> str:
    """Execute a shell command on the host. Returns stdout+stderr.

    Args:
        command: Shell command to execute.

    Returns:
        Combined stdout and stderr output, truncated to 4000 chars.
    """
    timeout = settings.code_execution_timeout

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr]\n{result.stderr}"
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"
    except subprocess.TimeoutExpired:
        output = f"Execution timed out after {timeout}s"
    except Exception as e:
        output = f"Execution failed: {e}"

    if len(output) > _MAX_OUTPUT:
        output = output[:_MAX_OUTPUT] + f"\n... (truncated, {len(output)} total chars)"
    return output or "(no output)"
