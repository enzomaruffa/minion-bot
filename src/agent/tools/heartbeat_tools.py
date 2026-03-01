"""Heartbeat-internal tools for deduplication, logging, notifications, and delegation."""

import asyncio
import logging
import re
from datetime import datetime, timedelta

from src.config import settings
from src.db import session_scope
from src.db.queries import (
    check_heartbeat_dedup,
    create_heartbeat_log,
    get_interest,
    get_user_profile,
    log_agent_event,
)
from src.notifications import notify

logger = logging.getLogger(__name__)


def _is_quiet_hours() -> bool:
    """Check if current time is within quiet hours (before work_start_hour)."""
    now = datetime.now(settings.timezone)
    with session_scope() as session:
        profile = get_user_profile(session)
        wake_hour = profile.work_start_hour if profile and profile.work_start_hour is not None else 9
    return now.hour < wake_hour


def _extract_task_ids(message: str) -> list[int]:
    """Extract task IDs from #N patterns in a message."""
    return [int(m) for m in re.findall(r"#(\d+)", message)]


def _all_tasks_recently_nudged(task_ids: list[int], within_hours: int = 24) -> bool:
    """Check if ALL referenced tasks were already nudged within the window."""
    if not task_ids:
        return False
    since = datetime.now(settings.timezone).replace(tzinfo=None) - timedelta(hours=within_hours)
    with session_scope() as session:
        for tid in task_ids:
            if not check_heartbeat_dedup(session, f"task_nudge_{tid}", since):
                return False
    return True


def _auto_log_task_nudges(task_ids: list[int]) -> None:
    """Log task_nudge entries for dedup tracking."""
    with session_scope() as session:
        for tid in task_ids:
            create_heartbeat_log(
                session,
                dedup_key=f"task_nudge_{tid}",
                action_type="notify",
                summary=f"Nudged user about task #{tid}",
                notified=True,
            )


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

    # Also log to shared event bus
    try:
        metadata = {"dedup_key": dedup_key}
        if interest_id:
            metadata["interest_id"] = interest_id
        with session_scope() as session:
            log_agent_event(
                session,
                source="heartbeat",
                event_type=action_type,
                summary=summary,
                metadata=metadata,
            )
    except Exception:
        logger.debug("Failed to log heartbeat action to event bus", exc_info=True)

    return f"Logged heartbeat action: {action_type} ({dedup_key})"


def send_proactive_notification(message: str) -> str:
    """Send a proactive notification to the user.

    Args:
        message: Message to send.

    Returns:
        Confirmation message.
    """
    # Gate: quiet hours
    if _is_quiet_hours():
        logger.info("Notification suppressed — quiet hours")
        return "Notification suppressed — quiet hours. Focus on research and prep work instead."

    # Gate: task nudge dedup
    task_ids = _extract_task_ids(message)
    if task_ids and _all_tasks_recently_nudged(task_ids):
        logger.info(f"Suppressed duplicate task nudge for tasks {task_ids}")
        return f"Suppressed duplicate task nudge — tasks {task_ids} already nudged in last 24h."

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(notify(message))
    except RuntimeError:
        asyncio.run(notify(message))
    except Exception as e:
        return f"Failed to send notification: {e}"

    # Auto-log task nudges for future dedup
    if task_ids:
        _auto_log_task_nudges(task_ids)

    return "Notification sent."


def task_nudge_dedup_key(task_id: int) -> str:
    """Get the standard dedup key for nudging a task. Use this with check_dedup before notifying about overdue tasks.

    Args:
        task_id: The task ID to generate a dedup key for.

    Returns:
        The dedup key string in format "task_nudge_{id}".
    """
    return f"task_nudge_{task_id}"


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
