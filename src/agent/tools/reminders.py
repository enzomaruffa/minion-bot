from src.db import session_scope
from src.db.queries import (
    create_reminder,
    delete_reminder,
    get_task,
    list_all_reminders,
)
from src.utils import parse_date


def set_reminder(
    message: str,
    remind_at: str,
    task_id: int | None = None,
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
    remind_dt = parse_date(remind_at)
    if not remind_dt:
        return f"Could not parse date: {remind_at}"

    with session_scope() as session:
        reminder = create_reminder(session, message, remind_dt, task_id)

        task_info = f" (linked to task #{task_id})" if task_id else ""
        return f"Reminder #{reminder.id} set for {remind_dt.strftime('%b %d, %H:%M')}{task_info}\n{message}"


def list_reminders(include_delivered: bool = False) -> str:
    """List reminders.

    Args:
        include_delivered: Whether to include already delivered reminders.

    Returns:
        Formatted list of reminders.
    """
    with session_scope() as session:
        reminders = list_all_reminders(session, include_delivered)

        if not reminders:
            if not include_delivered:
                return "No pending reminders. Try 'remind me to...' to set one!"
            return "No reminders found."

        lines = ["Reminders", ""]
        for rem in reminders:
            task_info = f" -> task #{rem.task_id}" if rem.task_id else ""
            status = " [delivered]" if rem.delivered else ""
            time_str = rem.remind_at.strftime("%b %d, %H:%M")
            lines.append(f"  #{rem.id} {time_str}{status}\n    {rem.message}{task_info}")

        return "\n".join(lines)


def cancel_reminder(reminder_id: int) -> str:
    """Cancel a pending reminder. DESTRUCTIVE - call list_reminders first to verify the ID!

    Args:
        reminder_id: The ID of the reminder. MUST call list_reminders first to verify correct ID.

    Returns:
        Confirmation message or error if not found.
    """
    with session_scope() as session:
        success = delete_reminder(session, reminder_id)

        if success:
            return f"Cancelled reminder #{reminder_id}"
        return f"Reminder #{reminder_id} not found"


def remind_before_deadline(task_id: int, hours_before: float = 1.0) -> str:
    """Set a reminder relative to a task's deadline.

    Creates a reminder that fires a specified number of hours before the task's due date.
    If an auto-reminder already exists for this task, it will be replaced.

    Args:
        task_id: The task ID to set a deadline reminder for.
        hours_before: How many hours before the deadline to be reminded (default: 1 hour).

    Returns:
        Confirmation message or error.
    """
    from src.services.reminders import ensure_deadline_reminder

    with session_scope() as session:
        task = get_task(session, task_id)
        if not task:
            return f"Task <code>#{task_id}</code> not found"

        if not task.due_date:
            return f"Task <code>#{task_id}</code> has no due date set"

        reminder = ensure_deadline_reminder(session, task, offset_hours=hours_before)

        if not reminder:
            return "Cannot set reminder — the computed time is already in the past"

        time_str = reminder.remind_at.strftime("%b %d, %H:%M")
        return (
            f"Reminder <code>#{reminder.id}</code> set for {time_str} "
            f"({hours_before}h before deadline of task <code>#{task_id}</code> "
            f"<i>{task.title}</i>)"
        )
