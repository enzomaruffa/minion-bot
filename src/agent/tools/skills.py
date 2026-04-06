"""Agent skills — .md files with progressive disclosure for multi-step workflows.

Skills live as markdown files under Skills/ in the Silverbullet notes space.
Each skill has YAML-like frontmatter (name, description, triggers) and ## sections.
"""

import logging
import re
from typing import Any

from src.integrations.silverbullet import (
    create_note,
    delete_note,
    list_notes_recursive,
    read_note,
    update_note,
)

logger = logging.getLogger(__name__)

SKILLS_FOLDER = "Skills"


def _parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Parse simple frontmatter from skill content. Returns (metadata, body)."""
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content

    meta: dict[str, Any] = {}
    for line in parts[1].strip().split("\n"):
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    return meta, parts[2].strip()


def _extract_section(content: str, section: str) -> str | None:
    """Extract content under a ## heading, up to the next ## heading."""
    lines = content.split("\n")
    collecting = False
    result: list[str] = []
    for line in lines:
        if line.startswith("## "):
            if collecting:
                break
            if section.lower() in line.lower():
                collecting = True
                result.append(line)
                continue
        if collecting:
            result.append(line)
    return "\n".join(result).strip() if result else None


def _skill_path(name: str) -> str:
    """Build the note path for a skill name."""
    return f"{SKILLS_FOLDER}/{name}"


def _find_skill_match(query: str, name: str, description: str, triggers: str) -> float:
    """Score how well a query matches a skill. Returns 0-1."""
    query_words = set(re.findall(r"\w+", query.lower()))
    if not query_words:
        return 0.0

    target = f"{name} {description} {triggers}".lower()
    target_words = set(re.findall(r"\w+", target))

    # Check trigger phrases for substring match
    for trigger in triggers.lower().split(","):
        trigger = trigger.strip()
        if trigger and trigger in query.lower():
            return 1.0

    # Word overlap score
    overlap = len(query_words & target_words)
    return overlap / len(query_words) if query_words else 0.0


def list_skills() -> str:
    """List all available skills with their names and descriptions.

    Returns:
        Formatted list of skills, or a message if none exist.
    """
    try:
        notes = list_notes_recursive(SKILLS_FOLDER)
    except ValueError:
        return "No skills found. Skills folder doesn't exist yet — create a skill to get started."

    if not notes:
        return "No skills found. Create one with create_skill."

    lines = ["<b>Available Skills:</b>"]
    for note_path in sorted(notes):
        name = note_path.replace(f"{SKILLS_FOLDER}/", "").removesuffix(".md")
        try:
            content = read_note(note_path)
            meta, _ = _parse_frontmatter(content)
            desc = meta.get("description", "")
            lines.append(f"  • <code>{name}</code> — {desc}" if desc else f"  • <code>{name}</code>")
        except Exception:
            lines.append(f"  • <code>{name}</code>")

    return "\n".join(lines)


def find_skill(query: str) -> str:
    """Find skills matching a query by searching triggers, names, and descriptions.

    Args:
        query: Natural language query or keyword to match against skills.

    Returns:
        Matching skills with names and descriptions, or "No matching skills found".
    """
    try:
        notes = list_notes_recursive(SKILLS_FOLDER)
    except ValueError:
        return "No skills found."

    if not notes:
        return "No skills found."

    scored: list[tuple[float, str, str, str]] = []
    for note_path in notes:
        name = note_path.replace(f"{SKILLS_FOLDER}/", "").removesuffix(".md")
        try:
            content = read_note(note_path)
            meta, _ = _parse_frontmatter(content)
            desc = meta.get("description", "")
            triggers = meta.get("triggers", "")
            score = _find_skill_match(query, name, desc, triggers)
            if score > 0:
                scored.append((score, name, desc, triggers))
        except Exception:
            continue

    if not scored:
        return f"No skills matching '{query}'."

    scored.sort(key=lambda x: x[0], reverse=True)
    lines = [f"<b>Skills matching '{query}':</b>"]
    for _score, name, desc, triggers in scored[:5]:
        line = f"  • <code>{name}</code>"
        if desc:
            line += f" — {desc}"
        if triggers:
            line += f" (triggers: {triggers})"
        lines.append(line)

    return "\n".join(lines)


def read_skill(name: str, section: str | None = None) -> str:
    """Read a skill file, optionally reading only a specific section.

    Progressive disclosure: read the full skill for an overview, or read a specific
    ## section (e.g., "Steps", "Prerequisites", "Troubleshooting") when executing.

    Args:
        name: Skill name (filename without .md, e.g., "deploy-blog").
        section: Optional header name to read only that section (e.g., "Steps").
            If None, returns the full skill content.

    Returns:
        The skill content (full or section only).
    """
    try:
        content = read_note(_skill_path(name))
    except ValueError:
        return f"Skill '{name}' not found. Use list_skills to see available skills."

    if section:
        extracted = _extract_section(content, section)
        if extracted:
            return extracted
        return f"Section '{section}' not found in skill '{name}'. Available sections: " + ", ".join(
            line.replace("## ", "") for line in content.split("\n") if line.startswith("## ")
        )

    return content


def create_skill(name: str, description: str, triggers: str, content: str) -> str:
    """Create a new skill file with frontmatter and content.

    Args:
        name: Skill name (will become the filename, e.g., "deploy-blog").
        description: One-line description of what the skill teaches.
        triggers: Comma-separated trigger phrases (e.g., "deploy blog, push to production").
        content: Markdown body of the skill (the actual instructions with ## sections).

    Returns:
        Confirmation message.
    """
    frontmatter = f"---\nname: {name}\ndescription: {description}\ntriggers: {triggers}\n---\n\n"
    full_content = frontmatter + content

    try:
        create_note(_skill_path(name), full_content)
        return f"Skill '<code>{name}</code>' created."
    except ValueError as e:
        return f"Failed to create skill: {e}"


def update_skill(name: str, content: str) -> str:
    """Update the content of an existing skill.

    Args:
        name: Skill name (filename without .md).
        content: New full content for the skill (including frontmatter if you want to change it).

    Returns:
        Confirmation message.
    """
    try:
        update_note(_skill_path(name), content)
        return f"Skill '<code>{name}</code>' updated."
    except ValueError as e:
        return f"Failed to update skill: {e}"


def delete_skill(name: str) -> str:
    """Delete a skill file.

    Args:
        name: Skill name (filename without .md).

    Returns:
        Confirmation message.
    """
    try:
        delete_note(_skill_path(name))
        return f"Skill '<code>{name}</code>' deleted."
    except ValueError as e:
        return f"Failed to delete skill: {e}"
