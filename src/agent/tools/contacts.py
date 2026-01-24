from datetime import datetime
from typing import Optional

from src.config import settings
from src.db import session_scope
from src.utils import parse_date
from src.db.queries import (
    create_contact,
    delete_contact,
    get_contact,
    get_tasks_by_contact,
    list_contacts as db_list_contacts,
    list_upcoming_birthdays,
    update_contact as db_update_contact,
)


def add_contact(
    name: str,
    aliases: Optional[str] = None,
    birthday: Optional[str] = None,
    notes: Optional[str] = None,
) -> str:
    """Add a new contact with optional birthday and aliases.

    Args:
        name: The contact's primary name.
        aliases: Optional comma-separated aliases (e.g., "Jana, Ja" for someone named Janaina).
        birthday: Optional birthday (natural language like "March 15" or ISO format "1990-03-15").
        notes: Optional notes about the contact.

    Returns:
        Confirmation message with the created contact ID.
    """
    with session_scope() as session:
        # Parse birthday
        birthday_dt = None
        if birthday:
            birthday_dt = parse_date(birthday)

        contact = create_contact(session, name=name, aliases=aliases, birthday=birthday_dt, notes=notes)

        info_parts = []
        if aliases:
            info_parts.append(f"aliases: {aliases}")
        if birthday_dt:
            info_parts.append(f"birthday: {birthday_dt.strftime('%B %d')}")

        info = f" ({', '.join(info_parts)})" if info_parts else ""
        return f"Added contact #{contact.id}: {name}{info}"


def show_contacts() -> str:
    """List all contacts with their aliases, birthdays, and linked task counts.

    Returns:
        Formatted list of all contacts.
    """
    with session_scope() as session:
        contacts = db_list_contacts(session)

        if not contacts:
            return "No contacts saved. Try 'add contact John' to get started!"

        lines = ["Contacts"]
        for contact in contacts:
            # Count linked tasks
            tasks = get_tasks_by_contact(session, contact.id)
            task_count = len(tasks)

            alias_info = f" (aka {contact.aliases})" if contact.aliases else ""
            bday_info = f" {contact.birthday.strftime('%B %d')}" if contact.birthday else ""
            task_info = f" [{task_count} task{'s' if task_count != 1 else ''}]" if task_count > 0 else ""
            notes_info = f" - {contact.notes}" if contact.notes else ""

            lines.append(f"  #{contact.id} {contact.name}{alias_info}{bday_info}{task_info}{notes_info}")

        return "\n".join(lines)


def upcoming_birthdays(days: int = 14) -> str:
    """Show contacts with upcoming birthdays.

    Args:
        days: Number of days to look ahead. Default 14.

    Returns:
        List of contacts with birthdays within the specified days.
    """
    with session_scope() as session:
        contacts = list_upcoming_birthdays(session, within_days=days)

        if not contacts:
            return f"No birthdays in the next {days} days."

        lines = [f"Upcoming Birthdays (next {days} days)"]
        today = datetime.now(settings.timezone).date()

        for contact in contacts:
            if contact.birthday:
                bday = contact.birthday.date() if isinstance(contact.birthday, datetime) else contact.birthday
                this_year_bday = bday.replace(year=today.year)
                if this_year_bday < today:
                    this_year_bday = bday.replace(year=today.year + 1)
                days_until = (this_year_bday - today).days

                if days_until == 0:
                    when = "TODAY!"
                elif days_until == 1:
                    when = "tomorrow"
                elif days_until <= 7:
                    when = f"in {days_until} days"
                else:
                    when = f"in {days_until} days"

                lines.append(f"  #{contact.id} {contact.name} - {this_year_bday.strftime('%B %d')} ({when})")

        return "\n".join(lines)


def update_contact_tool(
    contact_id: int,
    name: Optional[str] = None,
    aliases: Optional[str] = None,
    birthday: Optional[str] = None,
    notes: Optional[str] = None,
    clear_birthday: bool = False,
    clear_aliases: bool = False,
) -> str:
    """Update an existing contact.

    Args:
        contact_id: The ID of the contact to update.
        name: New name for the contact.
        aliases: New comma-separated aliases (e.g., "Jana, Ja").
        birthday: New birthday (natural language or ISO format).
        notes: New notes for the contact.
        clear_birthday: If True, removes the birthday.
        clear_aliases: If True, removes all aliases.

    Returns:
        Confirmation message or error.
    """
    with session_scope() as session:
        birthday_dt = None
        if birthday:
            birthday_dt = parse_date(birthday)

        contact = db_update_contact(
            session,
            contact_id,
            name=name,
            aliases=aliases,
            birthday=birthday_dt,
            notes=notes,
            clear_birthday=clear_birthday,
            clear_aliases=clear_aliases,
        )

        if not contact:
            return f"Contact #{contact_id} not found."

        return f"Updated contact #{contact_id}: {contact.name}"


def remove_contact(contact_id: int) -> str:
    """Remove a contact. DESTRUCTIVE - call show_contacts first to verify the ID!

    Args:
        contact_id: The ID of the contact. MUST call show_contacts first to verify correct ID.

    Returns:
        Confirmation message or error.
    """
    with session_scope() as session:
        contact = get_contact(session, contact_id)
        if not contact:
            return f"Contact #{contact_id} not found."

        name = contact.name
        success = delete_contact(session, contact_id)

        if success:
            return f"Removed contact #{contact_id}: {name}"
        return f"Failed to remove contact #{contact_id}."


def get_contact_tasks(contact_id: int) -> str:
    """Get all tasks linked to a specific contact.

    Args:
        contact_id: The ID of the contact.

    Returns:
        List of tasks linked to the contact.
    """
    with session_scope() as session:
        contact = get_contact(session, contact_id)
        if not contact:
            return f"Contact #{contact_id} not found."

        contact_name = contact.name
        tasks = get_tasks_by_contact(session, contact_id)

        if not tasks:
            return f"No tasks linked to {contact_name}."

        lines = [f"Tasks for {contact_name}"]
        for task in tasks:
            project_emoji = task.project.emoji + " " if task.project else ""
            due = f" {task.due_date.strftime('%b %d')}" if task.due_date else ""
            status_icon = {"todo": "[ ]", "in_progress": "[~]", "done": "[x]", "cancelled": "[-]"}.get(task.status.value, "")
            lines.append(f"  #{task.id} {project_emoji}{task.title}{due} {status_icon}")

        return "\n".join(lines)
