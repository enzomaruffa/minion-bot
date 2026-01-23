import logging
from datetime import datetime, timedelta

from src.agent.tools.agenda import get_agenda
from src.config import settings
from src.db import get_session
from src.db.models import TaskStatus
from src.db.queries import list_tasks_by_status
from src.telegram.bot import send_message

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
        session = get_session()
        now = datetime.now(settings.timezone)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Get tasks completed today
        done_tasks = list_tasks_by_status(session, TaskStatus.DONE)
        completed_today = [
            t for t in done_tasks
            if t.updated_at and t.updated_at >= today_start.replace(tzinfo=None)
        ]

        # Get incomplete tasks
        todo_tasks = list_tasks_by_status(session, TaskStatus.TODO)
        in_progress = list_tasks_by_status(session, TaskStatus.IN_PROGRESS)
        session.close()

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
