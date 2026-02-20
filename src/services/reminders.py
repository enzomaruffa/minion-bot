"""Reminder-deadline coordination service.

All functions receive a session and operate within the caller's transaction.
They use session.flush() — never session.commit().
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from src.config import settings
from src.db.models import Reminder, Task
from src.db.queries import (
    create_reminder,
    delete_auto_reminders_for_task,
    get_task_reminders,
)

logger = logging.getLogger(__name__)


def ensure_deadline_reminder(session: Session, task: Task, offset_hours: float | None = None) -> Reminder | None:
    """Create or replace an auto-reminder for a task's due_date.

    - If task has no due_date, returns None.
    - Deletes existing auto-created undelivered reminders for this task.
    - Creates a new auto-created reminder at (due_date - offset_hours).
    - If the computed remind_at is in the past, returns None.
    - Never touches manually-created reminders.
    """
    if not task.due_date:
        return None

    if offset_hours is None:
        offset_hours = settings.default_reminder_offset_hours

    remind_at = task.due_date - timedelta(hours=offset_hours)
    now = datetime.now(settings.timezone).replace(tzinfo=None)

    if remind_at <= now:
        return None

    # Remove any previous auto-reminders for this task
    delete_auto_reminders_for_task(session, task.id)

    message = f"Deadline approaching: {task.title}"
    return create_reminder(session, message=message, remind_at=remind_at, task_id=task.id, auto_created=True)


def propagate_reminders_to_new_instance(session: Session, source_task: Task, new_task: Task) -> list[Reminder]:
    """Copy reminders from a completed recurring task to its new instance.

    Adjusts remind_at times by the same offset relative to due_date.
    Skips reminders whose new time would be in the past.
    Preserves the auto_created flag from the source reminder.
    """
    if not source_task.due_date or not new_task.due_date:
        return []

    source_reminders = [r for r in get_task_reminders(session, source_task.id) if not r.delivered]
    created = []

    for rem in source_reminders:
        offset = rem.remind_at - source_task.due_date
        new_remind_at = new_task.due_date + offset

        now = datetime.now(settings.timezone).replace(tzinfo=None)
        if new_remind_at <= now:
            continue

        new_rem = create_reminder(
            session,
            message=rem.message,
            remind_at=new_remind_at,
            task_id=new_task.id,
            auto_created=rem.auto_created,
        )
        created.append(new_rem)

    return created
