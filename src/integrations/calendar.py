import logging
from datetime import datetime
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from src.config import settings
from src.db import get_session
from src.db.queries import sync_calendar_event

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def get_credentials() -> Optional[Credentials]:
    """Get or refresh Google Calendar credentials."""
    creds = None

    # Load existing token
    if settings.google_token_path.exists():
        creds = Credentials.from_authorized_user_file(
            str(settings.google_token_path), SCOPES
        )

    # Refresh or get new credentials
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif not creds or not creds.valid:
        if not settings.google_credentials_path.exists():
            logger.warning("Google credentials file not found")
            return None

        flow = InstalledAppFlow.from_client_secrets_file(
            str(settings.google_credentials_path), SCOPES
        )
        creds = flow.run_local_server(port=0)

    # Save credentials
    if creds:
        settings.google_token_path.parent.mkdir(parents=True, exist_ok=True)
        with open(settings.google_token_path, "w") as token:
            token.write(creds.to_json())

    return creds


def fetch_events(start: datetime, end: datetime) -> list[dict]:
    """Fetch calendar events from Google Calendar.

    Args:
        start: Start of time range.
        end: End of time range.

    Returns:
        List of event dictionaries.
    """
    creds = get_credentials()
    if not creds:
        return []

    service = build("calendar", "v3", credentials=creds)

    events_result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=start.isoformat() + "Z",
            timeMax=end.isoformat() + "Z",
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    return events_result.get("items", [])


def sync_events(start: datetime, end: datetime) -> int:
    """Sync calendar events to local database.

    Args:
        start: Start of time range.
        end: End of time range.

    Returns:
        Number of events synced.
    """
    events = fetch_events(start, end)
    session = get_session()

    count = 0
    for event in events:
        google_id = event.get("id")
        title = event.get("summary", "Untitled")

        # Parse start/end times
        start_data = event.get("start", {})
        end_data = event.get("end", {})

        # Handle all-day events vs timed events
        if "dateTime" in start_data:
            start_time = datetime.fromisoformat(start_data["dateTime"].replace("Z", "+00:00"))
            end_time = datetime.fromisoformat(end_data["dateTime"].replace("Z", "+00:00"))
        else:
            # All-day event
            start_time = datetime.fromisoformat(start_data["date"])
            end_time = datetime.fromisoformat(end_data["date"])

        # Remove timezone info for storage
        start_time = start_time.replace(tzinfo=None)
        end_time = end_time.replace(tzinfo=None)

        sync_calendar_event(session, google_id, title, start_time, end_time)
        count += 1

    session.close()
    return count


def create_event(
    title: str,
    start: datetime,
    end: datetime,
    description: Optional[str] = None,
) -> Optional[str]:
    """Create a new calendar event.

    Args:
        title: Event title.
        start: Event start time.
        end: Event end time.
        description: Optional event description.

    Returns:
        Google event ID if successful, None otherwise.
    """
    creds = get_credentials()
    if not creds:
        return None

    service = build("calendar", "v3", credentials=creds)

    event = {
        "summary": title,
        "start": {"dateTime": start.isoformat(), "timeZone": str(settings.timezone)},
        "end": {"dateTime": end.isoformat(), "timeZone": str(settings.timezone)},
    }

    if description:
        event["description"] = description

    result = service.events().insert(calendarId="primary", body=event).execute()
    return result.get("id")
