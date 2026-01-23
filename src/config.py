from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
import os

load_dotenv()


@dataclass
class Settings:
    telegram_bot_token: str
    telegram_user_id: int
    openai_api_key: str
    google_credentials_path: Path
    google_token_path: Path
    database_path: Path
    timezone: ZoneInfo

    @classmethod
    def from_env(cls) -> "Settings":
        telegram_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        if not telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")

        telegram_user_id = os.environ.get("TELEGRAM_USER_ID")
        if not telegram_user_id:
            raise ValueError("TELEGRAM_USER_ID is required")

        openai_api_key = os.environ.get("OPENAI_API_KEY")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY is required")

        google_credentials_path = Path(
            os.environ.get("GOOGLE_CREDENTIALS_PATH", "credentials/google_credentials.json")
        )
        google_token_path = Path(
            os.environ.get("GOOGLE_TOKEN_PATH", "credentials/google_token.json")
        )
        database_path = Path(os.environ.get("DATABASE_PATH", "data/minion.db"))

        tz_name = os.environ.get("TIMEZONE", "America/Sao_Paulo")
        timezone = ZoneInfo(tz_name)

        return cls(
            telegram_bot_token=telegram_bot_token,
            telegram_user_id=int(telegram_user_id),
            openai_api_key=openai_api_key,
            google_credentials_path=google_credentials_path,
            google_token_path=google_token_path,
            database_path=database_path,
            timezone=timezone,
        )


settings = Settings.from_env()
