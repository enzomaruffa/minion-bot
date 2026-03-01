import logging
import time as _time
import uuid
from datetime import datetime

from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from src.agent import chat, chat_stream
from src.config import settings
from src.db import session_scope
from src.db.queries import log_agent_event
from src.integrations.vision import extract_task_from_image
from src.integrations.voice import transcribe_voice
from src.telegram.commands import (
    auth_command,
    birthdays_command,
    calendar_command,
    clear_command_context,
    contacts_command,
    get_last_command_context,
    gifts_command,
    groceries_command,
    help_command,
    lists_command,
    me_command,
    projects_command,
    reminders_command,
    require_auth,
    tasks_command,
    today_command,
    wishlist_command,
)
from telegram import Update

logger = logging.getLogger(__name__)


async def safe_reply(message, text: str) -> None:
    """Reply with HTML, falling back to plain text if parsing fails.
    Splits long messages to stay within Telegram's 4096-char limit."""
    MAX_LEN = 4096
    chunks: list[str] = []
    if len(text) <= MAX_LEN:
        chunks = [text]
    else:
        current = ""
        for line in text.split("\n"):
            candidate = (current + "\n" + line) if current else line
            if len(candidate) > MAX_LEN:
                if current:
                    chunks.append(current)
                # If a single line exceeds the limit, hard-split it
                while len(line) > MAX_LEN:
                    chunks.append(line[:MAX_LEN])
                    line = line[MAX_LEN:]
                current = line
            else:
                current = candidate
        if current:
            chunks.append(current)

    for chunk in chunks:
        try:
            await message.reply_text(chunk, parse_mode="HTML")
        except BadRequest as e:
            if "Can't parse entities" in str(e):
                logger.warning(f"HTML parse failed, sending as plain text: {e}")
                await message.reply_text(chunk)
            else:
                raise


@require_auth
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming text messages."""
    if not update.message or not update.message.text:
        return

    user_message = update.message.text
    logger.info(f"Received message: {user_message[:50]}...")

    # Log to event bus
    try:
        with session_scope() as session:
            log_agent_event(session, "user", "user_message", user_message[:500])
    except Exception:
        logger.debug("Failed to log user message to event bus", exc_info=True)

    # Inject last command context if recent
    cmd_context = get_last_command_context()
    if cmd_context:
        user_message = f"[User just ran {cmd_context['command']} and saw:\n{cmd_context['output']}]\n\n{user_message}"
        clear_command_context()

    try:
        # Use streaming if SDK is enabled and chat_stream is available
        if chat_stream is not None:
            await _handle_streaming_message(update, user_message)
        else:
            response = await chat(user_message)
            await safe_reply(update.message, response)
    except Exception as e:
        logger.exception("Error processing message")
        await update.message.reply_text(f"Sorry, I encountered an error: {str(e)[:100]}")


async def _handle_streaming_message(update: Update, user_message: str) -> None:
    """Handle a message with streaming response (progressive edits)."""
    assert update.message  # guaranteed by caller
    placeholder = None
    accumulated = ""
    last_edit = 0.0

    try:
        async for chunk in chat_stream(user_message):
            accumulated += chunk
            # Send first message once we have real text (no "..." placeholder)
            if placeholder is None and len(accumulated) > 3:
                placeholder = await update.message.reply_text(accumulated + " ...")
                last_edit = _time.time()
                continue
            if placeholder is None:
                continue
            now = _time.time()
            # Rate-limit edits to every 1.5 seconds to avoid Telegram API throttle
            if now - last_edit >= 1.5:
                try:
                    display = accumulated[:4000] + " ..." if len(accumulated) > 4000 else accumulated + " ..."
                    await placeholder.edit_text(display)
                    last_edit = now
                except BadRequest:
                    pass  # Edit can fail if text is unchanged

        # Final edit with the complete response
        if placeholder is None:
            # Never got a placeholder — send the full response (or fallback)
            text = accumulated.strip() or "Done."
            await safe_reply(update.message, text)
        elif accumulated.strip():
            import contextlib

            if len(accumulated) > 4096:
                # Too long for a single edit — delete placeholder and chunk-send
                with contextlib.suppress(Exception):
                    await placeholder.delete()
                await safe_reply(update.message, accumulated)
            else:
                try:
                    await placeholder.edit_text(accumulated, parse_mode="HTML")
                except BadRequest:
                    # HTML parse failed — try plain text
                    with contextlib.suppress(BadRequest):
                        await placeholder.edit_text(accumulated)
        else:
            await placeholder.edit_text("Done.")
    except Exception:
        logger.exception("Streaming error, falling back to non-streaming")
        response = await chat(user_message)
        if placeholder:
            import contextlib

            if len(response) > 4096:
                with contextlib.suppress(Exception):
                    await placeholder.delete()
                await safe_reply(update.message, response)
            else:
                try:
                    await placeholder.edit_text(response, parse_mode="HTML")
                except BadRequest:
                    await placeholder.edit_text(response)
        else:
            await safe_reply(update.message, response)


@require_auth
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming voice messages."""
    if not update.message or not update.message.voice:
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
        await safe_reply(update.message, f"<i>Heard: {transcript}</i>")

        # Add transcription context for the agent
        agent_message = (
            f"[This message was transcribed from audio - may contain spelling errors. "
            f"Confirm names/details if needed before taking action.]\n\n{transcript}"
        )
        response = await chat(agent_message)
        await safe_reply(update.message, response)
    except Exception as e:
        logger.exception("Error processing voice message")
        await update.message.reply_text(f"Sorry, I couldn't process that voice message: {str(e)[:100]}")


@require_auth
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming photo messages."""
    if not update.message or not update.message.photo:
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

        await safe_reply(update.message, f"<i>Image analysis: {analysis[:200]}...</i>")

        response = await chat(message)
        await safe_reply(update.message, response)
    except Exception as e:
        logger.exception("Error processing photo")
        await update.message.reply_text(f"Sorry, I couldn't process that image: {str(e)[:100]}")


async def register_commands(application: Application) -> None:
    """Register bot commands with Telegram for the menu."""
    from telegram import BotCommand

    commands = [
        BotCommand("tasks", "Pending tasks"),
        BotCommand("today", "Today's agenda"),
        BotCommand("projects", "All projects"),
        BotCommand("reminders", "Pending reminders"),
        BotCommand("calendar", "Upcoming events"),
        BotCommand("lists", "All shopping lists"),
        BotCommand("groceries", "Grocery list"),
        BotCommand("gifts", "Gift ideas"),
        BotCommand("wishlist", "Wishlist"),
        BotCommand("contacts", "All contacts"),
        BotCommand("birthdays", "Upcoming birthdays"),
        BotCommand("me", "Your profile"),
        BotCommand("auth", "Connect Google Calendar"),
        BotCommand("help", "Show help"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands registered with Telegram")


def create_application() -> Application:
    """Create and configure the Telegram application."""
    assert settings.telegram_bot_token, "TELEGRAM_BOT_TOKEN is required"
    application = Application.builder().token(settings.telegram_bot_token).build()

    # Add command handlers
    application.add_handler(CommandHandler("tasks", tasks_command))
    application.add_handler(CommandHandler("today", today_command))
    application.add_handler(CommandHandler("calendar", calendar_command))
    application.add_handler(CommandHandler("auth", auth_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("start", help_command))
    # Shopping list commands
    application.add_handler(CommandHandler("lists", lists_command))
    application.add_handler(CommandHandler("groceries", groceries_command))
    application.add_handler(CommandHandler("gifts", gifts_command))
    application.add_handler(CommandHandler("wishlist", wishlist_command))
    # Project and reminder commands
    application.add_handler(CommandHandler("projects", projects_command))
    application.add_handler(CommandHandler("reminders", reminders_command))
    # Contact commands
    application.add_handler(CommandHandler("contacts", contacts_command))
    application.add_handler(CommandHandler("birthdays", birthdays_command))
    # Profile command
    application.add_handler(CommandHandler("me", me_command))

    # Add message handler for text messages
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Add voice message handler
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))

    # Add photo message handler
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    return application


async def send_message(text: str, parse_mode: str = "HTML") -> None:
    """Send a proactive message to the user.
    Splits long messages to stay within Telegram's 4096-char limit."""
    from telegram import Bot

    MAX_LEN = 4096
    chunks: list[str] = []
    if len(text) <= MAX_LEN:
        chunks = [text]
    else:
        current = ""
        for line in text.split("\n"):
            candidate = (current + "\n" + line) if current else line
            if len(candidate) > MAX_LEN:
                if current:
                    chunks.append(current)
                while len(line) > MAX_LEN:
                    chunks.append(line[:MAX_LEN])
                    line = line[MAX_LEN:]
                current = line
            else:
                current = candidate
        if current:
            chunks.append(current)

    assert settings.telegram_bot_token, "TELEGRAM_BOT_TOKEN is required"
    bot = Bot(token=settings.telegram_bot_token)
    for chunk in chunks:
        try:
            await bot.send_message(
                chat_id=settings.telegram_user_id,
                text=chunk,
                parse_mode=parse_mode,
            )
        except BadRequest as e:
            if "Can't parse entities" in str(e):
                logger.warning(f"HTML parse failed in send_message, sending plain: {e}")
                await bot.send_message(
                    chat_id=settings.telegram_user_id,
                    text=chunk,
                )
            else:
                raise


def register_notification_handler() -> None:
    """Register send_message as a notification handler."""
    from src.notifications import register_handler

    register_handler(send_message)


# Error notification rate limiting (bounded to prevent memory leak)
_MAX_ERROR_ENTRIES = 100
_last_error_notification: dict[str, datetime] = {}
_ERROR_RATE_LIMIT_SECONDS = 60


async def notify_error(tool_name: str, error: Exception, error_id: str | None = None) -> None:
    """Send an error notification to the user.

    Rate limited to 1 per minute per tool to avoid spam.
    """
    global _last_error_notification

    # Rate limit by tool name
    now = datetime.now()
    if len(_last_error_notification) > _MAX_ERROR_ENTRIES:
        _last_error_notification.clear()
    if tool_name in _last_error_notification:
        elapsed = (now - _last_error_notification[tool_name]).total_seconds()
        if elapsed < _ERROR_RATE_LIMIT_SECONDS:
            logger.debug(f"Skipping error notification for {tool_name}, rate limited")
            return

    _last_error_notification[tool_name] = now

    if not error_id:
        error_id = str(uuid.uuid4())[:8]

    # Brief error message without sensitive details
    error_msg = str(error)[:100]

    text = f"⚠️ Error in <code>{tool_name}</code>\n{error_msg}\nID: <code>{error_id}</code>"

    try:
        await send_message(text)
    except Exception as e:
        logger.error(f"Failed to send error notification: {e}")
