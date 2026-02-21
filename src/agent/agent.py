import asyncio
import logging
import time
import uuid
from collections.abc import Callable
from typing import Any

from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.learn import (
    DecisionLogConfig,
    EntityMemoryConfig,
    LearningMachine,
    LearningMode,
    SessionContextConfig,
    UserMemoryConfig,
    UserProfileConfig,
)
from agno.models.openai import OpenAIChat

from src.config import settings

logger = logging.getLogger(__name__)


def tool_logger_hook(function_name: str, function_call: Callable, arguments: dict[str, Any]) -> Any:
    """Log tool calls with execution time and send error notifications."""
    logger.info(f"Tool call: {function_name}({list(arguments.keys())})")
    start_time = time.time()

    try:
        result = function_call(**arguments)
        duration = time.time() - start_time
        logger.info(f"Tool {function_name} completed in {duration:.2f}s")
        return result
    except Exception as e:
        duration = time.time() - start_time
        error_id = str(uuid.uuid4())[:8]
        logger.exception(f"Tool {function_name} failed after {duration:.2f}s: {e} (ID: {error_id})")

        # Send async error notification
        try:
            from src.telegram.bot import notify_error

            loop = asyncio.get_running_loop()
            loop.create_task(notify_error(function_name, e, error_id))
        except RuntimeError:
            # No event loop running
            pass
        except Exception as notify_err:
            logger.debug(f"Could not send error notification: {notify_err}")

        raise


from src.agent.tools import (  # noqa: E402 — must follow tool_logger_hook definition
    # Contact tools
    add_contact,
    # Interest tools
    add_interest,
    add_subtask,
    add_tasks,
    # Shopping tools
    add_to_list,
    append_to_note_tool,
    archive_project,
    assign_tasks_to_project,
    assign_to_project,
    # Beads fallback tools
    beads_create,
    beads_list,
    beads_ready,
    # Notes tools
    browse_notes,
    cancel_reminder,
    check_item,
    clear_checked,
    complete_task,
    create_calendar_event,
    create_note_tool,
    # Project tools
    create_project,
    delete_calendar_event,
    delete_task_tool,
    # Web tools
    fetch_url,
    # Scheduling tools
    find_free_slot,
    get_agenda,
    get_contact_tasks,
    get_current_datetime,
    get_overdue_tasks,
    get_task_details,
    # Profile tools
    get_weather,
    list_calendar_events,
    list_interests,
    list_projects_tool,
    # Bookmark tools
    list_reading_list,
    # Recurring task tools
    list_recurring,
    list_reminders,
    list_tags,
    list_tasks,
    # Mood tools
    log_mood,
    mark_read,
    mood_summary,
    move_project_tasks,
    move_task,
    purchase_item,
    read_note_tool,
    remind_before_deadline,
    remove_bookmark,
    remove_contact,
    remove_interest,
    remove_item,
    # Code execution tools
    run_python_code,
    run_shell_command,
    save_bookmark,
    search_notes_tool,
    search_reading_list,
    search_tasks_tool,
    # Reminder tools
    set_reminder,
    show_contacts,
    show_gifts_for_contact,
    show_list,
    show_mood_history,
    show_profile,
    show_project,
    stop_recurring,
    test_calendar,
    unassign_from_project,
    uncheck_item,
    upcoming_birthdays,
    update_calendar_event,
    update_contact_tool,
    update_interest_tool,
    update_note_tool,
    update_profile,
    update_project,
    update_task_tool,
    web_search,
)

SYSTEM_PROMPT_BASE = """You are Minion, a personal assistant bot.

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
- Work 💼: job tasks, meetings, PRs, code reviews, office work
- Personal 🏠: home tasks, errands, personal items
- Health 🏃: exercise, medical appointments, wellness
- Finance 💰: bills, budget, investments, taxes
- Social 👥: friends, family, events, gatherings
- Learning 📚: courses, books, skills, tutorials

Example tag mappings:
- "finish FBI PR" → Work
- "buy groceries" → Personal
- "schedule dentist" → Health
- "pay electricity bill" → Finance
- "call Jana about party" → Social
- "read React docs" → Learning

PROJECTS (User-Created):
Projects are user-created containers for related tasks (e.g., "MinionBot", "House Renovation").
- Projects have a name, emoji, and optional tag for categorization
- Use create_project to create new projects
- Use assign_to_project to add tasks to a project
- Use show_project to see all tasks in a project
- Tasks can have both a tag (category) AND belong to a project
- When user mentions a project name, use it; otherwise don't assign projects
- Projects show as [📁ProjectName] in task lists

TASK DESCRIPTIONS:
Tasks can have optional descriptions for extra context. Descriptions:
- Are hidden in list views to keep them clean
- Are shown when using get_task_details
- Are searchable with search_tasks_tool
Use descriptions for notes, links, or details that don't fit in the title.

SHOPPING LISTS:
Three types - auto-infer, never ask:
- Gifts 🎁: "gift for mom" → Gifts (anything with a recipient or gift-related keywords)
- Groceries 🛒: "buy eggs" → Groceries (supermarket/house items, default for ambiguous)
- Wishlist ✨: "that PS5 I want" → Wishlist (personal wants, "wish", "want", "someday")
Just add items. Don't ask "which list?" - infer it.
Gift items with recipients auto-link to contacts if they exist.
Use show_gifts_for_contact to see all gift ideas for someone.

Quantities: Add "12 eggs" and it creates with target=12. Use purchase_item to track partial purchases
(e.g., "bought 3 eggs" → purchase_item(id, 3)). Items auto-complete when purchased >= target.

IMPORTANT - Item IDs: Item IDs are database IDs starting from 1, NOT list positions. IDs are shown as
#1, #2, etc. in show_list output. NEVER guess IDs - if you need to check/remove/purchase an item and
don't know its ID, call show_list FIRST to see actual IDs. There is no item #0.

CONTACTS:
Track birthdays with add_contact. You'll be reminded of upcoming birthdays at 5pm daily.
Contacts support aliases (e.g., "Jana" is also "Janaina") - use these for nicknames/full names.
When creating tasks about a person (e.g., "call Jana"), link to their contact if they exist.
Just create contacts when user mentions birthdays - don't ask permission.

NOTES (Silverbullet):
Notes are markdown files. Use paths like "Journal/2024-01-15" or "Projects/Minion".
- browse_notes to explore folders
- search_notes_tool to find notes by title or content
- read_note_tool to read a specific note
- create_note_tool to create (fails if exists)
- update_note_tool to replace content entirely
- append_to_note_tool to add to end of note
Preserve [[wiki-link]] syntax when editing. Search first if you don't know the exact path.

IMPORTANT: Task IDs are prefixed with # (e.g., #5, #12). When the user refers to a task by number,
ALWAYS use the exact numeric ID shown after the # symbol. Do NOT confuse list position with task ID.
For example, if the list shows "#10: Buy groceries", the task ID is 10, not the position in the list.

USER PROFILE:
When user mentions where they live, their name, or timezone preferences, use update_profile to save it.
Use show_profile to check stored preferences when relevant.

WEATHER:
Weather is automatically shown in the agenda. User can also ask "what's the weather?" and you'll use get_weather.

RECURRING TASKS:
When user says "every day/week/month/year", set recurrence on the task.
Map natural language to RRULE format:
- "every day" → FREQ=DAILY
- "every Monday" → FREQ=WEEKLY;BYDAY=MO
- "every weekday" → FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR
- "every month on the 15th" → FREQ=MONTHLY;BYMONTHDAY=15
- "every year" → FREQ=YEARLY
- "every Saturday" → FREQ=WEEKLY;BYDAY=SA
Recurring tasks show 🔄 in list views. When completed, a new instance auto-generates.
Use stop_recurring to end a recurrence pattern.

BOOKMARKS:
When user shares a URL or says "save this link", use save_bookmark.
Auto-detect URLs in messages and offer to save them.
Use list_reading_list to show bookmarks, search_reading_list to search.

SMART SCHEDULING:
When user asks to find time for something, use find_free_slot.
Suggest slots and offer to create the event directly.

MOOD TRACKING:
When user shares how they feel or rates their day, use log_mood (1-5 scale).
1: terrible, 2: bad, 3: okay, 4: good, 5: great.
Use mood_summary to check trends when relevant.

CODE EXECUTION:
You can run Python code and shell commands directly on the host.
- run_python_code: execute Python scripts, install packages if needed
- run_shell_command: execute shell commands
Use these for calculations, data processing, file operations, or any computational task.

WEB BROWSING:
You can search the web and fetch content from URLs.
- web_search: search via DuckDuckGo for current information
- fetch_url: extract readable text from any URL
- Browser tools (via Playwright MCP): navigate, click, fill forms, take screenshots
Use these for research, price comparisons, news, or any web-based task.

INTERESTS:
Track topics the user cares about for proactive monitoring.
- add_interest: start tracking a topic (e.g., "Rust news", "PS5 prices")
- list_interests: show all tracked interests
- remove_interest / update_interest_tool: manage interests
The heartbeat system will proactively research these and notify the user.

BEADS (Work Tracking):
Track sub-tasks and delegated work via Beads.
- beads_create: create a tracked work item
- beads_list: list tracked items
- beads_ready: show items ready to work on

CONSTANT LEARNING:
You are ALWAYS learning. After EVERY interaction, think:
- User corrected you or expressed a preference? → save it via memory tools immediately
- You learned a fact about a person/service/website? → entity memory captures it
- User made a decision with reasoning? → decision log captures it
- You discovered a workflow pattern? → save it as learned knowledge
When the user says "I don't like X", "actually do it this way", "I prefer Y" — IMMEDIATELY save it.
Before making decisions, your stored memories and knowledge are already in context — act on them.

When the user mentions something that sounds like a task, offer to add it.
When they mention a time or deadline, offer to set a reminder.
Always confirm actions taken.

LANGUAGE: Always reply in English, regardless of the language the user writes in.

Current timezone: America/Sao_Paulo
"""

SYSTEM_PROMPT = SYSTEM_PROMPT_BASE

# ── Formatter prompts (separate LLM pass for channel-specific formatting) ──

TELEGRAM_FORMATTER_PROMPT = """\
You are a formatting agent. Convert the message below to Telegram HTML format.
Output ONLY the reformatted message — no preamble, no explanation.

HTML TAGS (the only allowed markup):
• <b>bold</b> — section headers, emphasis
• <i>italic</i> — secondary info, notes, timestamps
• <code>#12</code> — task/item IDs, technical values
• <s>strikethrough</s> — completed/cancelled items
• Use literal newlines for line breaks (never <br>)
• Use • for bullet points (never -)
• Keep under 4096 characters

EMOJI STYLE GUIDE (always apply):
Action confirmations: ✅ Done/Completed, 🆕 Added/Created, ✏️ Updated/Renamed, \
🗑️ Deleted/Removed, ⏰ Reminder set
Task status markers in lists: [ ] todo, [~] in progress, [✓] done
Category icons (always show next to tasks):
  💼 Work  🏠 Personal  🏃 Health  💰 Finance  👥 Social  📚 Learning
Section headers: 🎂 Birthdays, 📅 Calendar, 🛒 Shopping, 📋 Tasks
Recurring tasks: 🔄
Weather: use the emoji that matches conditions (☀️ ⛅ 🌧️ etc.)

CRITICAL — NEVER output any Markdown syntax:
No **bold**, no *italic*, no `backticks`, no ~~strike~~, no - bullets, no # headers.

Preserve the message's content and meaning exactly. Only change formatting.\
"""

WEB_FORMATTER_PROMPT = """\
You are a formatting agent. Convert the message below to clean Markdown.
Output ONLY the reformatted message — no preamble, no explanation.

RULES:
• **bold** for headers and emphasis
• *italic* for secondary info
• `code` for IDs like #12
• - for bullet points
• ~~strikethrough~~ for completed items

NEVER output HTML tags.
Preserve the message's content and meaning exactly. Only change formatting.\
"""

FORMATTER_PROMPTS = {
    "telegram": TELEGRAM_FORMATTER_PROMPT,
    "web": WEB_FORMATTER_PROMPT,
}

# Session database for agent memory and learning
_db: SqliteDb | None = None


def get_db() -> SqliteDb:
    """Get or create the session database."""
    global _db
    if _db is None:
        db_path = settings.database_path.parent / "agent_sessions.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _db = SqliteDb(db_file=str(db_path))
    return _db


def _get_learning_machine() -> LearningMachine:
    """Create the LearningMachine with 6 specialized stores."""
    db = get_db()
    model = OpenAIChat(id=settings.memory_model, api_key=settings.openai_api_key)

    return LearningMachine(
        db=db,
        model=model,
        # Structured profile: name, preferences — only when agent decides
        user_profile=UserProfileConfig(mode=LearningMode.AGENTIC),
        # Unstructured observations — agent decides what to save
        user_memory=UserMemoryConfig(mode=LearningMode.AGENTIC),
        # Session goals, plan, progress — only when agent decides
        session_context=SessionContextConfig(mode=LearningMode.AGENTIC),
        # Facts about external entities (people, companies, services)
        entity_memory=EntityMemoryConfig(mode=LearningMode.AGENTIC),
        # Decisions with reasoning
        decision_log=DecisionLogConfig(mode=LearningMode.AGENTIC),
        namespace="user",
    )


# All custom tools (non-MCP)
_CUSTOM_TOOLS = [
    # Utility tools
    get_current_datetime,
    # Task management tools
    add_tasks,
    update_task_tool,
    complete_task,
    get_overdue_tasks,
    list_tasks,
    search_tasks_tool,
    get_task_details,
    delete_task_tool,
    # Task hierarchy tools
    add_subtask,
    move_task,
    # Tag tools
    list_tags,
    # Project tools
    create_project,
    list_projects_tool,
    show_project,
    assign_to_project,
    unassign_from_project,
    archive_project,
    assign_tasks_to_project,
    move_project_tasks,
    update_project,
    # Reminder tools
    set_reminder,
    list_reminders,
    cancel_reminder,
    remind_before_deadline,
    # Agenda tool
    get_agenda,
    # Calendar tools
    test_calendar,
    create_calendar_event,
    update_calendar_event,
    delete_calendar_event,
    list_calendar_events,
    # Shopping list tools
    add_to_list,
    show_list,
    check_item,
    uncheck_item,
    remove_item,
    clear_checked,
    show_gifts_for_contact,
    purchase_item,
    # Contact tools
    add_contact,
    show_contacts,
    upcoming_birthdays,
    update_contact_tool,
    remove_contact,
    get_contact_tasks,
    # Notes tools
    browse_notes,
    read_note_tool,
    create_note_tool,
    update_note_tool,
    append_to_note_tool,
    search_notes_tool,
    # Profile tools
    update_profile,
    show_profile,
    get_weather,
    # Bookmark tools
    save_bookmark,
    list_reading_list,
    mark_read,
    remove_bookmark,
    search_reading_list,
    # Mood tools
    log_mood,
    show_mood_history,
    mood_summary,
    # Scheduling tools
    find_free_slot,
    # Recurring task tools
    list_recurring,
    stop_recurring,
    # Code execution tools
    run_python_code,
    run_shell_command,
    # Web tools
    web_search,
    fetch_url,
    # Interest tools
    add_interest,
    list_interests,
    remove_interest,
    update_interest_tool,
    # Beads fallback tools
    beads_create,
    beads_list,
    beads_ready,
]


def create_agent(mcp_tools: list | None = None) -> Agent:
    """Create and configure the Minion agent.

    Args:
        mcp_tools: Optional list of MCPTools instances (Playwright, Beads, etc.)
    """
    logger.info("Creating Minion agent...")

    tools: list = list(_CUSTOM_TOOLS)
    if mcp_tools:
        tools.extend(mcp_tools)

    return Agent(
        model=OpenAIChat(
            id=settings.agent_model,
            api_key=settings.openai_api_key,
        ),
        tools=tools,
        instructions=SYSTEM_PROMPT,
        markdown=True,
        # Tool hooks for logging
        tool_hooks=[tool_logger_hook],
        # Database for persistence
        db=get_db(),
        # LearningMachine (replaces old MemoryManager)
        learning=_get_learning_machine(),
        add_learnings_to_context=True,
        # Session history
        add_history_to_context=True,
        num_history_runs=5,
        read_chat_history=True,
        max_tool_calls_from_history=3,
        # Context enhancements
        add_datetime_to_context=True,
    )


# Singleton agent instance
_agent: Agent | None = None


def get_agent() -> Agent:
    """Get or create the agent singleton."""
    global _agent
    if _agent is None:
        _agent = create_agent()
    return _agent


def reset_agent() -> None:
    """Reset the agent singleton (e.g., after MCP init)."""
    global _agent
    _agent = None


# Fixed session ID for single-user bot
SESSION_ID = f"user_{settings.telegram_user_id}"


async def _format_output(text: str, format_hint: str) -> str:
    """Format agent output for the target channel using a lightweight LLM."""
    prompt = FORMATTER_PROMPTS.get(format_hint)
    if not prompt or not text.strip():
        return text

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.openai_api_key)
        resp = await client.chat.completions.create(
            model=settings.memory_model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": text},
            ],
        )
        formatted = resp.choices[0].message.content or text
        logger.debug(f"Formatter ({format_hint}): {len(text)}→{len(formatted)} chars")
        return formatted
    except Exception:
        logger.exception("Formatter failed, returning raw output")
        return text


async def chat(message: str, format_hint: str = "telegram") -> str:
    """Send a message to the agent and get a response.

    Args:
        message: User message text.
        format_hint: "telegram" for HTML formatting, "web" for Markdown.
    """
    logger.info(f"Chat input: {message[:100]}{'...' if len(message) > 100 else ''}")

    try:
        agent = get_agent()

        response = await asyncio.to_thread(
            agent.run,
            message,
            user_id=str(settings.telegram_user_id),
            session_id=SESSION_ID,
        )

        content = response.content or ""

        # Guard against empty responses (model only emitted tool calls)
        if not content.strip():
            logger.warning("Agent returned empty content after tool calls, using fallback")
            content = "Done."

        logger.info(f"Chat output (raw): {content[:100]}{'...' if len(content) > 100 else ''}")

        formatted = await _format_output(content, format_hint)
        logger.info(f"Chat output (fmt): {formatted[:100]}{'...' if len(formatted) > 100 else ''}")

        return formatted
    except Exception as e:
        logger.exception(f"Agent error: {e}")
        raise
