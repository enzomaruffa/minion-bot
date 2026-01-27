import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from src.config import settings
from src.db import get_session, session_scope
from src.db.queries import (
    get_user_calendar_token,
    sync_calendar_event,
    update_user_calendar_token_credentials,
)

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]  # Full read/write access

# Store pending auth flow for bot-based authentication
_pending_flow: Optional[InstalledAppFlow] = None


def get_auth_url() -> Optional[str]:
    """Generate OAuth URL for bot-based authentication.
    
    Returns:
        Authorization URL to send to user, or None if credentials file missing.
    """
    global _pending_flow
    
    logger.info(f"Checking for credentials at: {settings.google_credentials_path}")
    logger.info(f"Credentials file exists: {settings.google_credentials_path.exists()}")
    
    if not settings.google_credentials_path.exists():
        logger.warning("Google credentials file not found at %s", settings.google_credentials_path)
        return None
    
    try:
        _pending_flow = InstalledAppFlow.from_client_secrets_file(
            str(settings.google_credentials_path), 
            SCOPES,
            redirect_uri="http://localhost"  # Localhost redirect - user copies code from URL
        )
        
        auth_url, _ = _pending_flow.authorization_url(
            prompt="select_account consent",
            access_type="offline",  # Get refresh token
        )
        logger.info("Generated OAuth URL successfully")
        return auth_url
    except Exception as e:
        logger.exception(f"Failed to create auth flow: {e}")
        return None


def complete_auth(code: str) -> bool:
    """Complete OAuth flow with authorization code from user.
    
    Args:
        code: The authorization code from Google.
        
    Returns:
        True if successful, False otherwise.
    """
    global _pending_flow
    
    logger.info(f"Completing auth with code: {code[:20]}...")
    
    if not _pending_flow:
        logger.error("No pending auth flow. Call get_auth_url first.")
        return False
    
    try:
        _pending_flow.fetch_token(code=code)
        creds = _pending_flow.credentials
        
        # Save credentials
        logger.info(f"Saving token to: {settings.google_token_path}")
        settings.google_token_path.parent.mkdir(parents=True, exist_ok=True)
        with open(settings.google_token_path, "w") as token:
            token.write(creds.to_json())
        
        logger.info("Google Calendar authorization successful, token saved")
        _pending_flow = None
        return True
    except Exception as e:
        logger.exception(f"Failed to complete auth: {e}")
        _pending_flow = None
        return False


def is_calendar_connected() -> bool:
    """Check if calendar is connected and credentials are valid."""
    if not settings.google_token_path.exists():
        return False

    try:
        creds = Credentials.from_authorized_user_file(
            str(settings.google_token_path), SCOPES
        )
        return creds and creds.valid
    except Exception:
        return False


def is_calendar_connected_for_user(telegram_user_id: int) -> bool:
    """Check if calendar is connected for a specific Telegram user."""
    with session_scope() as session:
        token = get_user_calendar_token(session, telegram_user_id)
        if not token:
            return False

        # Check if we have credentials that can be used
        # (either valid or can be refreshed)
        return bool(token.access_token and (token.refresh_token or not _is_token_expired(token)))


def _is_token_expired(token) -> bool:
    """Check if a token is expired."""
    if not token.expiry:
        return False
    return token.expiry < datetime.utcnow()


def get_credentials_for_user(telegram_user_id: int) -> Optional[Credentials]:
    """Get or refresh Google Calendar credentials for a specific user.

    Args:
        telegram_user_id: The Telegram user ID.

    Returns:
        Credentials object if available and valid/refreshable, None otherwise.
    """
    with session_scope() as session:
        token = get_user_calendar_token(session, telegram_user_id)
        if not token:
            logger.debug(f"No token found for user {telegram_user_id}")
            return None

        # Parse scopes from JSON
        try:
            scopes = json.loads(token.scopes) if token.scopes else SCOPES
        except json.JSONDecodeError:
            scopes = SCOPES

        # Create credentials object
        creds = Credentials(
            token=token.access_token,
            refresh_token=token.refresh_token,
            token_uri=token.token_uri,
            client_id=token.client_id,
            client_secret=token.client_secret,
            scopes=scopes,
            expiry=token.expiry,
        )

        # Refresh if expired
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                # Save updated token
                update_user_calendar_token_credentials(
                    session,
                    telegram_user_id,
                    access_token=creds.token,
                    expiry=creds.expiry,
                )
                logger.info(f"Refreshed token for user {telegram_user_id}")
            except Exception as e:
                logger.exception(f"Failed to refresh token for user {telegram_user_id}: {e}")
                return None

        return creds if creds.valid else None


def get_service_for_user(telegram_user_id: int):
    """Get Google Calendar service object for a specific user.

    Args:
        telegram_user_id: The Telegram user ID.

    Returns:
        Calendar service object if credentials available, None otherwise.
    """
    creds = get_credentials_for_user(telegram_user_id)
    if not creds:
        return None
    return build("calendar", "v3", credentials=creds)


def get_credentials(headless: bool = False) -> Optional[Credentials]:
    """Get or refresh Google Calendar credentials.
    
    Args:
        headless: If True, use console-based auth flow (prints URL to visit).
    """
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
            logger.warning("Google credentials file not found at %s", settings.google_credentials_path)
            return None

        flow = InstalledAppFlow.from_client_secrets_file(
            str(settings.google_credentials_path), SCOPES
        )
        
        if headless:
            # For headless servers - prints URL to visit
            creds = flow.run_console()
        else:
            creds = flow.run_local_server(port=0)

    # Save credentials
    if creds:
        settings.google_token_path.parent.mkdir(parents=True, exist_ok=True)
        with open(settings.google_token_path, "w") as token:
            token.write(creds.to_json())

    return creds


def fetch_events(
    start: datetime, end: datetime, telegram_user_id: int | None = None
) -> list[dict]:
    """Fetch calendar events from Google Calendar.

    Args:
        start: Start of time range.
        end: End of time range.
        telegram_user_id: Optional user ID for per-user auth.

    Returns:
        List of event dictionaries. Empty list on error.
    """
    try:
        service = _get_service_with_fallback(telegram_user_id)
        if not service:
            return []

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
    except Exception as e:
        logger.exception(f"Failed to fetch calendar events: {e}")
        return []


def sync_events(start: datetime, end: datetime) -> int:
    """Sync calendar events to local database.

    Args:
        start: Start of time range.
        end: End of time range.

    Returns:
        Number of events synced.
    """
    from src.db import session_scope
    
    events = fetch_events(start, end)
    
    count = 0
    with session_scope() as session:
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

    return count


def get_service():
    """Get Google Calendar service object (file-based auth)."""
    creds = get_credentials()
    if not creds:
        return None
    return build("calendar", "v3", credentials=creds)


def _get_service_with_fallback(telegram_user_id: int | None = None):
    """Get Calendar service, preferring per-user DB auth with file-based fallback.

    Args:
        telegram_user_id: Optional user ID for per-user auth.

    Returns:
        Calendar service object or None.
    """
    # Try per-user auth first if user_id provided
    if telegram_user_id:
        service = get_service_for_user(telegram_user_id)
        if service:
            logger.debug(f"Using per-user auth for user {telegram_user_id}")
            return service
        logger.debug(f"No DB token for user {telegram_user_id}, falling back to file-based")

    # Fall back to file-based auth
    return get_service()


def test_connection(telegram_user_id: int | None = None) -> dict:
    """Test the calendar connection.

    Args:
        telegram_user_id: Optional user ID for per-user auth.

    Returns:
        Dict with status and calendar info, or error message.
    """
    try:
        service = _get_service_with_fallback(telegram_user_id)
        if not service:
            return {"ok": False, "error": "Not authenticated. Use /auth to connect."}

        # Try to get calendar info
        calendar = service.calendars().get(calendarId="primary").execute()

        return {
            "ok": True,
            "calendar_name": calendar.get("summary", "Primary"),
            "timezone": calendar.get("timeZone", "Unknown"),
        }
    except Exception as e:
        logger.exception(f"Calendar connection test failed: {e}")
        return {"ok": False, "error": str(e)}


def create_event(
    title: str,
    start: datetime,
    end: datetime,
    description: Optional[str] = None,
    location: Optional[str] = None,
    telegram_user_id: int | None = None,
) -> Optional[dict]:
    """Create a new calendar event.

    Args:
        title: Event title.
        start: Event start time.
        end: Event end time.
        description: Optional event description.
        location: Optional event location.
        telegram_user_id: Optional user ID for per-user auth.

    Returns:
        Event dict with id and htmlLink if successful, None otherwise.
    """
    service = _get_service_with_fallback(telegram_user_id)
    if not service:
        return None

    event = {
        "summary": title,
        "start": {"dateTime": start.isoformat(), "timeZone": str(settings.timezone)},
        "end": {"dateTime": end.isoformat(), "timeZone": str(settings.timezone)},
    }

    if description:
        event["description"] = description
    if location:
        event["location"] = location

    result = service.events().insert(calendarId="primary", body=event).execute()
    return {"id": result.get("id"), "link": result.get("htmlLink")}


def update_event(
    event_id: str,
    title: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    telegram_user_id: int | None = None,
) -> Optional[dict]:
    """Update an existing calendar event.

    Args:
        event_id: Google event ID.
        title: New title (optional).
        start: New start time (optional).
        end: New end time (optional).
        description: New description (optional).
        location: New location (optional).
        telegram_user_id: Optional user ID for per-user auth.

    Returns:
        Updated event dict if successful, None otherwise.
    """
    service = _get_service_with_fallback(telegram_user_id)
    if not service:
        return None

    try:
        # Get existing event
        event = service.events().get(calendarId="primary", eventId=event_id).execute()
        
        # Update fields
        if title:
            event["summary"] = title
        if description is not None:
            event["description"] = description
        if location is not None:
            event["location"] = location
        if start:
            event["start"] = {"dateTime": start.isoformat(), "timeZone": str(settings.timezone)}
        if end:
            event["end"] = {"dateTime": end.isoformat(), "timeZone": str(settings.timezone)}
        
        result = service.events().update(calendarId="primary", eventId=event_id, body=event).execute()
        return {"id": result.get("id"), "link": result.get("htmlLink")}
    except Exception as e:
        logger.exception(f"Failed to update event: {e}")
        return None


def delete_event(event_id: str, telegram_user_id: int | None = None) -> bool:
    """Delete a calendar event.

    Args:
        event_id: Google event ID.
        telegram_user_id: Optional user ID for per-user auth.

    Returns:
        True if successful, False otherwise.
    """
    service = _get_service_with_fallback(telegram_user_id)
    if not service:
        return False

    try:
        service.events().delete(calendarId="primary", eventId=event_id).execute()
        return True
    except Exception as e:
        logger.exception(f"Failed to delete event: {e}")
        return False


def get_event(event_id: str, telegram_user_id: int | None = None) -> Optional[dict]:
    """Get a single calendar event by ID.

    Args:
        event_id: Google event ID.
        telegram_user_id: Optional user ID for per-user auth.

    Returns:
        Event dict if found, None otherwise.
    """
    service = _get_service_with_fallback(telegram_user_id)
    if not service:
        return None

    try:
        event = service.events().get(calendarId="primary", eventId=event_id).execute()
        return event
    except Exception as e:
        logger.exception(f"Failed to get event: {e}")
        return None


def list_upcoming_events(
    days: int = 7, max_results: int = 20, telegram_user_id: int | None = None
) -> list[dict]:
    """List upcoming calendar events.

    Args:
        days: Number of days to look ahead.
        max_results: Maximum number of events to return.
        telegram_user_id: Optional user ID for per-user auth.

    Returns:
        List of event dictionaries.
    """
    service = _get_service_with_fallback(telegram_user_id)
    if not service:
        return []

    now = datetime.utcnow()
    end = now + timedelta(days=days)

    try:
        events_result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=now.isoformat() + "Z",
                timeMax=end.isoformat() + "Z",
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        return events_result.get("items", [])
    except Exception as e:
        logger.exception(f"Failed to list events: {e}")
        return []
