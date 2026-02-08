from src.db import session_scope
from src.db.queries import (
    bulk_update_tasks_project,
    create_user_project,
    delete_user_project,
    get_project_by_name,
    get_tasks_by_user_project,
    get_user_project_by_name,
    move_all_tasks_between_projects,
    update_task,
    update_user_project,
)
from src.db.queries import (
    list_user_projects as db_list_user_projects,
)


def create_project(
    name: str,
    description: str | None = None,
    emoji: str = "folder",
    tag: str | None = None,
) -> str:
    """Create a new project to organize related tasks.

    Args:
        name: Name of the project (e.g., "MinionBot", "House Renovation").
        description: Optional description of the project.
        emoji: Emoji for the project. Defaults to folder.
        tag: Optional category tag (Work/Personal/Health/Finance/Social/Learning).

    Returns:
        Confirmation message with the created project.
    """
    with session_scope() as session:
        # Check if project already exists
        existing = get_user_project_by_name(session, name)
        if existing:
            return f"Project '{name}' already exists."

        # Resolve tag to project_id
        tag_id = None
        if tag:
            tag_obj = get_project_by_name(session, tag)
            if tag_obj:
                tag_id = tag_obj.id

        create_user_project(
            session,
            name=name,
            description=description,
            emoji=emoji,
            tag_id=tag_id,
        )

        tag_info = f" [{tag}]" if tag else ""
        return f"Created project {emoji} {name}{tag_info}"


def list_projects_tool(
    include_archived: bool = False,
    has_todo: bool | None = None,
    has_done: bool | None = None,
    is_empty: bool | None = None,
) -> str:
    """List all user-created projects with optional filters.

    Args:
        include_archived: If True, also show archived projects.
        has_todo: If True, only projects with pending tasks. If False, only without.
        has_done: If True, only projects with completed tasks. If False, only without.
        is_empty: If True, only empty projects. If False, only non-empty.

    Returns:
        List of projects with task counts.
    """
    with session_scope() as session:
        projects = db_list_user_projects(
            session,
            include_archived=include_archived,
            has_todo=has_todo,
            has_done=has_done,
            is_empty=is_empty,
        )

        if not projects:
            return "No projects yet. Create one with create_project."

        # Batch load all tasks for all project IDs to avoid N+1 query
        project_ids = [p.id for p in projects]
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from src.db.models import Task

        stmt = select(Task).options(selectinload(Task.project)).where(Task.user_project_id.in_(project_ids))
        all_tasks = session.scalars(stmt).all()

        # Group tasks by project
        tasks_by_project: dict[int, list] = {pid: [] for pid in project_ids}
        for task in all_tasks:
            if task.user_project_id in tasks_by_project:
                tasks_by_project[task.user_project_id].append(task)

        lines = ["Projects", ""]
        for p in projects:
            tasks = tasks_by_project.get(p.id, [])
            pending = sum(1 for t in tasks if t.status.value in ("todo", "in_progress"))
            done = sum(1 for t in tasks if t.status.value == "done")

            tag_info = f" [{p.tag.name}]" if p.tag else ""
            archived = " (archived)" if p.archived else ""
            lines.append(f"#{p.id} {p.emoji} {p.name}{tag_info}{archived}")
            lines.append(f"   {pending} pending, {done} done")

        return "\n".join(lines)


def show_project(project_name: str) -> str:
    """Show details and tasks for a specific project.

    Args:
        project_name: Name of the project.

    Returns:
        Project details and list of tasks.
    """
    with session_scope() as session:
        project = get_user_project_by_name(session, project_name)

        if not project:
            return f"Project '{project_name}' not found."

        tasks = get_tasks_by_user_project(session, project.id)

        lines = [
            f"{project.emoji} {project.name}",
        ]

        if project.description:
            lines.append(f"{project.description}")

        if project.tag:
            lines.append(f"Tag: {project.tag.emoji} {project.tag.name}")

        lines.append("")

        if not tasks:
            lines.append("No tasks in this project")
        else:
            # Group by status
            in_progress = [t for t in tasks if t.status.value == "in_progress"]
            todo = [t for t in tasks if t.status.value == "todo"]
            done = [t for t in tasks if t.status.value == "done"]

            if in_progress:
                lines.append("In Progress")
                for t in in_progress:
                    lines.append(f"  #{t.id} {t.title}")

            if todo:
                lines.append("To Do")
                for t in todo:
                    lines.append(f"  #{t.id} {t.title}")

            if done:
                lines.append(f"{len(done)} completed")

        return "\n".join(lines)


def assign_to_project(task_id: int, project_name: str) -> str:
    """Assign a task to a project.

    Args:
        task_id: The ID of the task.
        project_name: Name of the project to assign to.

    Returns:
        Confirmation message.
    """
    with session_scope() as session:
        project = get_user_project_by_name(session, project_name)

        if not project:
            return f"Project '{project_name}' not found."

        task = update_task(session, task_id, user_project_id=project.id)

        if not task:
            return f"Task #{task_id} not found."

        return f"Assigned #{task_id} to {project.emoji} {project.name}"


def unassign_from_project(task_id: int) -> str:
    """Remove a task from its project.

    Args:
        task_id: The ID of the task.

    Returns:
        Confirmation message.
    """
    with session_scope() as session:
        task = update_task(session, task_id, clear_user_project=True)

        if not task:
            return f"Task #{task_id} not found."

        return f"Removed #{task_id} from project"


def archive_project(project_name: str) -> str:
    """Archive a project (hides it from list but preserves tasks).

    Args:
        project_name: Name of the project to archive.

    Returns:
        Confirmation message.
    """
    with session_scope() as session:
        project = get_user_project_by_name(session, project_name)

        if not project:
            return f"Project '{project_name}' not found."

        delete_user_project(session, project.id)

        return f"Archived project {project.emoji} {project.name}"


def assign_tasks_to_project(task_ids: list[int], project_name: str) -> str:
    """Assign multiple tasks to a project at once.

    Args:
        task_ids: List of task IDs to assign.
        project_name: Name of the project to assign to.

    Returns:
        Confirmation message with count of assigned tasks.
    """
    with session_scope() as session:
        project = get_user_project_by_name(session, project_name)

        if not project:
            return f"Project '{project_name}' not found."

        updated = bulk_update_tasks_project(session, task_ids, project.id)

        if not updated:
            return "No tasks were updated (IDs not found)."

        not_found = set(task_ids) - set(updated)
        msg = f"Assigned {len(updated)} tasks to {project.emoji} {project.name}"
        if not_found:
            msg += f" (IDs not found: {sorted(not_found)})"
        return msg


def move_project_tasks(from_project: str, to_project: str) -> str:
    """Move all tasks from one project to another.

    Args:
        from_project: Name of the source project.
        to_project: Name of the destination project.

    Returns:
        Confirmation message with count of moved tasks.
    """
    with session_scope() as session:
        src = get_user_project_by_name(session, from_project)
        if not src:
            return f"Source project '{from_project}' not found."

        dst = get_user_project_by_name(session, to_project)
        if not dst:
            return f"Destination project '{to_project}' not found."

        count = move_all_tasks_between_projects(session, src.id, dst.id)

        if count == 0:
            return f"No tasks to move from {src.emoji} {src.name}"

        return f"Moved {count} tasks from {src.emoji} {src.name} to {dst.emoji} {dst.name}"


def update_project(
    project_name: str,
    new_name: str | None = None,
    new_emoji: str | None = None,
    new_description: str | None = None,
    archived: bool | None = None,
) -> str:
    """Update project fields. Only provided fields are changed.

    Args:
        project_name: Name of the project to update.
        new_name: New name for the project.
        new_emoji: New emoji for the project.
        new_description: New description for the project.
        archived: Set to True to archive, False to unarchive.

    Returns:
        Confirmation message.
    """
    with session_scope() as session:
        project = get_user_project_by_name(session, project_name)

        # If not found by name (maybe archived), try looking up archived ones
        if not project and archived is False:
            from sqlalchemy import select

            from src.db.models import UserProject

            stmt = select(UserProject).where(UserProject.name.ilike(project_name), UserProject.archived.is_(True))
            project = session.scalars(stmt).first()

        if not project:
            return f"Project '{project_name}' not found."

        updated = update_user_project(
            session,
            project.id,
            name=new_name,
            description=new_description,
            emoji=new_emoji,
            archived=archived,
        )

        if not updated:
            return "Failed to update project."

        changes = []
        if new_name:
            changes.append(f"name -> {new_name}")
        if new_emoji:
            changes.append(f"emoji -> {new_emoji}")
        if new_description:
            changes.append("description updated")
        if archived is True:
            changes.append("archived")
        if archived is False:
            changes.append("unarchived")

        return f"Updated {updated.emoji} {updated.name}: {', '.join(changes)}"
