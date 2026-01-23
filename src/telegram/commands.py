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

    parts = ["📋 *Tasks*", ""]
    
    if in_progress and in_progress != "No tasks found.":
        parts.append("🔄 *In Progress*")
        parts.append(in_progress)
        parts.append("")
    
    if todo and todo != "No tasks found.":
        parts.append("📝 *To Do*")
        parts.append(todo)

    if len(parts) == 2:  # Only header
        parts.append("_No pending tasks!_ 🎉")

    await update.message.reply_text("\n".join(parts), parse_mode="Markdown")


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
    
    formatted = f"📅 *{today_str}*\n\n{result}"
    await update.message.reply_text(formatted, parse_mode="Markdown")


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
        await update.message.reply_text("📆 _No events in the next 7 days._", parse_mode="Markdown")
        return

    lines = ["📆 *Upcoming Events*", ""]
    
    current_day = None
    for event in events:
        event_day = event.start_time.strftime("%A, %b %d")
        if event_day != current_day:
            if current_day is not None:
                lines.append("")
            lines.append(f"*{event_day}*")
            current_day = event_day
        
        time_str = event.start_time.strftime("%H:%M")
        lines.append(f"  {time_str} — {event.title}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


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
        "🔗 *Google Calendar Authorization*\n\n"
        f"1. [Tap here to authorize]({auth_url})\n\n"
        "2. Sign in with your Google account and allow access\n\n"
        "3. You'll see a page that *won't load* - this is expected!\n\n"
        "4. *On iPhone:* Tap the URL bar at the top to see the full URL\n"
        "   *On desktop:* Look at the address bar\n\n"
        "5. Find `code=` in the URL and copy everything after it until the `&`\n"
        "   Example URL: `localhost/?code=4/0AeanS0r...&scope=...`\n"
        "   Copy: `4/0AeanS0r...` (the part between `code=` and `&`)\n\n"
        "6. Send that code back to me here\n\n"
        "_Waiting for your code..._",
        parse_mode="Markdown",
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

    lines = ["📇 *Contacts*", ""]
    for contact in contacts:
        alias_info = f" _{contact.aliases}_" if contact.aliases else ""
        bday_info = f" 🎂 {contact.birthday.strftime('%b %d')}" if contact.birthday else ""
        lines.append(f"• *{contact.name}*{alias_info}{bday_info}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


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

    lines = ["🎂 *Upcoming Birthdays*", ""]
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

            lines.append(f"• *{contact.name}* — {this_year_bday.strftime('%b %d')} ({when})")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


def _format_shopping_list(items, list_type: ShoppingListType, emoji: str, title: str) -> str:
    """Format a shopping list for display."""
    filtered = [i for i in items if i.shopping_list.list_type == list_type]
    
    if not filtered:
        return f"{emoji} *{title}*\n_Empty_"

    unchecked = [i for i in filtered if not i.checked]
    checked = [i for i in filtered if i.checked]

    lines = [f"{emoji} *{title}*", ""]
    
    for item in unchecked:
        recipient = ""
        if item.contact:
            recipient = f" → {item.contact.name}"
        elif item.recipient:
            recipient = f" → {item.recipient}"
        notes = f" _({item.notes})_" if item.notes else ""
        lines.append(f"⬜ {item.name}{recipient}{notes}")

    if checked:
        lines.append("")
        lines.append(f"_Checked ({len(checked)}):_")
        for item in checked[:3]:  # Show max 3 checked
            lines.append(f"  ☑️ ~{item.name}~")
        if len(checked) > 3:
            lines.append(f"  _...and {len(checked) - 3} more_")

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
    result = _format_shopping_list(items, ShoppingListType.GROCERIES, "🛒", "Groceries")
    session.close()

    await update.message.reply_text(result, parse_mode="Markdown")


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
    result = _format_shopping_list(items, ShoppingListType.GIFTS, "🎁", "Gift Ideas")
    session.close()

    await update.message.reply_text(result, parse_mode="Markdown")


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
    result = _format_shopping_list(items, ShoppingListType.WISHLIST, "✨", "Wishlist")
    session.close()

    await update.message.reply_text(result, parse_mode="Markdown")


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
    
    await update.message.reply_text("\n\n".join(parts), parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command - show available commands."""
    if not update.message:
        return

    calendar_status = "✓" if is_calendar_connected() else "✗ (/auth)"

    help_text = f"""📋 *Commands*

*Tasks & Agenda*
/tasks — pending tasks
/today — today's agenda
/calendar — upcoming events

*Shopping Lists*
/lists — all lists
/groceries — grocery items
/gifts — gift ideas
/wishlist — wishlist

*Contacts*
/contacts — all contacts
/birthdays — upcoming birthdays

*Settings*
/auth — connect Google Calendar
/help — this help

─────────────────
📅 Calendar: {calendar_status}

_Or just chat with me!_"""
    await update.message.reply_text(help_text, parse_mode="Markdown")
