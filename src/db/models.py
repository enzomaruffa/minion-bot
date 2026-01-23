from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import ForeignKey, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TaskStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[TaskStatus] = mapped_column(default=TaskStatus.TODO)
    priority: Mapped[TaskPriority] = mapped_column(default=TaskPriority.MEDIUM)
    due_date: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, onupdate=datetime.utcnow
    )

    parent: Mapped[Optional["Task"]] = relationship(
        "Task", remote_side=[id], back_populates="subtasks"
    )
    subtasks: Mapped[list["Task"]] = relationship("Task", back_populates="parent")
    attachments: Mapped[list["Attachment"]] = relationship(back_populates="task")
    reminders: Mapped[list["Reminder"]] = relationship(back_populates="task")


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    file_type: Mapped[str] = mapped_column(String(50))
    file_id: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    task: Mapped["Task"] = relationship(back_populates="attachments")


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    remind_at: Mapped[datetime] = mapped_column()
    delivered: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    task: Mapped[Optional["Task"]] = relationship(back_populates="reminders")


class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    google_event_id: Mapped[str] = mapped_column(String(255), unique=True)
    title: Mapped[str] = mapped_column(String(255))
    start_time: Mapped[datetime] = mapped_column()
    end_time: Mapped[datetime] = mapped_column()
    synced_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


def init_db(database_url: str) -> None:
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
