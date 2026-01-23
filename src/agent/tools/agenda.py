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


def get_agenda(date: Optional[str] = None) -> str:
    """Get the agenda for a specific date, including tasks, calendar events, and reminders.

    Args:
        date: The date to get the agenda for in ISO format (YYYY-MM-DD). Defaults to today.

    Returns:
        Formatted agenda with tasks due, calendar events, and reminders for the day.
    """
    if date:
        target_date = datetime.fromisoformat(date).replace(tzinfo=settings.timezone)
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

    session.close()

    # Format output
    lines = [f"Agenda for {target_date.strftime('%A, %B %d, %Y')}"]
    lines.append("=" * 40)

    # Calendar events
    if events:
        lines.append("\nCalendar Events:")
        for event in events:
            time_str = event.start_time.strftime("%H:%M")
            end_str = event.end_time.strftime("%H:%M")
            lines.append(f"  {time_str}-{end_str}: {event.title}")
    else:
        lines.append("\nNo calendar events.")

    # Tasks due today
    if tasks_due:
        lines.append("\nTasks Due Today:")
        for task in tasks_due:
            priority = f"[{task.priority.value}]" if task.priority else ""
            lines.append(f"  [{task.id}] {task.title} {priority}")
    else:
        lines.append("\nNo tasks due today.")

    # Reminders
    if today_reminders:
        lines.append("\nReminders:")
        for rem in today_reminders:
            time_str = rem.remind_at.strftime("%H:%M")
            lines.append(f"  {time_str}: {rem.message}")

    # Pending tasks (backlog)
    if pending_tasks:
        lines.append(f"\nBacklog ({len(pending_tasks)} pending tasks)")

    return "\n".join(lines)
