"""Notification dispatcher — decouples scheduler jobs from Telegram."""

import logging
from collections.abc import Callable, Coroutine
from typing import Any

logger = logging.getLogger(__name__)

NotificationHandler = Callable[[str, str], Coroutine[Any, Any, None]]

_handlers: list[NotificationHandler] = []


def register_handler(fn: NotificationHandler) -> None:
    """Register a notification handler (e.g. Telegram send_message)."""
    _handlers.append(fn)
    logger.info(f"Registered notification handler: {fn.__qualname__}")


async def notify(message: str, parse_mode: str = "HTML") -> None:
    """Send a notification through all registered handlers."""
    for handler in _handlers:
        try:
            await handler(message, parse_mode)
        except Exception:
            logger.exception(f"Notification handler {handler.__qualname__} failed")
