"""Claude Agent SDK tool wrappers for all Minion tools.

Uses auto-schema generation from function signatures for most tools,
with manual JSON Schema overrides for complex parameter types (list[dict], etc.).

The original tool functions in src/agent/tools/ are kept as-is — they
become the implementation layer. This module wraps them for the SDK.
"""

from __future__ import annotations

import inspect
import logging
import types
from typing import Any, get_args, get_origin

from claude_agent_sdk import tool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema generation helpers
# ---------------------------------------------------------------------------


def _type_to_json_schema(annotation: Any) -> dict[str, Any]:
    """Convert a Python type annotation to a JSON Schema fragment."""
    if annotation is inspect.Parameter.empty or annotation is Any:
        return {"type": "string"}

    # Handle Union types (str | None, int | None, etc.)
    origin = get_origin(annotation)
    if origin is types.UnionType:
        non_none = [a for a in get_args(annotation) if a is not type(None)]
        if non_none:
            return _type_to_json_schema(non_none[0])

    if annotation is str:
        return {"type": "string"}
    if annotation is int:
        return {"type": "integer"}
    if annotation is float:
        return {"type": "number"}
    if annotation is bool:
        return {"type": "boolean"}

    # list[int], list[str], etc.
    if origin is list:
        args = get_args(annotation)
        if args:
            return {"type": "array", "items": _type_to_json_schema(args[0])}
        return {"type": "array"}

    # dict -> generic object
    if origin is dict or annotation is dict:
        return {"type": "object"}

    return {"type": "string"}  # fallback


def _auto_schema(fn: Any) -> dict[str, Any]:
    """Generate a JSON Schema from a function's signature and type annotations."""
    sig = inspect.signature(fn)
    properties: dict[str, Any] = {}
    required: list[str] = []

    for name, param in sig.parameters.items():
        prop = _type_to_json_schema(param.annotation)
        if param.default is inspect.Parameter.empty:
            required.append(name)
        properties[name] = prop

    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = required
    return schema


def _first_docstring_line(fn: Any) -> str:
    """Extract the first line of a function's docstring."""
    doc = fn.__doc__ or ""
    return doc.strip().split("\n")[0] or fn.__name__


def make_sdk_tool(
    impl_fn: Any,
    *,
    name: str | None = None,
    description: str | None = None,
    schema: dict[str, Any] | None = None,
) -> Any:
    """Wrap a sync tool function as an async @tool for the Claude Agent SDK.

    Args:
        impl_fn: The original sync tool function from src/agent/tools/.
        name: Override tool name (defaults to impl_fn.__name__).
        description: Override description (defaults to first docstring line).
        schema: Override JSON Schema (defaults to auto-generated from signature).
    """
    tool_name = name or impl_fn.__name__
    tool_desc = description or _first_docstring_line(impl_fn)
    tool_schema = schema or _auto_schema(impl_fn)

    @tool(tool_name, tool_desc, tool_schema)
    async def wrapper(args: dict[str, Any]) -> dict[str, Any]:
        # Filter out None values for optional params
        kwargs = {k: v for k, v in args.items() if v is not None}
        result = impl_fn(**kwargs)
        return {"content": [{"type": "text", "text": str(result)}]}

    return wrapper


# ---------------------------------------------------------------------------
# Import all implementation functions
# ---------------------------------------------------------------------------

from src.agent.tools import (  # noqa: E402
    get_current_datetime,
)
from src.agent.tools.agenda import get_agenda  # noqa: E402
from src.agent.tools.beads import beads_create, beads_list, beads_ready  # noqa: E402
from src.agent.tools.bookmarks import (  # noqa: E402
    list_reading_list,
    mark_read,
    remove_bookmark,
    save_bookmark,
    search_reading_list,
)
from src.agent.tools.calendar import (  # noqa: E402
    create_calendar_event,
    delete_calendar_event,
    list_calendar_events,
    test_calendar,
    update_calendar_event,
)
from src.agent.tools.code import run_python_code, run_shell_command  # noqa: E402
from src.agent.tools.contacts import (  # noqa: E402
    add_contact,
    get_contact_tasks,
    remove_contact,
    show_contacts,
    upcoming_birthdays,
    update_contact_tool,
)
from src.agent.tools.heartbeat_tools import (  # noqa: E402
    check_dedup,
    delegate_research,
    delegate_task_work,
    log_heartbeat_action,
    send_proactive_notification,
    task_nudge_dedup_key,
)
from src.agent.tools.interests import (  # noqa: E402
    add_interest,
    list_interests,
    remove_interest,
    update_interest_tool,
)
from src.agent.tools.mood import log_mood, mood_summary, show_mood_history  # noqa: E402
from src.agent.tools.notes import (  # noqa: E402
    append_to_note_tool,
    browse_notes,
    create_note_tool,
    read_note_tool,
    search_notes_tool,
    update_note_tool,
)
from src.agent.tools.profile import get_weather, show_profile, update_profile  # noqa: E402
from src.agent.tools.projects import (  # noqa: E402
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
from src.agent.tools.reminders import (  # noqa: E402
    cancel_reminder,
    list_reminders,
    remind_before_deadline,
    set_reminder,
)
from src.agent.tools.scheduling import find_free_slot  # noqa: E402
from src.agent.tools.shopping import (  # noqa: E402
    add_to_list,
    check_item,
    clear_checked,
    purchase_item,
    remove_item,
    show_gifts_for_contact,
    show_list,
    uncheck_item,
)
from src.agent.tools.tasks import (  # noqa: E402
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
from src.agent.tools.web import fetch_url, web_search  # noqa: E402

# ---------------------------------------------------------------------------
# Wrap all tools — auto-schema for simple tools, manual for complex
# ---------------------------------------------------------------------------

# -- Tools with complex schemas that need manual overrides --

sdk_add_tasks = make_sdk_tool(
    add_tasks,
    schema={
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "description": "List of task objects",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Task title"},
                        "description": {"type": "string", "description": "Task description"},
                        "priority": {
                            "type": "string",
                            "enum": ["low", "medium", "high", "urgent"],
                            "description": "Task priority",
                        },
                        "due_date": {
                            "type": "string",
                            "description": "Due date in natural language or ISO format",
                        },
                        "parent_id": {"type": "integer", "description": "Parent task ID for subtasks"},
                        "project": {"type": "string", "description": "Project name"},
                        "contact": {"type": "string", "description": "Contact name to link"},
                        "recurrence": {
                            "type": "string",
                            "description": "RRULE string like FREQ=WEEKLY;BYDAY=SA",
                        },
                    },
                    "required": ["title"],
                },
            },
        },
        "required": ["tasks"],
    },
)

sdk_assign_tasks_to_project = make_sdk_tool(
    assign_tasks_to_project,
    schema={
        "type": "object",
        "properties": {
            "task_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "List of task IDs to assign",
            },
            "project_name": {"type": "string", "description": "Project name"},
        },
        "required": ["task_ids", "project_name"],
    },
)

# -- All other tools use auto-schema --

_AUTO_WRAP_MAIN = [
    get_current_datetime,
    update_task_tool,
    complete_task,
    get_overdue_tasks,
    list_tasks,
    search_tasks_tool,
    get_task_details,
    delete_task_tool,
    add_subtask,
    move_task,
    list_tags,
    list_recurring,
    stop_recurring,
    # Projects (except assign_tasks_to_project — manual above)
    create_project,
    list_projects_tool,
    show_project,
    assign_to_project,
    unassign_from_project,
    archive_project,
    move_project_tasks,
    update_project,
    # Reminders
    set_reminder,
    list_reminders,
    cancel_reminder,
    remind_before_deadline,
    # Agenda
    get_agenda,
    # Calendar
    test_calendar,
    create_calendar_event,
    update_calendar_event,
    delete_calendar_event,
    list_calendar_events,
    # Shopping
    add_to_list,
    show_list,
    check_item,
    uncheck_item,
    remove_item,
    clear_checked,
    show_gifts_for_contact,
    purchase_item,
    # Contacts
    add_contact,
    show_contacts,
    upcoming_birthdays,
    update_contact_tool,
    remove_contact,
    get_contact_tasks,
    # Notes
    browse_notes,
    read_note_tool,
    create_note_tool,
    update_note_tool,
    append_to_note_tool,
    search_notes_tool,
    # Profile
    update_profile,
    show_profile,
    get_weather,
    # Bookmarks
    save_bookmark,
    list_reading_list,
    mark_read,
    remove_bookmark,
    search_reading_list,
    # Mood
    log_mood,
    show_mood_history,
    mood_summary,
    # Scheduling
    find_free_slot,
    # Code
    run_python_code,
    run_shell_command,
    # Web
    web_search,
    fetch_url,
    # Interests
    add_interest,
    list_interests,
    remove_interest,
    update_interest_tool,
    # Beads
    beads_create,
    beads_list,
    beads_ready,
]

_AUTO_WRAP_HEARTBEAT_ONLY = [
    check_dedup,
    log_heartbeat_action,
    send_proactive_notification,
    delegate_research,
    delegate_task_work,
    task_nudge_dedup_key,
]

# Build the SDK tool instances
_auto_main = [make_sdk_tool(fn) for fn in _AUTO_WRAP_MAIN]
_auto_heartbeat = [make_sdk_tool(fn) for fn in _AUTO_WRAP_HEARTBEAT_ONLY]

# ---------------------------------------------------------------------------
# Exported tool lists
# ---------------------------------------------------------------------------

# Tools given to the main chat agent
MAIN_TOOLS: list[Any] = [sdk_add_tasks, sdk_assign_tasks_to_project, *_auto_main]

# Tools given to the heartbeat agent (subset of main + heartbeat-specific)
HEARTBEAT_TOOLS: list[Any] = [
    # From main tools - context/read tools
    *[t for t in _auto_main if t.name in {
        "get_current_datetime",
        "get_agenda",
        "get_overdue_tasks",
        "list_tasks",
        "get_weather",
        "show_mood_history",
        "list_interests",
        "web_search",
        "fetch_url",
        "run_python_code",
        "run_shell_command",
        "beads_create",
        "beads_list",
        "beads_ready",
    }],
    # Heartbeat-specific tools
    *_auto_heartbeat,
]

logger.info(f"SDK tools initialized: {len(MAIN_TOOLS)} main, {len(HEARTBEAT_TOOLS)} heartbeat")
