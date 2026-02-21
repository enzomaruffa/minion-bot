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

# Phase 4: Autonomous Proactive Agent tools
from .beads import beads_create, beads_list, beads_ready  # noqa: E402
from .bookmarks import (  # noqa: E402
    list_reading_list,
    mark_read,
    remove_bookmark,
    save_bookmark,
    search_reading_list,
)
from .calendar import (  # noqa: E402
    create_calendar_event,
    delete_calendar_event,
    list_calendar_events,
    test_calendar,
    update_calendar_event,
)
from .code import run_python_code, run_shell_command  # noqa: E402
from .contacts import (  # noqa: E402
    add_contact,
    get_contact_tasks,
    remove_contact,
    show_contacts,
    upcoming_birthdays,
    update_contact_tool,
)
from .heartbeat_tools import (  # noqa: E402
    check_dedup,
    delegate_research,
    delegate_task_work,
    log_heartbeat_action,
    send_proactive_notification,
)
from .interests import (  # noqa: E402
    add_interest,
    list_interests,
    remove_interest,
    update_interest_tool,
)
from .mood import log_mood, mood_summary, show_mood_history  # noqa: E402
from .notes import (  # noqa: E402
    append_to_note_tool,
    browse_notes,
    create_note_tool,
    read_note_tool,
    search_notes_tool,
    update_note_tool,
)
from .profile import get_weather, show_profile, update_profile  # noqa: E402
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
    remind_before_deadline,
    set_reminder,
)
from .scheduling import find_free_slot  # noqa: E402
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
    list_recurring,
    list_tags,
    list_tasks,
    move_task,
    search_tasks_tool,
    stop_recurring,
    update_task_tool,
)
from .web import fetch_url, web_search  # noqa: E402

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
    "remind_before_deadline",
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
    # Profile tools
    "update_profile",
    "show_profile",
    "get_weather",
    # Bookmark tools
    "save_bookmark",
    "list_reading_list",
    "mark_read",
    "remove_bookmark",
    "search_reading_list",
    # Mood tools
    "log_mood",
    "show_mood_history",
    "mood_summary",
    # Scheduling tools
    "find_free_slot",
    # Recurring task tools
    "list_recurring",
    "stop_recurring",
    # Code execution tools
    "run_python_code",
    "run_shell_command",
    # Web tools
    "web_search",
    "fetch_url",
    # Interest tools
    "add_interest",
    "list_interests",
    "remove_interest",
    "update_interest_tool",
    # Beads fallback tools
    "beads_create",
    "beads_list",
    "beads_ready",
    # Heartbeat-internal tools
    "check_dedup",
    "log_heartbeat_action",
    "send_proactive_notification",
    "delegate_research",
    "delegate_task_work",
]
