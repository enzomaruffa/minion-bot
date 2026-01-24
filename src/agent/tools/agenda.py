from datetime import datetime, timedelta
from typing import Optional

from src.config import settings
from src.db import session_scope
from src.db.models import TaskStatus
from src.db.queries import (
    list_calendar_events_range,
    list_pending_reminders,
    list_tasks_by_status,
)
from src.utils import parse_date, format_date


def get_agenda(date: Optional[str] = None) -> str:
    """Get the agenda for a specific date, including tasks, calendar events, and reminders.

    Args:
        date: The date to get the agenda for (natural language like "tomorrow" or YYYY-MM-DD). Defaults to today.

    Returns:
        Formatted agenda with tasks due, calendar events, and reminders for the day.
    """
    if date:
        parsed = parse_date(date)
        if parsed:
            target_date = parsed.replace(tzinfo=settings.timezone)
        else:
            target_date = datetime.now(settings.timezone)
    else:
        target_date = datetime.now(settings.timezone)

    day_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    with session_scope() as session:
        # Get tasks due today
        all_tasks = list_tasks_by_status(session, None)
        tasks_due = [
            t for t in all_tasks
            if t.due_date and day_start.replace(tzinfo=None) <= t.due_date < day_end.replace(tzinfo=None)
            and t.status not in (TaskStatus.DONE, TaskStatus.CANCELLED)
        ]

        # Check for overdue tasks
        now = datetime.now(settings.timezone).replace(tzinfo=None)
        overdue_tasks = [
            t for t in all_tasks
            if t.due_date and t.due_date < day_start.replace(tzinfo=None)
            and t.status not in (TaskStatus.DONE, TaskStatus.CANCELLED)
        ]

        # Get pending tasks (no due date but not done)
        pending_tasks = [
            t for t in all_tasks
            if t.status == TaskStatus.TODO and not t.due_date
        ]

        # Get calendar events
        events = list_calendar_events_range(
            session,
            day_start.replace(tzinfo=None),
            day_end.replace(tzinfo=None),
        )

        # Get reminders for today
        reminders = list_pending_reminders(session, day_end.replace(tzinfo=None))
        today_reminders = [
            r for r in reminders
            if r.remind_at >= day_start.replace(tzinfo=None)
        ]

        # Format output while session is still open (to access relationships)
        lines = []

        # Overdue tasks (show first!)
        if overdue_tasks:
            lines.append("OVERDUE")
            for task in overdue_tasks:
                project_emoji = task.project.emoji + " " if task.project else ""
                days_overdue = (now - task.due_date).days
                lines.append(f"  #{task.id} {project_emoji}{task.title} ({days_overdue}d overdue)")
            lines.append("")

        # Calendar events
        if events:
            lines.append("Events")
            for event in events:
                time_str = event.start_time.strftime("%H:%M")
                end_str = event.end_time.strftime("%H:%M")
                lines.append(f"  {time_str}-{end_str}  {event.title}")
        else:
            lines.append("No calendar events")

        # Tasks due today
        lines.append("")
        if tasks_due:
            lines.append("Due Today")
            for task in tasks_due:
                project_emoji = task.project.emoji + " " if task.project else ""
                contact_info = f" {task.contact.name}" if task.contact else ""
                lines.append(f"  #{task.id} {project_emoji}{task.title}{contact_info}")
        else:
            lines.append("No tasks due today")

        # Reminders
        if today_reminders:
            lines.append("")
            lines.append("Reminders")
            for rem in today_reminders:
                time_str = rem.remind_at.strftime("%H:%M")
                lines.append(f"  {time_str} #{rem.id} {rem.message}")

        # Pending tasks (backlog)
        if pending_tasks:
            lines.append("")
            lines.append(f"{len(pending_tasks)} tasks in backlog")

        return "\n".join(lines)
