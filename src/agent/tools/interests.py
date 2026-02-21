"""User interest management tools for proactive heartbeat."""

import logging

from src.db import session_scope
from src.db.queries import (
    create_interest,
    delete_interest,
    get_interest,
    update_interest,
)
from src.db.queries import (
    list_interests as _list_interests,
)

logger = logging.getLogger(__name__)


def add_interest(
    topic: str,
    description: str | None = None,
    priority: int = 1,
    check_interval_hours: int = 24,
) -> str:
    """Add a user interest for proactive monitoring.

    Args:
        topic: Short topic name (e.g., "Rust programming", "PS5 prices").
        description: Optional detailed description of what to track.
        priority: 1 (low) to 3 (high). Higher priority = checked more often.
        check_interval_hours: How often to check this interest (default 24h).

    Returns:
        Confirmation message.
    """
    with session_scope() as session:
        interest = create_interest(
            session,
            topic=topic,
            description=description,
            priority=max(1, min(3, priority)),
            check_interval_hours=check_interval_hours,
        )
        return f"Added interest #{interest.id}: {topic} (priority {priority}, check every {check_interval_hours}h)"


def list_interests() -> str:
    """List all active user interests.

    Returns:
        Formatted list of interests with IDs, priorities, and check intervals.
    """
    with session_scope() as session:
        interests = _list_interests(session, active_only=True)
        if not interests:
            return "No active interests."

        lines = ["Your interests:\n"]
        for i in interests:
            checked = (
                f"last checked {i.last_checked_at.strftime('%Y-%m-%d %H:%M')}" if i.last_checked_at else "never checked"
            )
            lines.append(f"#{i.id}: {i.topic} (P{i.priority}, every {i.check_interval_hours}h, {checked})")
            if i.description:
                lines.append(f"   {i.description}")
        return "\n".join(lines)


def remove_interest(interest_id: int) -> str:
    """Remove a user interest by ID.

    Args:
        interest_id: The interest ID to remove.

    Returns:
        Confirmation message.
    """
    with session_scope() as session:
        interest = get_interest(session, interest_id)
        if not interest:
            return f"Interest #{interest_id} not found."
        topic = interest.topic
        delete_interest(session, interest_id)
        return f"Removed interest #{interest_id}: {topic}"


def update_interest_tool(
    interest_id: int,
    topic: str | None = None,
    description: str | None = None,
    priority: int | None = None,
    check_interval_hours: int | None = None,
    active: bool | None = None,
) -> str:
    """Update an existing interest.

    Args:
        interest_id: The interest ID to update.
        topic: New topic name.
        description: New description.
        priority: New priority (1-3).
        check_interval_hours: New check interval.
        active: Whether the interest is active.

    Returns:
        Confirmation message.
    """
    with session_scope() as session:
        interest = get_interest(session, interest_id)
        if not interest:
            return f"Interest #{interest_id} not found."

        kwargs = {}
        if topic is not None:
            kwargs["topic"] = topic
        if description is not None:
            kwargs["description"] = description
        if priority is not None:
            kwargs["priority"] = max(1, min(3, priority))
        if check_interval_hours is not None:
            kwargs["check_interval_hours"] = check_interval_hours
        if active is not None:
            kwargs["active"] = active

        update_interest(session, interest_id, **kwargs)
        return f"Updated interest #{interest_id}: {interest.topic}"
