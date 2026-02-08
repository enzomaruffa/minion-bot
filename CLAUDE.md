# MINION - Telegram Personal Assistant Bot

Single-user Telegram bot powered by an Agno agent (OpenAI GPT). Manages tasks, reminders, shopping lists, contacts/birthdays, calendar events, and Silverbullet notes. Runs a FastAPI OAuth server alongside the Telegram polling loop. APScheduler handles proactive behaviors (morning summary, reminders, birthday nudges, calendar sync).

## Tech Stack
- Python 3.11+ with `uv` for package management
- Agno agent framework with configurable OpenAI models
- SQLite via SQLAlchemy (declarative models)
- python-telegram-bot for Telegram integration
- APScheduler for proactive behaviors
- Google Calendar API + FastAPI OAuth server
- Silverbullet notes via filesystem mount

## Commands
- Use `uv` for all Python operations (never raw `python`)
- Use `git pr` alias for PRs (never `gh` CLI)
- Prefer one-liner conventional commits
- NEVER use `git merge` - always squash & rebase
- Start bot: `pushd /Users/enzolitos/Diversos/minion && uv run python -m src.main`

## Project Structure
```
minion/
├── src/
│   ├── main.py              # Entrypoint: DB init, scheduler, web server, Telegram polling
│   ├── config.py             # Settings dataclass from env vars
│   ├── utils.py              # Shared helpers (date parsing, birthday calc)
│   ├── agent/
│   │   ├── agent.py          # Agent singleton, system prompt, tool_logger_hook
│   │   └── tools/            # ~40 tool functions (tasks, shopping, contacts, calendar, notes)
│   ├── telegram/
│   │   ├── bot.py            # Message/voice/photo handlers, send_message, error notifications
│   │   └── commands.py       # Slash command handlers (/tasks, /today, /auth, etc.)
│   ├── integrations/
│   │   ├── calendar.py       # Google Calendar: auth, fetch, sync, CRUD
│   │   ├── silverbullet.py   # Filesystem-based notes: read, write, search
│   │   ├── vision.py         # GPT image analysis
│   │   └── voice.py          # Whisper transcription
│   ├── scheduler/
│   │   └── jobs.py           # Cron/interval jobs: agenda, reminders, calendar sync
│   ├── db/
│   │   ├── __init__.py       # session_scope, init_database
│   │   ├── models.py         # SQLAlchemy models (Task, Reminder, Contact, etc.)
│   │   ├── migrations.py     # Consolidated migration system (5 migrations)
│   │   └── queries.py        # All DB query functions
│   └── web/
│       └── server.py         # FastAPI OAuth callback server
├── tasks/                    # Task files for development workflow
├── scripts/                  # One-off scripts (calendar auth)
├── data/                     # SQLite databases
└── credentials/              # Google OAuth credentials
```

## Task Workflow

Tasks live in the `tasks/` folder:
- `tasks/todo/` - Pending tasks numbered like `1-task-name.md`
- `tasks/done/` - Completed tasks (moved from todo)

1. Every decision/feature becomes a task file
2. Each task gets its own branch: `task/1-task-name`
3. Work on the branch with many small commits
4. Move task to `done/` when complete

---

## Architecture Decisions & Patterns

### Database Sessions: session_scope owns the transaction
`session_scope()` commits on success and rolls back on error. All query functions use `session.flush()` — never `session.commit()`. This means:
- Every `with session_scope() as session:` block is one atomic transaction
- Query functions are composable — you can call several in one scope
- Never add `session.commit()` to a query function

### Authorization: @require_auth decorator
All Telegram handlers use the `@require_auth` decorator from `src/telegram/commands.py`. Never duplicate the `is_authorized()` check inline. The decorator returns early with "Not authorized." if the user doesn't match `settings.telegram_user_id`.

### AI Models: configurable via settings
Model names live in `settings.agent_model`, `settings.memory_model`, `settings.vision_model` (default to `gpt-5.2`/`gpt-5-mini`/`gpt-5.2`). Override via `AGENT_MODEL`, `MEMORY_MODEL`, `VISION_MODEL` env vars. Never hardcode model strings in agent/vision code.

### Datetimes: always timezone-aware
Use `datetime.now(timezone.utc)` everywhere. Model defaults use `default=lambda: datetime.now(timezone.utc)`. Never use `datetime.utcnow()` (deprecated).

### OAuth: unpredictable state tokens
The OAuth flow generates `secrets.token_urlsafe(32)` for state, stored as `(flow, user_id, timestamp)` tuples. Flows expire after 10 minutes. Never use the Telegram user ID as the state parameter.

### HTML formatting in tool responses
The bot uses `parse_mode="HTML"`. Tool return strings should use `<code>#12</code>` and `<i>title</i>`, never Markdown backticks or underscores.

### Migrations: single consolidated system
All migrations live in `src/db/migrations.py` as `(id, description, fn)` tuples appended to `MIGRATIONS`. Each migration function must be idempotent (check before acting). Never create standalone migration scripts in `scripts/`.

### Silverbullet helpers
- `_atomic_write(path, content)` — write-via-tempfile for crash safety
- `_safe_resolve(space, subpath)` — path traversal protection
Use these instead of inline implementations.

### Birthday calculation: shared utility
Use `days_until_birthday(birthday, today)` and `format_birthday_proximity(days)` from `src/utils.py`. Four callsites use these — never reimplement the year-rollover logic.

### Query patterns
- Use `_task_query()` / `_shopping_item_query()` base helpers for eager loading
- For subtask trees: load all tasks in one query, build tree with `_build_task_tree()`, format recursively — never N+1 `get_subtasks()` per task
- Bulk operations: use `update(Model).where(Model.id.in_(ids))` or `delete(Model).where(...)` — never loop-per-row

### Error notifications: bounded dict
`_last_error_notification` in `bot.py` is capped at 100 entries. If it exceeds that, it clears entirely. This prevents unbounded growth from diverse tool error keys.

### Scheduler jobs
Registered in `src/main.py:register_jobs()`. Current jobs:
- Morning summary (10:30), EOD review (21:00), Proactive intelligence (17:00)
- Reminder delivery (every 1 min), Calendar sync (every 30 min)
