import logging
from datetime import datetime, timedelta

from src.agent.tools.agenda import get_agenda
from src.agent.tools.profile import get_weather
from src.config import settings
from src.db import session_scope
from src.db.models import TaskStatus
from src.db.queries import (
    create_next_recurring_instance,
    get_mood_log,
    get_task,
    list_completed_recurring_tasks,
    list_pending_reminders,
    list_tasks_by_status,
    mark_reminder_delivered,
)
from src.notifications import notify
from src.services.reminders import propagate_reminders_to_new_instance

logger = logging.getLogger(__name__)


async def _agent_compose(prompt: str) -> str | None:
    """Run a prompt through the main chat agent and return its response.

    Returns None if the agent call fails (caller should use fallback).
    """
    try:
        from src.agent import chat

        return await chat(prompt, format_hint="telegram")
    except Exception:
        logger.exception("Agent compose failed, using fallback")
        return None


async def morning_summary() -> None:
    """Send the daily morning agenda summary via the main agent."""
    logger.info("Running morning summary job")

    try:
        agenda = get_agenda()

        try:
            weather = get_weather()
        except Exception:
            weather = "(unavailable)"

        prompt = (
            "[SCHEDULED TASK: Morning Summary]\n"
            "Compose a concise morning briefing for the user and send it as a single message.\n"
            "Include the agenda, weather, and any highlights worth noting.\n"
            "Keep it short and friendly.\n\n"
            f"AGENDA:\n{agenda}\n\n"
            f"WEATHER: {weather}"
        )

        response = await _agent_compose(prompt)

        if response:
            await notify(response)
        else:
            # Fallback to hardcoded template
            message = f"Good morning! Here's your agenda for today:\n\n{agenda}"
            await notify(message)

        logger.info("Morning summary sent")
    except Exception as e:
        logger.exception(f"Error sending morning summary: {e}")


async def eod_review() -> None:
    """Send the end-of-day review via the main agent."""
    logger.info("Running EOD review job")

    try:
        with session_scope() as session:
            now = datetime.now(settings.timezone)
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

            # Get tasks completed today
            done_tasks = list_tasks_by_status(session, TaskStatus.DONE)
            completed_today = [
                t for t in done_tasks if t.updated_at and t.updated_at >= today_start.replace(tzinfo=None)
            ]

            # Get incomplete tasks
            todo_tasks = list_tasks_by_status(session, TaskStatus.TODO)
            in_progress = list_tasks_by_status(session, TaskStatus.IN_PROGRESS)

            # Tomorrow's agenda
            tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
            tomorrow_agenda = get_agenda(tomorrow)

            # Mood check
            today_naive = today_start.replace(tzinfo=None)
            mood_today = get_mood_log(session, today_naive)

        # Build raw data for the agent
        data_lines = []

        if completed_today:
            data_lines.append(f"Completed today ({len(completed_today)}):")
            for t in completed_today[:10]:
                data_lines.append(f"  - #{t.id}: {t.title}")
        else:
            data_lines.append("No tasks completed today.")

        data_lines.append(f"\nPending: {len(todo_tasks)} todo, {len(in_progress)} in progress")
        if in_progress:
            for t in in_progress[:5]:
                data_lines.append(f"  - #{t.id}: {t.title}")

        data_lines.append(f"\nTomorrow's agenda:\n{tomorrow_agenda}")

        if not mood_today:
            data_lines.append("\nUser has NOT logged mood today.")

        raw_data = "\n".join(data_lines)

        prompt = (
            "[SCHEDULED TASK: End-of-Day Review]\n"
            "Compose a concise evening review for the user.\n"
            "Summarize what was accomplished, what's still pending, and preview tomorrow.\n"
            "If the user hasn't logged mood today, gently ask how their day was (1-5 scale).\n"
            "Keep it friendly and brief.\n\n"
            f"RAW DATA:\n{raw_data}"
        )

        response = await _agent_compose(prompt)

        if response:
            await notify(response)
        else:
            # Fallback to hardcoded template
            lines = ["Good evening! Here's your daily review:", ""]
            if completed_today:
                lines.append(f"Completed today ({len(completed_today)}):")
                for t in completed_today[:5]:
                    lines.append(f"  - {t.title}")
            else:
                lines.append("No tasks completed today.")
            lines.append("")
            incomplete = len(todo_tasks) + len(in_progress)
            if incomplete > 0:
                lines.append(f"Still pending: {incomplete} task(s)")
            lines.append("")
            lines.append(f"Tomorrow's preview:\n{tomorrow_agenda}")
            if not mood_today:
                lines.append("\nHow was your day? Rate 1-5")
            await notify("\n".join(lines))

        logger.info("EOD review sent")
    except Exception as e:
        logger.exception(f"Error sending EOD review: {e}")


async def deliver_reminders() -> None:
    """Check and deliver due reminders via the main agent."""
    try:
        with session_scope() as session:
            now = datetime.now(settings.timezone).replace(tzinfo=None)
            reminders = list_pending_reminders(session, now)

            if not reminders:
                return

            # Batch all due reminders into one agent call
            reminder_lines = []
            reminder_ids = []
            for r in reminders:
                line = f"- Reminder #{r.id}: {r.message}"
                if r.task_id:
                    task = get_task(session, r.task_id)
                    if task:
                        line += f" (linked to task #{task.id}: {task.title})"
                reminder_lines.append(line)
                reminder_ids.append(r.id)

            raw = "\n".join(reminder_lines)

            prompt = (
                "[SCHEDULED TASK: Deliver Reminders]\n"
                f"The following {len(reminders)} reminder(s) are due NOW. "
                "Compose a single message delivering them to the user.\n"
                "Be concise but include all the relevant context.\n\n"
                f"DUE REMINDERS:\n{raw}"
            )

            response = await _agent_compose(prompt)

            if response:
                await notify(response)
            else:
                # Fallback: send each reminder individually
                for r in reminders:
                    message = f"Reminder: {r.message}"
                    if r.task_id:
                        message += f" (task #{r.task_id})"
                    await notify(message)

            # Mark all as delivered
            for rid in reminder_ids:
                mark_reminder_delivered(session, rid)
                logger.info(f"Delivered reminder #{rid}")

    except Exception as e:
        logger.exception(f"Error in reminder delivery job: {e}")


async def sync_calendar() -> None:
    """Sync Google Calendar events to local database."""
    logger.info("Running calendar sync job")
    try:
        from src.integrations.calendar import sync_events

        now = datetime.now(settings.timezone).replace(tzinfo=None)
        end = now + timedelta(days=14)
        count = sync_events(now, end)
        logger.info(f"Calendar sync complete: {count} events synced")
    except Exception as e:
        logger.exception(f"Error in calendar sync job: {e}")


def _get_next_occurrence(rrule_str: str, after: datetime, now: datetime | None = None) -> datetime | None:
    """Calculate next occurrence from an RRULE string after a given date.

    When a task is completed late, pass ``now`` so the generated instance is
    always in the future rather than still overdue.
    """
    try:
        from dateutil.rrule import rrulestr

        rule = rrulestr(f"RRULE:{rrule_str}", dtstart=after)
        # Skip any occurrences already in the past when task was completed late
        cutoff = max(after, now) if now is not None else after
        return rule.after(cutoff, inc=False)
    except Exception as e:
        logger.warning(f"Failed to parse RRULE '{rrule_str}': {e}")
        return None


async def generate_recurring_tasks() -> None:
    """Generate next instances of completed recurring tasks."""
    logger.info("Running recurring tasks generation")
    try:
        with session_scope() as session:
            tasks = list_completed_recurring_tasks(session)
            generated = 0
            now = datetime.now(settings.timezone).replace(tzinfo=None)

            for task in tasks:
                if not task.recurrence_rule:
                    continue
                after = task.due_date or task.updated_at or now
                next_due = _get_next_occurrence(task.recurrence_rule, after, now=now)

                if next_due:
                    new_task = create_next_recurring_instance(session, task, next_due)
                    propagated = propagate_reminders_to_new_instance(session, task, new_task)
                    generated += 1
                    logger.info(f"Generated next instance for task #{task.id}: due {next_due}")
                    if propagated:
                        logger.info(f"Propagated {len(propagated)} reminders to task #{new_task.id}")
                else:
                    logger.warning(f"Could not compute next occurrence for task #{task.id}")

            if generated:
                logger.info(f"Generated {generated} recurring task instances")
    except Exception as e:
        logger.exception(f"Error generating recurring tasks: {e}")
