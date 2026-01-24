from typing import Optional

from src.db import session_scope
from src.db.queries import (
    create_user_project,
    get_project_by_name,
    get_user_project_by_name,
    list_user_projects as db_list_user_projects,
    get_tasks_by_user_project,
    delete_user_project,
    update_task,
)


def create_project(
    name: str,
    description: Optional[str] = None,
    emoji: str = "folder",
    tag: Optional[str] = None,
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

        project = create_user_project(
            session,
            name=name,
            description=description,
            emoji=emoji,
            tag_id=tag_id,
        )

        tag_info = f" [{tag}]" if tag else ""
        return f"Created project {emoji} {name}{tag_info}"


def list_projects_tool(include_archived: bool = False) -> str:
    """List all user-created projects.

    Args:
        include_archived: If True, also show archived projects.

    Returns:
        List of projects with task counts.
    """
    with session_scope() as session:
        projects = db_list_user_projects(session, include_archived=include_archived)

        if not projects:
            return "No projects yet. Create one with create_project."

        # Batch load all tasks for all project IDs to avoid N+1 query
        project_ids = [p.id for p in projects]
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        from src.db.models import Task
        
        stmt = (
            select(Task)
            .options(selectinload(Task.project))
            .where(Task.user_project_id.in_(project_ids))
        )
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
