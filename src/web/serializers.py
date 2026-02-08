"""Pydantic models for REST API request/response."""

from datetime import datetime

from pydantic import BaseModel


# --- Tasks ---
class TaskOut(BaseModel):
    id: int
    title: str
    description: str | None = None
    status: str
    priority: str
    due_date: datetime | None = None
    parent_id: int | None = None
    project_name: str | None = None
    project_emoji: str | None = None
    user_project_name: str | None = None
    user_project_emoji: str | None = None
    contact_name: str | None = None
    recurrence_rule: str | None = None
    created_at: datetime
    updated_at: datetime


class TaskCreate(BaseModel):
    title: str
    description: str | None = None
    priority: str = "medium"
    due_date: datetime | None = None
    parent_id: int | None = None
    project_id: int | None = None
    user_project_id: int | None = None
    contact_id: int | None = None
    recurrence_rule: str | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: str | None = None
    due_date: datetime | None = None
    parent_id: int | None = None
    project_id: int | None = None
    user_project_id: int | None = None
    contact_id: int | None = None
    clear_parent: bool = False
    clear_project: bool = False
    clear_user_project: bool = False
    clear_contact: bool = False


# --- Contacts ---
class ContactOut(BaseModel):
    id: int
    name: str
    aliases: str | None = None
    birthday: datetime | None = None
    notes: str | None = None
    created_at: datetime


class ContactCreate(BaseModel):
    name: str
    aliases: str | None = None
    birthday: datetime | None = None
    notes: str | None = None


class ContactUpdate(BaseModel):
    name: str | None = None
    aliases: str | None = None
    birthday: datetime | None = None
    notes: str | None = None
    clear_birthday: bool = False
    clear_aliases: bool = False


# --- Bookmarks ---
class BookmarkOut(BaseModel):
    id: int
    url: str
    title: str | None = None
    description: str | None = None
    domain: str | None = None
    tags: str | None = None
    read: bool
    created_at: datetime


class BookmarkCreate(BaseModel):
    url: str
    title: str | None = None
    description: str | None = None
    tags: str | None = None


# --- Mood ---
class MoodLogOut(BaseModel):
    id: int
    date: datetime
    score: int
    note: str | None = None
    created_at: datetime


class MoodLogCreate(BaseModel):
    date: datetime
    score: int
    note: str | None = None


# --- Projects ---
class ProjectOut(BaseModel):
    id: int
    name: str
    emoji: str
    created_at: datetime


class UserProjectOut(BaseModel):
    id: int
    name: str
    description: str | None = None
    emoji: str
    tag_name: str | None = None
    archived: bool
    created_at: datetime


class UserProjectCreate(BaseModel):
    name: str
    description: str | None = None
    emoji: str = "📁"
    tag_id: int | None = None


class UserProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    emoji: str | None = None
    tag_id: int | None = None
    archived: bool | None = None


# --- Shopping ---
class ShoppingItemOut(BaseModel):
    id: int
    name: str
    notes: str | None = None
    recipient: str | None = None
    priority: str
    checked: bool
    quantity_target: int
    quantity_purchased: int
    created_at: datetime


class ShoppingItemCreate(BaseModel):
    name: str
    notes: str | None = None
    recipient: str | None = None
    priority: str = "medium"
    quantity_target: int = 1


# --- Reminders ---
class ReminderOut(BaseModel):
    id: int
    message: str
    remind_at: datetime
    delivered: bool
    task_id: int | None = None
    created_at: datetime


class ReminderCreate(BaseModel):
    message: str
    remind_at: datetime
    task_id: int | None = None


# --- Profile ---
class ProfileOut(BaseModel):
    display_name: str | None = None
    city: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    timezone_str: str | None = None
    work_start_hour: int | None = None
    work_end_hour: int | None = None


class ProfileUpdate(BaseModel):
    display_name: str | None = None
    city: str | None = None
    timezone_str: str | None = None
    work_start_hour: int | None = None
    work_end_hour: int | None = None


# --- Calendar ---
class CalendarEventOut(BaseModel):
    id: int
    google_event_id: str
    title: str
    start_time: datetime
    end_time: datetime


# --- Chat ---
class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str
