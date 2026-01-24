#!/usr/bin/env python3
"""Migration script to add user_projects table and user_project_id to tasks."""

import sqlite3
from pathlib import Path

# Database path
DB_PATH = Path(__file__).parent.parent / "data" / "minion.db"


def migrate():
    """Run the migration."""
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if user_projects table exists
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='user_projects'"
    )
    if cursor.fetchone():
        print("user_projects table already exists")
    else:
        print("Creating user_projects table...")
        cursor.execute("""
            CREATE TABLE user_projects (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                description TEXT,
                emoji VARCHAR(10) DEFAULT '📁',
                tag_id INTEGER REFERENCES projects(id),
                archived BOOLEAN DEFAULT FALSE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("Created user_projects table")

    # Check if tasks table has user_project_id column
    cursor.execute("PRAGMA table_info(tasks)")
    columns = [col[1] for col in cursor.fetchall()]

    if "user_project_id" in columns:
        print("user_project_id column already exists in tasks")
    else:
        print("Adding user_project_id column to tasks...")
        cursor.execute("""
            ALTER TABLE tasks ADD COLUMN user_project_id INTEGER REFERENCES user_projects(id)
        """)
        print("Added user_project_id column")

    conn.commit()
    conn.close()
    print("Migration complete!")


if __name__ == "__main__":
    migrate()
