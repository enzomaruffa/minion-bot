import logging
from collections.abc import Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import settings

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    """Get or create the scheduler singleton."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone=settings.timezone)
    return _scheduler


def add_cron_job(
    func: Callable,
    hour: int,
    minute: int = 0,
    job_id: str | None = None,
) -> None:
    """Add a cron job to run at a specific time daily.

    Args:
        func: The async function to run.
        hour: Hour to run (0-23).
        minute: Minute to run (0-59).
        job_id: Optional unique job identifier.
    """
    scheduler = get_scheduler()
    trigger = CronTrigger(hour=hour, minute=minute, timezone=settings.timezone)
    scheduler.add_job(func, trigger, id=job_id, replace_existing=True)
    logger.info(f"Added cron job '{job_id}' to run at {hour:02d}:{minute:02d}")


def add_interval_job(
    func: Callable,
    minutes: int = 1,
    job_id: str | None = None,
) -> None:
    """Add an interval job to run every N minutes.

    Args:
        func: The async function to run.
        minutes: Interval in minutes.
        job_id: Optional unique job identifier.
    """
    scheduler = get_scheduler()
    scheduler.add_job(func, "interval", minutes=minutes, id=job_id, replace_existing=True)
    logger.info(f"Added interval job '{job_id}' to run every {minutes} minute(s)")


def start_scheduler() -> None:
    """Start the scheduler."""
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started")


def shutdown_scheduler() -> None:
    """Shutdown the scheduler gracefully."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=True)
        logger.info("Scheduler stopped")
    _scheduler = None
