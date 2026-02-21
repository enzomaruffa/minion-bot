"""Proactive heartbeat engine — autonomous agent that runs on a schedule."""

import logging
from datetime import datetime

from agno.agent import Agent
from agno.models.openai import OpenAIChat

from src.agent.agent import get_db, tool_logger_hook
from src.agent.tools import (
    beads_create,
    beads_list,
    beads_ready,
    fetch_url,
    get_agenda,
    get_current_datetime,
    get_overdue_tasks,
    get_weather,
    list_interests,
    list_tasks,
    run_python_code,
    run_shell_command,
    show_mood_history,
    web_search,
)
from src.agent.tools.heartbeat_tools import (
    check_dedup,
    delegate_research,
    delegate_task_work,
    log_heartbeat_action,
    send_proactive_notification,
)
from src.config import settings
from src.db import session_scope
from src.db.models import TaskStatus
from src.db.queries import (
    list_due_interests,
    list_recent_heartbeat_logs,
    list_tasks_by_status,
    list_tasks_due_soon,
    mark_interest_checked,
)
from src.db.queries import (
    list_overdue_tasks as db_list_overdue,
)

logger = logging.getLogger(__name__)

HEARTBEAT_PROMPT = """You are Minion in PROACTIVE mode. The user did NOT message you.
Think about what would GENUINELY help the user right now.

CURRENT STATE:
{context}

INTERESTS TO CHECK:
{interests}

RECENT HEARTBEAT ACTIONS (for dedup):
{recent_actions}

WHAT YOU CAN DO:
1. RESEARCH interests (web_search, fetch_url) — find news, updates, prices
2. HELP WITH TASKS — compare prices for shopping items, research for tasks, draft notes
3. PLAN — suggest scheduling, break down complex tasks, suggest next steps
4. NOTIFY — send concise, actionable messages to the user via send_proactive_notification
5. DELEGATE — use delegate_research/delegate_task_work for deep dives
6. TRACK WORK — use beads_create/beads_list to track sub-tasks

RULES:
- Max {max_notifications} notifications per run
- ALWAYS check_dedup before notifying (skip if sent within interval)
- High-priority interests first
- Be concise — user is busy
- If shopping list has items, consider searching for prices/availability
- If tasks have deadlines approaching, consider what preparatory work you can do
- Log EVERY action with log_heartbeat_action (even "skip")
- Do NOT notify unless you have something genuinely useful to share
"""


def _build_context() -> str:
    """Build current state context for the heartbeat agent."""
    lines = []

    now = datetime.now(settings.timezone)
    lines.append(f"Current time: {now.strftime('%A, %B %d, %Y at %H:%M')}")

    # Agenda
    try:
        agenda = get_agenda()
        lines.append(f"\nToday's Agenda:\n{agenda}")
    except Exception as e:
        lines.append(f"\nAgenda unavailable: {e}")

    # Weather
    try:
        weather = get_weather()
        lines.append(f"\nWeather: {weather}")
    except Exception:
        pass

    # Overdue tasks
    with session_scope() as session:
        now_naive = now.replace(tzinfo=None)
        overdue = db_list_overdue(session, now_naive)
        if overdue:
            lines.append(f"\nOverdue tasks ({len(overdue)}):")
            for t in overdue[:5]:
                days = (now_naive - t.due_date).days
                lines.append(f"  #{t.id}: {t.title} ({days}d overdue)")

        # Due soon
        due_soon = list_tasks_due_soon(session, now_naive, within_hours=24)
        if due_soon:
            lines.append(f"\nDue within 24h ({len(due_soon)}):")
            for t in due_soon[:5]:
                hours = (t.due_date - now_naive).total_seconds() / 3600
                lines.append(f"  #{t.id}: {t.title} (in {hours:.0f}h)")

        # In-progress tasks
        in_progress = list_tasks_by_status(session, TaskStatus.IN_PROGRESS)
        if in_progress:
            lines.append(f"\nIn progress ({len(in_progress)}):")
            for t in in_progress[:5]:
                lines.append(f"  #{t.id}: {t.title}")

    # Recent mood
    try:
        mood = show_mood_history(days=3)
        if mood and "No mood" not in mood:
            lines.append(f"\nRecent mood:\n{mood}")
    except Exception:
        pass

    return "\n".join(lines)


def _build_interests_context() -> str:
    """Build interests context — which are due for checking."""
    with session_scope() as session:
        now = datetime.now(settings.timezone).replace(tzinfo=None)
        due = list_due_interests(session, now)
        if not due:
            return "No interests due for checking."

        lines = []
        for i in due:
            checked = (
                f"last checked {i.last_checked_at.strftime('%m/%d %H:%M')}" if i.last_checked_at else "never checked"
            )
            lines.append(f"P{i.priority} #{i.id}: {i.topic} ({checked}, every {i.check_interval_hours}h)")
            if i.description:
                lines.append(f"   {i.description}")
        return "\n".join(lines)


def _build_recent_actions() -> str:
    """Build recent heartbeat actions for dedup context."""
    with session_scope() as session:
        logs = list_recent_heartbeat_logs(session, limit=20)
        if not logs:
            return "No recent actions."

        lines = []
        for log in logs:
            ts = log.created_at.strftime("%m/%d %H:%M") if log.created_at else "?"
            notified = " [notified]" if log.notified else ""
            lines.append(f"[{ts}] {log.action_type}: {log.summary}{notified}")
        return "\n".join(lines)


def _create_heartbeat_agent() -> Agent:
    """Create a lightweight agent for heartbeat runs."""
    return Agent(
        model=OpenAIChat(
            id=settings.heartbeat_model,
            api_key=settings.openai_api_key,
        ),
        tools=[
            # Context tools (read-only)
            get_current_datetime,
            get_agenda,
            get_overdue_tasks,
            list_tasks,
            get_weather,
            show_mood_history,
            list_interests,
            # Web tools
            web_search,
            fetch_url,
            # Code execution
            run_python_code,
            run_shell_command,
            # Heartbeat-specific tools
            check_dedup,
            log_heartbeat_action,
            send_proactive_notification,
            delegate_research,
            delegate_task_work,
            # Beads
            beads_create,
            beads_list,
            beads_ready,
        ],
        markdown=True,
        tool_hooks=[tool_logger_hook],
        db=get_db(),
        add_history_to_context=True,
        num_history_runs=3,
        add_datetime_to_context=True,
    )


async def run_heartbeat() -> None:
    """Run a single heartbeat cycle."""
    if not settings.heartbeat_enabled:
        return

    logger.info("Running heartbeat cycle")

    try:
        context = _build_context()
        interests = _build_interests_context()
        recent_actions = _build_recent_actions()

        prompt = HEARTBEAT_PROMPT.format(
            context=context,
            interests=interests,
            recent_actions=recent_actions,
            max_notifications=settings.heartbeat_max_notifications,
        )

        agent = _create_heartbeat_agent()

        import asyncio

        response = await asyncio.to_thread(
            agent.run,
            prompt,
            user_id=str(settings.telegram_user_id),
            session_id="heartbeat",
        )

        # Mark checked interests as checked
        with session_scope() as session:
            now = datetime.now(settings.timezone).replace(tzinfo=None)
            due = list_due_interests(session, now)
            for interest in due:
                mark_interest_checked(session, interest.id, now)

        logger.info(f"Heartbeat complete: {response.content[:100] if response.content else '(no output)'}...")

    except Exception as e:
        logger.exception(f"Heartbeat failed: {e}")
