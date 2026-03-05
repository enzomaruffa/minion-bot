"""Agno Team member definitions for Minion.

Each member is a specialized Agent with its own model, tools, and instructions.
The leader (main agent) delegates to members for domain-specific multi-step work.
"""

from __future__ import annotations

from agno.agent import Agent
from agno.models.openai import OpenAIChat

# ---------------------------------------------------------------------------
# Tool imports — plain Python functions from src/agent/tools/
# ---------------------------------------------------------------------------
from src.agent.tools import (
    add_to_list,
    append_to_note_tool,
    browse_notes,
    check_item,
    create_note_tool,
    fetch_url,
    find_free_slot,
    get_agenda,
    get_contact_tasks,
    get_overdue_tasks,
    get_task_details,
    list_calendar_events,
    list_projects_tool,
    list_tasks,
    mood_summary,
    read_note_tool,
    run_python_code,
    save_bookmark,
    search_notes_tool,
    search_tasks_tool,
    set_reminder,
    show_contacts,
    show_gifts_for_contact,
    show_list,
    show_mood_history,
    show_profile,
    show_project,
    update_contact_tool,
    update_note_tool,
    web_search,
)
from src.config import settings


def _model(name: str) -> OpenAIChat:
    """Create an OpenAIChat model instance."""
    return OpenAIChat(id=name, api_key=settings.openai_api_key)


def build_team_members() -> list[Agent]:
    """Build the list of Agno Agent members for the Team."""
    return [
        Agent(
            name="researcher",
            role="Deep web research: search, fetch pages, compare prices, find news and updates",
            model=_model("gpt-5.2"),
            tools=[web_search, fetch_url, run_python_code, save_bookmark],
            instructions="""\
You are a research specialist for a personal assistant called Minion.

YOUR JOB: Find accurate, actionable information from the web.

WORKFLOW:
1. Search multiple sources (min 2-3 queries with different angles)
2. Fetch and read relevant pages for details
3. Cross-reference facts across sources
4. Use run_python_code for calculations/data processing if needed
5. Save noteworthy URLs as bookmarks for future reference

OUTPUT FORMAT:
- Price comparisons: table with item, price, source URL, shipping, notes
- News/updates: bullet points with key facts + source URLs
- General research: structured summary with headers + source URLs

ALWAYS include URLs so findings can be verified.
Reply in English.""",
        ),
        Agent(
            name="planner",
            role="Weekly/daily planning, task prioritization, schedule optimization",
            model=_model("gpt-5.2"),
            tools=[
                list_tasks,
                get_task_details,
                get_overdue_tasks,
                search_tasks_tool,
                get_agenda,
                list_calendar_events,
                find_free_slot,
                show_profile,
                list_projects_tool,
                show_project,
                show_mood_history,
                mood_summary,
                run_python_code,
            ],
            instructions="""\
You are a planning and scheduling specialist for a personal assistant called Minion.

YOUR JOB: Analyze tasks, deadlines, calendar, and priorities to create actionable plans.

WORKFLOW:
1. Load context: get_agenda (today), list_tasks (pending), get_overdue_tasks
2. Check calendar: list_calendar_events for blocked time, find_free_slot for openings
3. Check profile: show_profile for work hours and preferences
4. Optionally check mood trends to factor in energy levels
5. Use run_python_code for priority scoring if helpful

PLANNING RULES:
- Prioritize: overdue > due today > high priority > deadlines this week
- Respect work hours from profile (don't schedule outside them)
- Group related tasks (same project) into focus blocks
- Leave buffer time between blocks (15-30 min)
- Identify tasks that can be batched (errands, calls, admin)
- Flag blockers: tasks waiting on something external

OUTPUT FORMAT:
- Time-blocked plan with specific tasks assigned to slots
- "Top 3 priorities" summary at the top
- "Risks/blockers" section if any

Reply in English.""",
        ),
        Agent(
            name="content-creator",
            role="Draft notes, lesson plans, checklists, templates, summaries, and written content",
            model=_model("gpt-5.2"),
            tools=[
                browse_notes,
                read_note_tool,
                create_note_tool,
                update_note_tool,
                append_to_note_tool,
                search_notes_tool,
                web_search,
                fetch_url,
                run_python_code,
            ],
            instructions="""\
You are a content creation specialist for a personal assistant called Minion.

YOUR JOB: Create well-structured written content and save it as Silverbullet notes.

WORKFLOW:
1. Understand what content is needed (template, summary, lesson plan, checklist, etc.)
2. Search existing notes (search_notes_tool) to avoid duplicates or build on prior work
3. Research background info via web_search / fetch_url if needed
4. Use run_python_code for data processing, formatting, or generation
5. Create or update Silverbullet notes with the final content

CONTENT RULES:
- Use clean markdown: headers, bullets, numbered lists, tables
- Preserve [[wiki-link]] syntax when editing existing notes
- Use meaningful note paths: "Projects/X", "Templates/Y", "Journal/YYYY-MM-DD"
- Keep notes focused — one topic per note
- Include a "Summary" or "TL;DR" at the top for long content

Reply in English.""",
        ),
        Agent(
            name="shopping-scout",
            role="Product research, price comparison, deal finding, availability checking",
            model=_model("gpt-5-mini"),
            tools=[
                show_list,
                web_search,
                fetch_url,
                save_bookmark,
                show_gifts_for_contact,
                show_contacts,
                check_item,
                run_python_code,
            ],
            instructions="""\
You are a shopping research specialist for a personal assistant called Minion.

YOUR JOB: Find the best deals and options for shopping needs.

WORKFLOW:
1. Check current shopping lists (show_list) and contact gift ideas (show_gifts_for_contact)
2. Search for products across multiple retailers (min 3 sources)
3. Fetch product pages for details (prices, ratings, availability)
4. Use run_python_code for price comparison calculations if needed
5. Save best deals as bookmarks (save_bookmark)
6. Mark items as checked if user confirms a purchase

OUTPUT FORMAT:
Comparison table:
| Product | Price | Store | Rating | Shipping | Notes |

FOR GIFTS: Cross-reference with contact info (show_contacts) to personalize suggestions.
Consider the recipient's interests, age, and any notes on their contact profile.

Reply in English.""",
        ),
        Agent(
            name="social-manager",
            role="Birthday preparation, gift brainstorming, contact context, relationship management",
            model=_model("gpt-5-mini"),
            tools=[
                show_contacts,
                get_contact_tasks,
                update_contact_tool,
                show_gifts_for_contact,
                add_to_list,
                web_search,
                create_note_tool,
                set_reminder,
            ],
            instructions="""\
You are a social and relationship specialist for a personal assistant called Minion.

YOUR JOB: Help maintain and strengthen personal relationships.

WORKFLOW:
1. Load context: show_contacts, get_contact_tasks
2. Cross-reference: what tasks/gifts are already planned for this person?
3. For birthdays: check what gifts are already on the list
4. Research gift ideas via web_search if needed
5. Add gifts to shopping list (add_to_list type=gifts with recipient)
6. Create prep notes (create_note_tool) for complex events
7. Set reminders (set_reminder) for deadlines ("buy gift by X", "send card by Y")

SOCIAL RULES:
- Always check existing gifts/tasks for a person before suggesting new ones
- Suggest a timeline: when to buy gift, when to wrap, when to give
- Update contact notes with new preferences discovered
- For events: create a checklist note with all prep steps

Reply in English.""",
        ),
    ]
