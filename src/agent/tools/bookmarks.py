from urllib.parse import urlparse

from src.db import session_scope
from src.db.queries import (
    create_bookmark,
    delete_bookmark,
    list_bookmarks,
    mark_bookmark_read,
    search_bookmarks,
)


def save_bookmark(url: str, title: str | None = None, tags: str | None = None, notes: str | None = None) -> str:
    """Save a URL to the reading list.

    Args:
        url: The URL to save.
        title: Optional title (auto-detects domain if not provided).
        tags: Optional comma-separated tags (e.g. "python, tutorial").
        notes: Optional description or notes about the link.

    Returns:
        Confirmation message with bookmark ID.
    """
    domain = urlparse(url).netloc or None
    if not title:
        title = domain

    with session_scope() as session:
        bookmark = create_bookmark(session, url=url, title=title, description=notes, domain=domain, tags=tags)
        tag_info = f" [{tags}]" if tags else ""
        return f"✓ Saved <code>#{bookmark.id}</code> <i>{title}</i>{tag_info}"


def list_reading_list(filter: str | None = None) -> str:
    """Show the reading list.

    Args:
        filter: Optional filter: "all", "read", "unread" (default), or a tag name.

    Returns:
        Formatted list of bookmarks.
    """
    with session_scope() as session:
        read_filter = None
        tag_filter = None

        if filter == "read":
            read_filter = True
        elif filter == "all":
            pass  # No filter
        elif filter and filter not in ("unread", None):
            tag_filter = filter  # Treat as tag name
        else:
            read_filter = False  # Default: unread

        bookmarks = list_bookmarks(session, read=read_filter, tag=tag_filter)

        if not bookmarks:
            label = filter or "unread"
            return f"<i>No {label} bookmarks.</i>"

        lines = ["<b>📚 Reading List</b>"]
        for b in bookmarks:
            status = "✓" if b.read else "○"
            tags = f" [{b.tags}]" if b.tags else ""
            domain = f" <i>({b.domain})</i>" if b.domain else ""
            lines.append(f"{status} <code>#{b.id}</code> {b.title}{domain}{tags}")

        return "\n".join(lines)


def mark_read(bookmark_id: int) -> str:
    """Mark a bookmark as read.

    Args:
        bookmark_id: The bookmark ID to mark as read.

    Returns:
        Confirmation message.
    """
    with session_scope() as session:
        if mark_bookmark_read(session, bookmark_id, read=True):
            return f"✓ Marked <code>#{bookmark_id}</code> as read"
        return f"Bookmark <code>#{bookmark_id}</code> not found"


def remove_bookmark(bookmark_id: int) -> str:
    """Delete a bookmark from the reading list.

    Args:
        bookmark_id: The bookmark ID to delete.

    Returns:
        Confirmation message.
    """
    with session_scope() as session:
        if delete_bookmark(session, bookmark_id):
            return f"✓ Removed bookmark <code>#{bookmark_id}</code>"
        return f"Bookmark <code>#{bookmark_id}</code> not found"


def search_reading_list(query: str) -> str:
    """Search bookmarks by title, description, or tags.

    Args:
        query: Search query string.

    Returns:
        Matching bookmarks.
    """
    with session_scope() as session:
        bookmarks = search_bookmarks(session, query)

        if not bookmarks:
            return f"<i>No bookmarks matching '{query}'.</i>"

        lines = [f"<b>🔍 Results for '{query}'</b>"]
        for b in bookmarks:
            status = "✓" if b.read else "○"
            tags = f" [{b.tags}]" if b.tags else ""
            lines.append(f"{status} <code>#{b.id}</code> {b.title}{tags}")
            lines.append(f"  {b.url}")

        return "\n".join(lines)
