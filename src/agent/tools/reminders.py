from datetime import datetime
from typing import Optional

from src.db import get_session
from src.db.queries import (
    create_reminder,
    delete_reminder,
    list_all_reminders,
)
from src.utils import parse_date


def set_reminder(
    message: str,
    remind_at: str,
    task_id: Optional[int] = None,
) -> str:
    """Set a reminder for a specific time.

    Args:
        message: The reminder message to be sent.
        remind_at: When to send the reminder (natural language like "tomorrow at 3pm",
                   "in 2 hours", "next Monday" or ISO format).
        task_id: Optional task ID to link this reminder to.

    Returns:
        Confirmation message with reminder ID.
    """
    session = get_session()

    remind_dt = parse_date(remind_at)
    if not remind_dt:
        session.close()
        return f"Could not parse date: {remind_at}"
    reminder = create_reminder(session, message, remind_dt, task_id)
    session.close()

    return f"Reminder #{reminder.id} set for {remind_dt.strftime('%Y-%m-%d %H:%M')}: {message}"


def list_reminders(include_delivered: bool = False) -> str:
    """List reminders.

    Args:
        include_delivered: Whether to include already delivered reminders.

    Returns:
        Formatted list of reminders.
    """
    session = get_session()
    reminders = list_all_reminders(session, include_delivered)
    session.close()

    if not reminders:
        return "No reminders found." if include_delivered else "No pending reminders."

    lines = []
    for rem in reminders:
        task_info = f" (task #{rem.task_id})" if rem.task_id else ""
        status = " ✓" if rem.delivered else ""
        lines.append(
            f"#{rem.id}: {rem.remind_at.strftime('%Y-%m-%d %H:%M')}: {rem.message}{task_info}{status}"
        )

    return "\n".join(lines)


def cancel_reminder(reminder_id: int) -> str:
    """Cancel a pending reminder.

    Args:
        reminder_id: The ID of the reminder to cancel.

    Returns:
        Confirmation message or error if not found.
    """
    session = get_session()
    success = delete_reminder(session, reminder_id)
    session.close()

    if success:
        return f"Cancelled reminder #{reminder_id}."
    return f"Reminder #{reminder_id} not found."
