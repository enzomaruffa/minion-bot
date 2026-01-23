import logging

from src.config import settings
from src.db import init_database
from src.telegram.bot import create_application

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Start the bot."""
    logger.info("Initializing database...")
    init_database(settings.database_path)

    logger.info("Starting Minion bot...")
    application = create_application()
    application.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
