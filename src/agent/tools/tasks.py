from datetime import datetime

from src.config import settings
from src.db import session_scope
from src.db.models import Task, TaskPriority, TaskStatus
from src.db.queries import (
    create_task,
    delete_task,
    get_contact_by_name,
    get_project_by_name,
    get_subtasks,
    get_task,
    list_attachments_by_task,
    list_tasks_by_status,
    search_tasks,
    update_task,
)
from src.db.queries import (
    list_projects as db_list_projects,
)
from src.utils import format_date, parse_date


def add_tasks(tasks: list[dict]) -> str:
    """Add one or more tasks to the task list.

    Args:
        tasks: List of task dictionaries with keys: title (required), description (optional),
               priority (optional: low/medium/high/urgent), due_date (optional: natural language
               like "tomorrow", "next Monday", "in 2 hours" or ISO format),
               parent_id (optional: ID of parent task for creating subtasks),
               project (optional: project name like "Work", "Personal", "Health", etc.),
               contact (optional: contact name to link the task to),
               recurrence (optional: RRULE string like "FREQ=WEEKLY;BYDAY=SA")

    Returns:
        Confirmation message with created task IDs.
    """
    with session_scope() as session:
        created_ids = []
        recurrence_flags = []

        for task_data in tasks:
            title = task_data.get("title")
            if not title:
                continue

            priority_str = task_data.get("priority", "medium")
            priority = TaskPriority(priority_str.lower())

            due_date = None
            if due_str := task_data.get("due_date"):
                due_date = parse_date(due_str)

            parent_id = task_data.get("parent_id")
            recurrence = task_data.get("recurrence")

            # Resolve project by name
            project_id = None
            if project_name := task_data.get("project"):
                project = get_project_by_name(session, project_name)
                if project:
                    project_id = project.id

            # Resolve contact by name
            contact_id = None
            if contact_name := task_data.get("contact"):
                contact = get_contact_by_name(session, contact_name)
                if contact:
                    contact_id = contact.id

            task = create_task(
                session,
                title=title,
                description=task_data.get("description"),
                priority=priority,
                due_date=due_date,
                parent_id=parent_id,
                project_id=project_id,
                contact_id=contact_id,
            )

            # Set recurrence rule if provided
            if recurrence:
                task.recurrence_rule = recurrence
                session.flush()
                recurrence_flags.append(True)
            else:
                recurrence_flags.append(False)

            created_ids.append(task.id)

    if len(created_ids) == 1:
        recur = " 🔄" if recurrence_flags[0] else ""
        return f"Created task <code>#{created_ids[0]}</code>{recur}"
    return f"Created {len(created_ids)} tasks: {', '.join(f'<code>#{id}</code>' for id in created_ids)}"


def update_task_tool(
    task_id: int,
    title: str | None = None,
    description: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    due_date: str | None = None,
    project: str | None = None,
    contact: str | None = None,
) -> str:
    """Update an existing task.

    Args:
        task_id: The ID of the task to update.
        title: New title for the task.
        description: New description for the task.
        status: New status (todo/in_progress/done/cancelled).
        priority: New priority (low/medium/high/urgent).
        due_date: New due date (natural language like "tomorrow" or ISO format).
        project: Project name (Work/Personal/Health/Finance/Social/Learning).
        contact: Contact name to link this task to.

    Returns:
        Confirmation message or error if task not found.
    """
    with session_scope() as session:
        status_enum = TaskStatus(status.lower()) if status else None
        priority_enum = TaskPriority(priority.lower()) if priority else None
        due_dt = parse_date(due_date) if due_date else None

        # Resolve project by name
        project_id = None
        if project:
            proj = get_project_by_name(session, project)
            if proj:
                project_id = proj.id

        # Resolve contact by name
        contact_id = None
        if contact:
            c = get_contact_by_name(session, contact)
            if c:
                contact_id = c.id

        task = update_task(
            session,
            task_id,
            title=title,
            description=description,
            status=status_enum,
            priority=priority_enum,
            due_date=due_dt,
            project_id=project_id,
            contact_id=contact_id,
        )

        if not task:
            return f"Task <code>#{task_id}</code> not found"

        return f"Updated <code>#{task_id}</code> <i>{task.title}</i>"


def complete_task(task_id: int) -> str:
    """Mark a task as done (shorthand for updating status to done).

    Args:
        task_id: The ID of the task to complete.

    Returns:
        Confirmation message or error if task not found.
    """
    with session_scope() as session:
        task = update_task(session, task_id, status=TaskStatus.DONE)

        if not task:
            return f"Task <code>#{task_id}</code> not found"

        return f"✓ Completed <code>#{task_id}</code> <i>{task.title}</i>"


def get_overdue_tasks() -> str:
    """Get all tasks that are past their due date.

    Returns:
        Formatted list of overdue tasks or message if none.
    """
    from src.db.queries import list_overdue_tasks

    with session_scope() as session:
        now = datetime.now(settings.timezone).replace(tzinfo=None)
        tasks = list_overdue_tasks(session, now)

        if not tasks:
            return "No overdue tasks! 🎉"

        lines = ["<b>⚠️ Overdue Tasks</b>"]
        for task in tasks:
            lines.append(_format_task_line(task))

        return "\n".join(lines)


def _format_task_line(task: Task, indent: int = 0) -> str:
    """Format a single task line with optional indentation."""
    prefix = "  " if indent > 0 else ""
    project_emoji = task.project.emoji + " " if task.project else ""
    contact_info = f" {task.contact.name}" if task.contact else ""
    recur_icon = " 🔄" if task.recurrence_rule else ""

    # Check if overdue
    now = datetime.now(settings.timezone).replace(tzinfo=None)
    overdue_badge = ""
    if task.due_date and task.due_date < now and task.status.value in ("todo", "in_progress"):
        overdue_badge = " OVERDUE"

    due = f" {format_date(task.due_date)}" if task.due_date else ""
    status_icon = {"todo": "[ ]", "in_progress": "[~]", "done": "[x]", "cancelled": "[-]"}.get(task.status.value, "")
    return f"{prefix}{status_icon} #{task.id} {project_emoji}{task.title}{contact_info}{due}{overdue_badge}{recur_icon}"


def _build_task_tree(tasks: list[Task]) -> dict[int | None, list[Task]]:
    """Group tasks by parent_id for in-memory tree traversal."""
    tree: dict[int | None, list[Task]] = {}
    for task in tasks:
        tree.setdefault(task.parent_id, []).append(task)
    return tree


def _format_task_with_subtasks(task: Task, tree: dict[int | None, list[Task]], indent: int = 0) -> list[str]:
    """Format a task and its subtasks from a pre-built tree."""
    lines = [_format_task_line(task, indent)]
    for subtask in tree.get(task.id, []):
        lines.extend(_format_task_with_subtasks(subtask, tree, indent + 1))
    return lines


def list_tasks(
    status: str | None = None,
    project: str | None = None,
    include_subtasks: bool = True,
) -> str:
    """List tasks, optionally filtered by status and/or project.

    Args:
        status: Filter by status (todo/in_progress/done/cancelled). If not provided, lists all.
        project: Filter by project name (Work/Personal/Health/Finance/Social/Learning).
        include_subtasks: If True, show subtasks nested under their parents. Default True.

    Returns:
        Formatted list of tasks with IDs prefixed by # and project emoji.
    """
    with session_scope() as session:
        status_enum = TaskStatus(status.lower()) if status else None

        # Resolve project filter
        project_id = None
        if project:
            proj = get_project_by_name(session, project)
            if proj:
                project_id = proj.id

        if include_subtasks:
            # Load all matching tasks in one query, build tree in memory
            all_tasks = list_tasks_by_status(session, status_enum, project_id=project_id)
            if not all_tasks:
                return "No tasks found. Try saying 'remind me to...' to create one!"

            tree = _build_task_tree(list(all_tasks))
            root_tasks = [t for t in all_tasks if t.parent_id is None]

            lines = []
            for task in root_tasks:
                lines.extend(_format_task_with_subtasks(task, tree))
        else:
            # Flat list of all tasks
            tasks = list_tasks_by_status(session, status_enum, project_id=project_id)
            if not tasks:
                return "No tasks found. Try saying 'remind me to...' to create one!"

            lines = [_format_task_line(task) for task in tasks]

        return "\n".join(lines)


def search_tasks_tool(query: str) -> str:
    """Search tasks by title or description.

    Args:
        query: Search query to match against task titles and descriptions.

    Returns:
        List of matching tasks with IDs prefixed by # and project emoji.
    """
    with session_scope() as session:
        tasks = search_tasks(session, query)

        if not tasks:
            return f"No tasks found matching '{query}'."

        lines = []
        for task in tasks:
            project_emoji = task.project.emoji + " " if task.project else ""
            parent_info = f" (subtask of #{task.parent_id})" if task.parent_id else ""
            lines.append(f"#{task.id}: {project_emoji}{task.title} [{task.status.value}]{parent_info}")

        return "\n".join(lines)


def get_task_details(task_id: int) -> str:
    """Get detailed information about a specific task.

    Args:
        task_id: The ID of the task.

    Returns:
        Detailed task information including parent, subtasks, contact, and attachments.
    """
    with session_scope() as session:
        task = get_task(session, task_id)

        if not task:
            return f"Task #{task_id} not found."

        attachments = list_attachments_by_task(session, task_id)
        subtasks = get_subtasks(session, task_id)

        lines = [
            f"Task #{task.id}: {task.title}",
            f"Status: {task.status.value}",
            f"Priority: {task.priority.value}",
        ]

        if task.project:
            lines.append(f"Project: {task.project.emoji} {task.project.name}")

        if task.contact:
            contact_info = f"Contact: {task.contact.name}"
            if task.contact.birthday:
                contact_info += f" ({task.contact.birthday.strftime('%B %d')})"
            lines.append(contact_info)

        if task.parent_id:
            parent = get_task(session, task.parent_id)
            if parent:
                lines.append(f"Parent: #{parent.id} ({parent.title})")

        if task.description:
            lines.append(f"Description: {task.description}")
        if task.due_date:
            lines.append(f"Due: {task.due_date.strftime('%Y-%m-%d %H:%M')}")

        lines.append(f"Created: {task.created_at.strftime('%Y-%m-%d %H:%M')}")

        if subtasks:
            lines.append(f"Subtasks ({len(subtasks)}):")
            for sub in subtasks:
                lines.append(f"  - #{sub.id}: {sub.title} [{sub.status.value}]")

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
    with session_scope() as session:
        success = delete_task(session, task_id)

        if success:
            return f"Deleted task #{task_id}."
        return f"Task #{task_id} not found."


def add_subtask(
    parent_id: int,
    title: str,
    description: str | None = None,
    priority: str | None = None,
    due_date: str | None = None,
    project: str | None = None,
) -> str:
    """Add a subtask to an existing task.

    Args:
        parent_id: The ID of the parent task (must use the exact # ID from list_tasks).
        title: Title of the subtask.
        description: Optional description.
        priority: Priority (low/medium/high/urgent). Defaults to medium.
        due_date: Due date (natural language like "tomorrow" or ISO format).
        project: Project name. If not provided, inherits from parent task.

    Returns:
        Confirmation message with the created subtask ID.
    """
    with session_scope() as session:
        # Verify parent exists
        parent = get_task(session, parent_id)
        if not parent:
            return f"Parent task #{parent_id} not found."

        priority_enum = TaskPriority(priority.lower()) if priority else TaskPriority.MEDIUM
        due_dt = parse_date(due_date) if due_date else None

        # Resolve project - inherit from parent if not specified
        project_id = parent.project_id  # inherit by default
        if project:
            proj = get_project_by_name(session, project)
            if proj:
                project_id = proj.id

        task = create_task(
            session,
            title=title,
            description=description,
            priority=priority_enum,
            due_date=due_dt,
            parent_id=parent_id,
            project_id=project_id,
        )

        return f"Created subtask #{task.id} under parent #{parent_id}: {title}"


def move_task(task_id: int, new_parent_id: int | None = None) -> str:
    """Move a task to become a subtask of another task, or make it a root task.

    Args:
        task_id: The ID of the task to move.
        new_parent_id: The ID of the new parent task, or None to make it a root task.

    Returns:
        Confirmation message or error.
    """
    with session_scope() as session:
        task = get_task(session, task_id)
        if not task:
            return f"Task #{task_id} not found."

        if new_parent_id is not None:
            # Verify new parent exists
            new_parent = get_task(session, new_parent_id)
            if not new_parent:
                return f"New parent task #{new_parent_id} not found."

            # Prevent circular references
            if new_parent_id == task_id:
                return "A task cannot be its own parent."

            # Check if new_parent is a descendant of task (would create cycle)
            current = new_parent
            while current.parent_id:
                if current.parent_id == task_id:
                    return f"Cannot move task #{task_id}: would create circular reference."
                current = get_task(session, current.parent_id)
                if not current:
                    break

            update_task(session, task_id, parent_id=new_parent_id)
            return f"Moved task #{task_id} under parent #{new_parent_id}"
        else:
            update_task(session, task_id, clear_parent=True)
            return f"Made task #{task_id} a root task (no parent)"


def stop_recurring(task_id: int) -> str:
    """Stop a task from recurring. Clears the recurrence rule.

    Args:
        task_id: The ID of the recurring task.

    Returns:
        Confirmation message.
    """
    with session_scope() as session:
        task = get_task(session, task_id)
        if not task:
            return f"Task <code>#{task_id}</code> not found."
        if not task.recurrence_rule:
            return f"Task <code>#{task_id}</code> is not recurring."

        task.recurrence_rule = None
        session.flush()
        return f"✓ Stopped recurrence for <code>#{task_id}</code> <i>{task.title}</i>"


def list_recurring() -> str:
    """List all active recurring tasks.

    Returns:
        Formatted list of recurring tasks with their recurrence rules.
    """
    with session_scope() as session:
        from sqlalchemy import select

        from src.db.models import Task as TaskModel

        stmt = (
            select(TaskModel)
            .where(
                TaskModel.recurrence_rule.isnot(None),
                TaskModel.status.in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS]),
            )
            .order_by(TaskModel.created_at.desc())
        )
        tasks = session.scalars(stmt).all()

        if not tasks:
            return "<i>No active recurring tasks.</i>"

        lines = ["<b>🔄 Recurring Tasks</b>"]
        for task in tasks:
            due = f" {format_date(task.due_date)}" if task.due_date else ""
            lines.append(f"• <code>#{task.id}</code> {task.title}{due}")
            lines.append(f"  <i>{task.recurrence_rule}</i>")

        return "\n".join(lines)


def list_tags() -> str:
    """List all available tags (categories) for task categorization.

    Returns:
        List of tags with their emojis.
    """
    with session_scope() as session:
        projects = db_list_projects(session)

        if not projects:
            return "No tags found."

        lines = ["Tags", ""]
        for p in projects:
            lines.append(f"  {p.emoji} {p.name}")
        return "\n".join(lines)
