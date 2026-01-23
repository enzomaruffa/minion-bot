from telegram import Update
from telegram.ext import ContextTypes

from src.agent.tools import get_agenda, list_tasks
from src.config import settings
from src.db import get_session
from src.db.models import TaskStatus
from src.db.queries import list_calendar_events_range, list_tasks_by_status, update_task
from datetime import datetime, timedelta


def is_authorized(user_id: int) -> bool:
    """Check if the user is authorized."""
    return user_id == settings.telegram_user_id


async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /tasks command - list pending tasks."""
    if not update.message:
        return

    user_id = update.effective_user.id if update.effective_user else None
    if not user_id or not is_authorized(user_id):
        await update.message.reply_text("Not authorized.")
        return

    in_progress = list_tasks(status="in_progress")
    todo = list_tasks(status="todo")

    parts = []
    if in_progress and in_progress != "No tasks found.":
        parts.append(f"IN PROGRESS:\n{in_progress}")
    if todo and todo != "No tasks found.":
        parts.append(f"TODO:\n{todo}")

    result = "\n\n".join(parts) if parts else "No tasks found."
    await update.message.reply_text(result)


async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /today command - show today's agenda."""
    if not update.message:
        return

    user_id = update.effective_user.id if update.effective_user else None
    if not user_id or not is_authorized(user_id):
        await update.message.reply_text("Not authorized.")
        return

    result = get_agenda()
    await update.message.reply_text(result)


async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /done command - mark most recent in-progress task as done."""
    if not update.message:
        return

    user_id = update.effective_user.id if update.effective_user else None
    if not user_id or not is_authorized(user_id):
        await update.message.reply_text("Not authorized.")
        return

    session = get_session()
    tasks = list_tasks_by_status(session, TaskStatus.IN_PROGRESS)

    if not tasks:
        tasks = list_tasks_by_status(session, TaskStatus.TODO)

    if not tasks:
        await update.message.reply_text("No pending tasks to mark as done.")
        session.close()
        return

    # Get the most recent task
    task = tasks[0]
    update_task(session, task.id, status=TaskStatus.DONE)
    session.close()

    await update.message.reply_text(f"Marked as done: {task.title}")


async def calendar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /calendar command - show upcoming calendar events."""
    if not update.message:
        return

    user_id = update.effective_user.id if update.effective_user else None
    if not user_id or not is_authorized(user_id):
        await update.message.reply_text("Not authorized.")
        return

    session = get_session()
    now = datetime.now(settings.timezone).replace(tzinfo=None)
    end = now + timedelta(days=7)

    events = list_calendar_events_range(session, now, end)
    session.close()

    if not events:
        await update.message.reply_text("No upcoming events in the next 7 days.")
        return

    lines = ["Upcoming events:"]
    for event in events:
        date_str = event.start_time.strftime("%a %d %b %H:%M")
        lines.append(f"  {date_str}: {event.title}")

    await update.message.reply_text("\n".join(lines))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command - show available commands."""
    if not update.message:
        return

    help_text = """Available commands:

/tasks - List pending tasks
/today - Show today's agenda
/done - Mark recent task as complete
/calendar - Show upcoming events
/help - Show this help

Or just send a message and I'll help you manage your tasks and reminders!
"""
    await update.message.reply_text(help_text)
