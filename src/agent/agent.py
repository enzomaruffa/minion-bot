from agno.agent import Agent
from agno.models.openai import OpenAIChat

from src.config import settings
from src.agent.tools import (
    add_tasks,
    update_task_tool,
    list_tasks,
    search_tasks_tool,
    get_task_details,
    delete_task_tool,
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
- Reminders: set timed reminders, list pending, cancel
- Agenda: show combined view of tasks, events, and reminders

When the user mentions something that sounds like a task, offer to add it.
When they mention a time or deadline, offer to set a reminder.
Always confirm actions taken.

Current timezone: America/Sao_Paulo
"""


def create_agent() -> Agent:
    """Create and configure the Minion agent."""
    return Agent(
        model=OpenAIChat(
            id="gpt-4o",
            api_key=settings.openai_api_key,
        ),
        tools=[
            add_tasks,
            update_task_tool,
            list_tasks,
            search_tasks_tool,
            get_task_details,
            delete_task_tool,
            set_reminder,
            list_reminders,
            cancel_reminder,
            get_agenda,
        ],
        instructions=SYSTEM_PROMPT,
        markdown=True,
    )


# Singleton agent instance
_agent: Agent | None = None


def get_agent() -> Agent:
    """Get or create the agent singleton."""
    global _agent
    if _agent is None:
        _agent = create_agent()
    return _agent


async def chat(message: str) -> str:
    """Send a message to the agent and get a response."""
    agent = get_agent()
    response = agent.run(message)
    return response.content
