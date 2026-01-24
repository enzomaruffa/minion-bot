from typing import Optional

from src.db import get_session
from src.db.queries import (
    create_user_project,
    get_project_by_name,
    get_user_project,
    get_user_project_by_name,
    list_user_projects as db_list_user_projects,
    get_tasks_by_user_project,
    update_user_project,
    delete_user_project,
    update_task,
)


def create_project(
    name: str,
    description: Optional[str] = None,
    emoji: str = "📁",
    tag: Optional[str] = None,
) -> str:
    """Create a new project to organize related tasks.

    Args:
        name: Name of the project (e.g., "MinionBot", "House Renovation").
        description: Optional description of the project.
        emoji: Emoji for the project. Defaults to 📁.
        tag: Optional category tag (Work/Personal/Health/Finance/Social/Learning).

    Returns:
        Confirmation message with the created project.
    """
    session = get_session()

    # Check if project already exists
    existing = get_user_project_by_name(session, name)
    if existing:
        session.close()
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
    session.close()

    tag_info = f" [{tag}]" if tag else ""
    return f"✓ Created project {emoji} <b>{name}</b>{tag_info}"


def list_projects_tool(include_archived: bool = False) -> str:
    """List all user-created projects.

    Args:
        include_archived: If True, also show archived projects.

    Returns:
        List of projects with task counts.
    """
    session = get_session()
    projects = db_list_user_projects(session, include_archived=include_archived)

    if not projects:
        session.close()
        return "No projects yet. Create one with create_project."

    lines = ["<b>📂 Projects</b>", ""]
    for p in projects:
        tasks = get_tasks_by_user_project(session, p.id)
        pending = sum(1 for t in tasks if t.status.value in ("todo", "in_progress"))
        done = sum(1 for t in tasks if t.status.value == "done")

        tag_info = f" <i>[{p.tag.name}]</i>" if p.tag else ""
        archived = " <s>(archived)</s>" if p.archived else ""
        lines.append(f"{p.emoji} <b>{p.name}</b>{tag_info}{archived}")
        lines.append(f"   {pending} pending, {done} done")

    session.close()
    return "\n".join(lines)


def show_project(project_name: str) -> str:
    """Show details and tasks for a specific project.

    Args:
        project_name: Name of the project.

    Returns:
        Project details and list of tasks.
    """
    session = get_session()
    project = get_user_project_by_name(session, project_name)

    if not project:
        session.close()
        return f"Project '{project_name}' not found."

    tasks = get_tasks_by_user_project(session, project.id)

    lines = [
        f"{project.emoji} <b>{project.name}</b>",
    ]

    if project.description:
        lines.append(f"<i>{project.description}</i>")

    if project.tag:
        lines.append(f"Tag: {project.tag.emoji} {project.tag.name}")

    lines.append("")

    if not tasks:
        lines.append("<i>No tasks in this project</i>")
    else:
        # Group by status
        in_progress = [t for t in tasks if t.status.value == "in_progress"]
        todo = [t for t in tasks if t.status.value == "todo"]
        done = [t for t in tasks if t.status.value == "done"]

        if in_progress:
            lines.append("<b>🔄 In Progress</b>")
            for t in in_progress:
                lines.append(f"  • <code>#{t.id}</code> {t.title}")

        if todo:
            lines.append("<b>📝 To Do</b>")
            for t in todo:
                lines.append(f"  • <code>#{t.id}</code> {t.title}")

        if done:
            lines.append(f"<i>✅ {len(done)} completed</i>")

    session.close()
    return "\n".join(lines)


def assign_to_project(task_id: int, project_name: str) -> str:
    """Assign a task to a project.

    Args:
        task_id: The ID of the task.
        project_name: Name of the project to assign to.

    Returns:
        Confirmation message.
    """
    session = get_session()
    project = get_user_project_by_name(session, project_name)

    if not project:
        session.close()
        return f"Project '{project_name}' not found."

    task = update_task(session, task_id, user_project_id=project.id)
    session.close()

    if not task:
        return f"Task #{task_id} not found."

    return f"✓ Assigned <code>#{task_id}</code> to {project.emoji} {project.name}"


def unassign_from_project(task_id: int) -> str:
    """Remove a task from its project.

    Args:
        task_id: The ID of the task.

    Returns:
        Confirmation message.
    """
    session = get_session()
    task = update_task(session, task_id, clear_user_project=True)
    session.close()

    if not task:
        return f"Task #{task_id} not found."

    return f"✓ Removed <code>#{task_id}</code> from project"


def archive_project(project_name: str) -> str:
    """Archive a project (hides it from list but preserves tasks).

    Args:
        project_name: Name of the project to archive.

    Returns:
        Confirmation message.
    """
    session = get_session()
    project = get_user_project_by_name(session, project_name)

    if not project:
        session.close()
        return f"Project '{project_name}' not found."

    delete_user_project(session, project.id)
    session.close()

    return f"✓ Archived project {project.emoji} {project.name}"
