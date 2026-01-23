# MINION - Telegram Personal Assistant Bot

## Tech Stack
- Python 3.11+ with `uv` for package management
- Agno agent framework with GPT-4o
- SQLite via SQLAlchemy
- python-telegram-bot for Telegram integration
- APScheduler for proactive behaviors
- Google Calendar API integration

## Task Workflow

Tasks live in the `tasks/` folder:
- `tasks/todo/` - Pending tasks numbered like `1-task-name.md`
- `tasks/done/` - Completed tasks (moved from todo)

### Task File Format
```markdown
# Task Title

Brief overview of what needs to be done.

## Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2
```

### Workflow
1. Every decision/feature becomes a task file
2. Each task gets its own branch: `task/1-task-name`
3. Work on the branch with many small commits
4. Move task to `done/` when complete

## Keeping CLAUDE.md Updated

This file should be kept up-to-date with meaningful project decisions. When we make architectural choices, adopt patterns, or establish conventions, document them here for future context.

## Commands
- Use `uv` for all Python operations (never raw `python`)
- Use `git pr` alias for PRs (never `gh` CLI)
- Prefer one-liner conventional commits
- NEVER use `git merge` - always squash & rebase

## Project Structure
```
minion/
├── src/
│   ├── main.py
│   ├── config.py
│   ├── agent/
│   ├── telegram/
│   ├── integrations/
│   ├── scheduler/
│   └── db/
├── tasks/
│   ├── todo/
│   └── done/
├── data/
└── credentials/
```
