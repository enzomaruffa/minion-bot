"""HTMX dashboard page routes under /app/."""

import logging
from datetime import datetime, timedelta
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from src.config import settings
from src.db import session_scope
from src.db.models import ShoppingListType, TaskPriority, TaskStatus
from src.db.queries import (
    check_shopping_item,
    create_bookmark,
    create_contact,
    create_shopping_item,
    create_task,
    delete_bookmark,
    delete_contact,
    delete_shopping_item,
    delete_task,
    get_mood_history,
    get_mood_stats,
    get_subtasks,
    get_task,
    get_user_profile,
    list_bookmarks,
    list_calendar_events_range,
    list_contacts,
    list_overdue_tasks,
    list_pending_reminders,
    list_shopping_items,
    list_tasks_by_status,
    list_tasks_due_on_date,
    log_mood,
    mark_bookmark_read,
    update_task,
    upsert_user_profile,
)
from src.utils import days_until_birthday, format_birthday_proximity
from src.web.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/app", tags=["views"])


def _templates():
    from src.web.server import templates

    return templates


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


# ============================================================================
# Dashboard
# ============================================================================


@router.get("/", response_class=HTMLResponse, dependencies=[Depends(get_current_user)])
async def dashboard(request: Request):
    now = datetime.now(settings.timezone).replace(tzinfo=None)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    with session_scope() as session:
        tasks_due = list_tasks_due_on_date(session, day_start, day_end)
        overdue = list_overdue_tasks(session, day_start)
        in_progress = list_tasks_by_status(session, TaskStatus.IN_PROGRESS)
        events = list_calendar_events_range(session, day_start, day_end)
        reminders = list_pending_reminders(session, day_end)
        today_reminders = [r for r in reminders if r.remind_at >= day_start]

        # Weather
        weather = city = None
        profile = get_user_profile(session)
        if profile and profile.latitude and profile.longitude:
            from src.integrations.weather import fetch_weather, format_weather

            data = fetch_weather(profile.latitude, profile.longitude)
            if data:
                weather = format_weather(data)
                city = profile.city

        return _templates().TemplateResponse(
            request,
            "dashboard.html",
            {
                "active_page": "dashboard",
                "tasks_due": tasks_due,
                "tasks_due_count": len(tasks_due),
                "overdue_tasks": overdue,
                "overdue_count": len(overdue),
                "in_progress_count": len(in_progress),
                "events": events,
                "events_today": len(events),
                "reminders": today_reminders,
                "weather": weather,
                "city": city,
            },
        )


# ============================================================================
# Tasks
# ============================================================================


@router.get("/tasks", response_class=HTMLResponse, dependencies=[Depends(get_current_user)])
async def tasks_page(request: Request, status: str | None = None):
    with session_scope() as session:
        s = TaskStatus(status) if status else None
        tasks = list_tasks_by_status(session, s, root_only=True)
        return _templates().TemplateResponse(
            request,
            "tasks.html",
            {
                "active_page": "tasks",
                "tasks": tasks,
                "status_filter": status,
            },
        )


@router.post("/tasks", response_class=HTMLResponse, dependencies=[Depends(get_current_user)])
async def create_task_view(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    priority: str = Form("medium"),
    due_date: str = Form(""),
):
    dd = datetime.fromisoformat(due_date) if due_date else None
    with session_scope() as session:
        t = create_task(
            session,
            title=title,
            description=description or None,
            priority=TaskPriority(priority),
            due_date=dd,
        )
        return _templates().TemplateResponse(request, "partials/task_row.html", {"t": t})


@router.get("/tasks/{task_id}", response_class=HTMLResponse, dependencies=[Depends(get_current_user)])
async def task_detail(request: Request, task_id: int):
    with session_scope() as session:
        task = get_task(session, task_id)
        if not task:
            return RedirectResponse("/app/tasks", status_code=303)
        subtasks = get_subtasks(session, task_id)
        return _templates().TemplateResponse(
            request,
            "task_detail.html",
            {
                "active_page": "tasks",
                "task": task,
                "subtasks": subtasks,
            },
        )


@router.patch("/tasks/{task_id}", response_class=HTMLResponse, dependencies=[Depends(get_current_user)])
async def update_task_view(request: Request, task_id: int):
    form = await request.form()
    kwargs = {}
    if "title" in form and form["title"]:
        kwargs["title"] = form["title"]
    if "description" in form:
        kwargs["description"] = form["description"] or None
    if "status" in form and form["status"]:
        kwargs["status"] = TaskStatus(form["status"])
    if "priority" in form and form["priority"]:
        kwargs["priority"] = TaskPriority(form["priority"])
    if "due_date" in form and form["due_date"]:
        kwargs["due_date"] = datetime.fromisoformat(form["due_date"])

    with session_scope() as session:
        update_task(session, task_id, **kwargs)
    return RedirectResponse(f"/app/tasks/{task_id}", status_code=303)


@router.delete("/tasks/{task_id}", dependencies=[Depends(get_current_user)])
async def delete_task_view(task_id: int):
    with session_scope() as session:
        delete_task(session, task_id)
    return RedirectResponse("/app/tasks", status_code=303)


# ============================================================================
# Calendar
# ============================================================================


@router.get("/calendar", response_class=HTMLResponse, dependencies=[Depends(get_current_user)])
async def calendar_page(request: Request, days: int = Query(7)):
    now = datetime.now(settings.timezone).replace(tzinfo=None)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=days)

    with session_scope() as session:
        events = list_calendar_events_range(session, start, end)
        return _templates().TemplateResponse(
            request,
            "calendar.html",
            {
                "active_page": "calendar",
                "events": events,
                "days": days,
            },
        )


# ============================================================================
# Shopping
# ============================================================================


@router.get("/shopping", response_class=HTMLResponse, dependencies=[Depends(get_current_user)])
async def shopping_page(request: Request, list: str = Query("groceries", alias="list")):
    with session_scope() as session:
        lt = ShoppingListType(list)
        items = list_shopping_items(session, list_type=lt)
        return _templates().TemplateResponse(
            request,
            "shopping.html",
            {
                "active_page": "shopping",
                "items": items,
                "current_list": list,
            },
        )


@router.post("/shopping", response_class=HTMLResponse, dependencies=[Depends(get_current_user)])
async def add_shopping_item_view(request: Request, name: str = Form(...), list_type: str = Form("groceries")):
    with session_scope() as session:
        lt = ShoppingListType(list_type)
        item = create_shopping_item(session, lt, name=name)
        return _templates().TemplateResponse(request, "partials/shopping_item.html", {"item": item})


@router.patch("/shopping/items/{item_id}/check", response_class=HTMLResponse, dependencies=[Depends(get_current_user)])
async def check_item_view(request: Request, item_id: int, checked: str = Query("true")):
    check = checked.lower() == "true"
    with session_scope() as session:
        check_shopping_item(session, item_id, check)
        from src.db.queries import get_shopping_item

        item = get_shopping_item(session, item_id)
        if not item:
            return HTMLResponse("")
        return _templates().TemplateResponse(request, "partials/shopping_item.html", {"item": item})


@router.delete("/shopping/items/{item_id}", dependencies=[Depends(get_current_user)])
async def delete_shopping_item_view(item_id: int):
    with session_scope() as session:
        delete_shopping_item(session, item_id)
    return HTMLResponse("")


# ============================================================================
# Contacts
# ============================================================================


@router.get("/contacts", response_class=HTMLResponse, dependencies=[Depends(get_current_user)])
async def contacts_page(request: Request):
    with session_scope() as session:
        contacts = list_contacts(session)
        today = datetime.now(settings.timezone).date()
        birthday_info = {}
        for c in contacts:
            if c.birthday:
                d = days_until_birthday(c.birthday, today)
                birthday_info[c.id] = format_birthday_proximity(d)
        return _templates().TemplateResponse(
            request,
            "contacts.html",
            {
                "active_page": "contacts",
                "contacts": contacts,
                "birthday_info": birthday_info,
            },
        )


@router.post("/contacts", response_class=HTMLResponse, dependencies=[Depends(get_current_user)])
async def create_contact_view(
    request: Request,
    name: str = Form(...),
    aliases: str = Form(""),
    birthday: str = Form(""),
    notes: str = Form(""),
):
    bday = datetime.strptime(birthday, "%Y-%m-%d") if birthday else None
    with session_scope() as session:
        c = create_contact(session, name=name, aliases=aliases or None, birthday=bday, notes=notes or None)
        return _templates().TemplateResponse(request, "partials/contact_row.html", {"c": c, "birthday_info": {}})


@router.delete("/contacts/{contact_id}", dependencies=[Depends(get_current_user)])
async def delete_contact_view(contact_id: int):
    with session_scope() as session:
        delete_contact(session, contact_id)
    return HTMLResponse("")


# ============================================================================
# Bookmarks
# ============================================================================


@router.get("/bookmarks", response_class=HTMLResponse, dependencies=[Depends(get_current_user)])
async def bookmarks_page(request: Request, read: str | None = None):
    read_filter = None
    if read == "true":
        read_filter = True
    elif read == "false":
        read_filter = False

    with session_scope() as session:
        bookmarks = list_bookmarks(session, read=read_filter, limit=50)
        return _templates().TemplateResponse(
            request,
            "bookmarks.html",
            {
                "active_page": "bookmarks",
                "bookmarks": bookmarks,
                "read_filter": read_filter,
            },
        )


@router.post("/bookmarks", response_class=HTMLResponse, dependencies=[Depends(get_current_user)])
async def create_bookmark_view(
    request: Request,
    url: str = Form(...),
    title: str = Form(""),
    tags: str = Form(""),
):
    domain = urlparse(url).netloc or None
    with session_scope() as session:
        b = create_bookmark(session, url=url, title=title or None, domain=domain, tags=tags or None)
        return _templates().TemplateResponse(request, "partials/bookmark_row.html", {"b": b})


@router.patch("/bookmarks/{bookmark_id}/read", response_class=HTMLResponse, dependencies=[Depends(get_current_user)])
async def mark_read_view(request: Request, bookmark_id: int, read: str = Query("true")):
    r = read.lower() == "true"
    with session_scope() as session:
        mark_bookmark_read(session, bookmark_id, r)
        from src.db.queries import get_bookmark

        b = get_bookmark(session, bookmark_id)
        if not b:
            return HTMLResponse("")
        return _templates().TemplateResponse(request, "partials/bookmark_row.html", {"b": b})


@router.delete("/bookmarks/{bookmark_id}", dependencies=[Depends(get_current_user)])
async def delete_bookmark_view(bookmark_id: int):
    with session_scope() as session:
        delete_bookmark(session, bookmark_id)
    return HTMLResponse("")


# ============================================================================
# Mood
# ============================================================================


@router.get("/mood", response_class=HTMLResponse, dependencies=[Depends(get_current_user)])
async def mood_page(request: Request):
    with session_scope() as session:
        logs = get_mood_history(session, days=30)
        stats = get_mood_stats(session, days=30)
        return _templates().TemplateResponse(
            request,
            "mood.html",
            {
                "active_page": "mood",
                "logs": logs,
                "stats": stats,
            },
        )


@router.post("/mood", response_class=HTMLResponse, dependencies=[Depends(get_current_user)])
async def log_mood_view(request: Request, score: int = Form(...), note: str = Form("")):
    now = datetime.now(settings.timezone).replace(tzinfo=None)
    date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    with session_scope() as session:
        m = log_mood(session, date=date, score=score, note=note or None)
        return _templates().TemplateResponse(request, "partials/mood_row.html", {"m": m})


# ============================================================================
# Settings
# ============================================================================


@router.get("/settings", response_class=HTMLResponse, dependencies=[Depends(get_current_user)])
async def settings_page(request: Request):
    with session_scope() as session:
        profile = get_user_profile(session)
        if not profile:
            profile = upsert_user_profile(session)
        return _templates().TemplateResponse(
            request,
            "settings.html",
            {
                "active_page": "settings",
                "profile": profile,
            },
        )


@router.patch("/settings", dependencies=[Depends(get_current_user)])
async def update_settings_view(request: Request):
    form = await request.form()
    fields = {}
    for key in ["display_name", "city", "timezone_str"]:
        if key in form and form[key]:
            fields[key] = form[key]
    for key in ["work_start_hour", "work_end_hour"]:
        if key in form and form[key]:
            fields[key] = int(form[key])

    # Geocode city if changed
    if "city" in fields:
        try:
            from geopy.geocoders import Nominatim

            geo = Nominatim(user_agent="minion-bot")
            loc = geo.geocode(fields["city"])
            if loc:
                fields["latitude"] = loc.latitude
                fields["longitude"] = loc.longitude
        except Exception:
            logger.warning("Geocoding failed")

    with session_scope() as session:
        upsert_user_profile(session, **fields)
    return RedirectResponse("/app/settings", status_code=303)


# ============================================================================
# Chat
# ============================================================================


@router.get("/chat", response_class=HTMLResponse, dependencies=[Depends(get_current_user)])
async def chat_page(request: Request):
    return _templates().TemplateResponse(request, "chat.html", {"active_page": "chat"})
