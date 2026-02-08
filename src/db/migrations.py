"""Simple migration system for SQLite schema changes."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# List of migrations in order. Each is (id, description, function)
# Once a migration is added, NEVER remove or reorder it.
MIGRATIONS: list[tuple[str, str, Callable[[Session], None]]] = []


def _ensure_migrations_table(session: Session) -> None:
    """Create migrations tracking table if it doesn't exist."""
    session.execute(
        text("""
        CREATE TABLE IF NOT EXISTS _migrations (
            id TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
    """)
    )
    session.flush()


def _is_applied(session: Session, migration_id: str) -> bool:
    """Check if a migration has been applied."""
    result = session.execute(text("SELECT 1 FROM _migrations WHERE id = :id"), {"id": migration_id}).fetchone()
    return result is not None


def _mark_applied(session: Session, migration_id: str) -> None:
    """Mark a migration as applied."""
    session.execute(
        text("INSERT INTO _migrations (id, applied_at) VALUES (:id, :applied_at)"),
        {"id": migration_id, "applied_at": datetime.now(UTC).isoformat()},
    )
    session.flush()


def _column_exists(session: Session, table: str, column: str) -> bool:
    """Check if a column exists in a table (SQLite-specific)."""
    result = session.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return any(row[1] == column for row in result)


def run_migrations(session: Session) -> None:
    """Run all pending migrations."""
    _ensure_migrations_table(session)

    for migration_id, description, migrate_fn in MIGRATIONS:
        if _is_applied(session, migration_id):
            continue

        logger.info(f"Running migration {migration_id}: {description}")
        try:
            migrate_fn(session)
            _mark_applied(session, migration_id)
            logger.info(f"Migration {migration_id} completed")
        except Exception as e:
            logger.exception(f"Migration {migration_id} failed: {e}")
            raise


# --- Migration definitions ---


def _001_add_contact_id_to_tasks(session: Session) -> None:
    """Add contact_id column to tasks table."""
    if not _column_exists(session, "tasks", "contact_id"):
        session.execute(text("ALTER TABLE tasks ADD COLUMN contact_id INTEGER REFERENCES contacts(id)"))
        session.flush()


MIGRATIONS.append(
    (
        "001_add_contact_id_to_tasks",
        "Add contact_id foreign key to tasks table",
        _001_add_contact_id_to_tasks,
    )
)


def _002_add_parent_id_to_tasks(session: Session) -> None:
    """Add parent_id column to tasks table (from migrate_add_parent_id.py)."""
    if not _column_exists(session, "tasks", "parent_id"):
        session.execute(text("ALTER TABLE tasks ADD COLUMN parent_id INTEGER REFERENCES tasks(id)"))
        session.flush()


MIGRATIONS.append(
    (
        "002_add_parent_id_to_tasks",
        "Add parent_id self-referencing FK to tasks table",
        _002_add_parent_id_to_tasks,
    )
)


def _003_add_shopping_quantities(session: Session) -> None:
    """Add quantity columns to shopping_items (from migrate_shopping_quantities.py)."""
    if not _column_exists(session, "shopping_items", "quantity_target"):
        session.execute(text("ALTER TABLE shopping_items ADD COLUMN quantity_target INTEGER DEFAULT 1"))
    if not _column_exists(session, "shopping_items", "quantity_purchased"):
        session.execute(text("ALTER TABLE shopping_items ADD COLUMN quantity_purchased INTEGER DEFAULT 0"))
    session.flush()


MIGRATIONS.append(
    (
        "003_add_shopping_quantities",
        "Add quantity_target and quantity_purchased to shopping_items",
        _003_add_shopping_quantities,
    )
)


def _004_add_user_projects(session: Session) -> None:
    """Add user_projects table and FK (from migrate_user_projects.py)."""
    # Check if user_projects table exists
    result = session.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name='user_projects'")
    ).fetchone()
    if not result:
        session.execute(
            text("""
            CREATE TABLE user_projects (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                description TEXT,
                emoji VARCHAR(10) DEFAULT '📁',
                tag_id INTEGER REFERENCES projects(id),
                archived BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        )
    if not _column_exists(session, "tasks", "user_project_id"):
        session.execute(text("ALTER TABLE tasks ADD COLUMN user_project_id INTEGER REFERENCES user_projects(id)"))
    session.flush()


MIGRATIONS.append(
    (
        "004_add_user_projects",
        "Add user_projects table and user_project_id FK to tasks",
        _004_add_user_projects,
    )
)


def _005_add_indexes(session: Session) -> None:
    """Add performance indexes to frequently queried columns."""
    indexes = [
        ("ix_tasks_due_date", "tasks", "due_date"),
        ("ix_tasks_parent_id", "tasks", "parent_id"),
        ("ix_tasks_project_id", "tasks", "project_id"),
        ("ix_tasks_user_project_id", "tasks", "user_project_id"),
        ("ix_tasks_contact_id", "tasks", "contact_id"),
        ("ix_reminders_remind_at", "reminders", "remind_at"),
        ("ix_reminders_delivered", "reminders", "delivered"),
        ("ix_shopping_items_list_id", "shopping_items", "list_id"),
        ("ix_shopping_items_contact_id", "shopping_items", "contact_id"),
        ("ix_calendar_events_start_time", "calendar_events", "start_time"),
        ("ix_user_projects_archived", "user_projects", "archived"),
    ]
    for idx_name, table, column in indexes:
        session.execute(text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({column})"))
    session.flush()


MIGRATIONS.append(
    (
        "005_add_indexes",
        "Add performance indexes to frequently queried columns",
        _005_add_indexes,
    )
)


def _006_add_user_profile(session: Session) -> None:
    """Add user_profiles table."""
    result = session.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name='user_profiles'")
    ).fetchone()
    if not result:
        session.execute(
            text("""
            CREATE TABLE user_profiles (
                id INTEGER PRIMARY KEY,
                display_name VARCHAR(100),
                city VARCHAR(100),
                latitude FLOAT,
                longitude FLOAT,
                timezone_str VARCHAR(50),
                work_start_hour INTEGER,
                work_end_hour INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        )
    session.flush()


MIGRATIONS.append(
    (
        "006_add_user_profile",
        "Add user_profiles table",
        _006_add_user_profile,
    )
)


def _007_add_recurring_tasks(session: Session) -> None:
    """Add recurrence columns to tasks table."""
    if not _column_exists(session, "tasks", "recurrence_rule"):
        session.execute(text("ALTER TABLE tasks ADD COLUMN recurrence_rule VARCHAR(255)"))
    if not _column_exists(session, "tasks", "recurrence_source_id"):
        session.execute(text("ALTER TABLE tasks ADD COLUMN recurrence_source_id INTEGER REFERENCES tasks(id)"))
    session.flush()


MIGRATIONS.append(
    (
        "007_add_recurring_tasks",
        "Add recurrence_rule and recurrence_source_id to tasks",
        _007_add_recurring_tasks,
    )
)


def _008_add_bookmarks(session: Session) -> None:
    """Add bookmarks table."""
    result = session.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='bookmarks'")).fetchone()
    if not result:
        session.execute(
            text("""
            CREATE TABLE bookmarks (
                id INTEGER PRIMARY KEY,
                url VARCHAR(2048) UNIQUE NOT NULL,
                title VARCHAR(500),
                description TEXT,
                domain VARCHAR(255),
                tags VARCHAR(500),
                read BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        )
        session.execute(text("CREATE INDEX IF NOT EXISTS ix_bookmarks_read ON bookmarks (read)"))
    session.flush()


MIGRATIONS.append(
    (
        "008_add_bookmarks",
        "Add bookmarks table",
        _008_add_bookmarks,
    )
)


def _009_add_mood_logs(session: Session) -> None:
    """Add mood_logs table."""
    result = session.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='mood_logs'")).fetchone()
    if not result:
        session.execute(
            text("""
            CREATE TABLE mood_logs (
                id INTEGER PRIMARY KEY,
                date DATETIME UNIQUE NOT NULL,
                score INTEGER NOT NULL,
                note TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        )
        session.execute(text("CREATE INDEX IF NOT EXISTS ix_mood_logs_date ON mood_logs (date)"))
    session.flush()


MIGRATIONS.append(
    (
        "009_add_mood_logs",
        "Add mood_logs table",
        _009_add_mood_logs,
    )
)
