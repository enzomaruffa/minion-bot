"""Proactive heartbeat engine — autonomous agent that runs on a schedule."""

import logging
from datetime import datetime

from src.agent.tools.agenda import get_agenda
from src.agent.tools.mood import show_mood_history
from src.agent.tools.profile import get_weather
from src.config import settings
from src.db import session_scope
from src.db.models import TaskStatus
from src.db.queries import (
    get_active_work,
    get_recent_completed_work,
    get_recent_events,
    get_user_profile,
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

LANGUAGE: Always write in English — never Portuguese or any other language.

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
5. TRACK WORK — use beads_create/beads_list to track sub-tasks

RULES:
- Max {max_notifications} notifications per run
- Daily cap: {daily_cap} total. Already sent today: {daily_notifications_sent}.
  If at or over cap, send NOTHING this run.
- ALWAYS call check_dedup before notifying — if it returns "duplicate",
  call log_heartbeat_action with action_type="skip" and move on. NEVER rephrase and resend.
- RECENT HEARTBEAT ACTIONS above lists what you already sent. If ANY [notified] entry
  in the last 24h covers the same task or topic, SKIP — do not rephrase and resend.
- For overdue task nudges: the ONLY valid dedup key is "task_nudge_{{task_id}}".
  Call task_nudge_dedup_key(task_id) to get it. Never invent ad-hoc keys like "Naomi_gift".
- Only notify if you have NEW information (price found, stock confirmed, date changed)
  — not just because a task is still overdue.
- Prefer actionable help (research, price comparison, prep work) over "this is overdue" reminders
- High-priority interests first
- Be concise — user is busy
- If shopping list has items, consider searching for prices/availability
- If tasks have deadlines approaching, consider what preparatory work you can do
- Log EVERY action with log_heartbeat_action (even "skip")
- Do NOT notify unless you have something genuinely useful to share

7. MEMORY MAINTENANCE — call list_memories() and review for:
   - Duplicates (same fact, different keys) → keep newest, forget_memory the older
   - Contradictions (old preference overridden by recent activity) → save_memory to update
   - Stale facts (dates passed, tasks completed, no longer relevant) → forget_memory
   - Important patterns from recent activity not yet saved → save_memory
   Only do light cleanup each run (max 3 memory ops). Don't obsess over it.

{quiet_hours_note}
"""


def _get_quiet_hours_note() -> str:
    """Return quiet hours note for the heartbeat prompt."""
    from src.agent.tools.heartbeat_tools import _is_quiet_hours

    if not _is_quiet_hours():
        return ""
    with session_scope() as session:
        profile = get_user_profile(session)
        wake_hour = profile.work_start_hour if profile and profile.work_start_hour is not None else 9
    return f"QUIET HOURS ACTIVE — notifications are suppressed until {wake_hour}:00. Focus on research and prep work."


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
                days = (now_naive - t.due_date).days if t.due_date else 0
                lines.append(f"  #{t.id}: {t.title} ({days}d overdue)")

        # Due soon
        due_soon = list_tasks_due_soon(session, now_naive, within_hours=24)
        if due_soon:
            lines.append(f"\nDue within 24h ({len(due_soon)}):")
            for t in due_soon[:5]:
                hours = (t.due_date - now_naive).total_seconds() / 3600 if t.due_date else 0
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

    # Recent event bus activity (user messages, agent responses, notifications)
    try:
        with session_scope() as session:
            events = get_recent_events(session, limit=20, since_hours=24)
            if events:
                lines.append("\nRecent activity (event bus):")
                for e in reversed(events):
                    ts = e.timestamp.strftime("%H:%M") if e.timestamp else "?"
                    lines.append(f"  [{ts} {e.source}] {e.event_type}: {e.summary[:150]}")

            # Active subagent work
            active = get_active_work(session)
            if active:
                lines.append("\nActive subagent work:")
                for w in active:
                    lines.append(f"  {w.agent_name}: {w.description}")

            # Recently completed work
            completed = get_recent_completed_work(session, hours=24)
            if completed:
                lines.append("\nRecently completed work:")
                for w in completed[:5]:
                    result_preview = w.result[:100] if w.result else "(no result)"
                    lines.append(f"  {w.agent_name}: {w.description} -> {result_preview}")
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


HEARTBEAT_TIMEOUT = 300  # 5 minutes — hard cap so a hung tool can't freeze the bot


async def _run_heartbeat_agno(prompt: str) -> str | None:
    """Run a heartbeat cycle using an Agno Agent (with timeout)."""
    import asyncio

    from agno.agent import Agent
    from agno.models.openai import OpenAIChat

    from src.agent.tools import (
        beads_create,
        beads_list,
        beads_ready,
        check_dedup,
        delegate_research,
        delegate_task_work,
        fetch_url,
        forget_memory,
        get_agenda,
        get_current_datetime,
        get_overdue_tasks,
        get_weather,
        list_interests,
        list_memories,
        list_tasks,
        log_heartbeat_action,
        recall_memory,
        run_python_code,
        run_shell_command,
        save_memory,
        send_proactive_notification,
        show_mood_history,
        task_nudge_dedup_key,
        web_search,
    )

    heartbeat_tools = [
        get_current_datetime,
        get_agenda,
        get_overdue_tasks,
        list_tasks,
        get_weather,
        show_mood_history,
        list_interests,
        web_search,
        fetch_url,
        run_python_code,
        run_shell_command,
        beads_create,
        beads_list,
        beads_ready,
        check_dedup,
        log_heartbeat_action,
        send_proactive_notification,
        delegate_research,
        delegate_task_work,
        task_nudge_dedup_key,
        # Memory tools for consolidation
        save_memory,
        recall_memory,
        list_memories,
        forget_memory,
    ]

    agent = Agent(
        name="Heartbeat",
        model=OpenAIChat(id=settings.heartbeat_model, api_key=settings.openai_api_key),
        tools=heartbeat_tools,
        instructions=[prompt],
        telemetry=False,
    )

    async with asyncio.timeout(HEARTBEAT_TIMEOUT):
        response = await agent.arun(prompt)
    return response.content if response and response.content else None


async def run_heartbeat() -> None:
    """Run a single heartbeat cycle."""
    if not settings.heartbeat_enabled:
        return

    logger.info("Running heartbeat cycle")

    try:
        context = _build_context()
        interests = _build_interests_context()
        recent_actions = _build_recent_actions()

        quiet_hours_note = _get_quiet_hours_note()

        # Count notifications already sent in the last 24h for the daily cap
        with session_scope() as session:
            from datetime import UTC, timedelta

            cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=24)
            all_recent = list_recent_heartbeat_logs(session, limit=200)
            daily_notifications_sent = sum(
                1 for log in all_recent if log.notified and log.created_at and log.created_at >= cutoff
            )

        prompt = HEARTBEAT_PROMPT.format(
            context=context,
            interests=interests,
            recent_actions=recent_actions,
            max_notifications=settings.heartbeat_max_notifications,
            daily_cap=settings.heartbeat_daily_cap,
            daily_notifications_sent=daily_notifications_sent,
            quiet_hours_note=quiet_hours_note,
        )

        response_content = await _run_heartbeat_agno(prompt)

        # Mark checked interests as checked
        with session_scope() as session:
            now = datetime.now(settings.timezone).replace(tzinfo=None)
            due = list_due_interests(session, now)
            for interest in due:
                mark_interest_checked(session, interest.id, now)

        logger.info(f"Heartbeat complete: {response_content[:100] if response_content else '(no output)'}...")

    except TimeoutError:
        logger.error(f"Heartbeat timed out after {HEARTBEAT_TIMEOUT}s — skipping this cycle")
    except Exception as e:
        logger.exception(f"Heartbeat failed: {e}")
