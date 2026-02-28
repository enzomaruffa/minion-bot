# MINION - Personal Assistant Bot

Single-user personal assistant powered by the Claude Agent SDK via LiteLLM proxy (model-agnostic). Manages tasks, reminders, shopping lists, contacts/birthdays, calendar events, and Silverbullet notes. Accessible via Telegram bot and web dashboard (HTMX). Runs a FastAPI server alongside the optional Telegram polling loop. APScheduler handles proactive behaviors (morning summary, reminders, birthday nudges, calendar sync, heartbeat).

## Tech Stack
- Python 3.11+ with `uv` for package management
- Claude Agent SDK (`claude-agent-sdk`) — wraps Claude Code CLI, tools via in-process MCP server
- LiteLLM proxy — Anthropic-compatible API translating to Gemini/GPT backends
- SQLite via SQLAlchemy (declarative models)
- python-telegram-bot for Telegram integration (optional — web-only mode supported)
- FastAPI + Jinja2 + HTMX + Pico CSS for web dashboard
- APScheduler for proactive behaviors
- Google Calendar API + OAuth server
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
│   ├── notifications.py      # Notification dispatcher (decouples scheduler from Telegram)
│   ├── utils.py              # Shared helpers (date parsing, birthday calc)
│   ├── agent/
│   │   ├── sdk_agent.py      # Claude Agent SDK client, chat(), chat_stream(), system prompt
│   │   ├── sdk_tools/        # SDK tool wrappers: make_sdk_tool(), auto-schema, MAIN_TOOLS/HEARTBEAT_TOOLS
│   │   └── tools/            # ~76 tool implementation functions (tasks, shopping, contacts, calendar, notes, profile, bookmarks, mood, scheduling, memory)
│   ├── telegram/
│   │   ├── bot.py            # Message/voice/photo handlers, send_message, error notifications
│   │   └── commands.py       # Slash command handlers (/tasks, /today, /auth, etc.)
│   ├── integrations/
│   │   ├── calendar.py       # Google Calendar: auth, fetch, sync, CRUD
│   │   ├── weather.py        # Open-Meteo weather API (free, no key)
│   │   ├── silverbullet.py   # Filesystem-based notes: read, write, search
│   │   ├── vision.py         # GPT image analysis
│   │   └── voice.py          # Whisper transcription
│   ├── scheduler/
│   │   └── jobs.py           # Cron/interval jobs: agenda, reminders, calendar sync
│   ├── db/
│   │   ├── __init__.py       # session_scope, init_database
│   │   ├── models.py         # SQLAlchemy models (Task, Reminder, Contact, UserProfile, Bookmark, MoodLog, WebSession, etc.)
│   │   ├── migrations.py     # Consolidated migration system (10 migrations)
│   │   └── queries.py        # All DB query functions
│   └── web/
│       ├── server.py         # FastAPI app: mounts routers, OAuth, templates
│       ├── auth.py           # Telegram code-based login, session management
│       ├── api.py            # REST API endpoints (/api/v1/*)
│       ├── views.py          # HTMX dashboard page routes (/app/*)
│       ├── serializers.py    # Pydantic models for API request/response
│       └── templates/        # Jinja2 templates (base, login, dashboard, tasks, etc.)
├── tasks/                    # Task files for development workflow
├── scripts/                  # One-off scripts (calendar auth)
├── data/                     # SQLite databases
└── credentials/              # Google OAuth credentials
```

## Task Workflow

- Use Beads - command is `bd`
- Persist learnings in LEARNINGS.md

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
Model names live in `settings.agent_model`, `settings.vision_model` (default to `claude-sonnet-4-5`/`gpt-5.2`). Override via `AGENT_MODEL`, `VISION_MODEL` env vars. LiteLLM proxy translates Anthropic model names to actual provider models. Never hardcode model strings in agent/vision code.

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

### Recurring tasks: RRULE-based
Tasks with `recurrence_rule` (iCalendar RRULE format) auto-generate next instances when completed. Scheduler job runs every 5 min via `dateutil.rrule`. New instances link back via `recurrence_source_id`.

### User profile: single-row pattern
`UserProfile` is single-row (one user bot). `get_user_profile(session)` returns it, `upsert_user_profile(session, **fields)` creates or updates. Used by weather (lat/lon), smart scheduling (work hours), and `/me` command.

### Weather: Open-Meteo API
`src/integrations/weather.py` — free, no API key. Injected into agenda via `get_agenda()` when profile has lat/lon.

### Notification dispatcher
`src/notifications.py` — `register_handler(fn)` / `notify(message, parse_mode)`. Scheduler jobs call `notify()` instead of importing `send_message` directly. Telegram `send_message` is registered as a handler on startup. This enables web-only mode (no Telegram bot token).

### Web dashboard auth: Telegram code flow
Login: enter Telegram user ID -> receive 6-digit code via Telegram -> verify in browser -> `WebSession` row created -> httponly cookie set for 30 days. `get_current_user` FastAPI dependency reads cookie, checks DB session.

### Web-only mode
When `TELEGRAM_BOT_TOKEN` is not set, the bot starts in web-only mode: no Telegram polling, scheduler still runs, web dashboard fully functional.

### Format-aware agent
`SYSTEM_PROMPT_BASE` + `FORMAT_HINTS[format]`. Telegram uses HTML formatting, web chat uses Markdown. `chat(message, format_hint="telegram"|"web")`.

### Google OAuth moved to /oauth/*
OAuth routes moved from `/auth/start` to `/oauth/start`, `/auth/callback` to `/oauth/callback`. Legacy redirects in place for backwards compatibility.

### Agent architecture: Claude Agent SDK + LiteLLM
- `src/agent/sdk_agent.py` — creates `ClaudeSDKClient`, passes `ANTHROPIC_BASE_URL`/`ANTHROPIC_API_KEY` env vars pointing to LiteLLM proxy
- Tools are plain Python functions in `src/agent/tools/`, wrapped via `make_sdk_tool()` in `src/agent/sdk_tools/__init__.py` and served as in-process MCP server
- Format hints (Telegram HTML vs web Markdown) are injected into the system prompt, eliminating the old double-LLM-call formatter
- Streaming: `chat_stream()` yields text chunks; Telegram uses placeholder+edit pattern, web uses SSE
- Session persistence via `session_id` passed as `resume=` on subsequent calls
- Heartbeat uses a separate short-lived `ClaudeSDKClient` with a subset of tools (`HEARTBEAT_TOOLS`)
- Explicit memory: `AgentMemory` model (save/recall/list/forget) — agent is instructed to save preferences and facts

### Scheduler jobs
Registered in `src/main.py:register_jobs()`. Current jobs:
- Morning summary (10:30), EOD review (21:00 + mood prompt)
- Heartbeat engine (configurable interval, default 60 min)
- Reminder delivery (every 1 min), Calendar sync (every 30 min), Recurring tasks generation (every 5 min)
- Web session cleanup (daily 3 AM)

# Agent Instructions

This project uses **bd** (beads) for issue tracking. Run `bd onboard` to get started.

## Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --status in_progress  # Claim work
bd close <id>         # Complete work
bd sync               # Sync with git
```

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd sync
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds

