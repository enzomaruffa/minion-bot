"""Notification dispatcher — decouples scheduler jobs from Telegram."""

import logging
from collections.abc import Callable, Coroutine
from typing import Any

from src.db import session_scope
from src.db.queries import log_agent_event

logger = logging.getLogger(__name__)

NotificationHandler = Callable[[str, str], Coroutine[Any, Any, None]]

_handlers: list[NotificationHandler] = []


def register_handler(fn: NotificationHandler) -> None:
    """Register a notification handler (e.g. Telegram send_message)."""
    _handlers.append(fn)
    logger.info(f"Registered notification handler: {getattr(fn, '__qualname__', repr(fn))}")


async def notify(message: str, parse_mode: str = "HTML") -> None:
    """Send a notification through all registered handlers."""
    for handler in _handlers:
        try:
            await handler(message, parse_mode)
        except Exception:
            logger.exception(f"Notification handler {getattr(handler, '__qualname__', repr(handler))} failed")

    # Log to event bus
    try:
        with session_scope() as session:
            log_agent_event(session, "notification", "notification_sent", message[:500])
    except Exception:
        logger.debug("Failed to log notification to event bus", exc_info=True)
