"""Claude Agent SDK based agent for Minion.

Replaces the Agno-based agent with ClaudeSDKClient. Tools are served as
an in-process MCP server; external MCP servers (Playwright, Beads) are
passed as subprocess configs. LiteLLM proxy handles model routing via
ANTHROPIC_BASE_URL override.
"""

from __future__ import annotations

import logging
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    create_sdk_mcp_server,
)

from src.agent.sdk_tools import MAIN_TOOLS
from src.agent.subagents import SUBAGENTS
from src.config import settings
from src.db import session_scope
from src.db.queries import log_agent_event

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# System prompt — format hints are inline, no separate formatter LLM pass
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_BASE = """\
You are Minion, a personal assistant bot.

Your personality:
- Friendly and helpful, but concise
- Proactive - just do reversible actions, confirm after
- Remember context from the conversation

Your capabilities:
- Task management: create, update, list, search, and delete tasks
- Task hierarchy: create subtasks under parent tasks, move tasks between parents
- Project categorization: auto-assign tasks to projects based on context
- Reminders: set timed reminders, list pending, cancel
- Agenda: show combined view of tasks, events, and reminders
- Shopping lists: manage gifts, groceries, and wishlist items
- Contacts: track people and their birthdays
- Notes: browse, read, create, update, and search Silverbullet notes
- Code execution: run Python code and shell commands directly
- Web browsing: search the web, fetch URLs, browse pages with a full browser
- Interest tracking: monitor topics proactively (news, prices, updates)
- Beads: track work items and sub-agent tasks
- Memory: save and recall long-term memories about user preferences and facts

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
- Work: job tasks, meetings, PRs, code reviews, office work
- Personal: home tasks, errands, personal items
- Health: exercise, medical appointments, wellness
- Finance: bills, budget, investments, taxes
- Social: friends, family, events, gatherings
- Learning: courses, books, skills, tutorials

PROJECTS (User-Created):
Projects are user-created containers for related tasks (e.g., "MinionBot", "House Renovation").
- When user mentions a project name, use it; otherwise don't assign projects
- Tasks can have both a tag (category) AND belong to a project

SHOPPING LISTS:
Three types - auto-infer, never ask:
- Gifts: "gift for mom" (anything with a recipient or gift-related keywords)
- Groceries: "buy eggs" (supermarket/house items, default for ambiguous)
- Wishlist: "that PS5 I want" (personal wants)
Just add items. Don't ask "which list?" - infer it.

CONTACTS:
Track birthdays with add_contact. Contacts support aliases.
When creating tasks about a person, link to their contact if they exist.

NOTES (Silverbullet):
Notes are markdown files. Use paths like "Journal/2024-01-15" or "Projects/Minion".
Preserve [[wiki-link]] syntax when editing. Search first if you don't know the exact path.

TASK IDs: Always prefixed with # (e.g., #5, #12). Use the exact numeric ID, not list position.

RECURRING TASKS:
Map natural language to RRULE format:
- "every day" -> FREQ=DAILY
- "every Monday" -> FREQ=WEEKLY;BYDAY=MO
- "every weekday" -> FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR
- "every month on the 15th" -> FREQ=MONTHLY;BYMONTHDAY=15

CONSTANT LEARNING:
When the user corrects you, expresses a preference, or you learn a fact:
- Use save_memory to store it for future reference
- Before decisions, use recall_memory to check stored context
- Keep memory keys descriptive (e.g., "preference_meeting_times", "fact_user_name")

SUBAGENT DELEGATION:
You have specialized subagents you can delegate to. Use them for complex tasks:
- researcher: web research, price comparison, news, information gathering
- planner: daily/weekly planning, schedule optimization, prioritization
- task-breakdown: decompose complex tasks into subtasks with action plans
- content-creator: draft notes, lesson plans, checklists, templates
- shopping-scout: product research, price comparison, deal finding
- social-manager: birthday prep, gift ideas, contact management
- analyst: mood trends, task patterns, productivity reports
Delegate proactively — subagents do deeper, focused work than you can inline.

LANGUAGE: Always reply in English, regardless of the language the user writes in.

Current timezone: America/Sao_Paulo
"""

FORMAT_HINTS = {
    "telegram": """
OUTPUT FORMAT: Telegram HTML.
Use <b>bold</b>, <i>italic</i>, <code>monospace</code>, <s>strikethrough</s>.
Use literal newlines for line breaks (never <br>). Use bullet character for lists.
Emoji style: checkmark Done, +New Added, pencil Updated, wastebasket Deleted, alarm Reminder set.
Task status in lists: [ ] todo, [~] in progress, [check] done.
Category icons: briefcase Work, house Personal, runner Health, moneybag Finance, people Social, books Learning.
NEVER use Markdown syntax. Keep under 4096 characters.
""",
    "web": """
OUTPUT FORMAT: Markdown.
Use **bold**, *italic*, `code`, ~~strikethrough~~, - bullets.
NEVER use HTML tags.
""",
}


# ---------------------------------------------------------------------------
# In-process MCP server for custom tools
# ---------------------------------------------------------------------------

_tools_server = create_sdk_mcp_server(
    name="minion-tools",
    version="1.0.0",
    tools=MAIN_TOOLS,
)


def _get_external_mcp_servers() -> dict[str, Any]:
    """Return MCP server configs for external servers (Playwright, Beads, user-configured)."""
    servers: dict[str, Any] = {}

    # Playwright (headless browser)
    servers["playwright"] = {
        "command": "npx",
        "args": ["@playwright/mcp@latest", "--headless"],
    }

    # Beads (task tracking)
    servers["beads"] = {
        "command": "uvx",
        "args": ["beads-mcp"],
    }

    # User-configured MCP servers
    for i, cmd in enumerate(settings.mcp_server_commands):
        parts = cmd.split()
        if parts:
            servers[f"custom_{i}"] = {
                "command": parts[0],
                "args": parts[1:],
            }

    return servers


# ---------------------------------------------------------------------------
# Agent state
# ---------------------------------------------------------------------------

_session_id: str | None = None


def _build_system_prompt(format_hint: str) -> str:
    """Build full system prompt with format hints, memory, and event bus context."""
    from src.db.queries import get_active_work, get_recent_completed_work, get_recent_events, list_agent_memories

    parts = [SYSTEM_PROMPT_BASE]

    # Inject long-term memories if available
    try:
        with session_scope() as session:
            memories = list_agent_memories(session, limit=20)
            if memories:
                lines = ["\nREMEMBERED CONTEXT (from long-term memory):"]
                for m in memories:
                    lines.append(f"- [{m.category}] {m.key}: {m.content}")
                parts.append("\n".join(lines))
    except Exception:
        pass

    # Inject recent event bus activity
    try:
        with session_scope() as session:
            events = get_recent_events(session, limit=30, since_hours=24)
            if events:
                lines = ["\nRECENT ACTIVITY (last 24h — includes heartbeat, scheduler, and your own responses):"]
                for e in reversed(events):  # chronological order
                    ts = e.timestamp.strftime("%H:%M") if e.timestamp else "?"
                    lines.append(f"- [{ts} {e.source}] {e.event_type}: {e.summary[:200]}")
                parts.append("\n".join(lines))

            # Show active subagent work
            active = get_active_work(session)
            if active:
                lines = ["\nACTIVE SUBAGENT WORK:"]
                for w in active:
                    started = w.started_at.strftime("%H:%M") if w.started_at else "?"
                    lines.append(f"- {w.agent_name}: {w.description} (started {started})")
                parts.append("\n".join(lines))

            # Show recently completed work
            completed = get_recent_completed_work(session, hours=24)
            if completed:
                lines = ["\nRECENTLY COMPLETED WORK:"]
                for w in completed[:5]:
                    result_preview = w.result[:150] if w.result else "(no result)"
                    lines.append(f"- {w.agent_name}: {w.description} -> {result_preview}")
                parts.append("\n".join(lines))
    except Exception:
        pass

    # Format-specific instructions
    fmt = FORMAT_HINTS.get(format_hint, "")
    if fmt:
        parts.append(fmt)

    return "\n\n".join(parts)


def _build_allowed_tools() -> list[str]:
    """Build the list of allowed tool names for the SDK."""
    return [f"mcp__minion-tools__{t.name}" for t in MAIN_TOOLS]


async def chat(message: str, format_hint: str = "telegram") -> str:
    """Send a message to the agent and get a response.

    Args:
        message: User message text.
        format_hint: "telegram" for HTML formatting, "web" for Markdown.
    """
    global _session_id

    logger.info(f"Chat input: {message[:100]}{'...' if len(message) > 100 else ''}")

    mcp_servers: dict[str, Any] = {"tools": _tools_server}

    # Add external MCP servers
    try:
        mcp_servers.update(_get_external_mcp_servers())
    except Exception as e:
        logger.warning(f"Failed to configure external MCP servers: {e}")

    options = ClaudeAgentOptions(
        model=settings.agent_model,
        system_prompt=_build_system_prompt(format_hint),
        mcp_servers=mcp_servers,
        allowed_tools=_build_allowed_tools(),
        agents=SUBAGENTS,
        permission_mode="bypassPermissions",
        max_turns=20,
        env={
            "ANTHROPIC_BASE_URL": settings.anthropic_base_url,
            "ANTHROPIC_API_KEY": settings.anthropic_api_key,
        },
    )

    # Resume previous session if available
    if _session_id:
        options.resume = _session_id

    response_text = ""

    try:
        async with ClaudeSDKClient(options=options) as client:
            await client.query(message)
            async for msg in client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            response_text += block.text
                elif isinstance(msg, ResultMessage):
                    _session_id = msg.session_id
                    logger.info(f"Session {_session_id}: {msg.num_turns} turns, ${msg.total_cost_usd:.4f}")
                    break
    except Exception as e:
        logger.exception(f"SDK agent error: {e}")
        raise

    if not response_text.strip():
        response_text = "Done."

    # Log to event bus
    try:
        with session_scope() as session:
            log_agent_event(session, "chat", "agent_response", response_text[:500])
    except Exception:
        logger.debug("Failed to log agent response to event bus", exc_info=True)

    logger.info(f"Chat output: {response_text[:100]}{'...' if len(response_text) > 100 else ''}")
    return response_text


async def chat_stream(message: str, format_hint: str = "telegram"):
    """Streaming version of chat — yields text chunks as they arrive.

    Args:
        message: User message text.
        format_hint: "telegram" for HTML formatting, "web" for Markdown.
    """
    global _session_id

    logger.info(f"Chat stream input: {message[:100]}{'...' if len(message) > 100 else ''}")

    mcp_servers: dict[str, Any] = {"tools": _tools_server}
    try:
        mcp_servers.update(_get_external_mcp_servers())
    except Exception as e:
        logger.warning(f"Failed to configure external MCP servers: {e}")

    options = ClaudeAgentOptions(
        model=settings.agent_model,
        system_prompt=_build_system_prompt(format_hint),
        mcp_servers=mcp_servers,
        allowed_tools=_build_allowed_tools(),
        agents=SUBAGENTS,
        permission_mode="bypassPermissions",
        max_turns=20,
        env={
            "ANTHROPIC_BASE_URL": settings.anthropic_base_url,
            "ANTHROPIC_API_KEY": settings.anthropic_api_key,
        },
    )

    if _session_id:
        options.resume = _session_id

    async with ClaudeSDKClient(options=options) as client:
        await client.query(message)
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        yield block.text
            elif isinstance(msg, ResultMessage):
                _session_id = msg.session_id
                break


async def shutdown() -> None:
    """Reset session state."""
    global _session_id
    _session_id = None
    logger.info("SDK agent session cleared")
