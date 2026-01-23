from telegram import Update
from telegram.ext import ContextTypes

from src.agent.tools import get_agenda, list_tasks
from src.config import settings
from src.db import get_session
from src.db.models import ShoppingListType
from src.db.queries import (
    list_calendar_events_range,
    list_contacts,
    list_shopping_items,
    list_upcoming_birthdays,
)
from src.integrations.calendar import get_auth_url, complete_auth, is_calendar_connected
from datetime import datetime, timedelta

# Track if we're waiting for an auth code
_awaiting_auth_code = False

# Track last command output for agent context injection
_last_command_context: dict | None = None


def is_authorized(user_id: int) -> bool:
    """Check if the user is authorized."""
    return user_id == settings.telegram_user_id


async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /tasks command - list pending tasks."""
    if not update.message:
        return

    user_id = update.effective_user.id if update.effective_user else None
    if not user_id or not is_authorized(user_id):
        await update.message.reply_text("Not authorized.")
        return

    in_progress = list_tasks(status="in_progress")
    todo = list_tasks(status="todo")

    parts = ["<b>📋 Tasks</b>", ""]

    if in_progress and in_progress != "No tasks found.":
        parts.append("<b>🔄 In Progress</b>")
        parts.append(in_progress)
        parts.append("")

    if todo and todo != "No tasks found.":
        parts.append("<b>📝 To Do</b>")
        parts.append(todo)

    if len(parts) == 2:  # Only header
        parts.append("<i>No pending tasks!</i> 🎉")

    output = "\n".join(parts)
    _store_command_context("/tasks", output)
    await update.message.reply_text(output, parse_mode="HTML")


async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /today command - show today's agenda."""
    if not update.message:
        return

    user_id = update.effective_user.id if update.effective_user else None
    if not user_id or not is_authorized(user_id):
        await update.message.reply_text("Not authorized.")
        return

    today_str = datetime.now().strftime("%A, %b %d")
    result = get_agenda()

    output = f"📅 <b>{today_str}</b>\n\n{result}"
    _store_command_context("/today", output)
    await update.message.reply_text(output, parse_mode="HTML")


async def calendar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /calendar command - show upcoming calendar events."""
    if not update.message:
        return

    user_id = update.effective_user.id if update.effective_user else None
    if not user_id or not is_authorized(user_id):
        await update.message.reply_text("Not authorized.")
        return

    session = get_session()
    now = datetime.now(settings.timezone).replace(tzinfo=None)
    end = now + timedelta(days=7)

    events = list_calendar_events_range(session, now, end)
    session.close()

    if not events:
        await update.message.reply_text("📆 <i>No events in the next 7 days.</i>", parse_mode="HTML")
        return

    lines = ["<b>📆 Upcoming Events</b>", ""]

    current_day = None
    for event in events:
        event_day = event.start_time.strftime("%A, %b %d")
        if event_day != current_day:
            if current_day is not None:
                lines.append("")
            lines.append(f"<b>{event_day}</b>")
            current_day = event_day

        time_str = event.start_time.strftime("%H:%M")
        lines.append(f"  {time_str} — {event.title}")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def auth_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /auth command - connect Google Calendar."""
    global _awaiting_auth_code
    
    if not update.message:
        return

    user_id = update.effective_user.id if update.effective_user else None
    if not user_id or not is_authorized(user_id):
        await update.message.reply_text("Not authorized.")
        return

    # Check if already connected
    if is_calendar_connected():
        await update.message.reply_text("✓ Google Calendar is already connected!")
        return

    # Get auth URL
    auth_url = get_auth_url()
    if not auth_url:
        await update.message.reply_text(
            "❌ Cannot start auth: credentials.json not found.\n"
            "Upload it to credentials/credentials.json first."
        )
        return

    _awaiting_auth_code = True
    await update.message.reply_text(
        "<b>🔗 Google Calendar Authorization</b>\n\n"
        f'1. <a href="{auth_url}">Tap here to authorize</a>\n\n'
        "2. Sign in with your Google account and allow access\n\n"
        "3. You'll see a page that <b>won't load</b> - this is expected!\n\n"
        "4. <b>On iPhone:</b> Tap the URL bar at the top to see the full URL\n"
        "   <b>On desktop:</b> Look at the address bar\n\n"
        "5. Find <code>code=</code> in the URL and copy everything after it until the <code>&amp;</code>\n"
        "   Example URL: <code>localhost/?code=4/0AeanS0r...&amp;scope=...</code>\n"
        "   Copy: <code>4/0AeanS0r...</code> (the part between <code>code=</code> and <code>&amp;</code>)\n\n"
        "6. Send that code back to me here\n\n"
        "<i>Waiting for your code...</i>",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


async def handle_auth_code(code: str) -> str:
    """Process an authorization code. Returns response message."""
    global _awaiting_auth_code
    
    if complete_auth(code.strip()):
        _awaiting_auth_code = False
        return "✓ Google Calendar connected successfully!"
    else:
        return "❌ Invalid code. Try /auth again."


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


async def contacts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /contacts command - list all contacts."""
    if not update.message:
        return

    user_id = update.effective_user.id if update.effective_user else None
    if not user_id or not is_authorized(user_id):
        await update.message.reply_text("Not authorized.")
        return

    session = get_session()
    contacts = list_contacts(session)
    session.close()

    if not contacts:
        await update.message.reply_text("📇 No contacts saved yet.")
        return

    lines = ["<b>📇 Contacts</b>", ""]
    for contact in contacts:
        alias_info = f" <i>{contact.aliases}</i>" if contact.aliases else ""
        bday_info = f" 🎂 {contact.birthday.strftime('%b %d')}" if contact.birthday else ""
        lines.append(f"• <b>{contact.name}</b>{alias_info}{bday_info}")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def birthdays_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /birthdays command - show upcoming birthdays."""
    if not update.message:
        return

    user_id = update.effective_user.id if update.effective_user else None
    if not user_id or not is_authorized(user_id):
        await update.message.reply_text("Not authorized.")
        return

    session = get_session()
    contacts = list_upcoming_birthdays(session, within_days=30)
    session.close()

    if not contacts:
        await update.message.reply_text("🎂 No birthdays in the next 30 days.")
        return

    lines = ["<b>🎂 Upcoming Birthdays</b>", ""]
    today = datetime.now().date()

    for contact in contacts:
        if contact.birthday:
            bday = contact.birthday.date() if hasattr(contact.birthday, 'date') else contact.birthday
            this_year_bday = bday.replace(year=today.year)
            if this_year_bday < today:
                this_year_bday = bday.replace(year=today.year + 1)
            days_until = (this_year_bday - today).days

            if days_until == 0:
                when = "🔴 TODAY!"
            elif days_until == 1:
                when = "🟠 tomorrow"
            elif days_until <= 7:
                when = f"🟡 in {days_until} days"
            else:
                when = f"in {days_until} days"

            lines.append(f"• <b>{contact.name}</b> — {this_year_bday.strftime('%b %d')} ({when})")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


def _format_shopping_list(items, list_type: ShoppingListType, emoji: str, title: str) -> str:
    """Format a shopping list for display."""
    filtered = [i for i in items if i.shopping_list.list_type == list_type]

    if not filtered:
        return f"{emoji} <b>{title}</b>\n<i>Empty</i>"

    unchecked = [i for i in filtered if not i.is_complete]
    checked = [i for i in filtered if i.is_complete]

    lines = [f"{emoji} <b>{title}</b>", ""]

    for item in unchecked:
        recipient = ""
        if item.contact:
            recipient = f" → {item.contact.name}"
        elif item.recipient:
            recipient = f" → {item.recipient}"
        notes = f" <i>({item.notes})</i>" if item.notes else ""
        # Show quantity progress if target > 1
        qty_info = f" ({item.quantity_purchased}/{item.quantity_target})" if item.quantity_target > 1 else ""
        lines.append(f"⬜ {item.name}{qty_info}{recipient}{notes}")

    if checked:
        lines.append("")
        lines.append(f"<i>Checked ({len(checked)}):</i>")
        for item in checked[:3]:  # Show max 3 checked
            qty_info = f" ({item.quantity_purchased}/{item.quantity_target})" if item.quantity_target > 1 else ""
            lines.append(f"  ☑️ <s>{item.name}</s>{qty_info}")
        if len(checked) > 3:
            lines.append(f"  <i>...and {len(checked) - 3} more</i>")

    return "\n".join(lines)


async def groceries_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /groceries command - show groceries list."""
    if not update.message:
        return

    user_id = update.effective_user.id if update.effective_user else None
    if not user_id or not is_authorized(user_id):
        await update.message.reply_text("Not authorized.")
        return

    session = get_session()
    items = list_shopping_items(session, ShoppingListType.GROCERIES, include_checked=True)
    output = _format_shopping_list(items, ShoppingListType.GROCERIES, "🛒", "Groceries")
    session.close()

    _store_command_context("/groceries", output)
    await update.message.reply_text(output, parse_mode="HTML")


async def gifts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /gifts command - show gifts list."""
    if not update.message:
        return

    user_id = update.effective_user.id if update.effective_user else None
    if not user_id or not is_authorized(user_id):
        await update.message.reply_text("Not authorized.")
        return

    session = get_session()
    items = list_shopping_items(session, ShoppingListType.GIFTS, include_checked=True)
    output = _format_shopping_list(items, ShoppingListType.GIFTS, "🎁", "Gift Ideas")
    session.close()

    _store_command_context("/gifts", output)
    await update.message.reply_text(output, parse_mode="HTML")


async def wishlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /wishlist command - show wishlist."""
    if not update.message:
        return

    user_id = update.effective_user.id if update.effective_user else None
    if not user_id or not is_authorized(user_id):
        await update.message.reply_text("Not authorized.")
        return

    session = get_session()
    items = list_shopping_items(session, ShoppingListType.WISHLIST, include_checked=True)
    output = _format_shopping_list(items, ShoppingListType.WISHLIST, "✨", "Wishlist")
    session.close()

    _store_command_context("/wishlist", output)
    await update.message.reply_text(output, parse_mode="HTML")


async def lists_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /lists command - show all shopping lists."""
    if not update.message:
        return

    user_id = update.effective_user.id if update.effective_user else None
    if not user_id or not is_authorized(user_id):
        await update.message.reply_text("Not authorized.")
        return

    session = get_session()
    all_items = list_shopping_items(session, include_checked=True)
    
    parts = []
    for lt, emoji, title in [
        (ShoppingListType.GROCERIES, "🛒", "Groceries"),
        (ShoppingListType.GIFTS, "🎁", "Gift Ideas"),
        (ShoppingListType.WISHLIST, "✨", "Wishlist"),
    ]:
        parts.append(_format_shopping_list(all_items, lt, emoji, title))
    
    session.close()

    output = "\n\n".join(parts)
    _store_command_context("/lists", output)
    await update.message.reply_text(output, parse_mode="HTML")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command - show available commands."""
    if not update.message:
        return

    calendar_status = "✓" if is_calendar_connected() else "✗ (/auth)"

    help_text = f"""<b>📋 Commands</b>

<b>Tasks &amp; Agenda</b>
/tasks — pending tasks
/today — today's agenda
/calendar — upcoming events

<b>Shopping Lists</b>
/lists — all lists
/groceries — grocery items
/gifts — gift ideas
/wishlist — wishlist

<b>Contacts</b>
/contacts — all contacts
/birthdays — upcoming birthdays

<b>Settings</b>
/auth — connect Google Calendar
/help — this help

─────────────────
📅 Calendar: {calendar_status}

<i>Or just chat with me!</i>"""
    await update.message.reply_text(help_text, parse_mode="HTML")
