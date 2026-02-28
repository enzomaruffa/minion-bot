"""Explicit long-term memory tools for the agent.

These tools let the agent save and recall facts, preferences, and decisions
across conversations. Stored in the agent_memories SQLite table.
"""

from src.db import session_scope
from src.db.queries import delete_agent_memory, list_agent_memories, save_agent_memory, search_agent_memories


def save_memory(key: str, content: str, category: str = "fact") -> str:
    """Save a fact, preference, or observation to long-term memory. Overwrites if key exists.

    Args:
        key: Short descriptive key (e.g., "preference_meeting_times", "fact_user_name").
        content: The information to remember.
        category: One of: preference, fact, person, decision, workflow.

    Returns:
        Confirmation message.
    """
    with session_scope() as session:
        memory = save_agent_memory(session, key, content, category)
        return f"Saved memory [{memory.category}] {memory.key}"


def recall_memory(query: str) -> str:
    """Search long-term memory for relevant information.

    Args:
        query: What to search for (matches against keys and content).

    Returns:
        Matching memories or "No memories found".
    """
    with session_scope() as session:
        memories = search_agent_memories(session, query)
        if not memories:
            return "No memories found."
        lines = []
        for m in memories:
            lines.append(f"[{m.category}] <b>{m.key}</b>: {m.content}")
        return "\n".join(lines)


def list_memories(category: str | None = None) -> str:
    """List all saved memories, optionally filtered by category.

    Args:
        category: Filter by category (preference, fact, person, decision, workflow).

    Returns:
        List of memories or "No memories saved yet".
    """
    with session_scope() as session:
        memories = list_agent_memories(session, limit=50, category=category)
        if not memories:
            return "No memories saved yet."
        lines = []
        for m in memories:
            lines.append(f"[{m.category}] <b>{m.key}</b>: {m.content}")
        return "\n".join(lines)


def forget_memory(key: str) -> str:
    """Delete a specific memory by its key.

    Args:
        key: The exact key of the memory to delete.

    Returns:
        Confirmation or not-found message.
    """
    with session_scope() as session:
        if delete_agent_memory(session, key):
            return f"Forgot memory: {key}"
        return f"No memory found with key: {key}"
