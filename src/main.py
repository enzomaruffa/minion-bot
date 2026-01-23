import logging

from src.config import settings
from src.db import init_database
from src.scheduler import add_cron_job, add_interval_job, start_scheduler, shutdown_scheduler
from src.scheduler.jobs import morning_summary, eod_review, deliver_reminders
from src.telegram.bot import create_application

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def register_jobs() -> None:
    """Register scheduled jobs (must be called before start)."""
    # Morning summary at 11 AM
    add_cron_job(morning_summary, hour=11, minute=0, job_id="morning_summary")

    # EOD review at 9 PM
    add_cron_job(eod_review, hour=21, minute=0, job_id="eod_review")

    # Reminder delivery every minute
    add_interval_job(deliver_reminders, minutes=1, job_id="reminder_delivery")


async def post_init(application) -> None:
    """Called after the application is initialized with event loop running."""
    logger.info("Starting scheduler...")
    start_scheduler()


async def post_shutdown(application) -> None:
    """Called during shutdown."""
    logger.info("Stopping scheduler...")
    shutdown_scheduler()


def main() -> None:
    """Start the bot."""
    logger.info("Initializing database...")
    init_database(settings.database_path)

    logger.info("Registering scheduled jobs...")
    register_jobs()

    logger.info("Starting Minion bot...")
    application = create_application()
    application.post_init = post_init
    application.post_shutdown = post_shutdown

    application.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
