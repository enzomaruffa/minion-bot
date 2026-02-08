"""FastAPI web server — OAuth, REST API, and HTMX dashboard."""

import html
import logging
import secrets
import time
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from google_auth_oauthlib.flow import Flow

from src.config import settings
from src.db import session_scope
from src.db.queries import get_user_calendar_token, save_user_calendar_token

logger = logging.getLogger(__name__)

app = FastAPI(title="Minion")

# Jinja2 templates
TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Mount routers
from src.web.api import router as api_router  # noqa: E402
from src.web.auth import router as auth_router  # noqa: E402
from src.web.views import router as views_router  # noqa: E402

app.include_router(auth_router)
app.include_router(api_router)
app.include_router(views_router)


@app.exception_handler(HTTPException)
async def auth_exception_handler(request: Request, exc: HTTPException):
    """Redirect unauthenticated browser requests to login; return JSON for API/HTMX."""
    if exc.status_code == 401:
        is_htmx = request.headers.get("HX-Request") == "true"
        is_api = request.url.path.startswith("/api/")
        if is_htmx:
            return HTMLResponse("", status_code=200, headers={"HX-Redirect": "/auth/login"})
        if not is_api:
            return RedirectResponse(url="/auth/login", status_code=303)
        return JSONResponse({"detail": exc.detail}, status_code=401)
    # Re-raise non-401 errors as default response
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=getattr(exc, "headers", None))


# ============================================================================
# Existing Google OAuth routes
# ============================================================================

SCOPES = ["https://www.googleapis.com/auth/calendar"]

# Store pending flows by state: state -> (flow, telegram_user_id, created_at)
_FLOW_TTL = 600  # 10 minutes
_pending_flows: dict[str, tuple[Flow, int, float]] = {}


def _get_redirect_uri() -> str:
    """Get the OAuth redirect URI."""
    return f"{settings.web_base_url}/oauth/callback"


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
    """Root — redirect to dashboard or login."""
    return RedirectResponse(url="/app/")


@app.get("/oauth/start/{telegram_user_id}")
async def start_auth(telegram_user_id: int):
    """Start OAuth flow - redirects to Google consent screen."""
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
            access_type="offline",
            state=state,
        )

        logger.info(f"Starting OAuth for user {telegram_user_id}")
        return RedirectResponse(url=auth_url)

    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail="Google credentials not configured.") from e
    except Exception as e:
        logger.exception(f"Failed to start OAuth: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/oauth/callback")
async def auth_callback(code: str | None = None, state: str | None = None, error: str | None = None):
    """Handle OAuth callback from Google."""
    if error:
        logger.warning(f"OAuth error: {error}")
        return HTMLResponse(content=_error_page("Authorization was denied", error), status_code=400)

    if not code or not state:
        return HTMLResponse(content=_error_page("Missing parameters", "code and state are required"), status_code=400)

    flow_entry = _pending_flows.pop(state, None)
    if not flow_entry:
        return HTMLResponse(
            content=_error_page("Session expired", "Please start the auth process again from Telegram"),
            status_code=400,
        )

    flow, telegram_user_id, _ = flow_entry

    try:
        flow.fetch_token(code=code)
        creds = flow.credentials

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
        return HTMLResponse(content=_error_page("Authorization failed", str(e)), status_code=500)


@app.get("/oauth/status/{telegram_user_id}")
async def auth_status(telegram_user_id: int):
    """Check if a user has connected their calendar."""
    with session_scope() as session:
        token = get_user_calendar_token(session, telegram_user_id)
        if not token:
            return {"connected": False}
        is_expired = token.expiry and token.expiry < datetime.now(UTC)
        return {
            "connected": True,
            "has_refresh_token": bool(token.refresh_token),
            "is_expired": is_expired,
        }


# Legacy redirect: old /auth/start -> /oauth/start
@app.get("/auth/start/{telegram_user_id}")
async def legacy_start_auth(telegram_user_id: int):
    return RedirectResponse(url=f"/oauth/start/{telegram_user_id}")


@app.get("/auth/callback")
async def legacy_callback(code: str | None = None, state: str | None = None, error: str | None = None):
    return RedirectResponse(url=f"/oauth/callback?code={code}&state={state}&error={error or ''}")


def _success_page() -> str:
    return """
<!DOCTYPE html>
<html><head><title>Minion - Calendar Connected</title>
<style>
body { font-family: -apple-system, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background: linear-gradient(135deg, #667eea, #764ba2); }
.card { background: white; padding: 40px; border-radius: 16px; box-shadow: 0 10px 40px rgba(0,0,0,0.2); text-align: center; max-width: 400px; }
h1 { color: #22c55e; } p { color: #666; line-height: 1.6; } .emoji { font-size: 64px; }
</style></head><body><div class="card"><div class="emoji">&#10004;</div><h1>Calendar Connected!</h1>
<p>Your Google Calendar is now connected to Minion.</p><p>You can close this window and return to Telegram.</p></div></body></html>"""


def _error_page(title: str, detail: str) -> str:
    title = html.escape(title)
    detail = html.escape(detail)
    return f"""
<!DOCTYPE html>
<html><head><title>Minion - Error</title>
<style>
body {{ font-family: -apple-system, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background: linear-gradient(135deg, #667eea, #764ba2); }}
.card {{ background: white; padding: 40px; border-radius: 16px; box-shadow: 0 10px 40px rgba(0,0,0,0.2); text-align: center; max-width: 400px; }}
h1 {{ color: #ef4444; }} p {{ color: #666; line-height: 1.6; }} .emoji {{ font-size: 64px; }}
</style></head><body><div class="card"><div class="emoji">&#10060;</div><h1>{title}</h1>
<p>Something went wrong.</p><p style="color: #999; font-size: 14px;">{detail}</p>
<p>Please try again from Telegram using /auth</p></div></body></html>"""


def run_server():
    """Run the web server (blocking)."""
    import uvicorn

    uvicorn.run(
        app,
        host=settings.web_host,
        port=settings.web_port,
        log_level="info",
    )
