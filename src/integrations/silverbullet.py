"""Filesystem-based integration with Silverbullet notes.

Reads/writes markdown files directly from a mounted Silverbullet space directory.
"""

import logging
import os
import tempfile
from pathlib import Path

from src.config import settings

logger = logging.getLogger(__name__)

MAX_NOTE_SIZE = 50 * 1024  # 50KB
MAX_SEARCH_RESULTS = 20


def _get_space_path() -> Path | None:
    """Get the configured space path, or None if not configured."""
    path = settings.silverbullet_space_path
    if str(path) in ("", ".") or not path.is_dir():
        return None
    return path.resolve()


def _note_path(name: str) -> Path:
    """Convert a note name to a filesystem path with safety checks.

    Args:
        name: Note name like "Journal/2024-01-15" (without .md extension).

    Returns:
        Resolved absolute path to the .md file.

    Raises:
        ValueError: If the path escapes the space directory.
    """
    space = _get_space_path()
    if space is None:
        raise ValueError("Notes not configured")

    # Add .md extension if not present
    if not name.endswith(".md"):
        name = name + ".md"

    target = (space / name).resolve()

    # Path traversal protection
    if not str(target).startswith(str(space.resolve())):
        raise ValueError("Invalid note path")

    return target


def note_exists(name: str) -> bool:
    """Check if a note exists.

    Args:
        name: Note name like "Journal/2024-01-15".

    Returns:
        True if the note exists.
    """
    try:
        return _note_path(name).is_file()
    except ValueError:
        return False


def read_note(name: str) -> str:
    """Read a note's markdown content.

    Args:
        name: Note name like "Journal/2024-01-15".

    Returns:
        The note's content as a string.

    Raises:
        ValueError: If the note doesn't exist or is too large.
    """
    path = _note_path(name)
    if not path.is_file():
        raise ValueError(f"Note not found: {name}")

    if path.stat().st_size > MAX_NOTE_SIZE:
        raise ValueError(f"Note is too large (>{MAX_NOTE_SIZE // 1024}KB): {name}")

    return path.read_text(encoding="utf-8", errors="replace")


def create_note(name: str, content: str) -> None:
    """Create a new note. Fails if the note already exists.

    Args:
        name: Note name like "Journal/2024-01-15".
        content: Markdown content for the note.

    Raises:
        ValueError: If the note already exists.
    """
    path = _note_path(name)
    if path.exists():
        raise ValueError(f"Note already exists: {name}")

    # Auto-create parent directories
    path.parent.mkdir(parents=True, exist_ok=True)

    # Atomic write
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".md.tmp")
    try:
        os.write(fd, content.encode("utf-8"))
        os.close(fd)
        os.replace(tmp, path)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def update_note(name: str, content: str) -> None:
    """Overwrite an existing note. Fails if the note doesn't exist.

    Args:
        name: Note name like "Journal/2024-01-15".
        content: New markdown content.

    Raises:
        ValueError: If the note doesn't exist.
    """
    path = _note_path(name)
    if not path.is_file():
        raise ValueError(f"Note not found: {name}")

    # Atomic write
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".md.tmp")
    try:
        os.write(fd, content.encode("utf-8"))
        os.close(fd)
        os.replace(tmp, path)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def append_to_note(name: str, content: str) -> None:
    """Append content to an existing note with a newline separator.

    Args:
        name: Note name like "Journal/2024-01-15".
        content: Content to append.

    Raises:
        ValueError: If the note doesn't exist.
    """
    path = _note_path(name)
    if not path.is_file():
        raise ValueError(f"Note not found: {name}")

    existing = path.read_text(encoding="utf-8", errors="replace")
    separator = "\n" if existing and not existing.endswith("\n") else ""
    new_content = existing + separator + content

    # Atomic write
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".md.tmp")
    try:
        os.write(fd, new_content.encode("utf-8"))
        os.close(fd)
        os.replace(tmp, path)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def list_notes(folder: str = "") -> tuple[list[str], list[str]]:
    """List files and folders in a directory (non-recursive).

    Args:
        folder: Subfolder path, or "" for root.

    Returns:
        Tuple of (folders, notes) where notes have .md stripped.

    Raises:
        ValueError: If the path is invalid.
    """
    space = _get_space_path()
    if space is None:
        raise ValueError("Notes not configured")

    if folder:
        target = (space / folder).resolve()
        if not str(target).startswith(str(space.resolve())):
            raise ValueError("Invalid folder path")
    else:
        target = space

    if not target.is_dir():
        raise ValueError(f"Folder not found: {folder}")

    folders = []
    notes = []

    for entry in sorted(target.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            rel = str(entry.relative_to(space))
            folders.append(rel)
        elif entry.suffix == ".md":
            rel = str(entry.relative_to(space))
            # Strip .md extension for display
            notes.append(rel[:-3])

    return folders, notes


def list_notes_recursive(folder: str = "") -> list[str]:
    """List all note names under a folder recursively.

    Args:
        folder: Subfolder path, or "" for root.

    Returns:
        List of note names (without .md extension).
    """
    space = _get_space_path()
    if space is None:
        raise ValueError("Notes not configured")

    if folder:
        target = (space / folder).resolve()
        if not str(target).startswith(str(space.resolve())):
            raise ValueError("Invalid folder path")
    else:
        target = space

    if not target.is_dir():
        raise ValueError(f"Folder not found: {folder}")

    notes = []
    for path in sorted(target.rglob("*.md")):
        if any(part.startswith(".") for part in path.relative_to(space).parts):
            continue
        rel = str(path.relative_to(space))
        notes.append(rel[:-3])

    return notes


def search_notes(query: str, folder: str = "") -> list[tuple[str, str]]:
    """Search notes by content (case-insensitive).

    Args:
        query: Text to search for.
        folder: Optional folder to restrict search.

    Returns:
        List of (note_name, matching_line) tuples, max 20 results.
    """
    space = _get_space_path()
    if space is None:
        raise ValueError("Notes not configured")

    if folder:
        target = (space / folder).resolve()
        if not str(target).startswith(str(space.resolve())):
            raise ValueError("Invalid folder path")
    else:
        target = space

    query_lower = query.lower()
    results: list[tuple[str, str]] = []

    for path in sorted(target.rglob("*.md")):
        if any(part.startswith(".") for part in path.relative_to(space).parts):
            continue
        if path.stat().st_size > MAX_NOTE_SIZE:
            continue

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for line in content.splitlines():
            if query_lower in line.lower():
                note_name = str(path.relative_to(space))[:-3]
                results.append((note_name, line.strip()))
                break  # One match per file

        if len(results) >= MAX_SEARCH_RESULTS:
            break

    return results


def search_notes_by_title(query: str, folder: str = "") -> list[str]:
    """Search notes by name (case-insensitive substring match).

    Args:
        query: Substring to match in note names.
        folder: Optional folder to restrict search.

    Returns:
        List of matching note names, max 20 results.
    """
    space = _get_space_path()
    if space is None:
        raise ValueError("Notes not configured")

    if folder:
        target = (space / folder).resolve()
        if not str(target).startswith(str(space.resolve())):
            raise ValueError("Invalid folder path")
    else:
        target = space

    query_lower = query.lower()
    results: list[str] = []

    for path in sorted(target.rglob("*.md")):
        if any(part.startswith(".") for part in path.relative_to(space).parts):
            continue
        rel = str(path.relative_to(space))[:-3]
        if query_lower in rel.lower():
            results.append(rel)
            if len(results) >= MAX_SEARCH_RESULTS:
                break

    return results
