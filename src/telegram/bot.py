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
    auth_command,
    handle_auth_code,
    is_awaiting_auth_code,
)

from src.config import settings
from src.agent import chat
from src.integrations.voice import transcribe_voice
from src.integrations.vision import extract_task_from_image

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

    # Check if we're waiting for an auth code
    if is_awaiting_auth_code():
        response = await handle_auth_code(user_message)
        await update.message.reply_text(response)
        return

    try:
        response = await chat(user_message)
        await update.message.reply_text(response, parse_mode="Markdown")
    except Exception as e:
        logger.exception("Error processing message")
        await update.message.reply_text(
            f"Sorry, I encountered an error: {str(e)[:100]}"
        )


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming voice messages."""
    if not update.message or not update.message.voice:
        return

    user_id = update.effective_user.id if update.effective_user else None
    if not user_id or not is_authorized(user_id):
        await update.message.reply_text("Sorry, you're not authorized to use this bot.")
        return

    logger.info("Received voice message, transcribing...")

    try:
        # Download the voice file
        voice = update.message.voice
        file = await context.bot.get_file(voice.file_id)
        audio_data = await file.download_as_bytearray()

        # Transcribe
        transcript = transcribe_voice(bytes(audio_data), "voice.ogg")
        logger.info(f"Transcribed: {transcript[:50]}...")

        # Send transcript and process with agent
        await update.message.reply_text(f"_Heard: {transcript}_", parse_mode="Markdown")

        response = await chat(transcript)
        await update.message.reply_text(response, parse_mode="Markdown")
    except Exception as e:
        logger.exception("Error processing voice message")
        await update.message.reply_text(
            f"Sorry, I couldn't process that voice message: {str(e)[:100]}"
        )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming photo messages."""
    if not update.message or not update.message.photo:
        return

    user_id = update.effective_user.id if update.effective_user else None
    if not user_id or not is_authorized(user_id):
        await update.message.reply_text("Sorry, you're not authorized to use this bot.")
        return

    logger.info("Received photo, analyzing...")

    try:
        # Get the largest photo
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        image_data = await file.download_as_bytearray()

        # Analyze image
        analysis = extract_task_from_image(bytes(image_data))
        logger.info(f"Image analysis: {analysis[:50]}...")

        # Get caption if any
        caption = update.message.caption or ""

        # Combine analysis with caption and process
        message = f"I received an image. Analysis: {analysis}"
        if caption:
            message += f"\nCaption: {caption}"

        await update.message.reply_text(f"_Image analysis: {analysis[:200]}..._", parse_mode="Markdown")

        response = await chat(message)
        await update.message.reply_text(response, parse_mode="Markdown")
    except Exception as e:
        logger.exception("Error processing photo")
        await update.message.reply_text(
            f"Sorry, I couldn't process that image: {str(e)[:100]}"
        )


async def register_commands(application: Application) -> None:
    """Register bot commands with Telegram for the menu."""
    from telegram import BotCommand
    
    commands = [
        BotCommand("tasks", "List pending tasks"),
        BotCommand("today", "Show today's agenda"),
        BotCommand("done", "Mark recent task as complete"),
        BotCommand("calendar", "Show upcoming events"),
        BotCommand("auth", "Connect Google Calendar"),
        BotCommand("help", "Show help"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands registered with Telegram")


def create_application() -> Application:
    """Create and configure the Telegram application."""
    application = Application.builder().token(settings.telegram_bot_token).build()

    # Add command handlers
    application.add_handler(CommandHandler("tasks", tasks_command))
    application.add_handler(CommandHandler("today", today_command))
    application.add_handler(CommandHandler("done", done_command))
    application.add_handler(CommandHandler("calendar", calendar_command))
    application.add_handler(CommandHandler("auth", auth_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("start", help_command))

    # Add message handler for text messages
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    # Add voice message handler
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))

    # Add photo message handler
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))

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
