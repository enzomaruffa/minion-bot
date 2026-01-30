"""Agent tools for Silverbullet notes integration."""

from typing import Optional

from src.integrations.silverbullet import (
    append_to_note,
    create_note,
    list_notes,
    read_note,
    search_notes,
    search_notes_by_title,
    update_note,
)

MAX_OUTPUT = 3500


def _truncate(text: str) -> str:
    if len(text) > MAX_OUTPUT:
        return text[:MAX_OUTPUT] + "\n\n<i>...truncated</i>"
    return text


def browse_notes(folder: str = "") -> str:
    """Browse folders and notes in the Silverbullet space.

    Args:
        folder: Folder path to browse, or empty for root.

    Returns:
        HTML-formatted list of folders and notes.
    """
    try:
        folders, notes = list_notes(folder)
    except ValueError as e:
        return str(e)

    location = folder or "root"
    parts = [f"<b>📂 Notes: {location}</b>\n"]

    if not folders and not notes:
        parts.append("<i>Empty folder</i>")
        return "\n".join(parts)

    if folders:
        parts.append("<b>Folders:</b>")
        for f in folders:
            parts.append(f"  📁 {f}/")

    if notes:
        if folders:
            parts.append("")
        parts.append("<b>Notes:</b>")
        for n in notes:
            parts.append(f"  📄 {n}")

    return _truncate("\n".join(parts))


def read_note_tool(name: str) -> str:
    """Read a note's markdown content.

    Args:
        name: Note path like "Journal/2024-01-15" (without .md).

    Returns:
        The note's content.
    """
    try:
        content = read_note(name)
    except ValueError as e:
        return str(e)

    header = f"<b>📄 {name}</b>\n\n"
    return _truncate(header + content)


def create_note_tool(name: str, content: str) -> str:
    """Create a new note. Fails if it already exists.

    Args:
        name: Note path like "Journal/2024-01-15" (without .md).
        content: Markdown content for the note.

    Returns:
        Confirmation message.
    """
    try:
        create_note(name, content)
    except ValueError as e:
        return f"❌ {e}"

    return f"✅ Created note: <b>{name}</b>"


def update_note_tool(name: str, content: str) -> str:
    """Replace the entire content of an existing note.

    Args:
        name: Note path like "Journal/2024-01-15" (without .md).
        content: New markdown content (replaces everything).

    Returns:
        Confirmation message.
    """
    try:
        update_note(name, content)
    except ValueError as e:
        return f"❌ {e}"

    return f"✅ Updated note: <b>{name}</b>"


def append_to_note_tool(name: str, content: str) -> str:
    """Append content to the end of an existing note.

    Args:
        name: Note path like "Journal/2024-01-15" (without .md).
        content: Content to append.

    Returns:
        Confirmation message.
    """
    try:
        append_to_note(name, content)
    except ValueError as e:
        return f"❌ {e}"

    return f"✅ Appended to note: <b>{name}</b>"


def search_notes_tool(query: str, folder: str = "") -> str:
    """Search notes by title and content.

    Args:
        query: Search query (case-insensitive).
        folder: Optional folder to restrict search.

    Returns:
        HTML-formatted search results.
    """
    try:
        title_matches = search_notes_by_title(query, folder)
        content_matches = search_notes(query, folder)
    except ValueError as e:
        return str(e)

    if not title_matches and not content_matches:
        scope = f" in {folder}" if folder else ""
        return f"No notes found matching <b>{query}</b>{scope}"

    parts = [f"<b>🔍 Search: {query}</b>\n"]

    if title_matches:
        parts.append("<b>By title:</b>")
        for name in title_matches[:10]:
            parts.append(f"  📄 {name}")

    if content_matches:
        if title_matches:
            parts.append("")
        parts.append("<b>By content:</b>")
        for name, line in content_matches[:10]:
            preview = line[:80] + "..." if len(line) > 80 else line
            parts.append(f"  📄 {name}")
            parts.append(f"     <i>{preview}</i>")

    return _truncate("\n".join(parts))
