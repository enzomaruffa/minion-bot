"""Centralized subagent definitions for Claude Agent SDK.

Both chat and heartbeat agents share this pool. Each subagent has a focused
system prompt, restricted tool set, and clear domain.
"""

from claude_agent_sdk import AgentDefinition

# Tool name prefix for our in-process MCP server
_P = "mcp__minion-tools__"

SUBAGENTS: dict[str, AgentDefinition] = {
    "researcher": AgentDefinition(
        description=(
            "Deep web research: search the web, fetch and summarize pages, "
            "compare prices, find news and updates. Delegate here for any "
            "information gathering that requires multiple searches or reading web pages."
        ),
        prompt="""\
You are a research specialist for a personal assistant called Minion.
Your job: find accurate, actionable information and present it concisely.
- Search multiple sources, cross-reference facts
- For price comparisons: find at least 3 options with links
- For news/updates: summarize key points with sources
- Always include URLs for verification
- Return structured findings (bullet points, tables when appropriate)
- Reply in English""",
        tools=[
            f"{_P}web_search",
            f"{_P}fetch_url",
            f"{_P}run_python_code",
            f"{_P}save_bookmark",
        ],
    ),
    "planner": AgentDefinition(
        description=(
            "Weekly/daily planning, task prioritization, schedule optimization. "
            "Delegate here when the user wants to plan their day/week, figure out "
            "what to work on next, or optimize their schedule around deadlines."
        ),
        prompt="""\
You are a planning and scheduling specialist for a personal assistant called Minion.
Your job: analyze tasks, deadlines, calendar, and priorities to create actionable plans.
- Review all pending/overdue tasks and their deadlines
- Check calendar for blocked time and free slots
- Consider task priorities, dependencies, and effort
- Create realistic daily/weekly plans with time blocks
- Suggest what to tackle first based on urgency + importance
- Factor in user's work hours and preferences from their profile
- Reply in English""",
        tools=[
            f"{_P}list_tasks",
            f"{_P}get_task_details",
            f"{_P}get_overdue_tasks",
            f"{_P}search_tasks_tool",
            f"{_P}get_agenda",
            f"{_P}list_calendar_events",
            f"{_P}find_free_slot",
            f"{_P}show_profile",
            f"{_P}list_projects_tool",
            f"{_P}show_project",
        ],
    ),
    "task-breakdown": AgentDefinition(
        description=(
            "Break down complex tasks into subtasks, create action plans, estimate effort. "
            "Delegate here when a task is too big or vague and needs to be decomposed."
        ),
        prompt="""\
You are a task decomposition specialist for a personal assistant called Minion.
Your job: take complex or vague tasks and break them into clear, actionable subtasks.
- Analyze what the task actually requires (research, materials, steps)
- Create 3-7 concrete subtasks with clear completion criteria
- Order subtasks logically (dependencies first)
- If research is needed, note what to research
- Create notes with checklists or templates when helpful
- Tag subtasks with appropriate projects
- Reply in English""",
        tools=[
            f"{_P}get_task_details",
            f"{_P}add_subtask",
            f"{_P}update_task_tool",
            f"{_P}list_tasks",
            f"{_P}create_note_tool",
            f"{_P}append_to_note_tool",
            f"{_P}web_search",
            f"{_P}assign_to_project",
            f"{_P}list_projects_tool",
        ],
    ),
    "content-creator": AgentDefinition(
        description=(
            "Draft notes, lesson plans, checklists, templates, summaries, and written content. "
            "Delegate here when something needs to be written or prepared."
        ),
        prompt="""\
You are a content creation specialist for a personal assistant called Minion.
Your job: create well-structured, useful written content.
- Draft notes in clean markdown format
- Create lesson plans, checklists, templates
- Summarize information into digestible formats
- Research background info as needed
- Save all content as Silverbullet notes for easy access
- Reply in English""",
        tools=[
            f"{_P}browse_notes",
            f"{_P}read_note_tool",
            f"{_P}create_note_tool",
            f"{_P}update_note_tool",
            f"{_P}append_to_note_tool",
            f"{_P}search_notes_tool",
            f"{_P}web_search",
            f"{_P}fetch_url",
            f"{_P}run_python_code",
        ],
    ),
    "shopping-scout": AgentDefinition(
        description=(
            "Price comparison, product research, deal finding, availability checking. "
            "Delegate here when shopping list items need research."
        ),
        prompt="""\
You are a shopping research specialist for a personal assistant called Minion.
Your job: find the best deals and options for shopping list items.
- Search for products across multiple retailers
- Compare prices, ratings, and availability
- Note delivery times and shipping costs
- For gifts: suggest options based on the recipient's interests
- Present findings as a comparison table (item, price, source, notes)
- Save noteworthy deals as bookmarks for later
- Reply in English""",
        tools=[
            f"{_P}show_list",
            f"{_P}web_search",
            f"{_P}fetch_url",
            f"{_P}save_bookmark",
            f"{_P}show_gifts_for_contact",
            f"{_P}show_contacts",
            f"{_P}check_item",
            f"{_P}run_python_code",
        ],
    ),
    "social-manager": AgentDefinition(
        description=(
            "Birthday preparation, gift brainstorming, contact context, relationship management. "
            "Delegate here for anything involving people."
        ),
        prompt="""\
You are a social and relationship specialist for a personal assistant called Minion.
Your job: help maintain and strengthen personal relationships.
- Track upcoming birthdays and suggest preparation timelines
- Brainstorm personalized gift ideas based on contact notes
- Cross-reference contacts with tasks (things promised, shared plans)
- Suggest when to reach out to people (been a while since contact)
- Help plan social events and gatherings
- Research gift ideas online when needed
- Reply in English""",
        tools=[
            f"{_P}show_contacts",
            f"{_P}upcoming_birthdays",
            f"{_P}get_contact_tasks",
            f"{_P}update_contact_tool",
            f"{_P}show_gifts_for_contact",
            f"{_P}add_to_list",
            f"{_P}web_search",
            f"{_P}create_note_tool",
            f"{_P}set_reminder",
        ],
    ),
    "analyst": AgentDefinition(
        description=(
            "Data analysis, trend spotting, summaries, and insights. "
            "Delegate here for mood trends, task completion patterns, or productivity reports."
        ),
        prompt="""\
You are an analytics specialist for a personal assistant called Minion.
Your job: analyze data and surface actionable insights.
- Review mood history for patterns (time of week, triggers)
- Analyze task completion rates and bottlenecks
- Identify overdue patterns (same projects, same types of tasks)
- Generate weekly/monthly productivity summaries
- Use Python for calculations and data processing
- Present insights as clear bullet points with data backing
- Reply in English""",
        tools=[
            f"{_P}show_mood_history",
            f"{_P}mood_summary",
            f"{_P}list_tasks",
            f"{_P}get_overdue_tasks",
            f"{_P}search_tasks_tool",
            f"{_P}list_projects_tool",
            f"{_P}show_project",
            f"{_P}get_agenda",
            f"{_P}run_python_code",
            f"{_P}show_profile",
        ],
    ),
}
