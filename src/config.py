import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    telegram_bot_token: str | None
    telegram_user_id: int
    openai_api_key: str | None  # Optional — only needed for vision/voice
    google_credentials_path: Path
    google_token_path: Path
    database_path: Path
    timezone: ZoneInfo
    # Web server settings for OAuth
    web_host: str
    web_port: int
    web_base_url: str
    # Web dashboard
    web_secret_key: str
    web_session_ttl_days: int
    # Silverbullet notes
    silverbullet_space_path: Path
    # AI model names (kept for vision/voice/heartbeat display, not used by main agent)
    agent_model: str
    vision_model: str
    # Reminder defaults
    default_reminder_offset_hours: float
    # Code execution
    code_execution_timeout: int
    # Heartbeat settings
    heartbeat_interval_minutes: int
    heartbeat_model: str
    heartbeat_enabled: bool
    heartbeat_max_notifications: int
    # MCP server commands
    mcp_server_commands: list[str]
    # Claude Agent SDK settings
    anthropic_base_url: str
    anthropic_api_key: str

    @classmethod
    def from_env(cls) -> "Settings":
        import secrets

        telegram_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")

        telegram_user_id = os.environ.get("TELEGRAM_USER_ID")
        if not telegram_user_id:
            raise ValueError("TELEGRAM_USER_ID is required")

        openai_api_key = os.environ.get("OPENAI_API_KEY")

        google_credentials_path = Path(os.environ.get("GOOGLE_CREDENTIALS_PATH", "credentials/google_credentials.json"))
        google_token_path = Path(os.environ.get("GOOGLE_TOKEN_PATH", "credentials/google_token.json"))
        database_path = Path(os.environ.get("DATABASE_PATH", "data/minion.db"))

        tz_name = os.environ.get("TIMEZONE", "America/Sao_Paulo")
        timezone = ZoneInfo(tz_name)

        # Web server settings
        web_host = os.environ.get("WEB_HOST", "0.0.0.0")
        web_port = int(os.environ.get("WEB_PORT", "21125"))
        web_base_url = os.environ.get("WEB_BASE_URL", "https://miniongoogleauth.enzomaruffa.dev")

        # Web dashboard settings
        web_secret_key = os.environ.get("WEB_SECRET_KEY", secrets.token_urlsafe(32))
        web_session_ttl_days = int(os.environ.get("WEB_SESSION_TTL_DAYS", "30"))

        silverbullet_space_path = Path(os.environ.get("SILVERBULLET_SPACE_PATH", ""))

        agent_model = os.environ.get("AGENT_MODEL", "claude-sonnet-4-5")
        vision_model = os.environ.get("VISION_MODEL", "gpt-5.2")

        default_reminder_offset_hours = float(os.environ.get("DEFAULT_REMINDER_OFFSET_HOURS", "1.0"))

        # Code execution
        code_execution_timeout = int(os.environ.get("CODE_EXECUTION_TIMEOUT", "60"))

        # Heartbeat settings
        heartbeat_interval_minutes = int(os.environ.get("HEARTBEAT_INTERVAL_MINUTES", "60"))
        heartbeat_model = os.environ.get("HEARTBEAT_MODEL", "claude-haiku-3-5")
        heartbeat_enabled = os.environ.get("HEARTBEAT_ENABLED", "true").lower() == "true"
        heartbeat_max_notifications = int(os.environ.get("HEARTBEAT_MAX_NOTIFICATIONS", "3"))

        # MCP server commands (comma-separated)
        mcp_cmds = os.environ.get("MCP_SERVER_COMMANDS", "")
        mcp_server_commands = [c.strip() for c in mcp_cmds.split(",") if c.strip()]

        # Claude Agent SDK settings
        anthropic_base_url = os.environ.get("ANTHROPIC_BASE_URL", "http://localhost:4000")
        anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "")

        return cls(
            telegram_bot_token=telegram_bot_token,
            telegram_user_id=int(telegram_user_id),
            openai_api_key=openai_api_key,
            google_credentials_path=google_credentials_path,
            google_token_path=google_token_path,
            database_path=database_path,
            timezone=timezone,
            web_host=web_host,
            web_port=web_port,
            web_base_url=web_base_url,
            web_secret_key=web_secret_key,
            web_session_ttl_days=web_session_ttl_days,
            silverbullet_space_path=silverbullet_space_path,
            agent_model=agent_model,
            vision_model=vision_model,
            default_reminder_offset_hours=default_reminder_offset_hours,
            code_execution_timeout=code_execution_timeout,
            heartbeat_interval_minutes=heartbeat_interval_minutes,
            heartbeat_model=heartbeat_model,
            heartbeat_enabled=heartbeat_enabled,
            heartbeat_max_notifications=heartbeat_max_notifications,
            mcp_server_commands=mcp_server_commands,
            anthropic_base_url=anthropic_base_url,
            anthropic_api_key=anthropic_api_key,
        )


settings = Settings.from_env()
