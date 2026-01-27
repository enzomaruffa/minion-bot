from datetime import datetime, timedelta
from typing import Optional

from src.integrations.calendar import (
    test_connection,
    create_event,
    update_event,
    delete_event,
    list_upcoming_events,
    is_calendar_connected,
    is_calendar_connected_for_user,
)
from src.utils import parse_date
from src.config import settings


def _get_user_id() -> int:
    """Get the configured telegram user ID for calendar auth."""
    return settings.telegram_user_id


def _is_connected() -> bool:
    """Check if calendar is connected (per-user or file-based)."""
    user_id = _get_user_id()
    return is_calendar_connected_for_user(user_id) or is_calendar_connected()


def test_calendar() -> str:
    """Test the Google Calendar connection.

    Returns:
        Connection status and calendar info.
    """
    result = test_connection(telegram_user_id=_get_user_id())

    if result["ok"]:
        return (
            f"✓ <b>Calendar connected</b>\n"
            f"• Calendar: <i>{result['calendar_name']}</i>\n"
            f"• Timezone: <code>{result['timezone']}</code>"
        )
    else:
        return f"✗ Calendar not connected: <i>{result['error']}</i>"


def create_calendar_event(
    title: str,
    start: str,
    end: Optional[str] = None,
    duration_minutes: Optional[int] = 60,
    description: Optional[str] = None,
    location: Optional[str] = None,
) -> str:
    """Create a new calendar event.

    Args:
        title: Event title/summary.
        start: Start time (natural language like "tomorrow at 3pm" or ISO format).
        end: End time (optional - if not provided, uses duration_minutes).
        duration_minutes: Duration in minutes if end not specified. Default 60.
        description: Optional event description.
        location: Optional event location.

    Returns:
        Confirmation with event details or error message.
    """
    if not _is_connected():
        return "Calendar not connected. Use /auth to connect Google Calendar."

    start_dt = parse_date(start)
    if not start_dt:
        return f"Could not parse start time: {start}"

    if end:
        end_dt = parse_date(end)
        if not end_dt:
            return f"Could not parse end time: {end}"
    else:
        end_dt = start_dt + timedelta(minutes=duration_minutes or 60)

    result = create_event(
        title=title,
        start=start_dt,
        end=end_dt,
        description=description,
        location=location,
        telegram_user_id=_get_user_id(),
    )
    
    if result:
        return (
            f"✓ <b>Event created</b>\n"
            f"• {title}\n"
            f"• {start_dt.strftime('%a %b %d, %H:%M')} – {end_dt.strftime('%H:%M')}\n"
            f"• ID: <code>{result['id'][:12]}</code>"
        )
    else:
        return "✗ Failed to create event. Check calendar connection."


def update_calendar_event(
    event_id: str,
    title: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
) -> str:
    """Update an existing calendar event.

    Args:
        event_id: The Google Calendar event ID (shown in list_calendar_events output).
        title: New title (optional).
        start: New start time (optional).
        end: New end time (optional).
        description: New description (optional).
        location: New location (optional).

    Returns:
        Confirmation or error message.
    """
    if not _is_connected():
        return "Calendar not connected. Use /auth to connect Google Calendar."

    start_dt = parse_date(start) if start else None
    end_dt = parse_date(end) if end else None

    result = update_event(
        event_id=event_id,
        title=title,
        start=start_dt,
        end=end_dt,
        description=description,
        location=location,
        telegram_user_id=_get_user_id(),
    )
    
    if result:
        return f"✓ Event updated: {result['id']}"
    else:
        return f"Failed to update event {event_id}. Check if it exists."


def delete_calendar_event(event_id: str) -> str:
    """Delete a calendar event.

    Args:
        event_id: The Google Calendar event ID (shown in list_calendar_events output).

    Returns:
        Confirmation or error message.
    """
    if not _is_connected():
        return "Calendar not connected. Use /auth to connect Google Calendar."

    if delete_event(event_id, telegram_user_id=_get_user_id()):
        return f"✓ Event deleted: {event_id}"
    else:
        return f"Failed to delete event {event_id}. Check if it exists."


def list_calendar_events(days: int = 7) -> str:
    """List upcoming calendar events.

    Args:
        days: Number of days to look ahead. Default 7.

    Returns:
        Formatted list of upcoming events with event IDs.
    """
    if not _is_connected():
        return "Calendar not connected. Use /auth to connect Google Calendar."

    events = list_upcoming_events(days=days, telegram_user_id=_get_user_id())
    
    if not events:
        return f"<i>No events in the next {days} days</i>"

    lines = [f"<b>📆 Events</b> <i>({days} days)</i>", ""]

    current_date = None
    for event in events:
        # Parse start time
        start_data = event.get("start", {})
        if "dateTime" in start_data:
            start = datetime.fromisoformat(start_data["dateTime"].replace("Z", "+00:00"))
            time_str = start.strftime("%H:%M")
            is_all_day = False
        else:
            start = datetime.fromisoformat(start_data.get("date", ""))
            time_str = "All day"
            is_all_day = True

        # Group by date
        date_str = start.strftime("%a %b %d")
        if date_str != current_date:
            if current_date is not None:
                lines.append("")
            current_date = date_str
            lines.append(f"<b>{date_str}</b>")

        title = event.get("summary", "Untitled")
        event_id = event.get("id", "")[:12]  # Truncate ID for display

        if is_all_day:
            lines.append(f"• {title} <i>(all day)</i> <code>{event_id}</code>")
        else:
            lines.append(f"• {time_str}  {title} <code>{event_id}</code>")

    return "\n".join(lines)
