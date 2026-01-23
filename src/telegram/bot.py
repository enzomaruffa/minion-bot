import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from src.telegram.commands import (
    tasks_command,
    today_command,
    done_command,
    calendar_command,
    help_command,
)

from src.config import settings
from src.agent import chat

logger = logging.getLogger(__name__)


def is_authorized(user_id: int) -> bool:
    """Check if the user is authorized to use the bot."""
    return user_id == settings.telegram_user_id


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming text messages."""
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id if update.effective_user else None
    if not user_id or not is_authorized(user_id):
        await update.message.reply_text("Sorry, you're not authorized to use this bot.")
        return

    user_message = update.message.text
    logger.info(f"Received message: {user_message[:50]}...")

    try:
        response = await chat(user_message)
        await update.message.reply_text(response, parse_mode="Markdown")
    except Exception as e:
        logger.exception("Error processing message")
        await update.message.reply_text(
            f"Sorry, I encountered an error: {str(e)[:100]}"
        )


def create_application() -> Application:
    """Create and configure the Telegram application."""
    application = Application.builder().token(settings.telegram_bot_token).build()

    # Add command handlers
    application.add_handler(CommandHandler("tasks", tasks_command))
    application.add_handler(CommandHandler("today", today_command))
    application.add_handler(CommandHandler("done", done_command))
    application.add_handler(CommandHandler("calendar", calendar_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("start", help_command))

    # Add message handler for text messages
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    return application


async def send_message(text: str) -> None:
    """Send a proactive message to the user."""
    from telegram import Bot

    bot = Bot(token=settings.telegram_bot_token)
    await bot.send_message(
        chat_id=settings.telegram_user_id,
        text=text,
        parse_mode="Markdown",
    )
