from datetime import datetime

from src.config import settings


def get_current_datetime() -> str:
    """Get the current date and time in the configured timezone.

    Returns:
        Current datetime formatted as a human-readable string.
    """
    now = datetime.now(settings.timezone)
    return now.strftime("%A, %B %d, %Y at %H:%M:%S %Z")


from .agenda import get_agenda  # noqa: E402
from .calendar import (  # noqa: E402
    create_calendar_event,
    delete_calendar_event,
    list_calendar_events,
    test_calendar,
    update_calendar_event,
)
from .contacts import (  # noqa: E402
    add_contact,
    get_contact_tasks,
    remove_contact,
    show_contacts,
    upcoming_birthdays,
    update_contact_tool,
)
from .notes import (  # noqa: E402
    append_to_note_tool,
    browse_notes,
    create_note_tool,
    read_note_tool,
    search_notes_tool,
    update_note_tool,
)
from .projects import (  # noqa: E402
    archive_project,
    assign_tasks_to_project,
    assign_to_project,
    create_project,
    list_projects_tool,
    move_project_tasks,
    show_project,
    unassign_from_project,
    update_project,
)
from .reminders import (  # noqa: E402
    cancel_reminder,
    list_reminders,
    set_reminder,
)
from .shopping import (  # noqa: E402
    add_to_list,
    check_item,
    clear_checked,
    purchase_item,
    remove_item,
    show_gifts_for_contact,
    show_list,
    uncheck_item,
)
from .tasks import (  # noqa: E402
    add_subtask,
    add_tasks,
    complete_task,
    delete_task_tool,
    get_overdue_tasks,
    get_task_details,
    list_tags,
    list_tasks,
    move_task,
    search_tasks_tool,
    update_task_tool,
)

__all__ = [
    "get_current_datetime",
    "add_tasks",
    "update_task_tool",
    "complete_task",
    "get_overdue_tasks",
    "list_tasks",
    "search_tasks_tool",
    "get_task_details",
    "delete_task_tool",
    "add_subtask",
    "move_task",
    "list_tags",
    # Project tools
    "create_project",
    "list_projects_tool",
    "show_project",
    "assign_to_project",
    "unassign_from_project",
    "archive_project",
    "assign_tasks_to_project",
    "move_project_tasks",
    "update_project",
    "set_reminder",
    "list_reminders",
    "cancel_reminder",
    "get_agenda",
    "test_calendar",
    "create_calendar_event",
    "update_calendar_event",
    "delete_calendar_event",
    "list_calendar_events",
    # Shopping tools
    "add_to_list",
    "show_list",
    "check_item",
    "uncheck_item",
    "remove_item",
    "clear_checked",
    "show_gifts_for_contact",
    "purchase_item",
    # Contact tools
    "add_contact",
    "show_contacts",
    "upcoming_birthdays",
    "update_contact_tool",
    "remove_contact",
    "get_contact_tasks",
    # Notes tools
    "browse_notes",
    "read_note_tool",
    "create_note_tool",
    "update_note_tool",
    "append_to_note_tool",
    "search_notes_tool",
]
