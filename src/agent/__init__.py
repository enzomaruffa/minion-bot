from src.config import settings

if settings.agent_sdk_enabled:
    from src.agent.sdk_agent import chat, chat_stream, shutdown
else:
    from src.agent.agent import chat, create_agent, get_agent  # noqa: F401

    chat_stream = None
    shutdown = None

__all__ = ["chat", "chat_stream", "shutdown"]
