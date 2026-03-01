import logging
from datetime import datetime, timedelta

from src.agent.tools.agenda import get_agenda
from src.config import settings
from src.db import session_scope
from src.db.models import TaskStatus
from src.db.queries import (
    create_next_recurring_instance,
    get_mood_log,
    list_completed_recurring_tasks,
    list_pending_reminders,
    list_tasks_by_status,
    log_agent_event,
    mark_reminder_delivered,
)
from src.notifications import notify
from src.services.reminders import propagate_reminders_to_new_instance

logger = logging.getLogger(__name__)


async def morning_summary() -> None:
    """Send the daily morning agenda summary."""
    logger.info("Running morning summary job")

    try:
        agenda = get_agenda()
        message = f"Good morning! Here's your agenda for today:\n\n{agenda}"
        await notify(message)
        logger.info("Morning summary sent")

        # Log to event bus
        try:
            with session_scope() as session:
                log_agent_event(session, "scheduler", "job_ran", f"Morning summary sent: {message[:200]}")
        except Exception:
            logger.debug("Failed to log morning summary to event bus", exc_info=True)
    except Exception as e:
        logger.exception(f"Error sending morning summary: {e}")


async def eod_review() -> None:
    """Send the end-of-day review and tomorrow preview."""
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

            # Build message
            lines = ["Good evening! Here's your daily review:"]
            lines.append("")

            if completed_today:
                lines.append(f"Completed today ({len(completed_today)}):")
                for task in completed_today[:5]:
                    lines.append(f"  - {task.title}")
                if len(completed_today) > 5:
                    lines.append(f"  ... and {len(completed_today) - 5} more")
            else:
                lines.append("No tasks completed today.")

            lines.append("")

            incomplete = len(todo_tasks) + len(in_progress)
            if incomplete > 0:
                lines.append(f"Still pending: {incomplete} task(s)")
                if in_progress:
                    lines.append("In progress:")
                    for task in in_progress[:3]:
                        lines.append(f"  - {task.title}")

            lines.append("")
            lines.append("Tomorrow's preview:")

            # Get tomorrow's agenda
            tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
            tomorrow_agenda = get_agenda(tomorrow)
            lines.append(tomorrow_agenda)

            # Mood prompt if not logged today
            today = now.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
            mood_today = get_mood_log(session, today)
            if not mood_today:
                lines.append("")
                lines.append("How was your day? Rate 1-5 (😞😕😐🙂😄)")

        eod_message = "\n".join(lines)
        await notify(eod_message)
        logger.info("EOD review sent")

        # Log to event bus
        try:
            with session_scope() as session:
                log_agent_event(session, "scheduler", "job_ran", f"EOD review sent: {eod_message[:200]}")
        except Exception:
            logger.debug("Failed to log EOD review to event bus", exc_info=True)
    except Exception as e:
        logger.exception(f"Error sending EOD review: {e}")


async def deliver_reminders() -> None:
    """Check and deliver due reminders."""
    try:
        with session_scope() as session:
            now = datetime.now(settings.timezone).replace(tzinfo=None)

            # Get reminders due up to now
            reminders = list_pending_reminders(session, now)

            for reminder in reminders:
                try:
                    message = f"Reminder: {reminder.message}"
                    if reminder.task_id:
                        message += f" (task #{reminder.task_id})"

                    await notify(message)
                    mark_reminder_delivered(session, reminder.id)
                    logger.info(f"Delivered reminder #{reminder.id}")
                except Exception as e:
                    logger.exception(f"Error delivering reminder #{reminder.id}: {e}")
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


def _get_next_occurrence(rrule_str: str, after: datetime) -> datetime | None:
    """Calculate next occurrence from an RRULE string after a given date."""
    try:
        from dateutil.rrule import rrulestr

        rule = rrulestr(f"RRULE:{rrule_str}", dtstart=after)
        next_dt = rule.after(after, inc=False)
        return next_dt
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

            for task in tasks:
                after = task.due_date or task.updated_at or datetime.now(settings.timezone).replace(tzinfo=None)
                next_due = _get_next_occurrence(task.recurrence_rule, after)

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
