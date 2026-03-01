import asyncio
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
    sync_calendar,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler.executors").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def _cleanup_event_bus() -> None:
    """Clean up old events and completed work from the event bus."""
    from src.db import session_scope
    from src.db.queries import cleanup_old_events, cleanup_old_work

    with session_scope() as session:
        events_deleted = cleanup_old_events(session, older_than_days=7)
        work_deleted = cleanup_old_work(session, older_than_days=3)
        if events_deleted or work_deleted:
            logger.info(f"Event bus cleanup: {events_deleted} events, {work_deleted} work items deleted")


def register_jobs() -> None:
    """Register scheduled jobs (must be called before start)."""
    # Morning summary at 10:30 AM
    add_cron_job(morning_summary, hour=10, minute=30, job_id="morning_summary")

    # EOD review at 9 PM
    add_cron_job(eod_review, hour=21, minute=0, job_id="eod_review")

    # Reminder delivery every minute
    add_interval_job(deliver_reminders, minutes=1, job_id="reminder_delivery")

    # Heartbeat engine (replaces old proactive_intelligence)
    if settings.heartbeat_enabled:
        from src.scheduler.heartbeat import run_heartbeat

        add_interval_job(run_heartbeat, minutes=settings.heartbeat_interval_minutes, job_id="heartbeat")

    # Calendar sync every 30 minutes
    add_interval_job(sync_calendar, minutes=30, job_id="calendar_sync")

    # Recurring task generation every 5 minutes
    add_interval_job(generate_recurring_tasks, minutes=5, job_id="recurring_tasks")

    # Expired web session cleanup daily at 3 AM
    from src.web.auth import cleanup_expired_sessions_job

    add_cron_job(cleanup_expired_sessions_job, hour=3, minute=0, job_id="session_cleanup")

    # Event bus + agent work cleanup daily at 4 AM
    add_cron_job(_cleanup_event_bus, hour=4, minute=0, job_id="event_bus_cleanup")


async def _init_mcp_and_agent() -> None:
    """Initialize MCP servers and recreate agent with MCP tools.

    In SDK mode, MCP is handled natively by ClaudeAgentOptions — this is a no-op.
    """
    logger.info("Claude Agent SDK handles MCP natively — skipping MCP init")


async def post_init(application) -> None:
    """Called after the application is initialized with event loop running."""
    from src.telegram.bot import register_commands

    logger.info("Registering bot commands...")
    await register_commands(application)

    logger.info("Initializing MCP servers...")
    await _init_mcp_and_agent()

    logger.info("Starting scheduler...")
    start_scheduler()


async def post_shutdown(application) -> None:
    """Called during shutdown."""
    logger.info("Stopping scheduler...")
    shutdown_scheduler()

    logger.info("Cleaning up agent...")
    try:
        from src.agent import shutdown

        if shutdown:
            await shutdown()
    except Exception as e:
        logger.warning(f"Error shutting down agent: {e}")


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

    logger.info("Starting web server...")
    start_web_server()

    if settings.telegram_bot_token:
        from src.telegram.bot import create_application, register_notification_handler

        logger.info("Registering Telegram notification handler...")
        register_notification_handler()

        logger.info("Starting Minion bot...")
        application = create_application()
        application.post_init = post_init
        application.post_shutdown = post_shutdown

        application.run_polling(allowed_updates=["message"])
    else:
        logger.info("No TELEGRAM_BOT_TOKEN — running in web-only mode")

        # Init MCP servers in web-only mode
        asyncio.run(_init_mcp_and_agent())

        start_scheduler()
        try:
            import time

            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            shutdown_scheduler()


if __name__ == "__main__":
    main()
