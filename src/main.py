import logging
import threading

from src.config import settings
from src.db import init_database
from src.scheduler import add_cron_job, add_interval_job, shutdown_scheduler, start_scheduler
from src.scheduler.jobs import (
    deliver_reminders,
    eod_review,
    generate_recurring_tasks,
    morning_summary,
    proactive_intelligence,
    sync_calendar,
)
from src.telegram.bot import create_application, register_commands

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler.executors").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def register_jobs() -> None:
    """Register scheduled jobs (must be called before start)."""
    # Morning summary at 10:30 AM
    add_cron_job(morning_summary, hour=10, minute=30, job_id="morning_summary")

    # EOD review at 9 PM
    add_cron_job(eod_review, hour=21, minute=0, job_id="eod_review")

    # Reminder delivery every minute
    add_interval_job(deliver_reminders, minutes=1, job_id="reminder_delivery")

    # Proactive intelligence at 5 PM daily
    add_cron_job(proactive_intelligence, hour=17, minute=0, job_id="proactive_intelligence")

    # Calendar sync every 30 minutes
    add_interval_job(sync_calendar, minutes=30, job_id="calendar_sync")

    # Recurring task generation every 5 minutes
    add_interval_job(generate_recurring_tasks, minutes=5, job_id="recurring_tasks")


async def post_init(application) -> None:
    """Called after the application is initialized with event loop running."""
    logger.info("Registering bot commands...")
    await register_commands(application)

    logger.info("Starting scheduler...")
    start_scheduler()


async def post_shutdown(application) -> None:
    """Called during shutdown."""
    logger.info("Stopping scheduler...")
    shutdown_scheduler()


def start_web_server() -> None:
    """Start the OAuth web server in a daemon thread."""
    from src.web.server import run_server

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    logger.info(f"Web server started on {settings.web_host}:{settings.web_port}")


def main() -> None:
    """Start the bot."""
    logger.info("Initializing database...")
    init_database(settings.database_path)

    logger.info("Registering scheduled jobs...")
    register_jobs()

    logger.info("Starting OAuth web server...")
    start_web_server()

    logger.info("Starting Minion bot...")
    application = create_application()
    application.post_init = post_init
    application.post_shutdown = post_shutdown

    application.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
