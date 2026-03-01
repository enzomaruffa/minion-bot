"""REST API endpoints under /api/v1/."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from src.config import settings
from src.db import session_scope
from src.db.models import (
    ItemPriority,
    ShoppingListType,
    TaskPriority,
    TaskStatus,
)
from src.db.queries import (
    check_shopping_item,
    create_bookmark,
    create_contact,
    create_interest,
    create_reminder,
    create_shopping_item,
    create_task,
    create_user_project,
    delete_bookmark,
    delete_contact,
    delete_interest,
    delete_reminder,
    delete_shopping_item,
    delete_task,
    get_bookmark,
    get_contact,
    get_interest,
    get_mood_history,
    get_mood_stats,
    get_subtasks,
    get_task,
    get_user_profile,
    get_user_project,
    list_all_reminders,
    list_bookmarks,
    list_calendar_events_range,
    list_contacts,
    list_interests,
    list_shopping_items,
    list_tasks_by_status,
    list_user_projects,
    log_mood,
    mark_bookmark_read,
    update_contact,
    update_interest,
    update_task,
    update_user_project,
    upsert_user_profile,
)
from src.web.auth import get_current_user
from src.web.serializers import (
    BookmarkCreate,
    BookmarkOut,
    CalendarEventOut,
    ChatRequest,
    ChatResponse,
    ContactCreate,
    ContactOut,
    ContactUpdate,
    InterestCreate,
    InterestOut,
    InterestUpdate,
    MoodLogCreate,
    MoodLogOut,
    ProfileOut,
    ProfileUpdate,
    ReminderCreate,
    ReminderOut,
    ShoppingItemCreate,
    ShoppingItemOut,
    TaskCreate,
    TaskOut,
    TaskUpdate,
    UserProjectCreate,
    UserProjectOut,
    UserProjectUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["api"])


# --- Helpers ---


def _task_to_out(t) -> TaskOut:
    return TaskOut(
        id=t.id,
        title=t.title,
        description=t.description,
        status=t.status.value,
        priority=t.priority.value,
        due_date=t.due_date,
        parent_id=t.parent_id,
        project_name=t.project.name if t.project else None,
        project_emoji=t.project.emoji if t.project else None,
        user_project_name=t.user_project.name if t.user_project else None,
        user_project_emoji=t.user_project.emoji if t.user_project else None,
        contact_name=t.contact.name if t.contact else None,
        recurrence_rule=t.recurrence_rule,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


# ============================================================================
# Tasks
# ============================================================================


@router.get("/tasks", dependencies=[Depends(get_current_user)])
async def api_list_tasks(
    status: str | None = None,
    project_id: int | None = None,
    root_only: bool = False,
) -> list[TaskOut]:
    with session_scope() as session:
        s = TaskStatus(status) if status else None
        tasks = list_tasks_by_status(session, s, root_only=root_only, project_id=project_id)
        return [_task_to_out(t) for t in tasks]


@router.get("/tasks/{task_id}", dependencies=[Depends(get_current_user)])
async def api_get_task(task_id: int) -> TaskOut:
    with session_scope() as session:
        t = get_task(session, task_id)
        if not t:
            raise HTTPException(404, "Task not found")
        return _task_to_out(t)


@router.post("/tasks", dependencies=[Depends(get_current_user)], status_code=201)
async def api_create_task(body: TaskCreate) -> TaskOut:
    with session_scope() as session:
        t = create_task(
            session,
            title=body.title,
            description=body.description,
            priority=TaskPriority(body.priority),
            due_date=body.due_date,
            parent_id=body.parent_id,
            project_id=body.project_id,
            user_project_id=body.user_project_id,
            contact_id=body.contact_id,
        )
        return _task_to_out(t)


@router.patch("/tasks/{task_id}", dependencies=[Depends(get_current_user)])
async def api_update_task(task_id: int, body: TaskUpdate) -> TaskOut:
    with session_scope() as session:
        t = update_task(
            session,
            task_id,
            title=body.title,
            description=body.description,
            status=TaskStatus(body.status) if body.status else None,
            priority=TaskPriority(body.priority) if body.priority else None,
            due_date=body.due_date,
            parent_id=body.parent_id,
            project_id=body.project_id,
            user_project_id=body.user_project_id,
            contact_id=body.contact_id,
            clear_parent=body.clear_parent,
            clear_project=body.clear_project,
            clear_user_project=body.clear_user_project,
            clear_contact=body.clear_contact,
        )
        if not t:
            raise HTTPException(404, "Task not found")
        return _task_to_out(t)


@router.delete("/tasks/{task_id}", dependencies=[Depends(get_current_user)], status_code=204)
async def api_delete_task(task_id: int):
    with session_scope() as session:
        if not delete_task(session, task_id):
            raise HTTPException(404, "Task not found")


@router.get("/tasks/{task_id}/subtasks", dependencies=[Depends(get_current_user)])
async def api_get_subtasks(task_id: int) -> list[TaskOut]:
    with session_scope() as session:
        subs = get_subtasks(session, task_id)
        return [_task_to_out(t) for t in subs]


@router.post("/tasks/{task_id}/subtasks", dependencies=[Depends(get_current_user)], status_code=201)
async def api_add_subtask(task_id: int, body: TaskCreate) -> TaskOut:
    with session_scope() as session:
        t = create_task(
            session,
            title=body.title,
            description=body.description,
            priority=TaskPriority(body.priority),
            due_date=body.due_date,
            parent_id=task_id,
            project_id=body.project_id,
            user_project_id=body.user_project_id,
        )
        return _task_to_out(t)


# ============================================================================
# Contacts
# ============================================================================


@router.get("/contacts", dependencies=[Depends(get_current_user)])
async def api_list_contacts() -> list[ContactOut]:
    with session_scope() as session:
        contacts = list_contacts(session)
        return [
            ContactOut(
                id=c.id,
                name=c.name,
                aliases=c.aliases,
                birthday=c.birthday,
                notes=c.notes,
                created_at=c.created_at,
            )
            for c in contacts
        ]


@router.get("/contacts/{contact_id}", dependencies=[Depends(get_current_user)])
async def api_get_contact(contact_id: int) -> ContactOut:
    with session_scope() as session:
        c = get_contact(session, contact_id)
        if not c:
            raise HTTPException(404, "Contact not found")
        return ContactOut(
            id=c.id,
            name=c.name,
            aliases=c.aliases,
            birthday=c.birthday,
            notes=c.notes,
            created_at=c.created_at,
        )


@router.post("/contacts", dependencies=[Depends(get_current_user)], status_code=201)
async def api_create_contact(body: ContactCreate) -> ContactOut:
    with session_scope() as session:
        c = create_contact(session, name=body.name, aliases=body.aliases, birthday=body.birthday, notes=body.notes)
        return ContactOut(
            id=c.id,
            name=c.name,
            aliases=c.aliases,
            birthday=c.birthday,
            notes=c.notes,
            created_at=c.created_at,
        )


@router.patch("/contacts/{contact_id}", dependencies=[Depends(get_current_user)])
async def api_update_contact(contact_id: int, body: ContactUpdate) -> ContactOut:
    with session_scope() as session:
        c = update_contact(
            session,
            contact_id,
            name=body.name,
            aliases=body.aliases,
            birthday=body.birthday,
            notes=body.notes,
            clear_birthday=body.clear_birthday,
            clear_aliases=body.clear_aliases,
        )
        if not c:
            raise HTTPException(404, "Contact not found")
        return ContactOut(
            id=c.id,
            name=c.name,
            aliases=c.aliases,
            birthday=c.birthday,
            notes=c.notes,
            created_at=c.created_at,
        )


@router.delete("/contacts/{contact_id}", dependencies=[Depends(get_current_user)], status_code=204)
async def api_delete_contact(contact_id: int):
    with session_scope() as session:
        if not delete_contact(session, contact_id):
            raise HTTPException(404, "Contact not found")


# ============================================================================
# Bookmarks
# ============================================================================


@router.get("/bookmarks", dependencies=[Depends(get_current_user)])
async def api_list_bookmarks(
    read: bool | None = None,
    tag: str | None = None,
    limit: int = Query(20, le=100),
) -> list[BookmarkOut]:
    with session_scope() as session:
        bookmarks = list_bookmarks(session, read=read, tag=tag, limit=limit)
        return [
            BookmarkOut(
                id=b.id,
                url=b.url,
                title=b.title,
                description=b.description,
                domain=b.domain,
                tags=b.tags,
                read=b.read,
                created_at=b.created_at,
            )
            for b in bookmarks
        ]


@router.get("/bookmarks/{bookmark_id}", dependencies=[Depends(get_current_user)])
async def api_get_bookmark(bookmark_id: int) -> BookmarkOut:
    with session_scope() as session:
        b = get_bookmark(session, bookmark_id)
        if not b:
            raise HTTPException(404, "Bookmark not found")
        return BookmarkOut(
            id=b.id,
            url=b.url,
            title=b.title,
            description=b.description,
            domain=b.domain,
            tags=b.tags,
            read=b.read,
            created_at=b.created_at,
        )


@router.post("/bookmarks", dependencies=[Depends(get_current_user)], status_code=201)
async def api_create_bookmark(body: BookmarkCreate) -> BookmarkOut:
    from urllib.parse import urlparse

    domain = urlparse(body.url).netloc or None
    with session_scope() as session:
        b = create_bookmark(
            session,
            url=body.url,
            title=body.title,
            description=body.description,
            domain=domain,
            tags=body.tags,
        )
        return BookmarkOut(
            id=b.id,
            url=b.url,
            title=b.title,
            description=b.description,
            domain=b.domain,
            tags=b.tags,
            read=b.read,
            created_at=b.created_at,
        )


@router.patch("/bookmarks/{bookmark_id}/read", dependencies=[Depends(get_current_user)])
async def api_mark_bookmark_read(bookmark_id: int, read: bool = True):
    with session_scope() as session:
        if not mark_bookmark_read(session, bookmark_id, read):
            raise HTTPException(404, "Bookmark not found")
    return {"status": "ok"}


@router.delete("/bookmarks/{bookmark_id}", dependencies=[Depends(get_current_user)], status_code=204)
async def api_delete_bookmark(bookmark_id: int):
    with session_scope() as session:
        if not delete_bookmark(session, bookmark_id):
            raise HTTPException(404, "Bookmark not found")


# ============================================================================
# Mood
# ============================================================================


@router.get("/mood", dependencies=[Depends(get_current_user)])
async def api_mood_history(days: int = Query(30, le=365)) -> list[MoodLogOut]:
    with session_scope() as session:
        logs = get_mood_history(session, days=days)
        return [MoodLogOut(id=m.id, date=m.date, score=m.score, note=m.note, created_at=m.created_at) for m in logs]


@router.post("/mood", dependencies=[Depends(get_current_user)], status_code=201)
async def api_log_mood(body: MoodLogCreate) -> MoodLogOut:
    with session_scope() as session:
        m = log_mood(session, date=body.date, score=body.score, note=body.note)
        return MoodLogOut(id=m.id, date=m.date, score=m.score, note=m.note, created_at=m.created_at)


@router.get("/mood/stats", dependencies=[Depends(get_current_user)])
async def api_mood_stats(days: int = Query(30, le=365)):
    with session_scope() as session:
        return get_mood_stats(session, days=days)


# ============================================================================
# Projects (user-created)
# ============================================================================


@router.get("/projects", dependencies=[Depends(get_current_user)])
async def api_list_projects(include_archived: bool = False) -> list[UserProjectOut]:
    with session_scope() as session:
        projects = list_user_projects(session, include_archived=include_archived)
        return [
            UserProjectOut(
                id=p.id,
                name=p.name,
                description=p.description,
                emoji=p.emoji,
                tag_name=p.tag.name if p.tag else None,
                archived=p.archived,
                created_at=p.created_at,
            )
            for p in projects
        ]


@router.get("/projects/{project_id}", dependencies=[Depends(get_current_user)])
async def api_get_project(project_id: int) -> UserProjectOut:
    with session_scope() as session:
        p = get_user_project(session, project_id)
        if not p:
            raise HTTPException(404, "Project not found")
        return UserProjectOut(
            id=p.id,
            name=p.name,
            description=p.description,
            emoji=p.emoji,
            tag_name=p.tag.name if p.tag else None,
            archived=p.archived,
            created_at=p.created_at,
        )


@router.post("/projects", dependencies=[Depends(get_current_user)], status_code=201)
async def api_create_project(body: UserProjectCreate) -> UserProjectOut:
    with session_scope() as session:
        p = create_user_project(
            session,
            name=body.name,
            description=body.description,
            emoji=body.emoji,
            tag_id=body.tag_id,
        )
        return UserProjectOut(
            id=p.id,
            name=p.name,
            description=p.description,
            emoji=p.emoji,
            tag_name=p.tag.name if p.tag else None,
            archived=p.archived,
            created_at=p.created_at,
        )


@router.patch("/projects/{project_id}", dependencies=[Depends(get_current_user)])
async def api_update_project(project_id: int, body: UserProjectUpdate) -> UserProjectOut:
    with session_scope() as session:
        p = update_user_project(
            session,
            project_id,
            name=body.name,
            description=body.description,
            emoji=body.emoji,
            tag_id=body.tag_id,
            archived=body.archived,
        )
        if not p:
            raise HTTPException(404, "Project not found")
        return UserProjectOut(
            id=p.id,
            name=p.name,
            description=p.description,
            emoji=p.emoji,
            tag_name=p.tag.name if p.tag else None,
            archived=p.archived,
            created_at=p.created_at,
        )


# ============================================================================
# Shopping
# ============================================================================


@router.get("/shopping/{list_type}", dependencies=[Depends(get_current_user)])
async def api_list_shopping(list_type: str, include_checked: bool = True) -> list[ShoppingItemOut]:
    with session_scope() as session:
        lt = ShoppingListType(list_type)
        items = list_shopping_items(session, list_type=lt, include_checked=include_checked)
        return [
            ShoppingItemOut(
                id=i.id,
                name=i.name,
                notes=i.notes,
                recipient=i.recipient,
                priority=i.priority.value,
                checked=i.checked,
                quantity_target=i.quantity_target,
                quantity_purchased=i.quantity_purchased,
                created_at=i.created_at,
            )
            for i in items
        ]


@router.post("/shopping/{list_type}", dependencies=[Depends(get_current_user)], status_code=201)
async def api_add_shopping_item(list_type: str, body: ShoppingItemCreate) -> ShoppingItemOut:
    with session_scope() as session:
        lt = ShoppingListType(list_type)
        i = create_shopping_item(
            session,
            lt,
            name=body.name,
            notes=body.notes,
            recipient=body.recipient,
            priority=ItemPriority(body.priority),
            quantity_target=body.quantity_target,
        )
        return ShoppingItemOut(
            id=i.id,
            name=i.name,
            notes=i.notes,
            recipient=i.recipient,
            priority=i.priority.value,
            checked=i.checked,
            quantity_target=i.quantity_target,
            quantity_purchased=i.quantity_purchased,
            created_at=i.created_at,
        )


@router.patch("/shopping/items/{item_id}/check", dependencies=[Depends(get_current_user)])
async def api_check_item(item_id: int, checked: bool = True):
    with session_scope() as session:
        if not check_shopping_item(session, item_id, checked):
            raise HTTPException(404, "Item not found")
    return {"status": "ok"}


@router.delete("/shopping/items/{item_id}", dependencies=[Depends(get_current_user)], status_code=204)
async def api_delete_shopping_item(item_id: int):
    with session_scope() as session:
        if not delete_shopping_item(session, item_id):
            raise HTTPException(404, "Item not found")


# ============================================================================
# Reminders
# ============================================================================


@router.get("/reminders", dependencies=[Depends(get_current_user)])
async def api_list_reminders() -> list[ReminderOut]:
    with session_scope() as session:
        reminders = list_all_reminders(session, include_delivered=False)
        return [
            ReminderOut(
                id=r.id,
                message=r.message,
                remind_at=r.remind_at,
                delivered=r.delivered,
                task_id=r.task_id,
                created_at=r.created_at,
            )
            for r in reminders
        ]


@router.post("/reminders", dependencies=[Depends(get_current_user)], status_code=201)
async def api_create_reminder(body: ReminderCreate) -> ReminderOut:
    with session_scope() as session:
        r = create_reminder(session, message=body.message, remind_at=body.remind_at, task_id=body.task_id)
        return ReminderOut(
            id=r.id,
            message=r.message,
            remind_at=r.remind_at,
            delivered=r.delivered,
            task_id=r.task_id,
            created_at=r.created_at,
        )


@router.delete("/reminders/{reminder_id}", dependencies=[Depends(get_current_user)], status_code=204)
async def api_delete_reminder(reminder_id: int):
    with session_scope() as session:
        if not delete_reminder(session, reminder_id):
            raise HTTPException(404, "Reminder not found")


# ============================================================================
# Calendar
# ============================================================================


@router.get("/calendar/events", dependencies=[Depends(get_current_user)])
async def api_list_events(
    start: str | None = None,
    end: str | None = None,
) -> list[CalendarEventOut]:
    from datetime import datetime, timedelta

    now = datetime.now(settings.timezone).replace(tzinfo=None)
    s = datetime.fromisoformat(start) if start else now.replace(hour=0, minute=0, second=0, microsecond=0)
    e = datetime.fromisoformat(end) if end else s + timedelta(days=7)

    with session_scope() as session:
        events = list_calendar_events_range(session, s, e)
        return [
            CalendarEventOut(
                id=ev.id,
                google_event_id=ev.google_event_id,
                title=ev.title,
                start_time=ev.start_time,
                end_time=ev.end_time,
            )
            for ev in events
        ]


@router.get("/calendar/free-slots", dependencies=[Depends(get_current_user)])
async def api_free_slots(
    date: str | None = None,
    duration_minutes: int = 60,
):
    from src.agent.tools.scheduling import find_free_slot

    result = find_free_slot(
        duration_minutes=duration_minutes,
    )
    return {"slots": result}


# ============================================================================
# Profile
# ============================================================================


@router.get("/profile", dependencies=[Depends(get_current_user)])
async def api_get_profile() -> ProfileOut:
    with session_scope() as session:
        p = get_user_profile(session)
        if not p:
            return ProfileOut()
        return ProfileOut(
            display_name=p.display_name,
            city=p.city,
            latitude=p.latitude,
            longitude=p.longitude,
            timezone_str=p.timezone_str,
            work_start_hour=p.work_start_hour,
            work_end_hour=p.work_end_hour,
        )


@router.patch("/profile", dependencies=[Depends(get_current_user)])
async def api_update_profile(body: ProfileUpdate) -> ProfileOut:
    with session_scope() as session:
        p = upsert_user_profile(session, **body.model_dump(exclude_none=True))
        return ProfileOut(
            display_name=p.display_name,
            city=p.city,
            latitude=p.latitude,
            longitude=p.longitude,
            timezone_str=p.timezone_str,
            work_start_hour=p.work_start_hour,
            work_end_hour=p.work_end_hour,
        )


# ============================================================================
# Weather
# ============================================================================


@router.get("/weather", dependencies=[Depends(get_current_user)])
async def api_weather():
    from src.integrations.weather import fetch_weather, format_weather

    with session_scope() as session:
        p = get_user_profile(session)
        if not p or not p.latitude or not p.longitude:
            raise HTTPException(400, "Profile location not set")
        data = fetch_weather(p.latitude, p.longitude)
        if not data:
            raise HTTPException(502, "Weather data unavailable")
        return {"weather": format_weather(data), "city": p.city}


# ============================================================================
# Interests
# ============================================================================


def _interest_to_out(i) -> InterestOut:
    return InterestOut(
        id=i.id,
        topic=i.topic,
        description=i.description,
        priority=i.priority,
        active=i.active,
        check_interval_hours=i.check_interval_hours,
        last_checked_at=i.last_checked_at,
        created_at=i.created_at,
    )


@router.get("/interests", dependencies=[Depends(get_current_user)])
async def api_list_interests(active_only: bool = False) -> list[InterestOut]:
    with session_scope() as session:
        interests = list_interests(session, active_only=active_only)
        return [_interest_to_out(i) for i in interests]


@router.get("/interests/{interest_id}", dependencies=[Depends(get_current_user)])
async def api_get_interest(interest_id: int) -> InterestOut:
    with session_scope() as session:
        i = get_interest(session, interest_id)
        if not i:
            raise HTTPException(404, "Interest not found")
        return _interest_to_out(i)


@router.post("/interests", dependencies=[Depends(get_current_user)], status_code=201)
async def api_create_interest(body: InterestCreate) -> InterestOut:
    with session_scope() as session:
        i = create_interest(
            session,
            topic=body.topic,
            description=body.description,
            priority=body.priority,
            check_interval_hours=body.check_interval_hours,
        )
        return _interest_to_out(i)


@router.patch("/interests/{interest_id}", dependencies=[Depends(get_current_user)])
async def api_update_interest(interest_id: int, body: InterestUpdate) -> InterestOut:
    with session_scope() as session:
        kwargs = body.model_dump(exclude_none=True)
        i = update_interest(session, interest_id, **kwargs)
        if not i:
            raise HTTPException(404, "Interest not found")
        return _interest_to_out(i)


@router.delete("/interests/{interest_id}", dependencies=[Depends(get_current_user)], status_code=204)
async def api_delete_interest(interest_id: int):
    with session_scope() as session:
        if not delete_interest(session, interest_id):
            raise HTTPException(404, "Interest not found")


# ============================================================================
# Chat
# ============================================================================


@router.post("/chat", dependencies=[Depends(get_current_user)])
async def api_chat(body: ChatRequest) -> ChatResponse:
    from src.agent import chat

    response = await chat(body.message, format_hint="web")
    return ChatResponse(response=response)


@router.post("/chat/stream", dependencies=[Depends(get_current_user)])
async def api_chat_stream(body: ChatRequest):
    """Streaming chat endpoint — returns Server-Sent Events."""
    import json

    from fastapi.responses import StreamingResponse

    from src.agent import chat_stream

    async def event_generator():
        if chat_stream is None:
            # Fallback to non-streaming
            from src.agent import chat

            response = await chat(body.message, format_hint="web")
            yield f"data: {json.dumps({'text': response})}\n\n"
        else:
            async for chunk in chat_stream(body.message, format_hint="web"):
                yield f"data: {json.dumps({'text': chunk})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
