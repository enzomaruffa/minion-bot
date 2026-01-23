from datetime import datetime
from typing import Optional

from src.db import get_session
from src.db.models import TaskPriority, TaskStatus
from src.db.queries import (
    create_task,
    delete_task,
    get_task,
    list_tasks_by_status,
    search_tasks,
    update_task,
    list_attachments_by_task,
)


def add_tasks(tasks: list[dict]) -> str:
    """Add one or more tasks to the task list.

    Args:
        tasks: List of task dictionaries with keys: title (required), description (optional),
               priority (optional: low/medium/high/urgent), due_date (optional: ISO format)

    Returns:
        Confirmation message with created task IDs.
    """
    session = get_session()
    created_ids = []

    for task_data in tasks:
        title = task_data.get("title")
        if not title:
            continue

        priority_str = task_data.get("priority", "medium")
        priority = TaskPriority(priority_str.lower())

        due_date = None
        if due_str := task_data.get("due_date"):
            due_date = datetime.fromisoformat(due_str)

        task = create_task(
            session,
            title=title,
            description=task_data.get("description"),
            priority=priority,
            due_date=due_date,
        )
        created_ids.append(task.id)

    session.close()
    return f"Created {len(created_ids)} task(s) with IDs: {created_ids}"


def update_task_tool(
    task_id: int,
    title: Optional[str] = None,
    description: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    due_date: Optional[str] = None,
) -> str:
    """Update an existing task.

    Args:
        task_id: The ID of the task to update.
        title: New title for the task.
        description: New description for the task.
        status: New status (todo/in_progress/done/cancelled).
        priority: New priority (low/medium/high/urgent).
        due_date: New due date in ISO format.

    Returns:
        Confirmation message or error if task not found.
    """
    session = get_session()

    status_enum = TaskStatus(status.lower()) if status else None
    priority_enum = TaskPriority(priority.lower()) if priority else None
    due_dt = datetime.fromisoformat(due_date) if due_date else None

    task = update_task(
        session,
        task_id,
        title=title,
        description=description,
        status=status_enum,
        priority=priority_enum,
        due_date=due_dt,
    )
    session.close()

    if not task:
        return f"Task {task_id} not found."

    return f"Updated task {task_id}: {task.title}"


def list_tasks(status: Optional[str] = None) -> str:
    """List tasks, optionally filtered by status.

    Args:
        status: Filter by status (todo/in_progress/done/cancelled). If not provided, lists all.

    Returns:
        Formatted list of tasks.
    """
    session = get_session()

    status_enum = TaskStatus(status.lower()) if status else None
    tasks = list_tasks_by_status(session, status_enum)
    session.close()

    if not tasks:
        return "No tasks found."

    lines = []
    for task in tasks:
        due = f" (due: {task.due_date.strftime('%Y-%m-%d')})" if task.due_date else ""
        lines.append(f"[{task.id}] {task.title} - {task.status.value}{due}")

    return "\n".join(lines)


def search_tasks_tool(query: str) -> str:
    """Search tasks by title or description.

    Args:
        query: Search query to match against task titles and descriptions.

    Returns:
        List of matching tasks.
    """
    session = get_session()
    tasks = search_tasks(session, query)
    session.close()

    if not tasks:
        return f"No tasks found matching '{query}'."

    lines = []
    for task in tasks:
        lines.append(f"[{task.id}] {task.title} - {task.status.value}")

    return "\n".join(lines)


def get_task_details(task_id: int) -> str:
    """Get detailed information about a specific task.

    Args:
        task_id: The ID of the task.

    Returns:
        Detailed task information including attachments.
    """
    session = get_session()
    task = get_task(session, task_id)

    if not task:
        session.close()
        return f"Task {task_id} not found."

    attachments = list_attachments_by_task(session, task_id)
    session.close()

    lines = [
        f"Task #{task.id}: {task.title}",
        f"Status: {task.status.value}",
        f"Priority: {task.priority.value}",
    ]

    if task.description:
        lines.append(f"Description: {task.description}")
    if task.due_date:
        lines.append(f"Due: {task.due_date.strftime('%Y-%m-%d %H:%M')}")

    lines.append(f"Created: {task.created_at.strftime('%Y-%m-%d %H:%M')}")

    if attachments:
        lines.append(f"Attachments: {len(attachments)}")
        for att in attachments:
            lines.append(f"  - {att.file_type}: {att.description or 'No description'}")

    return "\n".join(lines)


def delete_task_tool(task_id: int) -> str:
    """Delete a task.

    Args:
        task_id: The ID of the task to delete.

    Returns:
        Confirmation message or error if task not found.
    """
    session = get_session()
    success = delete_task(session, task_id)
    session.close()

    if success:
        return f"Deleted task {task_id}."
    return f"Task {task_id} not found."
