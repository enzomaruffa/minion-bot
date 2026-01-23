from .tasks import (
    add_tasks,
    update_task_tool,
    list_tasks,
    search_tasks_tool,
    get_task_details,
    delete_task_tool,
    add_subtask,
    move_task,
    list_projects,
)
from .reminders import (
    set_reminder,
    list_reminders,
    cancel_reminder,
)
from .agenda import get_agenda
from .calendar import (
    test_calendar,
    create_calendar_event,
    update_calendar_event,
    delete_calendar_event,
    list_calendar_events,
)
from .shopping import (
    add_to_list,
    show_list,
    check_item,
    uncheck_item,
    remove_item,
    clear_checked,
    show_gifts_for_contact,
)
from .contacts import (
    add_contact,
    show_contacts,
    upcoming_birthdays,
    update_contact_tool,
    remove_contact,
    get_contact_tasks,
)

__all__ = [
    "add_tasks",
    "update_task_tool",
    "list_tasks",
    "search_tasks_tool",
    "get_task_details",
    "delete_task_tool",
    "add_subtask",
    "move_task",
    "list_projects",
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
    # Contact tools
    "add_contact",
    "show_contacts",
    "upcoming_birthdays",
    "update_contact_tool",
    "remove_contact",
    "get_contact_tasks",
]
