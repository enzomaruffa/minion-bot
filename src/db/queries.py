from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql import Select

from .models import (
    Attachment,
    CalendarEvent,
    Contact,
    ItemPriority,
    Project,
    Reminder,
    ShoppingItem,
    ShoppingList,
    ShoppingListType,
    Task,
    TaskPriority,
    TaskStatus,
    UserCalendarToken,
    UserProject,
)

# ============================================================================
# Base Query Helpers (DRY)
# ============================================================================


def _task_query() -> Select[tuple[Task]]:
    """Base query for Task with common eager loads."""
    return select(Task).options(
        selectinload(Task.project),
        selectinload(Task.user_project),
        selectinload(Task.contact),
    )


def _shopping_item_query() -> Select[tuple[ShoppingItem]]:
    """Base query for ShoppingItem with common eager loads."""
    return select(ShoppingItem).options(
        selectinload(ShoppingItem.shopping_list),
        selectinload(ShoppingItem.contact),
    )


# ============================================================================
# Default projects to seed
DEFAULT_PROJECTS = [
    ("Work", "💼"),
    ("Personal", "🏠"),
    ("Health", "🏃"),
    ("Finance", "💰"),
    ("Social", "👥"),
    ("Learning", "📚"),
]


# Project CRUD
def seed_default_projects(session: Session) -> None:
    """Seed default projects if they don't exist."""
    for name, emoji in DEFAULT_PROJECTS:
        existing = session.scalars(select(Project).where(Project.name == name)).first()
        if not existing:
            session.add(Project(name=name, emoji=emoji))
    session.flush()


def get_project_by_name(session: Session, name: str) -> Project | None:
    """Get a project by name (case-insensitive)."""
    stmt = select(Project).where(Project.name.ilike(name))
    return session.scalars(stmt).first()


def list_projects(session: Session) -> Sequence[Project]:
    """List all projects."""
    stmt = select(Project).order_by(Project.name)
    return session.scalars(stmt).all()


def create_project(session: Session, name: str, emoji: str) -> Project:
    """Create a new project."""
    project = Project(name=name, emoji=emoji)
    session.add(project)
    session.flush()
    session.refresh(project)
    return project


# UserProject CRUD (user-created projects)
def create_user_project(
    session: Session,
    name: str,
    description: str | None = None,
    emoji: str = "📁",
    tag_id: int | None = None,
) -> UserProject:
    """Create a new user project."""
    project = UserProject(
        name=name,
        description=description,
        emoji=emoji,
        tag_id=tag_id,
    )
    session.add(project)
    session.flush()
    session.refresh(project)
    return project


def get_user_project(session: Session, project_id: int) -> UserProject | None:
    """Get a user project by ID."""
    return session.get(UserProject, project_id)


def get_user_project_by_name(session: Session, name: str) -> UserProject | None:
    """Get a user project by name (case-insensitive)."""
    stmt = select(UserProject).where(UserProject.name.ilike(name)).where(UserProject.archived == False)
    return session.scalars(stmt).first()


def list_user_projects(
    session: Session,
    include_archived: bool = False,
    has_todo: bool | None = None,
    has_done: bool | None = None,
    is_empty: bool | None = None,
) -> Sequence[UserProject]:
    """List user projects with optional filters.

    Args:
        include_archived: Include archived projects.
        has_todo: Filter to projects with pending tasks (todo/in_progress).
        has_done: Filter to projects with completed tasks.
        is_empty: Filter to projects with no tasks.
    """
    from sqlalchemy import and_, exists

    stmt = select(UserProject).order_by(UserProject.name)
    if not include_archived:
        stmt = stmt.where(UserProject.archived == False)

    # Filter by pending tasks
    if has_todo is not None:
        pending_exists = exists().where(
            and_(Task.user_project_id == UserProject.id, Task.status.in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS]))
        )
        if has_todo:
            stmt = stmt.where(pending_exists)
        else:
            stmt = stmt.where(~pending_exists)

    # Filter by completed tasks
    if has_done is not None:
        done_exists = exists().where(and_(Task.user_project_id == UserProject.id, Task.status == TaskStatus.DONE))
        if has_done:
            stmt = stmt.where(done_exists)
        else:
            stmt = stmt.where(~done_exists)

    # Filter by empty (no tasks at all)
    if is_empty is not None:
        task_exists = exists().where(Task.user_project_id == UserProject.id)
        if is_empty:
            stmt = stmt.where(~task_exists)
        else:
            stmt = stmt.where(task_exists)

    return session.scalars(stmt).all()


def update_user_project(
    session: Session,
    project_id: int,
    name: str | None = None,
    description: str | None = None,
    emoji: str | None = None,
    tag_id: int | None = None,
    archived: bool | None = None,
) -> UserProject | None:
    """Update a user project."""
    project = session.get(UserProject, project_id)
    if not project:
        return None

    if name is not None:
        project.name = name
    if description is not None:
        project.description = description
    if emoji is not None:
        project.emoji = emoji
    if tag_id is not None:
        project.tag_id = tag_id
    if archived is not None:
        project.archived = archived

    session.flush()
    session.refresh(project)
    return project


def delete_user_project(session: Session, project_id: int) -> bool:
    """Delete a user project (sets archived=True, doesn't actually delete)."""
    project = session.get(UserProject, project_id)
    if not project:
        return False
    project.archived = True
    session.flush()
    return True


def get_tasks_by_user_project(session: Session, project_id: int) -> Sequence[Task]:
    """Get all tasks in a user project."""
    stmt = _task_query().where(Task.user_project_id == project_id).order_by(Task.created_at.desc())
    return session.scalars(stmt).all()


def bulk_update_tasks_project(session: Session, task_ids: list[int], user_project_id: int | None) -> list[int]:
    """Bulk update user_project_id for multiple tasks.

    Args:
        session: Database session.
        task_ids: List of task IDs to update.
        user_project_id: Target project ID (or None to unassign).

    Returns:
        List of task IDs that were successfully updated.
    """
    from sqlalchemy import update

    if not task_ids:
        return []
    stmt = update(Task).where(Task.id.in_(task_ids)).values(user_project_id=user_project_id)
    session.execute(stmt)
    session.flush()
    return task_ids


def move_all_tasks_between_projects(session: Session, from_project_id: int, to_project_id: int) -> int:
    """Move all tasks from one project to another.

    Args:
        session: Database session.
        from_project_id: Source project ID.
        to_project_id: Destination project ID.

    Returns:
        Number of tasks moved.
    """
    from sqlalchemy import update

    stmt = update(Task).where(Task.user_project_id == from_project_id).values(user_project_id=to_project_id)
    result = session.execute(stmt)
    session.flush()
    return result.rowcount


# Task CRUD
def create_task(
    session: Session,
    title: str,
    description: str | None = None,
    priority: TaskPriority = TaskPriority.MEDIUM,
    due_date: datetime | None = None,
    parent_id: int | None = None,
    project_id: int | None = None,
    user_project_id: int | None = None,
    contact_id: int | None = None,
) -> Task:
    task = Task(
        title=title,
        description=description,
        priority=priority,
        due_date=due_date,
        parent_id=parent_id,
        project_id=project_id,
        user_project_id=user_project_id,
        contact_id=contact_id,
    )
    session.add(task)
    session.flush()
    session.refresh(task)
    return task


def get_task(session: Session, task_id: int) -> Task | None:
    stmt = _task_query().where(Task.id == task_id)
    return session.scalars(stmt).first()


def update_task(
    session: Session,
    task_id: int,
    title: str | None = None,
    description: str | None = None,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    due_date: datetime | None = None,
    parent_id: int | None = None,
    project_id: int | None = None,
    user_project_id: int | None = None,
    contact_id: int | None = None,
    clear_parent: bool = False,
    clear_project: bool = False,
    clear_user_project: bool = False,
    clear_contact: bool = False,
) -> Task | None:
    task = session.get(Task, task_id)
    if not task:
        return None

    if title is not None:
        task.title = title
    if description is not None:
        task.description = description
    if status is not None:
        task.status = status
    if priority is not None:
        task.priority = priority
    if due_date is not None:
        task.due_date = due_date
    if parent_id is not None:
        task.parent_id = parent_id
    if project_id is not None:
        task.project_id = project_id
    if user_project_id is not None:
        task.user_project_id = user_project_id
    if contact_id is not None:
        task.contact_id = contact_id
    if clear_parent:
        task.parent_id = None
    if clear_project:
        task.project_id = None
    if clear_user_project:
        task.user_project_id = None
    if clear_contact:
        task.contact_id = None

    session.flush()
    session.refresh(task)
    return task


def delete_task(session: Session, task_id: int) -> bool:
    task = session.get(Task, task_id)
    if not task:
        return False
    session.delete(task)
    session.flush()
    return True


def list_tasks_by_status(
    session: Session,
    status: TaskStatus | None = None,
    root_only: bool = False,
    project_id: int | None = None,
) -> Sequence[Task]:
    stmt = _task_query().order_by(Task.created_at.desc())
    if status:
        stmt = stmt.where(Task.status == status)
    if root_only:
        stmt = stmt.where(Task.parent_id.is_(None))
    if project_id:
        stmt = stmt.where(Task.project_id == project_id)
    return session.scalars(stmt).all()


def list_overdue_tasks(session: Session, now: datetime) -> Sequence[Task]:
    """Get tasks that are overdue (past due date and not done/cancelled)."""
    stmt = (
        _task_query()
        .where(Task.due_date < now)
        .where(Task.status.in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS]))
        .order_by(Task.due_date)
    )
    return session.scalars(stmt).all()


def list_tasks_due_soon(session: Session, now: datetime, within_hours: int = 24) -> Sequence[Task]:
    """Get tasks due within the next N hours."""
    deadline = now + timedelta(hours=within_hours)
    stmt = (
        _task_query()
        .where(Task.due_date >= now)
        .where(Task.due_date <= deadline)
        .where(Task.status.in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS]))
        .order_by(Task.due_date)
    )
    return session.scalars(stmt).all()


def count_tasks_by_due_date(session: Session, date: datetime) -> int:
    """Count tasks due on a specific date."""
    from sqlalchemy import func

    start = date.replace(hour=0, minute=0, second=0, microsecond=0)
    end = date.replace(hour=23, minute=59, second=59, microsecond=999999)
    stmt = (
        select(func.count())
        .select_from(Task)
        .where(Task.due_date >= start)
        .where(Task.due_date <= end)
        .where(Task.status.in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS]))
    )
    return session.scalar(stmt) or 0


def list_tasks_due_on_date(session: Session, day_start: datetime, day_end: datetime) -> Sequence[Task]:
    """Get active tasks due on a specific date range."""
    stmt = (
        _task_query()
        .where(Task.due_date >= day_start)
        .where(Task.due_date < day_end)
        .where(Task.status.in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS]))
        .order_by(Task.due_date)
    )
    return session.scalars(stmt).all()


def count_backlog_tasks(session: Session) -> int:
    """Count tasks with no due date and status=todo."""
    from sqlalchemy import func

    stmt = select(func.count()).select_from(Task).where(Task.status == TaskStatus.TODO).where(Task.due_date.is_(None))
    return session.scalar(stmt) or 0


def get_subtasks(session: Session, task_id: int) -> Sequence[Task]:
    """Get all subtasks of a given task."""
    stmt = _task_query().where(Task.parent_id == task_id).order_by(Task.created_at)
    return session.scalars(stmt).all()


def get_task_with_subtasks(session: Session, task_id: int) -> Task | None:
    """Get a task with its subtasks eagerly loaded."""
    task = session.get(Task, task_id)
    if task:
        # Force load subtasks
        _ = task.subtasks
    return task


def search_tasks(session: Session, query: str) -> Sequence[Task]:
    stmt = (
        _task_query()
        .where(Task.title.ilike(f"%{query}%") | Task.description.ilike(f"%{query}%"))
        .order_by(Task.created_at.desc())
    )
    return session.scalars(stmt).all()


# Reminder CRUD
def create_reminder(
    session: Session,
    message: str,
    remind_at: datetime,
    task_id: int | None = None,
) -> Reminder:
    reminder = Reminder(message=message, remind_at=remind_at, task_id=task_id)
    session.add(reminder)
    session.flush()
    session.refresh(reminder)
    return reminder


def list_pending_reminders(session: Session, before: datetime | None = None) -> Sequence[Reminder]:
    stmt = select(Reminder).where(Reminder.delivered == False).order_by(Reminder.remind_at)
    if before:
        stmt = stmt.where(Reminder.remind_at <= before)
    return session.scalars(stmt).all()


def list_all_reminders(session: Session, include_delivered: bool = False) -> Sequence[Reminder]:
    """List reminders, optionally including delivered ones."""
    stmt = select(Reminder).order_by(Reminder.remind_at.desc())
    if not include_delivered:
        stmt = stmt.where(Reminder.delivered == False)
    return session.scalars(stmt).all()


def mark_reminder_delivered(session: Session, reminder_id: int) -> bool:
    reminder = session.get(Reminder, reminder_id)
    if not reminder:
        return False
    reminder.delivered = True
    session.flush()
    return True


def delete_reminder(session: Session, reminder_id: int) -> bool:
    reminder = session.get(Reminder, reminder_id)
    if not reminder:
        return False
    session.delete(reminder)
    session.flush()
    return True


# CalendarEvent
def sync_calendar_event(
    session: Session,
    google_event_id: str,
    title: str,
    start_time: datetime,
    end_time: datetime,
) -> CalendarEvent:
    stmt = select(CalendarEvent).where(CalendarEvent.google_event_id == google_event_id)
    event = session.scalars(stmt).first()

    if event:
        event.title = title
        event.start_time = start_time
        event.end_time = end_time
        event.synced_at = datetime.now(UTC)
    else:
        event = CalendarEvent(
            google_event_id=google_event_id,
            title=title,
            start_time=start_time,
            end_time=end_time,
        )
        session.add(event)

    session.flush()
    session.refresh(event)
    return event


def list_calendar_events_range(session: Session, start: datetime, end: datetime) -> Sequence[CalendarEvent]:
    stmt = (
        select(CalendarEvent)
        .where(CalendarEvent.start_time >= start)
        .where(CalendarEvent.start_time <= end)
        .order_by(CalendarEvent.start_time)
    )
    return session.scalars(stmt).all()


def get_calendar_event_by_google_id(session: Session, google_event_id: str) -> CalendarEvent | None:
    stmt = select(CalendarEvent).where(CalendarEvent.google_event_id == google_event_id)
    return session.scalars(stmt).first()


# Attachment
def create_attachment(
    session: Session,
    task_id: int,
    file_type: str,
    file_id: str,
    description: str | None = None,
) -> Attachment:
    attachment = Attachment(
        task_id=task_id,
        file_type=file_type,
        file_id=file_id,
        description=description,
    )
    session.add(attachment)
    session.flush()
    session.refresh(attachment)
    return attachment


def list_attachments_by_task(session: Session, task_id: int) -> Sequence[Attachment]:
    stmt = select(Attachment).where(Attachment.task_id == task_id)
    return session.scalars(stmt).all()


# Shopping List CRUD
def seed_default_shopping_lists(session: Session) -> None:
    """Seed default shopping lists if they don't exist."""
    for list_type in ShoppingListType:
        existing = session.scalars(select(ShoppingList).where(ShoppingList.list_type == list_type)).first()
        if not existing:
            session.add(ShoppingList(list_type=list_type))
    session.flush()


def get_shopping_list_by_type(session: Session, list_type: ShoppingListType) -> ShoppingList | None:
    """Get a shopping list by type."""
    stmt = select(ShoppingList).where(ShoppingList.list_type == list_type)
    return session.scalars(stmt).first()


def create_shopping_item(
    session: Session,
    list_type: ShoppingListType,
    name: str,
    notes: str | None = None,
    recipient: str | None = None,
    contact_id: int | None = None,
    priority: ItemPriority = ItemPriority.MEDIUM,
    quantity_target: int = 1,
) -> ShoppingItem:
    """Create a new shopping item."""
    shopping_list = get_shopping_list_by_type(session, list_type)
    if not shopping_list:
        # Create the list if it doesn't exist
        shopping_list = ShoppingList(list_type=list_type)
        session.add(shopping_list)
        session.flush()

    item = ShoppingItem(
        list_id=shopping_list.id,
        name=name,
        notes=notes,
        recipient=recipient,
        contact_id=contact_id,
        priority=priority,
        quantity_target=quantity_target,
        quantity_purchased=0,
    )
    session.add(item)
    session.flush()
    session.refresh(item)
    return item


def get_shopping_item(session: Session, item_id: int) -> ShoppingItem | None:
    """Get a shopping item by ID."""
    stmt = _shopping_item_query().where(ShoppingItem.id == item_id)
    return session.scalars(stmt).first()


def list_shopping_items(
    session: Session,
    list_type: ShoppingListType | None = None,
    include_checked: bool = True,
) -> Sequence[ShoppingItem]:
    """List shopping items, optionally filtered by list type."""
    stmt = _shopping_item_query().order_by(ShoppingItem.created_at.desc())
    if list_type:
        shopping_list = get_shopping_list_by_type(session, list_type)
        if shopping_list:
            stmt = stmt.where(ShoppingItem.list_id == shopping_list.id)
        else:
            return []
    if not include_checked:
        stmt = stmt.where(ShoppingItem.checked == False)
    return session.scalars(stmt).all()


def check_shopping_item(session: Session, item_id: int, checked: bool = True) -> bool:
    """Mark a shopping item as checked/unchecked."""
    item = session.get(ShoppingItem, item_id)
    if not item:
        return False
    item.checked = checked
    session.flush()
    return True


def purchase_shopping_item(session: Session, item_id: int, quantity: int = 1) -> tuple[bool, int, int]:
    """Add to quantity purchased for a shopping item.

    Returns (success, new_purchased, target) tuple.
    Auto-checks item if purchased >= target.
    """
    item = session.get(ShoppingItem, item_id)
    if not item:
        return (False, 0, 0)

    item.quantity_purchased = min(item.quantity_purchased + quantity, item.quantity_target)

    # Auto-check if fully purchased
    if item.quantity_purchased >= item.quantity_target:
        item.checked = True

    session.flush()
    return (True, item.quantity_purchased, item.quantity_target)


def delete_shopping_item(session: Session, item_id: int) -> bool:
    """Delete a shopping item."""
    item = session.get(ShoppingItem, item_id)
    if not item:
        return False
    session.delete(item)
    session.flush()
    return True


def clear_checked_items(session: Session, list_type: ShoppingListType | None = None) -> int:
    """Clear all checked items, optionally from a specific list. Returns count."""
    from sqlalchemy import delete

    stmt = delete(ShoppingItem).where(ShoppingItem.checked == True)
    if list_type:
        shopping_list = get_shopping_list_by_type(session, list_type)
        if shopping_list:
            stmt = stmt.where(ShoppingItem.list_id == shopping_list.id)
        else:
            return 0
    result = session.execute(stmt)
    session.flush()
    return result.rowcount


# Contact CRUD
def create_contact(
    session: Session,
    name: str,
    aliases: str | None = None,
    birthday: datetime | None = None,
    notes: str | None = None,
) -> Contact:
    """Create a new contact."""
    contact = Contact(name=name, aliases=aliases, birthday=birthday, notes=notes)
    session.add(contact)
    session.flush()
    session.refresh(contact)
    return contact


def get_contact(session: Session, contact_id: int) -> Contact | None:
    """Get a contact by ID."""
    return session.get(Contact, contact_id)


def get_contact_by_name(session: Session, name: str) -> Contact | None:
    """Get a contact by name or alias (case-insensitive).

    Uses SQL LIKE for efficient alias searching instead of loading all contacts.
    """
    from sqlalchemy import func, or_

    # Try exact name match first
    stmt = select(Contact).where(Contact.name.ilike(name))
    contact = session.scalars(stmt).first()
    if contact:
        return contact

    # Search in aliases using SQL LIKE (aliases are comma-separated)
    # Match patterns: "name", "name, ...", "..., name", "..., name, ..."
    name_pattern = name.lower()
    stmt = select(Contact).where(
        or_(
            func.lower(Contact.aliases) == name_pattern,
            func.lower(Contact.aliases).like(f"{name_pattern},%"),
            func.lower(Contact.aliases).like(f"%, {name_pattern}"),
            func.lower(Contact.aliases).like(f"%, {name_pattern},%"),
        )
    )
    return session.scalars(stmt).first()


def list_contacts(session: Session) -> Sequence[Contact]:
    """List all contacts ordered by name."""
    stmt = select(Contact).order_by(Contact.name)
    return session.scalars(stmt).all()


def update_contact(
    session: Session,
    contact_id: int,
    name: str | None = None,
    aliases: str | None = None,
    birthday: datetime | None = None,
    notes: str | None = None,
    clear_birthday: bool = False,
    clear_aliases: bool = False,
) -> Contact | None:
    """Update a contact."""
    contact = session.get(Contact, contact_id)
    if not contact:
        return None

    if name is not None:
        contact.name = name
    if aliases is not None:
        contact.aliases = aliases
    if birthday is not None:
        contact.birthday = birthday
    if notes is not None:
        contact.notes = notes
    if clear_birthday:
        contact.birthday = None
    if clear_aliases:
        contact.aliases = None

    session.flush()
    session.refresh(contact)
    return contact


def delete_contact(session: Session, contact_id: int) -> bool:
    """Delete a contact."""
    contact = session.get(Contact, contact_id)
    if not contact:
        return False
    session.delete(contact)
    session.flush()
    return True


def list_upcoming_birthdays(session: Session, within_days: int = 14) -> Sequence[Contact]:
    """List contacts with birthdays within the next N days."""
    from src.config import settings
    from src.utils import days_until_birthday

    # Only load contacts that have a birthday set
    stmt = select(Contact).where(Contact.birthday.isnot(None)).order_by(Contact.name)
    contacts = session.scalars(stmt).all()
    today = datetime.now(settings.timezone).date()
    upcoming = []

    for contact in contacts:
        d = days_until_birthday(contact.birthday, today)
        if 0 <= d <= within_days:
            upcoming.append((contact, d))

    # Sort by days until birthday
    upcoming.sort(key=lambda x: x[1])
    return [c for c, _ in upcoming]


def get_tasks_by_contact(session: Session, contact_id: int) -> Sequence[Task]:
    """Get all tasks linked to a contact."""
    stmt = _task_query().where(Task.contact_id == contact_id).order_by(Task.created_at.desc())
    return session.scalars(stmt).all()


def get_task_counts_by_contacts(session: Session, contact_ids: list[int]) -> dict[int, int]:
    """Get task counts for multiple contacts in a single query.

    Args:
        session: Database session.
        contact_ids: List of contact IDs.

    Returns:
        Dict mapping contact_id -> task count.
    """
    if not contact_ids:
        return {}

    from sqlalchemy import func

    stmt = (
        select(Task.contact_id, func.count(Task.id)).where(Task.contact_id.in_(contact_ids)).group_by(Task.contact_id)
    )
    results = session.execute(stmt).all()
    return {contact_id: count for contact_id, count in results}


def get_gifts_by_contact(session: Session, contact_id: int) -> Sequence[ShoppingItem]:
    """Get all gift items linked to a contact."""
    stmt = _shopping_item_query().where(ShoppingItem.contact_id == contact_id).order_by(ShoppingItem.created_at.desc())
    return session.scalars(stmt).all()


# UserCalendarToken CRUD
def get_user_calendar_token(session: Session, telegram_user_id: int) -> UserCalendarToken | None:
    """Get calendar token for a Telegram user."""
    stmt = select(UserCalendarToken).where(UserCalendarToken.telegram_user_id == telegram_user_id)
    return session.scalars(stmt).first()


def save_user_calendar_token(
    session: Session,
    telegram_user_id: int,
    access_token: str,
    refresh_token: str | None,
    token_uri: str,
    client_id: str,
    client_secret: str,
    scopes: list[str],
    expiry: datetime | None = None,
) -> UserCalendarToken:
    """Save or update calendar token for a Telegram user."""
    import json

    existing = get_user_calendar_token(session, telegram_user_id)

    if existing:
        existing.access_token = access_token
        existing.refresh_token = refresh_token
        existing.token_uri = token_uri
        existing.client_id = client_id
        existing.client_secret = client_secret
        existing.scopes = json.dumps(scopes)
        existing.expiry = expiry
        session.flush()
        session.refresh(existing)
        return existing

    token = UserCalendarToken(
        telegram_user_id=telegram_user_id,
        access_token=access_token,
        refresh_token=refresh_token,
        token_uri=token_uri,
        client_id=client_id,
        client_secret=client_secret,
        scopes=json.dumps(scopes),
        expiry=expiry,
    )
    session.add(token)
    session.flush()
    session.refresh(token)
    return token


def delete_user_calendar_token(session: Session, telegram_user_id: int) -> bool:
    """Delete calendar token for a Telegram user."""
    token = get_user_calendar_token(session, telegram_user_id)
    if not token:
        return False
    session.delete(token)
    session.flush()
    return True


def update_user_calendar_token_credentials(
    session: Session,
    telegram_user_id: int,
    access_token: str,
    expiry: datetime | None = None,
) -> bool:
    """Update just the access token and expiry after a refresh."""
    token = get_user_calendar_token(session, telegram_user_id)
    if not token:
        return False
    token.access_token = access_token
    if expiry:
        token.expiry = expiry
    session.flush()
    return True
