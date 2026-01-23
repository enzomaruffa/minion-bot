"""Simple migration system for SQLite schema changes."""

import logging
from datetime import datetime
from typing import Callable

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# List of migrations in order. Each is (id, description, function)
# Once a migration is added, NEVER remove or reorder it.
MIGRATIONS: list[tuple[str, str, Callable[[Session], None]]] = []


def _ensure_migrations_table(session: Session) -> None:
    """Create migrations tracking table if it doesn't exist."""
    session.execute(text("""
        CREATE TABLE IF NOT EXISTS _migrations (
            id TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
    """))
    session.commit()


def _is_applied(session: Session, migration_id: str) -> bool:
    """Check if a migration has been applied."""
    result = session.execute(
        text("SELECT 1 FROM _migrations WHERE id = :id"),
        {"id": migration_id}
    ).fetchone()
    return result is not None


def _mark_applied(session: Session, migration_id: str) -> None:
    """Mark a migration as applied."""
    session.execute(
        text("INSERT INTO _migrations (id, applied_at) VALUES (:id, :applied_at)"),
        {"id": migration_id, "applied_at": datetime.utcnow().isoformat()}
    )
    session.commit()


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
        session.execute(text(
            "ALTER TABLE tasks ADD COLUMN contact_id INTEGER REFERENCES contacts(id)"
        ))
        session.commit()


MIGRATIONS.append((
    "001_add_contact_id_to_tasks",
    "Add contact_id foreign key to tasks table",
    _001_add_contact_id_to_tasks,
))
