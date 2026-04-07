"""Agno-based agent for Minion.

Uses Agno Team with OpenAIChat for direct API calls (no proxy).
Tools are plain Python functions passed directly to Agent(tools=[...]).
MCP servers (Playwright, Beads) are connected via agno.tools.mcp.MCPTools.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from agno.agent import RunEvent
from agno.db.sqlite import SqliteDb
from agno.models.openai import OpenAIChat
from agno.session.summary import SessionSummaryManager
from agno.team import Team, TeamRunEvent
from agno.team.team import TeamMode

from src.agent.memory_extractor import extract_memories_background
from src.agent.team import build_team_members
from src.agent.tools import (
    # FFmpeg
    add_audio,
    # Contacts
    add_contact,
    # Interests
    add_interest,
    add_subtask,
    # Tasks
    add_tasks,
    add_text_overlay,
    # Shopping
    add_to_list,
    append_to_note_tool,
    archive_project,
    assign_tasks_to_project,
    assign_to_project,
    # Beads
    beads_create,
    beads_list,
    beads_ready,
    # Notes
    browse_notes,
    cancel_reminder,
    check_item,
    clear_checked,
    complete_task,
    concat_videos,
    create_calendar_event,
    create_note_tool,
    # Projects
    create_project,
    # Skills
    create_skill,
    delete_calendar_event,
    delete_skill,
    delete_task_tool,
    # Media generation
    edit_image,
    extract_audio,
    fetch_url,
    # Scheduling
    find_free_slot,
    find_skill,
    forget_memory,
    generate_image,
    generate_video,
    # Agenda
    get_agenda,
    get_contact_tasks,
    # Misc
    get_current_datetime,
    get_overdue_tasks,
    get_task_details,
    get_weather,
    list_calendar_events,
    list_interests,
    list_memories,
    list_projects_tool,
    list_reading_list,
    list_recurring,
    list_reminders,
    list_skills,
    list_tags,
    list_tasks,
    # Mood
    log_mood,
    mark_read,
    mood_summary,
    move_project_tasks,
    move_task,
    probe_media,
    purchase_item,
    read_note_tool,
    read_skill,
    recall_memory,
    remind_before_deadline,
    remove_bookmark,
    remove_contact,
    remove_interest,
    remove_item,
    resize_video,
    # Code
    run_python_code,
    run_shell_command,
    # Bookmarks
    save_bookmark,
    # Memory
    save_memory,
    search_notes_tool,
    search_reading_list,
    search_tasks_tool,
    # Files
    send_file,
    # Reminders
    set_reminder,
    show_contacts,
    show_gifts_for_contact,
    show_list,
    show_mood_history,
    show_profile,
    show_project,
    speed_video,
    stop_recurring,
    # Calendar
    test_calendar,
    trim_video,
    unassign_from_project,
    uncheck_item,
    upcoming_birthdays,
    update_calendar_event,
    update_contact_tool,
    update_interest_tool,
    update_note_tool,
    # Profile
    update_profile,
    update_project,
    update_skill,
    update_task_tool,
    # Web
    web_search,
)
from src.config import settings
from src.db import session_scope
from src.db.queries import log_agent_event

logger = logging.getLogger(__name__)


async def _safe_extract(user_message: str, assistant_response: str) -> None:
    try:
        await extract_memories_background(user_message, assistant_response)
    except Exception:
        logger.exception("Memory extraction failed silently")


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
- Media generation: create images, edit photos, generate videos with audio

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

MEDIA GENERATION:
- generate_image: text-to-image. model="flash" (fast, default) or "imagen" (high quality).
- edit_image: send an image path + natural language instruction. No masks needed.
- generate_video: text-to-video or image-to-video. Takes 1-5 minutes.
  - Models: veo-3.1-lite (default, fast, has audio), veo-2, veo-3, veo-3.1, veo-3.1-fast
  - Supports start_image_path, end_image_path (frame interpolation), duration, resolution (720p/1080p/4k),
    aspect_ratio (16:9/9:16), audio (on by default for veo-3+), negative_prompt
When the user sends a photo with an editing instruction, use edit_image with the saved image path.
When generating video, warn the user it takes a few minutes.
If media generation fails, retry silently with a different model or simpler params.
Do NOT present long option lists — just pick the best fallback and try again. Keep errors short.

VIDEO EDITING (FFmpeg):
- trim_video: cut a clip to a time range (start/end or start/duration)
- concat_videos: stitch multiple videos together (with optional crossfade)
- add_audio: add or mix an audio track onto a video
- extract_audio: rip audio from a video (mp3/wav/m4a)
- resize_video: change resolution (480p/720p/1080p/4k)
- speed_video: speed up or slow down (e.g., 2.0 = 2x, 0.5 = half speed)
- add_text_overlay: burn text onto video (position, timing, color)
- probe_media: inspect file details (duration, resolution, codecs)
All output files are saved to data/media/. Use send_file to deliver results.
Chain these tools for complex edits (e.g., trim + concat + add audio).

TASK IDs: Always prefixed with # (e.g., #5, #12). Use the exact numeric ID, not list position.

RECURRING TASKS:
Map natural language to RRULE format:
- "every day" -> FREQ=DAILY
- "every Monday" -> FREQ=WEEKLY;BYDAY=MO
- "every weekday" -> FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR
- "every month on the 15th" -> FREQ=MONTHLY;BYMONTHDAY=15

SKILLS:
You have a skills system — .md files that teach you multi-step workflows.
When a user asks you to DO something complex (deploy, plan, generate a report, etc.):
1. Call find_skill(query) to check if a matching skill exists
2. If found, call read_skill(name) for overview, then read_skill(name, section) for specific steps
3. Follow the skill's instructions step by step
4. If no skill matches, proceed normally and offer to create one for next time
Use progressive disclosure: read only the section you need, execute it, then read the next.
When the user teaches you a workflow ("remember how to X", "here's how you should X"), create a skill.

CONSTANT LEARNING:
When the user corrects you, expresses a preference, or you learn a fact:
- Use save_memory to store it for future reference
- Before decisions, use recall_memory to check stored context
- Keep memory keys descriptive (e.g., "preference_meeting_times", "fact_user_name")

DELEGATION RULES:
You have 5 specialized team members. Delegate when a task matches their domain AND
requires focused multi-step work. Handle simple requests yourself — don't delegate
one-tool actions.

WHEN TO DELEGATE:
- researcher: User needs info from the web (prices, news, products, facts).
  Send if it requires 2+ searches or reading web pages.
- planner: User asks to plan their day/week/schedule, optimize priorities,
  or figure out what to work on. Send when it needs cross-referencing
  tasks + calendar + deadlines.
- content-creator: User needs something WRITTEN — notes, templates, lesson plans,
  summaries, checklists. Send when output is a document, not a chat reply.
- shopping-scout: User needs product research, price comparison, or gift ideas
  for specific items. Send when it requires searching multiple retailers.
- social-manager: User needs help with birthdays, gifts for specific people,
  relationship tracking, social event planning. Send when it involves
  cross-referencing contacts with tasks/gifts/events.

WHEN NOT TO DELEGATE:
- Simple CRUD (add task, set reminder, check item) → do it yourself
- Task decomposition → do it yourself (you have add_subtask)
- Data analysis / mood trends → do it yourself (you have run_python_code + mood tools)
- Quick questions → do it yourself
- Anything that needs 1 tool call → do it yourself

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
# All main tools — plain Python functions
# ---------------------------------------------------------------------------

MAIN_TOOLS: list[Any] = [
    get_current_datetime,
    # Tasks
    add_tasks,
    update_task_tool,
    complete_task,
    get_overdue_tasks,
    list_tasks,
    search_tasks_tool,
    get_task_details,
    delete_task_tool,
    add_subtask,
    move_task,
    list_tags,
    list_recurring,
    stop_recurring,
    # Projects
    create_project,
    list_projects_tool,
    show_project,
    assign_to_project,
    unassign_from_project,
    archive_project,
    assign_tasks_to_project,
    move_project_tasks,
    update_project,
    # Reminders
    set_reminder,
    list_reminders,
    cancel_reminder,
    remind_before_deadline,
    # Agenda
    get_agenda,
    # Calendar
    test_calendar,
    create_calendar_event,
    update_calendar_event,
    delete_calendar_event,
    list_calendar_events,
    # Shopping
    add_to_list,
    show_list,
    check_item,
    uncheck_item,
    remove_item,
    clear_checked,
    show_gifts_for_contact,
    purchase_item,
    # Contacts
    add_contact,
    show_contacts,
    upcoming_birthdays,
    update_contact_tool,
    remove_contact,
    get_contact_tasks,
    # Notes
    browse_notes,
    read_note_tool,
    create_note_tool,
    update_note_tool,
    append_to_note_tool,
    search_notes_tool,
    # Profile
    update_profile,
    show_profile,
    get_weather,
    # Bookmarks
    save_bookmark,
    list_reading_list,
    mark_read,
    remove_bookmark,
    search_reading_list,
    # Mood
    log_mood,
    show_mood_history,
    mood_summary,
    # Scheduling
    find_free_slot,
    # Code
    run_python_code,
    run_shell_command,
    # Web
    web_search,
    fetch_url,
    # Files
    send_file,
    # Media generation
    generate_image,
    edit_image,
    generate_video,
    # FFmpeg / video editing
    trim_video,
    concat_videos,
    add_audio,
    extract_audio,
    resize_video,
    speed_video,
    add_text_overlay,
    probe_media,
    # Interests
    add_interest,
    list_interests,
    remove_interest,
    update_interest_tool,
    # Beads
    beads_create,
    beads_list,
    beads_ready,
    # Memory
    save_memory,
    recall_memory,
    list_memories,
    forget_memory,
    # Skills
    list_skills,
    find_skill,
    read_skill,
    create_skill,
    update_skill,
    delete_skill,
]


# ---------------------------------------------------------------------------
# Agent / Team state
# ---------------------------------------------------------------------------

AGENT_TIMEOUT = 1200  # 20 minutes

_team: Team | None = None
_mcp_tools: list[Any] = []
_db = SqliteDb(
    session_table="agno_sessions",
    db_file=str(settings.database_path),
)
_summary_manager = SessionSummaryManager(
    model=OpenAIChat(id="gpt-5-mini", api_key=settings.openai_api_key),
)

SESSION_ID = "minion-main"


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

    # Inject available skills summary (lightweight — just filenames, no reads)
    try:
        from src.integrations.silverbullet import list_notes_recursive

        skill_notes = list_notes_recursive("Skills")
        if skill_notes:
            lines = ["\nAVAILABLE SKILLS:"]
            for sn in skill_notes[:20]:
                display_name = sn.replace("Skills/", "").removesuffix(".md")
                lines.append(f"- {display_name}")
            parts.append("\n".join(lines))
    except Exception:
        pass

    # Format-specific instructions
    fmt = FORMAT_HINTS.get(format_hint, "")
    if fmt:
        parts.append(fmt)

    return "\n\n".join(parts)


def set_mcp_tools(tools: list[Any]) -> None:
    """Set MCP tools to be included in the agent. Called from main.py after MCP init."""
    global _mcp_tools, _team
    _mcp_tools = tools
    _team = None  # force rebuild on next call


def _get_team(format_hint: str) -> Team:
    """Lazy-create (or rebuild) the Agno Team."""
    global _team

    all_tools = MAIN_TOOLS + _mcp_tools

    members = build_team_members()

    _team = Team(
        name="Minion",
        mode=TeamMode.coordinate,
        model=OpenAIChat(id=settings.agent_model, api_key=settings.openai_api_key),
        members=members,  # type: ignore[arg-type]
        tools=all_tools,
        instructions=[_build_system_prompt(format_hint)],
        db=_db,
        num_history_runs=5,
        add_history_to_context=True,
        show_members_responses=True,
        markdown=format_hint == "web",
        enable_session_summaries=True,
        session_summary_manager=_summary_manager,
        telemetry=False,
    )

    return _team


async def chat(message: str, format_hint: str = "telegram") -> str:
    """Send a message to the agent and get a response.

    Args:
        message: User message text.
        format_hint: "telegram" for HTML formatting, "web" for Markdown.
    """
    logger.info(f"Chat input: {message[:100]}{'...' if len(message) > 100 else ''}")

    team = _get_team(format_hint)

    response_text = ""
    try:
        async with asyncio.timeout(AGENT_TIMEOUT):
            response = await team.arun(
                message,
                session_id=SESSION_ID,
                stream=False,
            )
            if response and response.content:
                response_text = response.content
    except TimeoutError:
        logger.error("chat() timed out after %d seconds", AGENT_TIMEOUT)
        raise TimeoutError(f"Agent timed out after {AGENT_TIMEOUT // 60} minutes") from None
    except Exception:
        logger.exception("chat() error")
        raise

    if not response_text.strip():
        response_text = "Done."

    # Log to event bus
    try:
        with session_scope() as session:
            log_agent_event(session, "chat", "agent_response", response_text[:500])
    except Exception:
        logger.debug("Failed to log agent response to event bus", exc_info=True)

    # Extract memories in background (fire-and-forget)
    asyncio.create_task(_safe_extract(message, response_text))

    logger.info(f"Chat output: {response_text[:100]}{'...' if len(response_text) > 100 else ''}")
    return response_text


async def chat_stream(message: str, format_hint: str = "telegram"):
    """Streaming version of chat — yields (event_type, data) tuples.

    Event types:
        ("text", str)       — final response text chunk
        ("tool_call", str)  — name of tool being invoked
        ("thinking", str)   — reasoning snippet
        ("result", str)     — stream complete

    Args:
        message: User message text.
        format_hint: "telegram" for HTML formatting, "web" for Markdown.
    """
    logger.info(f"Chat stream input: {message[:100]}{'...' if len(message) > 100 else ''}")

    team = _get_team(format_hint)
    full_text = ""

    try:
        async for event in team.arun(
            message,
            session_id=SESSION_ID,
            stream=True,
            stream_events=True,
        ):
            # Team final content
            if event.event == TeamRunEvent.run_content:
                chunk = event.content or ""
                if chunk:
                    full_text += chunk
                    yield ("text", chunk)

            # Team-level tool call
            elif event.event == TeamRunEvent.tool_call_started:
                tool_obj = getattr(event, "tool", None)
                tool_name = tool_obj.tool_name if tool_obj else "unknown"
                yield ("tool_call", tool_name)

            # Member-level tool call
            elif event.event == RunEvent.tool_call_started:
                tool_obj = getattr(event, "tool", None)
                tool_name = tool_obj.tool_name if tool_obj else "unknown"
                agent_id = getattr(event, "agent_id", "")
                label = f"{agent_id}: {tool_name}" if agent_id else tool_name
                yield ("tool_call", label)

            # Team run completed
            elif event.event == TeamRunEvent.run_completed:
                yield ("result", "")

    except GeneratorExit:
        logger.info("chat_stream GeneratorExit")
        return
    except Exception:
        logger.exception("chat_stream error")
        raise

    # Log to event bus
    if full_text:
        try:
            with session_scope() as session:
                log_agent_event(session, "chat_stream", "agent_response", full_text[:500])
        except Exception:
            logger.debug("Failed to log agent response to event bus", exc_info=True)

        # Extract memories in background (fire-and-forget)
        asyncio.create_task(_safe_extract(message, full_text))


async def shutdown() -> None:
    """Clean up agent state."""
    global _team
    _team = None
    logger.info("Agno agent cleaned up")
