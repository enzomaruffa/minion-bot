"""Migration: Add parent_id column to tasks table for hierarchy support."""

import sqlite3
from pathlib import Path


def migrate(db_path: Path) -> None:
    """Add parent_id column to tasks table if it doesn't exist."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if column already exists
    cursor.execute("PRAGMA table_info(tasks)")
    columns = [row[1] for row in cursor.fetchall()]

    if "parent_id" not in columns:
        print("Adding parent_id column to tasks table...")
        cursor.execute(
            "ALTER TABLE tasks ADD COLUMN parent_id INTEGER REFERENCES tasks(id)"
        )
        conn.commit()
        print("Migration complete.")
    else:
        print("Column parent_id already exists, skipping.")

    conn.close()


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from src.config import settings

    migrate(settings.database_path)
