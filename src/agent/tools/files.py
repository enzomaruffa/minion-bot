"""File sending tool — sends files to the user via Telegram."""

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB (Telegram limit)


def send_file(file_path: str, caption: str = "") -> str:
    """Send a file from disk to the user via Telegram.

    Args:
        file_path: Absolute path to the file on disk.
        caption: Optional caption for the file.

    Returns:
        Confirmation message or error description.
    """
    path = Path(file_path)

    if not path.exists():
        return f"File not found: {file_path}"
    if not path.is_file():
        return f"Not a file: {file_path}"
    if path.stat().st_size > _MAX_FILE_SIZE:
        size_mb = path.stat().st_size / (1024 * 1024)
        return f"File too large ({size_mb:.1f} MB). Telegram limit is 50 MB."

    try:
        from src.notifications import notify_file

        asyncio.run(notify_file(file_path, caption))
    except Exception as e:
        logger.exception("Failed to send file")
        return f"Failed to send file: {e}"

    return f"Sent file: {path.name}" + (f" with caption: {caption}" if caption else "")
