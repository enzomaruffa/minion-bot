from datetime import UTC, datetime
from enum import StrEnum
from typing import Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TaskStatus(StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


class TaskPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class ShoppingListType(StrEnum):
    GIFTS = "gifts"
    GROCERIES = "groceries"
    WISHLIST = "wishlist"


class ItemPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    aliases: Mapped[str | None] = mapped_column(String(500), nullable=True)  # Comma-separated
    birthday: Mapped[datetime | None] = mapped_column(nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))

    tasks: Mapped[list["Task"]] = relationship(back_populates="contact")


class Project(Base):
    """Category/tag for tasks (Work, Personal, Health, etc.)."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    emoji: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))

    tasks: Mapped[list["Task"]] = relationship(back_populates="project")


class UserProject(Base):
    """User-created project with tasks (e.g., MinionBot, House Renovation)."""

    __tablename__ = "user_projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    emoji: Mapped[str] = mapped_column(String(10), default="📁")
    tag_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    archived: Mapped[bool] = mapped_column(default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))

    tag: Mapped[Optional["Project"]] = relationship()
    tasks: Mapped[list["Task"]] = relationship(back_populates="user_project")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[TaskStatus] = mapped_column(default=TaskStatus.TODO)
    priority: Mapped[TaskPriority] = mapped_column(default=TaskPriority.MEDIUM)
    due_date: Mapped[datetime | None] = mapped_column(nullable=True, index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True, index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True, index=True)
    user_project_id: Mapped[int | None] = mapped_column(ForeignKey("user_projects.id"), nullable=True, index=True)
    contact_id: Mapped[int | None] = mapped_column(ForeignKey("contacts.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    recurrence_rule: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recurrence_source_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    parent: Mapped[Optional["Task"]] = relationship(
        "Task", remote_side=[id], back_populates="subtasks", foreign_keys=[parent_id]
    )
    subtasks: Mapped[list["Task"]] = relationship("Task", back_populates="parent", foreign_keys="[Task.parent_id]")
    attachments: Mapped[list["Attachment"]] = relationship(back_populates="task")
    reminders: Mapped[list["Reminder"]] = relationship(back_populates="task")
    project: Mapped[Optional["Project"]] = relationship(back_populates="tasks")
    user_project: Mapped[Optional["UserProject"]] = relationship(back_populates="tasks")
    contact: Mapped[Optional["Contact"]] = relationship(back_populates="tasks")


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    file_type: Mapped[str] = mapped_column(String(50))
    file_id: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))

    task: Mapped["Task"] = relationship(back_populates="attachments")


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    remind_at: Mapped[datetime] = mapped_column(index=True)
    delivered: Mapped[bool] = mapped_column(default=False, index=True)
    auto_created: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))

    task: Mapped[Optional["Task"]] = relationship(back_populates="reminders")


class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    google_event_id: Mapped[str] = mapped_column(String(255), unique=True)
    title: Mapped[str] = mapped_column(String(255))
    start_time: Mapped[datetime] = mapped_column(index=True)
    end_time: Mapped[datetime] = mapped_column()
    synced_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))


class ShoppingList(Base):
    __tablename__ = "shopping_lists"

    id: Mapped[int] = mapped_column(primary_key=True)
    list_type: Mapped[ShoppingListType] = mapped_column(unique=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))

    items: Mapped[list["ShoppingItem"]] = relationship(back_populates="shopping_list")


class ShoppingItem(Base):
    __tablename__ = "shopping_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    list_id: Mapped[int] = mapped_column(ForeignKey("shopping_lists.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recipient: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Fallback if no contact
    contact_id: Mapped[int | None] = mapped_column(ForeignKey("contacts.id"), nullable=True, index=True)
    priority: Mapped[ItemPriority] = mapped_column(default=ItemPriority.MEDIUM)
    checked: Mapped[bool] = mapped_column(default=False)
    quantity_target: Mapped[int] = mapped_column(default=1)
    quantity_purchased: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))

    shopping_list: Mapped["ShoppingList"] = relationship(back_populates="items")
    contact: Mapped[Optional["Contact"]] = relationship()

    @property
    def is_complete(self) -> bool:
        """Check if item is complete (purchased >= target or manually checked)."""
        return self.checked or self.quantity_purchased >= self.quantity_target


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    latitude: Mapped[float | None] = mapped_column(nullable=True)
    longitude: Mapped[float | None] = mapped_column(nullable=True)
    timezone_str: Mapped[str | None] = mapped_column(String(50), nullable=True)
    work_start_hour: Mapped[int | None] = mapped_column(nullable=True)  # 0-23
    work_end_hour: Mapped[int | None] = mapped_column(nullable=True)  # 0-23
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))


class Bookmark(Base):
    __tablename__ = "bookmarks"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(2048), unique=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tags: Mapped[str | None] = mapped_column(String(500), nullable=True)  # Comma-separated
    read: Mapped[bool] = mapped_column(default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))


class MoodLog(Base):
    __tablename__ = "mood_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[datetime] = mapped_column(unique=True, index=True)  # Date only
    score: Mapped[int] = mapped_column()  # 1-5
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))


class WebSession(Base):
    """Browser session for web dashboard auth."""

    __tablename__ = "web_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_token: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    telegram_user_id: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    expires_at: Mapped[datetime] = mapped_column()


class UserInterest(Base):
    """User interests for proactive heartbeat monitoring."""

    __tablename__ = "user_interests"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[int] = mapped_column(default=1)  # 1-3, higher = more important
    active: Mapped[bool] = mapped_column(default=True, index=True)
    check_interval_hours: Mapped[int] = mapped_column(default=24)
    last_checked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))


class HeartbeatLog(Base):
    """Log of heartbeat agent actions for audit and dedup."""

    __tablename__ = "heartbeat_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    dedup_key: Mapped[str] = mapped_column(String(255), index=True)
    action_type: Mapped[str] = mapped_column(String(50))  # research, notify, skip, delegate, plan
    summary: Mapped[str] = mapped_column(Text)
    interest_id: Mapped[int | None] = mapped_column(ForeignKey("user_interests.id"), nullable=True)
    notified: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))

    interest: Mapped[Optional["UserInterest"]] = relationship()


class UserCalendarToken(Base):
    """Stores Google Calendar OAuth tokens per Telegram user."""

    __tablename__ = "user_calendar_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(unique=True, index=True)
    access_token: Mapped[str] = mapped_column(Text)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_uri: Mapped[str] = mapped_column(String(255))
    client_id: Mapped[str] = mapped_column(String(255))
    client_secret: Mapped[str] = mapped_column(String(255))
    scopes: Mapped[str] = mapped_column(Text)  # JSON list
    expiry: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
