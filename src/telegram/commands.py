from datetime import datetime, timedelta
from functools import wraps
from typing import Callable

from telegram import Update
from telegram.ext import ContextTypes

from src.agent.tools import get_agenda, list_tasks
from src.config import settings
from src.db import session_scope
from src.db.models import ShoppingListType
from src.db.queries import (
    list_calendar_events_range,
    list_contacts,
    list_shopping_items,
    list_upcoming_birthdays,
)
from src.integrations.calendar import (
    get_auth_url,
    complete_auth,
    is_calendar_connected,
    is_calendar_connected_for_user,
)

# Track if we're waiting for an auth code
_awaiting_auth_code = False

# Track last command output for agent context injection
_last_command_context: dict | None = None


def is_authorized(user_id: int) -> bool:
    """Check if the user is authorized."""
    return user_id == settings.telegram_user_id


def require_auth(func: Callable) -> Callable:
    """Decorator that requires user authorization for command handlers."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        
        user_id = update.effective_user.id if update.effective_user else None
        if not user_id or not is_authorized(user_id):
            await update.message.reply_text("Not authorized.")
            return
        
        return await func(update, context)
    return wrapper


@require_auth
async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /tasks command - list pending tasks."""
    in_progress = list_tasks(status="in_progress")
    todo = list_tasks(status="todo")

    parts = ["Tasks", ""]

    if in_progress and in_progress != "No tasks found. Try saying 'remind me to...' to create one!":
        parts.append("In Progress")
        parts.append(in_progress)
        parts.append("")

    if todo and todo != "No tasks found. Try saying 'remind me to...' to create one!":
        parts.append("To Do")
        parts.append(todo)

    if len(parts) == 2:  # Only header
        parts.append("No pending tasks!")

    output = "\n".join(parts)
    _store_command_context("/tasks", output)
    await update.message.reply_text(output)


@require_auth
async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /today command - show today's agenda."""
    today_str = datetime.now(settings.timezone).strftime("%A, %b %d")
    result = get_agenda()

    output = f"{today_str}\n\n{result}"
    _store_command_context("/today", output)
    await update.message.reply_text(output)


@require_auth
async def calendar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /calendar command - show upcoming calendar events."""
    with session_scope() as session:
        now = datetime.now(settings.timezone).replace(tzinfo=None)
        end = now + timedelta(days=7)

        events = list_calendar_events_range(session, now, end)

        if not events:
            await update.message.reply_text("No events in the next 7 days.")
            return

        lines = ["Upcoming Events", ""]

        current_day = None
        for event in events:
            event_day = event.start_time.strftime("%A, %b %d")
            if event_day != current_day:
                if current_day is not None:
                    lines.append("")
                lines.append(event_day)
                current_day = event_day

            time_str = event.start_time.strftime("%H:%M")
            lines.append(f"  {time_str} - {event.title}")

        await update.message.reply_text("\n".join(lines))


async def auth_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /auth command - connect Google Calendar via web OAuth."""
    if not update.message:
        return

    user_id = update.effective_user.id if update.effective_user else None
    if not user_id or not is_authorized(user_id):
        await update.message.reply_text("Not authorized.")
        return

    # Check if already connected (either file-based or DB-based)
    if is_calendar_connected() or is_calendar_connected_for_user(user_id):
        await update.message.reply_text("Google Calendar is already connected!")
        return

    # Generate web OAuth URL
    auth_url = f"{settings.web_base_url}/auth/start/{user_id}"

    await update.message.reply_text(
        "Google Calendar Authorization\n\n"
        f"Click this link to connect:\n{auth_url}\n\n"
        "After signing in, you'll see a success page and can close it.",
    )


async def handle_auth_code(code: str) -> str:
    """Process an authorization code. Returns response message."""
    global _awaiting_auth_code
    
    if complete_auth(code.strip()):
        _awaiting_auth_code = False
        return "Google Calendar connected successfully!"
    else:
        return "Invalid code. Try /auth again."


def is_awaiting_auth_code() -> bool:
    """Check if we're waiting for an auth code."""
    return _awaiting_auth_code


def cancel_auth() -> None:
    """Cancel pending auth."""
    global _awaiting_auth_code
    _awaiting_auth_code = False


def get_last_command_context() -> dict | None:
    """Get the last command context if recent (< 5 min)."""
    global _last_command_context
    if not _last_command_context:
        return None
    # Check if it's still recent
    elapsed = (datetime.now() - _last_command_context["time"]).total_seconds()
    if elapsed > 300:  # 5 minutes
        _last_command_context = None
        return None
    return _last_command_context


def clear_command_context() -> None:
    """Clear the stored command context."""
    global _last_command_context
    _last_command_context = None


def _store_command_context(command: str, output: str) -> None:
    """Store command output for agent context injection."""
    global _last_command_context
    _last_command_context = {
        "command": command,
        "output": output,
        "time": datetime.now(),
    }


@require_auth
async def contacts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /contacts command - list all contacts."""
    with session_scope() as session:
        contacts = list_contacts(session)

        if not contacts:
            await update.message.reply_text("No contacts saved yet.")
            return

        lines = ["Contacts", ""]
        for contact in contacts:
            alias_info = f" ({contact.aliases})" if contact.aliases else ""
            bday_info = f" {contact.birthday.strftime('%b %d')}" if contact.birthday else ""
            lines.append(f"  #{contact.id} {contact.name}{alias_info}{bday_info}")

        await update.message.reply_text("\n".join(lines))


@require_auth
async def birthdays_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /birthdays command - show upcoming birthdays."""
    with session_scope() as session:
        contacts = list_upcoming_birthdays(session, within_days=30)

        if not contacts:
            await update.message.reply_text("No birthdays in the next 30 days.")
            return

        lines = ["Upcoming Birthdays", ""]
        today = datetime.now(settings.timezone).date()

        for contact in contacts:
            if contact.birthday:
                bday = contact.birthday.date() if hasattr(contact.birthday, 'date') else contact.birthday
                this_year_bday = bday.replace(year=today.year)
                if this_year_bday < today:
                    this_year_bday = bday.replace(year=today.year + 1)
                days_until = (this_year_bday - today).days

                if days_until == 0:
                    when = "TODAY!"
                elif days_until == 1:
                    when = "tomorrow"
                elif days_until <= 7:
                    when = f"in {days_until} days"
                else:
                    when = f"in {days_until} days"

                lines.append(f"  {contact.name} - {this_year_bday.strftime('%b %d')} ({when})")

        await update.message.reply_text("\n".join(lines))


def _format_shopping_list(items, list_type: ShoppingListType, title: str) -> str:
    """Format a shopping list for display."""
    filtered = [i for i in items if i.shopping_list.list_type == list_type]

    if not filtered:
        return f"{title}\nEmpty"

    unchecked = [i for i in filtered if not i.is_complete]
    checked = [i for i in filtered if i.is_complete]

    lines = [title, ""]

    for item in unchecked:
        recipient_name = item.contact.name if item.contact else item.recipient
        recipient = f" -> {recipient_name}" if recipient_name else ""
        # Hide notes if redundant (mentions recipient or is just "Gift idea for X")
        notes = ""
        if item.notes and recipient_name:
            if recipient_name.lower() not in item.notes.lower():
                notes = f" ({item.notes})"
        elif item.notes:
            notes = f" ({item.notes})"
        # Show quantity progress if target > 1
        qty_info = f" ({item.quantity_purchased}/{item.quantity_target})" if item.quantity_target > 1 else ""
        lines.append(f"[ ] #{item.id} {item.name}{qty_info}{recipient}{notes}")

    if checked:
        lines.append("")
        lines.append(f"Checked ({len(checked)}):")
        for item in checked[:3]:  # Show max 3 checked
            qty_info = f" ({item.quantity_purchased}/{item.quantity_target})" if item.quantity_target > 1 else ""
            lines.append(f"  [x] #{item.id} {item.name}{qty_info}")
        if len(checked) > 3:
            lines.append(f"  ...and {len(checked) - 3} more")

    return "\n".join(lines)


@require_auth
async def groceries_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /groceries command - show groceries list."""
    with session_scope() as session:
        items = list_shopping_items(session, ShoppingListType.GROCERIES, include_checked=True)
        output = _format_shopping_list(items, ShoppingListType.GROCERIES, "Groceries")

    _store_command_context("/groceries", output)
    await update.message.reply_text(output)


@require_auth
async def gifts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /gifts command - show gifts list."""
    with session_scope() as session:
        items = list_shopping_items(session, ShoppingListType.GIFTS, include_checked=True)
        output = _format_shopping_list(items, ShoppingListType.GIFTS, "Gift Ideas")

    _store_command_context("/gifts", output)
    await update.message.reply_text(output)


@require_auth
async def wishlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /wishlist command - show wishlist."""
    with session_scope() as session:
        items = list_shopping_items(session, ShoppingListType.WISHLIST, include_checked=True)
        output = _format_shopping_list(items, ShoppingListType.WISHLIST, "Wishlist")

    _store_command_context("/wishlist", output)
    await update.message.reply_text(output)


@require_auth
async def lists_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /lists command - show all shopping lists."""
    with session_scope() as session:
        all_items = list_shopping_items(session, include_checked=True)
        
        parts = []
        for lt, title in [
            (ShoppingListType.GROCERIES, "Groceries"),
            (ShoppingListType.GIFTS, "Gift Ideas"),
            (ShoppingListType.WISHLIST, "Wishlist"),
        ]:
            parts.append(_format_shopping_list(all_items, lt, title))

    output = "\n\n".join(parts)
    _store_command_context("/lists", output)
    await update.message.reply_text(output)


@require_auth
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command - show available commands."""
    calendar_status = "connected" if is_calendar_connected() else "not connected (/auth)"

    help_text = f"""Commands

Tasks & Agenda
/tasks - pending tasks
/today - today's agenda
/calendar - upcoming events

Shopping Lists
/lists - all lists
/groceries - grocery items
/gifts - gift ideas
/wishlist - wishlist

Contacts
/contacts - all contacts
/birthdays - upcoming birthdays

Settings
/auth - connect Google Calendar
/help - this help

---
Calendar: {calendar_status}

Or just chat with me!"""
    await update.message.reply_text(help_text)
