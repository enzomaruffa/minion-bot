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
        return f"Could not parse date: <code>{remind_at}</code>"
    reminder = create_reminder(session, message, remind_dt, task_id)
    session.close()

    task_info = f" <i>(linked to task <code>#{task_id}</code>)</i>" if task_id else ""
    return f"⏰ Reminder <code>#{reminder.id}</code> set for <b>{remind_dt.strftime('%b %d, %H:%M')}</b>{task_info}\n<i>{message}</i>"


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
        return "<i>No pending reminders</i>" if not include_delivered else "<i>No reminders found</i>"

    lines = ["<b>⏰ Reminders</b>", ""]
    for rem in reminders:
        task_info = f" → task <code>#{rem.task_id}</code>" if rem.task_id else ""
        status = " ✓" if rem.delivered else ""
        time_str = rem.remind_at.strftime("%b %d, %H:%M")
        lines.append(f"• <code>#{rem.id}</code> {time_str}{status}\n  <i>{rem.message}</i>{task_info}")

    return "\n".join(lines)


def cancel_reminder(reminder_id: int) -> str:
    """Cancel a pending reminder. DESTRUCTIVE - call list_reminders first to verify the ID!

    Args:
        reminder_id: The ID of the reminder. MUST call list_reminders first to verify correct ID.

    Returns:
        Confirmation message or error if not found.
    """
    session = get_session()
    success = delete_reminder(session, reminder_id)
    session.close()

    if success:
        return f"✓ Cancelled reminder <code>#{reminder_id}</code>"
    return f"Reminder <code>#{reminder_id}</code> not found"
