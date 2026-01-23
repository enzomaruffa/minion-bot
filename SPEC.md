# Enzo's Personal Assistant Bot

## Overview

A Telegram-based personal assistant that manages tasks, reminders, and calendar through natural conversation. The assistant should feel like texting a highly competent personal assistant who remembers everything and proactively keeps you on track.

**Design Philosophy:** Hands-off, conversational, minimal friction. You talk, it figures out what to do. Commands exist as shortcuts but natural language always works.

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.11+ |
| Agent Framework | Agno |
| LLM | OpenAI GPT-4o |
| Speech-to-Text | OpenAI Whisper |
| Telegram | python-telegram-bot |
| Database | SQLite (via SQLAlchemy) |
| Scheduler | APScheduler |
| Calendar | Google Calendar API |

---

## Data Model

### Tasks

The core entity. Everything revolves around tasks.

```python
class Task:
    id: int  # auto-increment
    title: str  # short description
    status: TaskStatus  # enum
    priority: Priority  # enum
    topic: str  # auto-categorized or preset
    due_date: datetime | None  # optional deadline
    due_time_specific: bool  # True if user specified a time, not just date
    reminder_at: datetime | None  # when to send reminder
    context: dict  # JSON blob for notes, links, related info
    parent_id: int | None  # for subtasks
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None

class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"

class Priority(Enum):
    P1_URGENT = 1  # Do today, drop everything
    P2_HIGH = 2    # Do soon, this week
    P3_MEDIUM = 3  # Default, do when possible
    P4_LOW = 4     # Someday/maybe
```

### Attachments

Images or files linked to tasks.

```python
class Attachment:
    id: int
    task_id: int | None  # can be standalone
    type: str  # "image", "voice", "document"
    file_path: str  # local path to stored file
    telegram_file_id: str  # for re-fetching if needed
    caption: str | None  # extracted or provided description
    created_at: datetime
```

### Reminders

Scheduled notifications. Can be linked to a task or standalone.

```python
class Reminder:
    id: int
    task_id: int | None  # optional link to task
    message: str  # what to tell the user
    scheduled_for: datetime
    sent: bool
    created_at: datetime
```

### Calendar Events (Cached)

Local cache of Google Calendar events for quick access.

```python
class CalendarEvent:
    id: int
    google_event_id: str
    title: str
    description: str | None
    start: datetime
    end: datetime
    location: str | None
    all_day: bool
    synced_at: datetime
```

### Topics

Predefined + auto-generated task categories.

```python
PRESET_TOPICS = [
    "work",      # Plex, coding, PRs, meetings
    "personal",  # Life admin, relationships
    "errands",   # Shopping, appointments, physical tasks
    "health",    # Doctor, gym, medication
    "travel",    # Trips, bookings, planning
    "finance",   # Bills, accountant, taxes
    "home",      # Apartment, maintenance, dog
]
# Agent can create new topics as needed, stored in a topics table
```

---

## Agent Configuration

### System Prompt

```
You are Enzo's personal assistant, available via Telegram. Your job is to help him manage tasks, remember things, and stay on top of his schedule.

## Personality
- Concise and efficient. Don't over-explain.
- Casual tone, but professional when needed.
- Proactive but not annoying.
- When in doubt, do the sensible thing rather than asking.

## Core Behaviors

### Task Extraction
When Enzo sends a message (text or voice), analyze it for:
1. New tasks to create
2. Status updates on existing tasks
3. Additional context to attach to tasks
4. Requests for information

Extract tasks liberally. If he mentions needing to do something, it's probably a task. Use fuzzy matching to link updates to existing tasks.

### Status Updates
Recognize natural language status changes:
- "done with X" / "finished X" / "X is done" → mark done
- "started X" / "working on X" / "X is WIP" → mark in_progress
- "blocked on X" / "waiting for Y for X" → mark blocked, add context
- "nevermind about X" / "forget X" / "cancel X" → mark cancelled

### Context Accumulation
When Enzo mentions details about a task, append to its context:
- Links (PRs, docs, URLs)
- People involved
- Notes and updates
- Outcomes ("went well", "they said no")

### Fuzzy Matching
Resolve ambiguous references:
- "the accountant thing" → task about accountant
- "that PR" → most recently mentioned PR-related task
- "Teresa" → tasks mentioning Teresa
Use search_tasks tool when uncertain.

### Responses
- Confirm actions briefly: "✓ Marked 'pay accountant' done"
- For multiple extractions: show the list, don't ask for confirmation unless genuinely ambiguous
- For queries: format cleanly, don't over-explain

## Time & Location
- Timezone: America/Sao_Paulo (BRT)
- Current date/time will be provided in each message
- Enzo lives in Curitiba, Brazil

## About Enzo
- Data engineer at Plex (streaming media company)
- Works with: BigQuery, GCP, Kubernetes, Dagster, Python
- Has a Sheltie puppy coming soon
- Travels frequently (Japan, Vietnam trips coming up)
- Enjoys: gaming, photography, cocktails

Use memories to learn more about his life, work, and preferences over time.
```

### Agno Agent Setup

```python
from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.memory.v2 import Memory
from agno.storage.sqlite import SqliteStorage

agent = Agent(
    name="EnzoAssistant",
    model=OpenAIChat(id="gpt-4o"),
    memory=Memory(
        db=SqliteStorage(db_file="assistant.db"),
        create_user_memories=True,
        update_user_memories_after_run=True,
        create_session_summary=True,
    ),
    tools=[
        # Task tools
        add_tasks,
        update_task,
        list_tasks,
        search_tasks,
        get_task_details,
        delete_task,
        
        # Reminder tools
        set_reminder,
        list_reminders,
        cancel_reminder,
        
        # Calendar tools
        get_calendar_events,
        create_calendar_event,
        
        # Utility tools
        get_agenda,
        
        # Memory is handled automatically by Agno
    ],
    instructions=SYSTEM_PROMPT,
    markdown=True,
)
```

---

## Tools Specification

### Task Tools

#### add_tasks

Creates one or more tasks from extracted information.

```python
def add_tasks(
    tasks: list[dict]
) -> str:
    """
    Create multiple tasks at once.
    
    Args:
        tasks: List of task objects, each containing:
            - title (str, required): Short task description
            - priority (int, optional): 1-4, defaults to 3
            - topic (str, optional): Category, auto-inferred if not provided
            - due_date (str, optional): ISO date or natural language ("tomorrow", "friday")
            - due_time (str, optional): Time if specific ("8pm", "14:00")
            - reminder_at (str, optional): When to remind
            - context (dict, optional): Additional info (notes, links, people)
            - parent_id (int, optional): Parent task ID for subtasks
    
    Returns:
        Confirmation message with created task IDs
    
    Example:
        add_tasks([
            {"title": "Pay accountant", "topic": "finance", "priority": 2},
            {"title": "Reply to Teresa on WhatsApp", "topic": "personal"},
            {"title": "Meet Teresa at 8pm", "due_date": "today", "due_time": "20:00", "topic": "personal"}
        ])
    """
```

#### update_task

Modifies an existing task.

```python
def update_task(
    task_id: int = None,
    search_query: str = None,
    status: str = None,
    priority: int = None,
    topic: str = None,
    due_date: str = None,
    reminder_at: str = None,
    add_context: dict = None,
    title: str = None
) -> str:
    """
    Update a task by ID or search query.
    
    Args:
        task_id: Direct task ID if known
        search_query: Fuzzy search to find task (use if ID unknown)
        status: New status (pending, in_progress, done, blocked, cancelled)
        priority: New priority 1-4
        topic: New topic
        due_date: New due date
        reminder_at: Set/update reminder
        add_context: Dict of context to merge (doesn't replace, adds)
        title: Update the title
    
    Returns:
        Confirmation of what was updated
    
    Example:
        update_task(search_query="accountant", status="done")
        update_task(task_id=15, add_context={"note": "PR #743", "link": "https://github.com/..."})
    """
```

#### list_tasks

Retrieves tasks with filtering.

```python
def list_tasks(
    status: str | list[str] = None,
    topic: str = None,
    priority: int | list[int] = None,
    due_date: str = None,  # "today", "overdue", "this_week", "no_date"
    include_done: bool = False,
    limit: int = 20
) -> str:
    """
    List tasks with optional filters.
    
    Args:
        status: Filter by status(es)
        topic: Filter by topic
        priority: Filter by priority level(s)
        due_date: Filter by due date category
        include_done: Include completed tasks (default False)
        limit: Max tasks to return
    
    Returns:
        Formatted list of tasks
    
    Example:
        list_tasks(status="pending", due_date="today")
        list_tasks(topic="work", status=["pending", "in_progress"])
    """
```

#### search_tasks

Fuzzy search across tasks.

```python
def search_tasks(
    query: str,
    include_done: bool = False,
    limit: int = 10
) -> str:
    """
    Search tasks by title, context, or related info.
    
    Uses fuzzy matching to find relevant tasks.
    
    Args:
        query: Search terms
        include_done: Include completed tasks
        limit: Max results
    
    Returns:
        Matching tasks with relevance scores
    
    Example:
        search_tasks("teresa")
        search_tasks("PR brain")
    """
```

#### get_task_details

Get full details of a specific task.

```python
def get_task_details(
    task_id: int = None,
    search_query: str = None
) -> str:
    """
    Get complete details of a task including all context and attachments.
    
    Args:
        task_id: Direct task ID
        search_query: Search to find task
    
    Returns:
        Full task details formatted
    """
```

#### delete_task

Permanently remove a task.

```python
def delete_task(
    task_id: int = None,
    search_query: str = None
) -> str:
    """
    Permanently delete a task (use cancel status for soft delete).
    
    Args:
        task_id: Direct task ID
        search_query: Search to find task
    
    Returns:
        Confirmation
    """
```

### Reminder Tools

#### set_reminder

Schedule a reminder.

```python
def set_reminder(
    message: str,
    scheduled_for: str,
    task_id: int = None,
    task_query: str = None
) -> str:
    """
    Create a reminder.
    
    Args:
        message: What to remind about
        scheduled_for: When to remind (ISO datetime or natural language)
        task_id: Link to specific task (optional)
        task_query: Search to link to task (optional)
    
    Returns:
        Confirmation with reminder ID and scheduled time
    
    Example:
        set_reminder("Time to make ice cream!", "7pm today")
        set_reminder("Check on this", "in 2 hours", task_query="accountant")
    """
```

#### list_reminders

View scheduled reminders.

```python
def list_reminders(
    include_sent: bool = False
) -> str:
    """
    List pending reminders.
    
    Args:
        include_sent: Include already-sent reminders
    
    Returns:
        List of reminders with times
    """
```

#### cancel_reminder

Remove a scheduled reminder.

```python
def cancel_reminder(
    reminder_id: int
) -> str:
    """
    Cancel a pending reminder.
    
    Args:
        reminder_id: Reminder to cancel
    
    Returns:
        Confirmation
    """
```

### Calendar Tools

#### get_calendar_events

Fetch events from Google Calendar.

```python
def get_calendar_events(
    date: str = "today",
    days: int = 1
) -> str:
    """
    Get calendar events.
    
    Args:
        date: Start date ("today", "tomorrow", ISO date)
        days: Number of days to fetch (default 1)
    
    Returns:
        Formatted list of events
    
    Example:
        get_calendar_events()  # today
        get_calendar_events(date="monday", days=5)  # work week
    """
```

#### create_calendar_event

Add event to Google Calendar.

```python
def create_calendar_event(
    title: str,
    start: str,
    end: str = None,
    duration_minutes: int = 60,
    description: str = None,
    location: str = None
) -> str:
    """
    Create a calendar event.
    
    Args:
        title: Event title
        start: Start time (natural language or ISO)
        end: End time (optional, use duration if not provided)
        duration_minutes: Duration if end not specified (default 60)
        description: Event description
        location: Event location
    
    Returns:
        Confirmation with event details
    
    Example:
        create_calendar_event("Meeting with Teresa", "8pm today")
        create_calendar_event("Flight to Vietnam", "October 6 6am", duration_minutes=720)
    """
```

### Utility Tools

#### get_agenda

Combined view of tasks and calendar.

```python
def get_agenda(
    date: str = "today"
) -> str:
    """
    Get combined agenda: calendar events + tasks due + reminders.
    
    Args:
        date: Date to get agenda for (default today)
    
    Returns:
        Formatted agenda with:
        - Calendar events in chronological order
        - Tasks due today
        - Overdue tasks
        - Pending reminders
    
    Example:
        get_agenda()
        get_agenda("tomorrow")
    """
```

---

## Telegram Bot Implementation

### Message Handler Flow

```python
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat_id = message.chat_id
    user_input = None
    attachments = []
    
    # Store chat_id for proactive messages (first interaction)
    store_chat_id(chat_id)
    
    # Handle voice messages
    if message.voice or message.audio:
        file = await (message.voice or message.audio).get_file()
        audio_path = await download_file(file)
        user_input = await transcribe_audio(audio_path)
        attachments.append({"type": "voice", "path": audio_path})
    
    # Handle photos
    if message.photo:
        photo = message.photo[-1]  # highest res
        file = await photo.get_file()
        image_path = await download_file(file)
        attachments.append({"type": "image", "path": image_path})
        caption = message.caption or ""
        # Include image analysis if needed
        image_description = await analyze_image(image_path, caption)
        user_input = (user_input or "") + f"\n[Image attached: {image_description}]"
    
    # Handle text
    if message.text:
        user_input = message.text
    
    # Handle documents
    if message.document:
        file = await message.document.get_file()
        doc_path = await download_file(file)
        attachments.append({
            "type": "document", 
            "path": doc_path,
            "filename": message.document.file_name
        })
        user_input = (user_input or "") + f"\n[Document attached: {message.document.file_name}]"
    
    if not user_input:
        return
    
    # Check for command shortcuts
    if user_input.startswith("/"):
        response = await handle_command(user_input, chat_id)
    else:
        # Run agent
        response = await run_agent(
            user_input=user_input,
            chat_id=chat_id,
            attachments=attachments
        )
    
    await message.reply_text(response, parse_mode="Markdown")
```

### Command Shortcuts

```python
COMMANDS = {
    "/tasks": lambda: list_tasks(status=["pending", "in_progress"]),
    "/t": lambda: list_tasks(status=["pending", "in_progress"]),  # alias
    "/today": lambda: get_agenda("today"),
    "/week": lambda: get_agenda_week(),
    "/done": lambda q: update_task(search_query=q, status="done"),
    "/calendar": lambda: get_calendar_events(days=1),
    "/cal": lambda: get_calendar_events(days=1),  # alias
    "/topics": lambda: list_topics_summary(),
    "/help": lambda: show_help(),
}

async def handle_command(text: str, chat_id: int) -> str:
    parts = text.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else None
    
    if cmd in ["/done", "/d"] and arg:
        return await update_task(search_query=arg, status="done")
    elif cmd in COMMANDS:
        handler = COMMANDS[cmd]
        return await handler() if not arg else await handler(arg)
    else:
        return "Unknown command. Try /help"
```

### Voice Transcription

```python
from openai import OpenAI

client = OpenAI()

async def transcribe_audio(audio_path: str) -> str:
    """Transcribe voice message using Whisper."""
    with open(audio_path, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language="pt"  # Default Portuguese, Whisper auto-detects well
        )
    return transcript.text
```

### Image Analysis

```python
async def analyze_image(image_path: str, user_caption: str = "") -> str:
    """Analyze image using GPT-4o vision for context."""
    import base64
    
    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode()
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": f"Briefly describe this image for task context. User said: '{user_caption}'"},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
            ]
        }],
        max_tokens=150
    )
    return response.choices[0].message.content
```

---

## Proactive Behaviors

### Scheduler Setup

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")

def setup_scheduler(bot):
    # Morning summary at 11:00 AM BRT
    scheduler.add_job(
        send_morning_summary,
        CronTrigger(hour=11, minute=0),
        args=[bot],
        id="morning_summary"
    )
    
    # End of day review at 9:00 PM BRT
    scheduler.add_job(
        send_eod_review,
        CronTrigger(hour=21, minute=0),
        args=[bot],
        id="eod_review"
    )
    
    # Check reminders every minute
    scheduler.add_job(
        check_and_send_reminders,
        CronTrigger(minute="*"),
        args=[bot],
        id="reminder_check"
    )
    
    scheduler.start()
```

### Morning Summary (11:00 AM)

```python
async def send_morning_summary(bot):
    chat_id = get_stored_chat_id()
    if not chat_id:
        return
    
    agenda = await get_agenda("today")
    overdue = await list_tasks(due_date="overdue")
    stale = await get_stale_tasks(days=3)  # pending > 3 days
    
    message_parts = ["☀️ **Good morning!**\n"]
    
    if agenda:
        message_parts.append(f"**Today's agenda:**\n{agenda}\n")
    
    if overdue:
        message_parts.append(f"**Overdue:**\n{overdue}\n")
    
    if stale:
        message_parts.append(f"**Pending for a while:**\n{stale}")
    
    if len(message_parts) == 1:
        message_parts.append("Nothing scheduled today. Enjoy! 🎉")
    
    await bot.send_message(
        chat_id=chat_id,
        text="\n".join(message_parts),
        parse_mode="Markdown"
    )
```

### End of Day Review (9:00 PM)

```python
async def send_eod_review(bot):
    chat_id = get_stored_chat_id()
    if not chat_id:
        return
    
    completed_today = await get_tasks_completed_today()
    still_pending = await list_tasks(due_date="today", status="pending")
    
    message_parts = ["🌙 **End of day review**\n"]
    
    if completed_today:
        count = len(completed_today)
        message_parts.append(f"✅ Completed {count} task(s) today. Nice work!\n")
    
    if still_pending:
        message_parts.append(f"**Still pending from today:**\n{still_pending}")
        message_parts.append("\nWant me to reschedule these for tomorrow?")
    else:
        message_parts.append("All caught up! 🎉")
    
    await bot.send_message(
        chat_id=chat_id,
        text="\n".join(message_parts),
        parse_mode="Markdown"
    )
```

### Reminder Delivery

```python
async def check_and_send_reminders(bot):
    chat_id = get_stored_chat_id()
    if not chat_id:
        return
    
    due_reminders = await get_due_reminders()  # scheduled_for <= now, sent = False
    
    for reminder in due_reminders:
        message = f"⏰ **Reminder:** {reminder.message}"
        
        if reminder.task_id:
            task = await get_task_details(reminder.task_id)
            message += f"\n\n_Related task:_ {task.title}"
        
        await bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode="Markdown"
        )
        
        await mark_reminder_sent(reminder.id)
```

---

## Google Calendar Integration

### Setup

1. Create a Google Cloud project
2. Enable Google Calendar API
3. Create OAuth 2.0 credentials (desktop app)
4. Download `credentials.json`
5. First run will open browser for auth, saves `token.json`

### Implementation

```python
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
import os

SCOPES = ["https://www.googleapis.com/auth/calendar"]

def get_calendar_service():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    
    return build("calendar", "v3", credentials=creds)

async def fetch_calendar_events(start_date: datetime, end_date: datetime) -> list[dict]:
    service = get_calendar_service()
    
    events_result = service.events().list(
        calendarId="primary",
        timeMin=start_date.isoformat() + "Z",
        timeMax=end_date.isoformat() + "Z",
        singleEvents=True,
        orderBy="startTime"
    ).execute()
    
    events = events_result.get("items", [])
    
    return [
        {
            "id": e["id"],
            "title": e.get("summary", "No title"),
            "start": e["start"].get("dateTime", e["start"].get("date")),
            "end": e["end"].get("dateTime", e["end"].get("date")),
            "location": e.get("location"),
            "description": e.get("description"),
        }
        for e in events
    ]

async def create_event(
    title: str,
    start: datetime,
    end: datetime,
    description: str = None,
    location: str = None
) -> dict:
    service = get_calendar_service()
    
    event = {
        "summary": title,
        "start": {"dateTime": start.isoformat(), "timeZone": "America/Sao_Paulo"},
        "end": {"dateTime": end.isoformat(), "timeZone": "America/Sao_Paulo"},
    }
    
    if description:
        event["description"] = description
    if location:
        event["location"] = location
    
    created = service.events().insert(calendarId="primary", body=event).execute()
    
    return {"id": created["id"], "link": created.get("htmlLink")}
```

---

## Memory System (via Agno)

Agno's built-in memory system handles:

1. **User memories** — Facts learned about Enzo (auto-extracted)
2. **Session summaries** — Conversation context carried forward

### What the Agent Should Remember

The agent will automatically build memories like:

- "the-brain is one of Plex's repositories"
- "Teresa is Enzo's girlfriend"
- "Vince is a coworker"
- "FBI service is an internal Plex project"
- "Scott works on dependency management"
- "Enzo prefers mornings for focused work"
- "Enzo is planning a trip to Vietnam in October"

### Memory-Informed Behavior

When Enzo says "check Vince's message about FBI", the agent:

1. Knows Vince is a coworker (memory)
2. Knows FBI is an internal project (memory)
3. Creates task with appropriate topic (work) and context

---

## File Structure

```
enzo-assistant/
├── pyproject.toml
├── README.md
├── .env.example
├── src/
│   ├── __init__.py
│   ├── main.py              # Entry point
│   ├── config.py            # Settings, env vars
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── setup.py         # Agno agent configuration
│   │   ├── prompts.py       # System prompts
│   │   └── tools/
│   │       ├── __init__.py
│   │       ├── tasks.py     # Task CRUD tools
│   │       ├── reminders.py # Reminder tools
│   │       ├── calendar.py  # Google Calendar tools
│   │       └── agenda.py    # Combined views
│   ├── telegram/
│   │   ├── __init__.py
│   │   ├── bot.py           # Bot setup, handlers
│   │   ├── commands.py      # Command shortcuts
│   │   └── media.py         # Voice/image handling
│   ├── integrations/
│   │   ├── __init__.py
│   │   ├── whisper.py       # Audio transcription
│   │   ├── gcal.py          # Google Calendar client
│   │   └── vision.py        # Image analysis
│   ├── scheduler/
│   │   ├── __init__.py
│   │   └── jobs.py          # Scheduled jobs
│   └── db/
│       ├── __init__.py
│       ├── models.py        # SQLAlchemy models
│       ├── database.py      # DB connection
│       └── queries.py       # Common queries
├── data/
│   ├── assistant.db         # SQLite database
│   └── attachments/         # Stored files
└── credentials/
    ├── .gitignore
    ├── credentials.json     # Google OAuth
    └── token.json           # Google token (generated)
```

---

## Environment Variables

```bash
# .env
TELEGRAM_BOT_TOKEN=your-bot-token
OPENAI_API_KEY=your-openai-key

# Optional
GOOGLE_CREDENTIALS_PATH=credentials/credentials.json
DATABASE_URL=sqlite:///data/assistant.db
TIMEZONE=America/Sao_Paulo

# Proactive message times (24h format)
MORNING_SUMMARY_HOUR=11
EOD_REVIEW_HOUR=21
```

---

## Example Interactions

### Natural Task Creation

**User (voice):** "Alright so I need to get back to my accountant and pay them, check Vince's message about the FBI service, reply to Teresa and Amanda on WhatsApp, and make ice cream later"

**Bot:**
```
Got it, added 5 tasks:

• Pay accountant (finance, P2)
• Check Vince's message – FBI service (work)
• Reply to Teresa on WhatsApp (personal)
• Reply to Amanda on WhatsApp (personal)  
• Make ice cream (personal)

Want me to set any reminders?
```

### Status Update

**User:** "done with the accountant, Teresa is WIP"

**Bot:**
```
✓ Marked 'Pay accountant' done
✓ 'Reply to Teresa' → in progress
```

### Context Addition

**User:** "the vince thing was PR #743 https://github.com/plexinc/the-brain/pull/743"

**Bot:**
```
✓ Added to 'Check Vince's message':
  PR #743 – github.com/plexinc/the-brain/pull/743
```

### Quick Query

**User:** `/today`

**Bot:**
```
📅 **Thursday, Oct 5**

**Calendar:**
• 10:00 – Team standup
• 14:00 – 1:1 with manager
• 20:00 – Meet Teresa

**Tasks due:**
• Reply to real estate guy
• Start FBI PRs – metadata filter + custom query

**Pending:**
• Reply to Amanda on WhatsApp
• Ask Solange about dog delivery
• Check Weasy products for pets
• Make ice cream
```

### Reminder

**User:** "remind me about the ice cream at 7"

**Bot:**
```
⏰ Reminder set for 7:00 PM – Make ice cream
```

*At 7:00 PM:*

**Bot:**
```
⏰ **Reminder:** Make ice cream

_Related task:_ Make ice cream
```

---

## Future Enhancements (v2+)

- **Natural language time parsing improvements** — "next Tuesday", "in 2 weeks"
- **Recurring tasks** — "every Monday: review PRs"
- **Task dependencies** — "after X is done, remind me about Y"  
- **Location-based reminders** — "when I'm near the pet store"
- **Weekly review** — Summary of what got done, what carried over
- **Slack integration** — Forward messages to create tasks
- **Email integration** — Forward emails to create tasks
- **GitHub integration** — PR tracking, auto-close tasks on merge
