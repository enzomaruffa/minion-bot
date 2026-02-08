"""Web dashboard auth — Telegram code-based login."""

import logging
import secrets
import time
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from src.config import settings
from src.db import session_scope
from src.db.queries import cleanup_expired_sessions, create_web_session, delete_web_session, get_web_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# In-memory pending codes: code -> (telegram_user_id, created_at)
_CODE_TTL = 300  # 5 minutes
_pending_codes: dict[str, tuple[int, float]] = {}


def _purge_expired_codes() -> None:
    now = time.time()
    expired = [k for k, (_, t) in _pending_codes.items() if now - t > _CODE_TTL]
    for k in expired:
        del _pending_codes[k]


class RequestCodeBody(BaseModel):
    telegram_user_id: int


class VerifyCodeBody(BaseModel):
    telegram_user_id: int
    code: str


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Serve the login page."""
    from src.web.server import templates

    return templates.TemplateResponse(request, "login.html")


@router.post("/request-code")
async def request_code(body: RequestCodeBody):
    """Generate a 6-digit code and send it via Telegram."""
    if body.telegram_user_id != settings.telegram_user_id:
        raise HTTPException(status_code=403, detail="Unknown user")

    _purge_expired_codes()

    code = f"{secrets.randbelow(900000) + 100000}"
    _pending_codes[code] = (body.telegram_user_id, time.time())

    # Send code via Telegram
    if settings.telegram_bot_token:
        from src.notifications import notify

        await notify(f"Your web dashboard login code: <code>{code}</code>\nExpires in 5 minutes.")

    logger.info(f"Generated login code for user {body.telegram_user_id}")
    return {"status": "ok", "message": "Code sent to Telegram"}


@router.post("/verify-code")
async def verify_code(body: VerifyCodeBody, response: Response):
    """Verify code and create session."""
    _purge_expired_codes()

    entry = _pending_codes.pop(body.code, None)
    if not entry:
        raise HTTPException(status_code=401, detail="Invalid or expired code")

    uid, _ = entry
    if uid != body.telegram_user_id:
        raise HTTPException(status_code=401, detail="Invalid code")

    # Create session
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(days=settings.web_session_ttl_days)

    with session_scope() as session:
        create_web_session(session, body.telegram_user_id, token, expires_at)

    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        max_age=settings.web_session_ttl_days * 86400,
        samesite="lax",
    )
    logger.info(f"Web session created for user {body.telegram_user_id}")
    return {"status": "ok"}


@router.post("/logout")
async def logout(response: Response, session_token: str | None = Cookie(default=None)):
    """Clear session."""
    if session_token:
        with session_scope() as session:
            delete_web_session(session, session_token)

    response.delete_cookie("session_token")
    return RedirectResponse(url="/auth/login", status_code=303)


def get_current_user(session_token: str | None = Cookie(default=None)) -> int:
    """FastAPI dependency — returns telegram_user_id or raises 401."""
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated", headers={"HX-Redirect": "/auth/login"})

    with session_scope() as session:
        ws = get_web_session(session, session_token)
        if not ws:
            raise HTTPException(status_code=401, detail="Session expired", headers={"HX-Redirect": "/auth/login"})
        return ws.telegram_user_id


async def cleanup_expired_sessions_job() -> None:
    """Scheduled job to clean up expired sessions."""
    try:
        with session_scope() as session:
            count = cleanup_expired_sessions(session)
            if count:
                logger.info(f"Cleaned up {count} expired web sessions")
    except Exception:
        logger.exception("Error cleaning up expired sessions")
