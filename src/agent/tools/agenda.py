from datetime import datetime, timedelta
from typing import Optional

from src.config import settings
from src.db import get_session
from src.db.models import TaskStatus
from src.db.queries import (
    list_calendar_events_range,
    list_pending_reminders,
    list_tasks_by_status,
)
from src.utils import parse_date


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

    session = get_session()

    # Get tasks due today
    all_tasks = list_tasks_by_status(session, None)
    tasks_due = [
        t for t in all_tasks
        if t.due_date and day_start.replace(tzinfo=None) <= t.due_date < day_end.replace(tzinfo=None)
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

    # Calendar events
    if events:
        lines.append("<b>📆 Events</b>")
        for event in events:
            time_str = event.start_time.strftime("%H:%M")
            end_str = event.end_time.strftime("%H:%M")
            lines.append(f"• {time_str}–{end_str}  {event.title}")
    else:
        lines.append("<i>No calendar events</i>")

    # Tasks due today
    lines.append("")
    if tasks_due:
        lines.append("<b>📋 Due Today</b>")
        for task in tasks_due:
            project_emoji = task.project.emoji + " " if task.project else ""
            contact_info = f" → <u>{task.contact.name}</u>" if task.contact else ""
            lines.append(f"• <code>#{task.id}</code> {project_emoji}{task.title}{contact_info}")
    else:
        lines.append("<i>No tasks due today</i>")

    # Reminders
    if today_reminders:
        lines.append("")
        lines.append("<b>⏰ Reminders</b>")
        for rem in today_reminders:
            time_str = rem.remind_at.strftime("%H:%M")
            lines.append(f"• {time_str}  {rem.message}")

    # Pending tasks (backlog)
    if pending_tasks:
        lines.append("")
        lines.append(f"<i>📝 {len(pending_tasks)} tasks in backlog</i>")

    session.close()

    return "\n".join(lines)
