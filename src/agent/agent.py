from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.memory import MemoryManager
from agno.models.openai import OpenAIChat

from src.config import settings
from src.agent.tools import (
    add_tasks,
    update_task_tool,
    list_tasks,
    search_tasks_tool,
    get_task_details,
    delete_task_tool,
    add_subtask,
    move_task,
    set_reminder,
    list_reminders,
    cancel_reminder,
    get_agenda,
)

SYSTEM_PROMPT = """You are Minion, a personal assistant bot helping manage tasks, reminders, and calendar.

Your personality:
- Friendly and helpful, but concise
- Proactive in suggesting organization improvements
- Remember context from the conversation

Your capabilities:
- Task management: create, update, list, search, and delete tasks
- Task hierarchy: create subtasks under parent tasks, move tasks between parents
- Reminders: set timed reminders, list pending, cancel
- Agenda: show combined view of tasks, events, and reminders

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
        model=OpenAIChat(id="gpt-4o-mini", api_key=settings.openai_api_key),
        db=get_db(),
        additional_instructions="""
        Focus on remembering:
        - User preferences and habits
        - Recurring tasks and schedules
        - Important dates and deadlines
        - Project context and goals
        Do NOT store sensitive information like passwords or API keys.
        """,
    )


def create_agent() -> Agent:
    """Create and configure the Minion agent."""
    return Agent(
        model=OpenAIChat(
            id="gpt-4o",
            api_key=settings.openai_api_key,
        ),
        tools=[
            # Task management tools
            add_tasks,
            update_task_tool,
            list_tasks,
            search_tasks_tool,
            get_task_details,
            delete_task_tool,
            # Task hierarchy tools
            add_subtask,
            move_task,
            # Reminder tools
            set_reminder,
            list_reminders,
            cancel_reminder,
            # Agenda tool
            get_agenda,
        ],
        instructions=SYSTEM_PROMPT,
        markdown=True,
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
    agent = get_agent()
    response = agent.run(
        message,
        user_id=str(settings.telegram_user_id),
        session_id=SESSION_ID,
    )
    return response.content
