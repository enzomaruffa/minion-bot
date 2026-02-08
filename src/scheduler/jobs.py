import logging
from datetime import datetime, timedelta

from src.agent.tools.agenda import get_agenda
from src.config import settings
from src.db import session_scope
from src.db.models import TaskPriority, TaskStatus
from src.db.queries import (
    count_tasks_by_due_date,
    list_overdue_tasks,
    list_pending_reminders,
    list_tasks_by_status,
    list_tasks_due_soon,
    list_upcoming_birthdays,
    mark_reminder_delivered,
    update_task,
)
from src.telegram.bot import send_message
from src.utils import days_until_birthday, format_birthday_proximity

logger = logging.getLogger(__name__)


async def morning_summary() -> None:
    """Send the daily morning agenda summary."""
    logger.info("Running morning summary job")

    try:
        agenda = get_agenda()
        message = f"Good morning! Here's your agenda for today:\n\n{agenda}"
        await send_message(message)
        logger.info("Morning summary sent")
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

        await send_message("\n".join(lines))
        logger.info("EOD review sent")
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

                    await send_message(message)
                    mark_reminder_delivered(session, reminder.id)
                    logger.info(f"Delivered reminder #{reminder.id}")
                except Exception as e:
                    logger.exception(f"Error delivering reminder #{reminder.id}: {e}")
    except Exception as e:
        logger.exception(f"Error in reminder delivery job: {e}")


async def proactive_intelligence() -> None:
    """Smart nudges and suggestions sent proactively."""
    logger.info("Running proactive intelligence job")

    try:
        with session_scope() as session:
            now = datetime.now(settings.timezone).replace(tzinfo=None)
            messages = []

            # 1. Priority escalation: bump priority for tasks due within 24h
            due_soon = list_tasks_due_soon(session, now, within_hours=24)
            escalated = []
            for task in due_soon:
                if task.priority in [TaskPriority.LOW, TaskPriority.MEDIUM]:
                    update_task(session, task.id, priority=TaskPriority.HIGH)
                    escalated.append(task)

            if escalated:
                task_list = ", ".join([f"#{t.id}" for t in escalated[:5]])
                if len(escalated) > 5:
                    task_list += f" and {len(escalated) - 5} more"
                messages.append(f"Priority escalated for tasks due within 24h: {task_list}")

            # 2. Overdue nudges
            overdue = list_overdue_tasks(session, now)
            if overdue:
                lines = ["You have overdue tasks:"]
                for task in overdue[:5]:
                    days_overdue = (now - task.due_date).days
                    emoji = task.project.emoji if task.project else ""
                    lines.append(f"  #{task.id}: {emoji} {task.title} ({days_overdue}d overdue)")
                if len(overdue) > 5:
                    lines.append(f"  ... and {len(overdue) - 5} more")
                messages.append("\n".join(lines))

            # 3. Smart scheduling: warn about overloaded days
            tomorrow = now + timedelta(days=1)
            tomorrow_count = count_tasks_by_due_date(session, tomorrow)
            if tomorrow_count >= 5:
                messages.append(f"You have {tomorrow_count} tasks due tomorrow. Consider rescheduling some if needed.")

            # 4. Breakdown suggestions for complex tasks
            todo_tasks = list_tasks_by_status(session, TaskStatus.TODO, root_only=True)
            complex_tasks = [t for t in todo_tasks if len(t.title) > 50 or (t.description and len(t.description) > 200)]
            if complex_tasks:
                task = complex_tasks[0]  # Just suggest for one at a time
                messages.append(
                    f"Task #{task.id} seems complex. Consider breaking it into subtasks:\n"
                    f'  "{task.title[:60]}{"..." if len(task.title) > 60 else ""}"'
                )

            # 5. Upcoming birthdays (within 7 days)
            upcoming_contacts = list_upcoming_birthdays(session, within_days=7)
            if upcoming_contacts:
                today = datetime.now(settings.timezone).date()
                lines = ["Upcoming Birthdays"]
                for contact in upcoming_contacts:
                    if contact.birthday:
                        d = days_until_birthday(contact.birthday, today)
                        lines.append(f"  {contact.name} - {format_birthday_proximity(d)}")
                messages.append("\n".join(lines))

        # Send combined message if there are any nudges
        if messages:
            combined = "Proactive Check-in\n\n" + "\n\n".join(messages)
            await send_message(combined)
            logger.info(f"Sent proactive intelligence message with {len(messages)} nudges")
        else:
            logger.info("No proactive nudges needed")

    except Exception as e:
        logger.exception(f"Error in proactive intelligence job: {e}")


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
