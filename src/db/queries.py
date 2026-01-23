from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

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
    Topic,
)


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
    session.commit()


def get_project_by_name(session: Session, name: str) -> Optional[Project]:
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
    session.commit()
    session.refresh(project)
    return project


# Task CRUD
def create_task(
    session: Session,
    title: str,
    description: Optional[str] = None,
    priority: TaskPriority = TaskPriority.MEDIUM,
    due_date: Optional[datetime] = None,
    parent_id: Optional[int] = None,
    project_id: Optional[int] = None,
    contact_id: Optional[int] = None,
) -> Task:
    task = Task(
        title=title,
        description=description,
        priority=priority,
        due_date=due_date,
        parent_id=parent_id,
        project_id=project_id,
        contact_id=contact_id,
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


def get_task(session: Session, task_id: int) -> Optional[Task]:
    return session.get(Task, task_id)


def update_task(
    session: Session,
    task_id: int,
    title: Optional[str] = None,
    description: Optional[str] = None,
    status: Optional[TaskStatus] = None,
    priority: Optional[TaskPriority] = None,
    due_date: Optional[datetime] = None,
    parent_id: Optional[int] = None,
    project_id: Optional[int] = None,
    contact_id: Optional[int] = None,
    clear_parent: bool = False,
    clear_project: bool = False,
    clear_contact: bool = False,
) -> Optional[Task]:
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
    if contact_id is not None:
        task.contact_id = contact_id
    if clear_parent:
        task.parent_id = None
    if clear_project:
        task.project_id = None
    if clear_contact:
        task.contact_id = None

    session.commit()
    session.refresh(task)
    return task


def delete_task(session: Session, task_id: int) -> bool:
    task = session.get(Task, task_id)
    if not task:
        return False
    session.delete(task)
    session.commit()
    return True


def list_tasks_by_status(
    session: Session,
    status: Optional[TaskStatus] = None,
    root_only: bool = False,
    project_id: Optional[int] = None,
) -> Sequence[Task]:
    stmt = select(Task).order_by(Task.created_at.desc())
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
        select(Task)
        .where(Task.due_date < now)
        .where(Task.status.in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS]))
        .order_by(Task.due_date)
    )
    return session.scalars(stmt).all()


def list_tasks_due_soon(session: Session, now: datetime, within_hours: int = 24) -> Sequence[Task]:
    """Get tasks due within the next N hours."""
    from datetime import timedelta
    deadline = now + timedelta(hours=within_hours)
    stmt = (
        select(Task)
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


def get_subtasks(session: Session, task_id: int) -> Sequence[Task]:
    """Get all subtasks of a given task."""
    stmt = select(Task).where(Task.parent_id == task_id).order_by(Task.created_at)
    return session.scalars(stmt).all()


def get_task_with_subtasks(session: Session, task_id: int) -> Optional[Task]:
    """Get a task with its subtasks eagerly loaded."""
    task = session.get(Task, task_id)
    if task:
        # Force load subtasks
        _ = task.subtasks
    return task


def search_tasks(session: Session, query: str) -> Sequence[Task]:
    stmt = (
        select(Task)
        .where(Task.title.ilike(f"%{query}%") | Task.description.ilike(f"%{query}%"))
        .order_by(Task.created_at.desc())
    )
    return session.scalars(stmt).all()


# Reminder CRUD
def create_reminder(
    session: Session,
    message: str,
    remind_at: datetime,
    task_id: Optional[int] = None,
) -> Reminder:
    reminder = Reminder(message=message, remind_at=remind_at, task_id=task_id)
    session.add(reminder)
    session.commit()
    session.refresh(reminder)
    return reminder


def list_pending_reminders(session: Session, before: Optional[datetime] = None) -> Sequence[Reminder]:
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
    session.commit()
    return True


def delete_reminder(session: Session, reminder_id: int) -> bool:
    reminder = session.get(Reminder, reminder_id)
    if not reminder:
        return False
    session.delete(reminder)
    session.commit()
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
        event.synced_at = datetime.utcnow()
    else:
        event = CalendarEvent(
            google_event_id=google_event_id,
            title=title,
            start_time=start_time,
            end_time=end_time,
        )
        session.add(event)

    session.commit()
    session.refresh(event)
    return event


def list_calendar_events_range(
    session: Session, start: datetime, end: datetime
) -> Sequence[CalendarEvent]:
    stmt = (
        select(CalendarEvent)
        .where(CalendarEvent.start_time >= start)
        .where(CalendarEvent.start_time <= end)
        .order_by(CalendarEvent.start_time)
    )
    return session.scalars(stmt).all()


def get_calendar_event_by_google_id(
    session: Session, google_event_id: str
) -> Optional[CalendarEvent]:
    stmt = select(CalendarEvent).where(CalendarEvent.google_event_id == google_event_id)
    return session.scalars(stmt).first()


# Attachment
def create_attachment(
    session: Session,
    task_id: int,
    file_type: str,
    file_id: str,
    description: Optional[str] = None,
) -> Attachment:
    attachment = Attachment(
        task_id=task_id,
        file_type=file_type,
        file_id=file_id,
        description=description,
    )
    session.add(attachment)
    session.commit()
    session.refresh(attachment)
    return attachment


def list_attachments_by_task(session: Session, task_id: int) -> Sequence[Attachment]:
    stmt = select(Attachment).where(Attachment.task_id == task_id)
    return session.scalars(stmt).all()


# Topic
def create_topic(
    session: Session, name: str, description: Optional[str] = None
) -> Topic:
    topic = Topic(name=name, description=description)
    session.add(topic)
    session.commit()
    session.refresh(topic)
    return topic


def get_or_create_topic(
    session: Session, name: str, description: Optional[str] = None
) -> Topic:
    stmt = select(Topic).where(Topic.name == name)
    topic = session.scalars(stmt).first()
    if topic:
        return topic
    return create_topic(session, name, description)


def list_topics(session: Session) -> Sequence[Topic]:
    stmt = select(Topic).order_by(Topic.name)
    return session.scalars(stmt).all()


# Shopping List CRUD
def seed_default_shopping_lists(session: Session) -> None:
    """Seed default shopping lists if they don't exist."""
    for list_type in ShoppingListType:
        existing = session.scalars(
            select(ShoppingList).where(ShoppingList.list_type == list_type)
        ).first()
        if not existing:
            session.add(ShoppingList(list_type=list_type))
    session.commit()


def get_shopping_list_by_type(
    session: Session, list_type: ShoppingListType
) -> Optional[ShoppingList]:
    """Get a shopping list by type."""
    stmt = select(ShoppingList).where(ShoppingList.list_type == list_type)
    return session.scalars(stmt).first()


def create_shopping_item(
    session: Session,
    list_type: ShoppingListType,
    name: str,
    notes: Optional[str] = None,
    recipient: Optional[str] = None,
    contact_id: Optional[int] = None,
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
    session.commit()
    session.refresh(item)
    return item


def get_shopping_item(session: Session, item_id: int) -> Optional[ShoppingItem]:
    """Get a shopping item by ID."""
    return session.get(ShoppingItem, item_id)


def list_shopping_items(
    session: Session,
    list_type: Optional[ShoppingListType] = None,
    include_checked: bool = True,
) -> Sequence[ShoppingItem]:
    """List shopping items, optionally filtered by list type."""
    stmt = select(ShoppingItem).order_by(ShoppingItem.created_at.desc())
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
    session.commit()
    return True


def purchase_shopping_item(
    session: Session, item_id: int, quantity: int = 1
) -> tuple[bool, int, int]:
    """Add to quantity purchased for a shopping item.
    
    Returns (success, new_purchased, target) tuple.
    Auto-checks item if purchased >= target.
    """
    item = session.get(ShoppingItem, item_id)
    if not item:
        return (False, 0, 0)
    
    item.quantity_purchased = min(
        item.quantity_purchased + quantity,
        item.quantity_target
    )
    
    # Auto-check if fully purchased
    if item.quantity_purchased >= item.quantity_target:
        item.checked = True
    
    session.commit()
    return (True, item.quantity_purchased, item.quantity_target)


def delete_shopping_item(session: Session, item_id: int) -> bool:
    """Delete a shopping item."""
    item = session.get(ShoppingItem, item_id)
    if not item:
        return False
    session.delete(item)
    session.commit()
    return True


def clear_checked_items(
    session: Session, list_type: Optional[ShoppingListType] = None
) -> int:
    """Clear all checked items, optionally from a specific list. Returns count."""
    items = list_shopping_items(session, list_type, include_checked=True)
    count = 0
    for item in items:
        if item.checked:
            session.delete(item)
            count += 1
    session.commit()
    return count


# Contact CRUD
def create_contact(
    session: Session,
    name: str,
    aliases: Optional[str] = None,
    birthday: Optional[datetime] = None,
    notes: Optional[str] = None,
) -> Contact:
    """Create a new contact."""
    contact = Contact(name=name, aliases=aliases, birthday=birthday, notes=notes)
    session.add(contact)
    session.commit()
    session.refresh(contact)
    return contact


def get_contact(session: Session, contact_id: int) -> Optional[Contact]:
    """Get a contact by ID."""
    return session.get(Contact, contact_id)


def get_contact_by_name(session: Session, name: str) -> Optional[Contact]:
    """Get a contact by name or alias (case-insensitive)."""
    # First try exact name match
    stmt = select(Contact).where(Contact.name.ilike(name))
    contact = session.scalars(stmt).first()
    if contact:
        return contact

    # Search in aliases (comma-separated)
    contacts = list_contacts(session)
    name_lower = name.lower()
    for contact in contacts:
        if contact.aliases:
            aliases = [a.strip().lower() for a in contact.aliases.split(",")]
            if name_lower in aliases:
                return contact
    return None


def list_contacts(session: Session) -> Sequence[Contact]:
    """List all contacts ordered by name."""
    stmt = select(Contact).order_by(Contact.name)
    return session.scalars(stmt).all()


def update_contact(
    session: Session,
    contact_id: int,
    name: Optional[str] = None,
    aliases: Optional[str] = None,
    birthday: Optional[datetime] = None,
    notes: Optional[str] = None,
    clear_birthday: bool = False,
    clear_aliases: bool = False,
) -> Optional[Contact]:
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

    session.commit()
    session.refresh(contact)
    return contact


def delete_contact(session: Session, contact_id: int) -> bool:
    """Delete a contact."""
    contact = session.get(Contact, contact_id)
    if not contact:
        return False
    session.delete(contact)
    session.commit()
    return True


def list_upcoming_birthdays(session: Session, within_days: int = 14) -> Sequence[Contact]:
    """List contacts with birthdays within the next N days."""
    from datetime import timedelta

    contacts = list_contacts(session)
    today = datetime.now().date()
    upcoming = []

    for contact in contacts:
        if contact.birthday:
            # Get this year's birthday
            bday = contact.birthday.date() if isinstance(contact.birthday, datetime) else contact.birthday
            this_year_bday = bday.replace(year=today.year)

            # If birthday already passed this year, check next year
            if this_year_bday < today:
                this_year_bday = bday.replace(year=today.year + 1)

            days_until = (this_year_bday - today).days
            if 0 <= days_until <= within_days:
                upcoming.append((contact, days_until))

    # Sort by days until birthday
    upcoming.sort(key=lambda x: x[1])
    return [c for c, _ in upcoming]


def get_tasks_by_contact(session: Session, contact_id: int) -> Sequence[Task]:
    """Get all tasks linked to a contact."""
    stmt = (
        select(Task)
        .where(Task.contact_id == contact_id)
        .order_by(Task.created_at.desc())
    )
    return session.scalars(stmt).all()


def get_gifts_by_contact(session: Session, contact_id: int) -> Sequence[ShoppingItem]:
    """Get all gift items linked to a contact."""
    stmt = (
        select(ShoppingItem)
        .where(ShoppingItem.contact_id == contact_id)
        .order_by(ShoppingItem.created_at.desc())
    )
    return session.scalars(stmt).all()
