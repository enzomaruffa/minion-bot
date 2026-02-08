"""FastAPI web server for Google Calendar OAuth callbacks."""

import html
import json
import logging
import secrets
import time
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from src.config import settings
from src.db import session_scope
from src.db.queries import get_user_calendar_token, save_user_calendar_token

logger = logging.getLogger(__name__)

app = FastAPI(title="Minion OAuth Server")

SCOPES = ["https://www.googleapis.com/auth/calendar"]

# Store pending flows by state: state -> (flow, telegram_user_id, created_at)
_FLOW_TTL = 600  # 10 minutes
_pending_flows: dict[str, tuple[Flow, int, float]] = {}


def _get_redirect_uri() -> str:
    """Get the OAuth redirect URI."""
    return f"{settings.web_base_url}/auth/callback"


def _create_flow() -> Flow:
    """Create an OAuth flow configured for web app auth."""
    if not settings.google_credentials_path.exists():
        raise FileNotFoundError("Google credentials file not found")

    return Flow.from_client_secrets_file(
        str(settings.google_credentials_path),
        scopes=SCOPES,
        redirect_uri=_get_redirect_uri(),
    )


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "minion-oauth"}


@app.get("/auth/start/{telegram_user_id}")
async def start_auth(telegram_user_id: int):
    """Start OAuth flow - redirects to Google consent screen.

    Args:
        telegram_user_id: The Telegram user ID to associate with the token.
    """
    try:
        flow = _create_flow()

        # Purge expired flows
        now = time.time()
        expired = [k for k, (_, _, t) in _pending_flows.items() if now - t > _FLOW_TTL]
        for k in expired:
            del _pending_flows[k]

        # Generate unpredictable state token
        state = secrets.token_urlsafe(32)
        _pending_flows[state] = (flow, telegram_user_id, now)

        auth_url, _ = flow.authorization_url(
            prompt="select_account consent",
            access_type="offline",  # Get refresh token
            state=state,
        )

        logger.info(f"Starting OAuth for user {telegram_user_id}")
        return RedirectResponse(url=auth_url)

    except FileNotFoundError:
        raise HTTPException(
            status_code=500,
            detail="Google credentials not configured. Upload credentials.json first.",
        )
    except Exception as e:
        logger.exception(f"Failed to start OAuth: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/auth/callback")
async def auth_callback(code: str | None = None, state: str | None = None, error: str | None = None):
    """Handle OAuth callback from Google.

    Args:
        code: The authorization code from Google.
        state: The state parameter (telegram_user_id).
        error: Error message if auth was denied.
    """
    if error:
        logger.warning(f"OAuth error: {error}")
        return HTMLResponse(
            content=_error_page("Authorization was denied", error),
            status_code=400,
        )

    if not code or not state:
        return HTMLResponse(
            content=_error_page("Missing parameters", "code and state are required"),
            status_code=400,
        )

    flow_entry = _pending_flows.pop(state, None)
    if not flow_entry:
        return HTMLResponse(
            content=_error_page("Session expired", "Please start the auth process again from Telegram"),
            status_code=400,
        )

    flow, telegram_user_id, _ = flow_entry

    try:
        # Exchange code for tokens
        flow.fetch_token(code=code)
        creds = flow.credentials

        # Save to database
        with session_scope() as session:
            save_user_calendar_token(
                session,
                telegram_user_id=telegram_user_id,
                access_token=creds.token,
                refresh_token=creds.refresh_token,
                token_uri=creds.token_uri,
                client_id=creds.client_id,
                client_secret=creds.client_secret,
                scopes=list(creds.scopes) if creds.scopes else SCOPES,
                expiry=creds.expiry,
            )

        logger.info(f"Saved OAuth token for user {telegram_user_id}")
        return HTMLResponse(content=_success_page())

    except Exception as e:
        logger.exception(f"OAuth callback failed: {e}")
        return HTMLResponse(
            content=_error_page("Authorization failed", str(e)),
            status_code=500,
        )


@app.get("/auth/status/{telegram_user_id}")
async def auth_status(telegram_user_id: int):
    """Check if a user has connected their calendar.

    Args:
        telegram_user_id: The Telegram user ID to check.
    """
    with session_scope() as session:
        token = get_user_calendar_token(session, telegram_user_id)

        if not token:
            return {"connected": False}

        # Check if token is expired
        is_expired = token.expiry and token.expiry < datetime.now(timezone.utc)

        return {
            "connected": True,
            "has_refresh_token": bool(token.refresh_token),
            "is_expired": is_expired,
        }


def _success_page() -> str:
    """Generate success HTML page."""
    return """
<!DOCTYPE html>
<html>
<head>
    <title>Minion - Calendar Connected</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }
        .card {
            background: white;
            padding: 40px;
            border-radius: 16px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            text-align: center;
            max-width: 400px;
        }
        h1 { color: #22c55e; margin-bottom: 16px; }
        p { color: #666; line-height: 1.6; }
        .emoji { font-size: 64px; margin-bottom: 16px; }
    </style>
</head>
<body>
    <div class="card">
        <div class="emoji">&#10004;</div>
        <h1>Calendar Connected!</h1>
        <p>Your Google Calendar is now connected to Minion.</p>
        <p>You can close this window and return to Telegram.</p>
    </div>
</body>
</html>
"""


def _error_page(title: str, detail: str) -> str:
    """Generate error HTML page."""
    title = html.escape(title)
    detail = html.escape(detail)
    return f"""
<!DOCTYPE html>
<html>
<head>
    <title>Minion - Error</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }}
        .card {{
            background: white;
            padding: 40px;
            border-radius: 16px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            text-align: center;
            max-width: 400px;
        }}
        h1 {{ color: #ef4444; margin-bottom: 16px; }}
        p {{ color: #666; line-height: 1.6; }}
        .detail {{ color: #999; font-size: 14px; margin-top: 16px; }}
        .emoji {{ font-size: 64px; margin-bottom: 16px; }}
    </style>
</head>
<body>
    <div class="card">
        <div class="emoji">&#10060;</div>
        <h1>{title}</h1>
        <p>Something went wrong connecting your calendar.</p>
        <p class="detail">{detail}</p>
        <p>Please try again from Telegram using /auth</p>
    </div>
</body>
</html>
"""


def run_server():
    """Run the web server (blocking)."""
    import uvicorn

    uvicorn.run(
        app,
        host=settings.web_host,
        port=settings.web_port,
        log_level="info",
    )
