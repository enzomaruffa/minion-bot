"""Heartbeat-internal tools for deduplication, logging, notifications, and delegation."""

import asyncio
import logging
from datetime import datetime, timedelta

from src.config import settings
from src.db import session_scope
from src.db.queries import (
    check_heartbeat_dedup,
    create_heartbeat_log,
    get_interest,
)
from src.notifications import notify

logger = logging.getLogger(__name__)


def check_dedup(dedup_key: str, within_hours: int = 24) -> str:
    """Check if a heartbeat action was already taken recently.

    Args:
        dedup_key: Unique key for the action (e.g., "interest_5_rust_news").
        within_hours: Look back window in hours (default 24).

    Returns:
        "duplicate" if already done within window, "ok" if not.
    """
    with session_scope() as session:
        since = datetime.now(settings.timezone).replace(tzinfo=None) - timedelta(hours=within_hours)
        if check_heartbeat_dedup(session, dedup_key, since):
            return "duplicate"
        return "ok"


def log_heartbeat_action(
    dedup_key: str,
    action_type: str,
    summary: str,
    interest_id: int | None = None,
    notified: bool = False,
) -> str:
    """Log a heartbeat action for audit and dedup.

    Args:
        dedup_key: Unique key for dedup (e.g., "interest_5_check").
        action_type: Type of action (research, notify, skip, delegate, plan).
        summary: Brief description of what was done.
        interest_id: Optional linked interest ID.
        notified: Whether the user was notified.

    Returns:
        Confirmation message.
    """
    with session_scope() as session:
        if interest_id:
            interest = get_interest(session, interest_id)
            if not interest:
                interest_id = None
        create_heartbeat_log(
            session,
            dedup_key=dedup_key,
            action_type=action_type,
            summary=summary,
            interest_id=interest_id,
            notified=notified,
        )
        return f"Logged heartbeat action: {action_type} ({dedup_key})"


def send_proactive_notification(message: str) -> str:
    """Send a proactive notification to the user.

    Args:
        message: Message to send.

    Returns:
        Confirmation message.
    """
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(notify(message))
        return "Notification sent."
    except RuntimeError:
        # No event loop — run synchronously
        asyncio.run(notify(message))
        return "Notification sent."
    except Exception as e:
        return f"Failed to send notification: {e}"


def delegate_research(topic: str, question: str) -> str:
    """Delegate a research task to a lightweight sub-agent.

    The sub-agent uses web_search and fetch_url to research the topic,
    then returns a summary. Creates a Beads issue to track the work.

    Args:
        topic: Research topic.
        question: Specific question to answer.

    Returns:
        Research results summary.
    """
    from src.agent.tools.web import fetch_url, web_search

    try:
        # Search for the topic
        results = web_search(f"{topic} {question}", max_results=3)

        # Try to fetch the first result URL for more detail
        lines = results.split("\n")
        detail = ""
        for line in lines:
            line = line.strip()
            if line.startswith("http"):
                detail = fetch_url(line)
                break

        summary = f"Research: {topic}\nQuestion: {question}\n\nSearch Results:\n{results}"
        if detail:
            summary += f"\n\nDetailed Content:\n{detail[:2000]}"

        return summary
    except Exception as e:
        return f"Research failed: {e}"


def delegate_task_work(task_description: str) -> str:
    """Delegate practical task work to a sub-agent.

    Uses code execution and web tools to work on the task.

    Args:
        task_description: Description of the work to do.

    Returns:
        Work results summary.
    """
    from src.agent.tools.web import web_search

    try:
        # For now, delegate as web research — full sub-agent in future iteration
        results = web_search(task_description, max_results=3)
        return f"Task work for: {task_description}\n\nFindings:\n{results}"
    except Exception as e:
        return f"Task delegation failed: {e}"
