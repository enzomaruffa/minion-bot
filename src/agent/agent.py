import asyncio
import logging
import time
import uuid
from typing import Any, Callable, Dict

from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.memory import MemoryManager
from agno.models.openai import OpenAIChat

from src.config import settings

logger = logging.getLogger(__name__)


def tool_logger_hook(
    function_name: str, function_call: Callable, arguments: Dict[str, Any]
) -> Any:
    """Log tool calls with execution time and send error notifications."""
    logger.info(f"Tool call: {function_name}({arguments})")
    start_time = time.time()
    
    try:
        result = function_call(**arguments)
        duration = time.time() - start_time
        logger.info(f"Tool {function_name} completed in {duration:.2f}s")
        return result
    except Exception as e:
        duration = time.time() - start_time
        error_id = str(uuid.uuid4())[:8]
        logger.exception(f"Tool {function_name} failed after {duration:.2f}s: {e} (ID: {error_id})")
        
        # Send async error notification
        try:
            from src.telegram.bot import notify_error
            loop = asyncio.get_running_loop()
            loop.create_task(notify_error(function_name, e, error_id))
        except RuntimeError:
            # No event loop running
            pass
        except Exception as notify_err:
            logger.debug(f"Could not send error notification: {notify_err}")
        
        raise
from src.agent.tools import (
    get_current_datetime,
    add_tasks,
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
    # Project tools
    create_project,
    list_projects_tool,
    show_project,
    assign_to_project,
    unassign_from_project,
    archive_project,
    assign_tasks_to_project,
    move_project_tasks,
    update_project,
    # Reminder tools
    set_reminder,
    list_reminders,
    cancel_reminder,
    get_agenda,
    test_calendar,
    create_calendar_event,
    update_calendar_event,
    delete_calendar_event,
    list_calendar_events,
    # Shopping tools
    add_to_list,
    show_list,
    check_item,
    uncheck_item,
    remove_item,
    clear_checked,
    show_gifts_for_contact,
    purchase_item,
    # Contact tools
    add_contact,
    show_contacts,
    upcoming_birthdays,
    update_contact_tool,
    remove_contact,
    get_contact_tasks,
)

SYSTEM_PROMPT = """You are Minion, a personal assistant bot running on Telegram.

Your personality:
- Friendly and helpful, but concise
- Proactive - just do reversible actions, confirm after
- Remember context from the conversation

TELEGRAM FORMATTING (HTML mode):
Use these HTML tags for formatting:
- <b>bold</b> — headers, emphasis
- <i>italic</i> — secondary info, notes
- <s>strikethrough</s> — completed/cancelled items
- <code>code</code> — IDs like #12, technical values
- • for bullet points (unicode, not -)

DO NOT use: Markdown syntax (*bold*, _italic_, `code`)
Use \n for line breaks, not <br>
Keep messages under 4096 chars.

Example format:
<b>📋 Tasks Due Today</b>
• <code>#12</code> 💼 Buy groceries <i>(Personal)</i>
• <code>#15</code> 🏃 Call dentist

Your capabilities:
- Task management: create, update, list, search, and delete tasks
- Task hierarchy: create subtasks under parent tasks, move tasks between parents
- Project categorization: auto-assign tasks to projects based on context
- Reminders: set timed reminders, list pending, cancel
- Agenda: show combined view of tasks, events, and reminders
- Shopping lists: manage gifts, groceries, and wishlist items
- Contacts: track people and their birthdays

BEHAVIOR:
Be proactive! For reversible actions (adding tasks, items, contacts), just do it - don't ask permission.
You can always undo. Only ask BEFORE for destructive/non-reversible actions (deleting, clearing).
After doing something, confirm what you did so the user can correct if needed.

CRITICAL RULES:
1. NEVER lie about your actions. If you made a mistake, own it immediately.
2. ONLY perform the exact action requested. Don't "clean up" or modify unrelated data.
3. When asked to fix X, only touch X. Don't touch Y or Z "while you're at it".
4. ALWAYS call show_list/show_contacts/list_tasks BEFORE any delete/remove operation to verify IDs.
   Tool calls are cheap. Deleting the wrong thing is expensive. NEVER guess IDs from memory.
5. For deletions: if user clearly specified what to delete (e.g., "delete Chikonato with K"), just do it
   after verifying IDs. Only ask for confirmation when genuinely ambiguous.

TAGS (Categories):
When creating tasks, ALWAYS auto-assign a tag based on the task content. NEVER ask the user
which tag to use - infer it from context. Available tags:
- Work 💼: job tasks, meetings, PRs, code reviews, office work
- Personal 🏠: home tasks, errands, personal items
- Health 🏃: exercise, medical appointments, wellness
- Finance 💰: bills, budget, investments, taxes
- Social 👥: friends, family, events, gatherings
- Learning 📚: courses, books, skills, tutorials

Example tag mappings:
- "finish FBI PR" → Work
- "buy groceries" → Personal
- "schedule dentist" → Health
- "pay electricity bill" → Finance
- "call Jana about party" → Social
- "read React docs" → Learning

PROJECTS (User-Created):
Projects are user-created containers for related tasks (e.g., "MinionBot", "House Renovation").
- Projects have a name, emoji, and optional tag for categorization
- Use create_project to create new projects
- Use assign_to_project to add tasks to a project
- Use show_project to see all tasks in a project
- Tasks can have both a tag (category) AND belong to a project
- When user mentions a project name, use it; otherwise don't assign projects
- Projects show as [📁ProjectName] in task lists

TASK DESCRIPTIONS:
Tasks can have optional descriptions for extra context. Descriptions:
- Are hidden in list views to keep them clean
- Are shown when using get_task_details
- Are searchable with search_tasks_tool
Use descriptions for notes, links, or details that don't fit in the title.

SHOPPING LISTS:
Three types - auto-infer, never ask:
- Gifts 🎁: "gift for mom" → Gifts (anything with a recipient or gift-related keywords)
- Groceries 🛒: "buy eggs" → Groceries (supermarket/house items, default for ambiguous)
- Wishlist ✨: "that PS5 I want" → Wishlist (personal wants, "wish", "want", "someday")
Just add items. Don't ask "which list?" - infer it.
Gift items with recipients auto-link to contacts if they exist. Use show_gifts_for_contact to see all gift ideas for someone.

Quantities: Add "12 eggs" and it creates with target=12. Use purchase_item to track partial purchases
(e.g., "bought 3 eggs" → purchase_item(id, 3)). Items auto-complete when purchased >= target.

IMPORTANT - Item IDs: Item IDs are database IDs starting from 1, NOT list positions. IDs are shown as
#1, #2, etc. in show_list output. NEVER guess IDs - if you need to check/remove/purchase an item and
don't know its ID, call show_list FIRST to see actual IDs. There is no item #0.

CONTACTS:
Track birthdays with add_contact. You'll be reminded of upcoming birthdays at 5pm daily.
Contacts support aliases (e.g., "Jana" is also "Janaina") - use these for nicknames/full names.
When creating tasks about a person (e.g., "call Jana"), link to their contact if they exist.
Just create contacts when user mentions birthdays - don't ask permission.

IMPORTANT: Task IDs are prefixed with # (e.g., #5, #12). When the user refers to a task by number,
ALWAYS use the exact numeric ID shown after the # symbol. Do NOT confuse list position with task ID.
For example, if the list shows "#10: Buy groceries", the task ID is 10, not the position in the list.

When the user mentions something that sounds like a task, offer to add it.
When they mention a time or deadline, offer to set a reminder.
Always confirm actions taken.

Current timezone: America/Sao_Paulo
"""

# Session database for agent memory
_db: SqliteDb | None = None


def get_db() -> SqliteDb:
    """Get or create the session database."""
    global _db
    if _db is None:
        db_path = settings.database_path.parent / "agent_sessions.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _db = SqliteDb(db_file=str(db_path))
    return _db


def get_memory_manager() -> MemoryManager:
    """Create a memory manager with custom instructions."""
    return MemoryManager(
        model=OpenAIChat(id="gpt-5-mini", api_key=settings.openai_api_key),
        db=get_db(),
        additional_instructions="""
        Focus on remembering:
        
        PEOPLE:
        - Names and relationships (e.g., "Jana is friend", "Carlos is accountant")
        - Context about people mentioned (work colleague, family, service provider)
        - How the user prefers to interact with them
        
        PROJECTS & GOALS:
        - Active projects the user is working on
        - Project goals and desired outcomes
        - Project deadlines and milestones
        
        PREFERENCES & HABITS:
        - Work hours and productivity patterns
        - Preferred task organization style
        - Communication preferences
        - Recurring schedules (gym days, meeting patterns)
        
        CONTEXT FROM CONVERSATIONS:
        - Ongoing situations (job search, health goals, events planning)
        - Decisions made and their reasoning
        - Things the user said they would do later
        
        IMPORTANT DATES:
        - Birthdays, anniversaries, deadlines
        - Recurring appointments
        
        Do NOT store:
        - Passwords, API keys, or sensitive credentials
        - Financial account details
        - Temporary information with no lasting value
        """,
    )


def create_agent() -> Agent:
    """Create and configure the Minion agent."""
    logger.info("Creating Minion agent...")
    return Agent(
        model=OpenAIChat(
            id="gpt-5.2",
            api_key=settings.openai_api_key,
        ),
        tools=[
            # Utility tools
            get_current_datetime,
            # Task management tools
            add_tasks,
            update_task_tool,
            complete_task,
            get_overdue_tasks,
            list_tasks,
            search_tasks_tool,
            get_task_details,
            delete_task_tool,
            # Task hierarchy tools
            add_subtask,
            move_task,
            # Tag tools
            list_tags,
            # Project tools
            create_project,
            list_projects_tool,
            show_project,
            assign_to_project,
            unassign_from_project,
            archive_project,
            assign_tasks_to_project,
            move_project_tasks,
            update_project,
            # Reminder tools
            set_reminder,
            list_reminders,
            cancel_reminder,
            # Agenda tool
            get_agenda,
            # Calendar tools
            test_calendar,
            create_calendar_event,
            update_calendar_event,
            delete_calendar_event,
            list_calendar_events,
            # Shopping list tools
            add_to_list,
            show_list,
            check_item,
            uncheck_item,
            remove_item,
            clear_checked,
            show_gifts_for_contact,
            purchase_item,
            # Contact tools
            add_contact,
            show_contacts,
            upcoming_birthdays,
            update_contact_tool,
            remove_contact,
            get_contact_tasks,
        ],
        instructions=SYSTEM_PROMPT,
        markdown=True,
        # Tool hooks for logging
        tool_hooks=[tool_logger_hook],
        # Database for persistence
        db=get_db(),
        # Memory configuration
        memory_manager=get_memory_manager(),
        enable_user_memories=True,
        enable_agentic_memory=True,
        add_memories_to_context=True,
        # Session history
        add_history_to_context=True,
        num_history_runs=10,
        read_chat_history=True,
        max_tool_calls_from_history=5,
        # Context enhancements
        add_datetime_to_context=True,
    )


# Singleton agent instance
_agent: Agent | None = None


def get_agent() -> Agent:
    """Get or create the agent singleton."""
    global _agent
    if _agent is None:
        _agent = create_agent()
    return _agent


# Fixed session ID for single-user bot
SESSION_ID = f"user_{settings.telegram_user_id}"


async def chat(message: str) -> str:
    """Send a message to the agent and get a response."""
    logger.info(f"Chat input: {message[:100]}{'...' if len(message) > 100 else ''}")
    
    try:
        agent = get_agent()
        response = agent.run(
            message,
            user_id=str(settings.telegram_user_id),
            session_id=SESSION_ID,
        )
        
        content = response.content or ""
        logger.info(f"Chat output: {content[:100]}{'...' if len(content) > 100 else ''}")
        
        return content
    except Exception as e:
        logger.exception(f"Agent error: {e}")
        raise
