from datetime import datetime
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    Attachment,
    CalendarEvent,
    Reminder,
    Task,
    TaskPriority,
    TaskStatus,
    Topic,
)


# Task CRUD
def create_task(
    session: Session,
    title: str,
    description: Optional[str] = None,
    priority: TaskPriority = TaskPriority.MEDIUM,
    due_date: Optional[datetime] = None,
) -> Task:
    task = Task(
        title=title,
        description=description,
        priority=priority,
        due_date=due_date,
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
    session: Session, status: Optional[TaskStatus] = None
) -> Sequence[Task]:
    stmt = select(Task).order_by(Task.created_at.desc())
    if status:
        stmt = stmt.where(Task.status == status)
    return session.scalars(stmt).all()


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
