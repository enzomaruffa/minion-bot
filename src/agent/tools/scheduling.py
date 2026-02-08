from datetime import datetime, timedelta

from src.config import settings
from src.db import session_scope
from src.db.queries import get_user_profile
from src.integrations.calendar import _get_service_with_fallback


def find_free_slot(
    duration_minutes: int,
    days_ahead: int = 7,
    prefer_morning: bool = False,
) -> str:
    """Find available time slots in the calendar.

    Args:
        duration_minutes: How long the slot needs to be (e.g. 60 for 1 hour).
        days_ahead: How many days ahead to search (default 7).
        prefer_morning: If True, prefer morning slots.

    Returns:
        Formatted list of up to 5 available slots.
    """
    user_id = settings.telegram_user_id
    service = _get_service_with_fallback(telegram_user_id=user_id)
    if not service:
        return "Calendar not connected. Use /auth to connect Google Calendar."

    # Get work hours from profile
    work_start = 9
    work_end = 18
    with session_scope() as session:
        profile = get_user_profile(session)
        if profile:
            if profile.work_start_hour is not None:
                work_start = profile.work_start_hour
            if profile.work_end_hour is not None:
                work_end = profile.work_end_hour

    now = datetime.now(settings.timezone)
    # Start from next hour boundary
    start_search = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    end_search = now + timedelta(days=days_ahead)

    # FreeBusy query
    body = {
        "timeMin": start_search.isoformat(),
        "timeMax": end_search.isoformat(),
        "items": [{"id": "primary"}],
    }

    try:
        result = service.freebusy().query(body=body).execute()
    except Exception as e:
        return f"Failed to query calendar: {e}"

    busy_periods = result.get("calendars", {}).get("primary", {}).get("busy", [])

    # Parse busy periods
    busy = []
    for period in busy_periods:
        b_start = datetime.fromisoformat(period["start"].replace("Z", "+00:00"))
        b_end = datetime.fromisoformat(period["end"].replace("Z", "+00:00"))
        # Convert to local timezone
        b_start = b_start.astimezone(settings.timezone)
        b_end = b_end.astimezone(settings.timezone)
        busy.append((b_start, b_end))

    busy.sort(key=lambda x: x[0])

    # Find free slots day by day
    slots = []
    current_day = start_search.date()
    end_day = end_search.date()

    while current_day <= end_day and len(slots) < 5:
        # Work window for this day
        day_start = datetime(current_day.year, current_day.month, current_day.day, work_start, tzinfo=settings.timezone)
        day_end = datetime(current_day.year, current_day.month, current_day.day, work_end, tzinfo=settings.timezone)

        # Skip past times for today
        if day_start < now:
            day_start = start_search if current_day == now.date() else day_start

        if day_start >= day_end:
            current_day += timedelta(days=1)
            continue

        # Get busy periods that overlap this day
        day_busy = [(max(bs, day_start), min(be, day_end)) for bs, be in busy if bs < day_end and be > day_start]
        day_busy.sort(key=lambda x: x[0])

        # Find gaps
        cursor = day_start
        for bs, be in day_busy:
            if bs > cursor:
                gap_minutes = (bs - cursor).total_seconds() / 60
                if gap_minutes >= duration_minutes:
                    slots.append((cursor, bs, gap_minutes))
                    if len(slots) >= 5:
                        break
            cursor = max(cursor, be)

        # Gap after last busy period
        if len(slots) < 5 and cursor < day_end:
            gap_minutes = (day_end - cursor).total_seconds() / 60
            if gap_minutes >= duration_minutes:
                slots.append((cursor, day_end, gap_minutes))

        current_day += timedelta(days=1)

    if not slots:
        return f"<i>No free slots of {duration_minutes} min found in the next {days_ahead} days.</i>"

    # Sort: morning preference
    if prefer_morning:
        slots.sort(key=lambda x: x[0].hour)

    lines = [f"<b>📅 Free Slots ({duration_minutes} min)</b>"]
    for slot_start, slot_end, gap_min in slots[:5]:
        day_str = slot_start.strftime("%a %b %d")
        start_str = slot_start.strftime("%H:%M")
        end_str = slot_end.strftime("%H:%M")
        hours = gap_min / 60
        gap_label = f"{hours:.1f}h free" if hours >= 1 else f"{int(gap_min)}min free"
        lines.append(f"• {day_str}: {start_str}–{end_str} ({gap_label})")

    lines.append("\n<i>Want me to create an event in one of these slots?</i>")
    return "\n".join(lines)
