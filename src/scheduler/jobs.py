import logging
from datetime import datetime

from src.agent.tools.agenda import get_agenda
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
