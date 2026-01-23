#!/usr/bin/env python3
"""Migration 001: Add projects support.

Run with: uv run python scripts/migrate_001_projects.py
"""
import sqlite3
from pathlib import Path

# Default database path
DB_PATH = Path("data/minion.db")

DEFAULT_PROJECTS = [
    ("Work", "💼"),
    ("Personal", "🏠"),
    ("Health", "🏃"),
    ("Finance", "💰"),
    ("Social", "👥"),
    ("Learning", "📚"),
]


def migrate(db_path: Path = DB_PATH) -> None:
    if not db_path.exists():
        print(f"Database {db_path} does not exist. Nothing to migrate.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if projects table already exists
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='projects'"
    )
    if cursor.fetchone():
        print("Projects table already exists. Skipping migration.")
        conn.close()
        return

    print("Creating projects table...")
    cursor.execute("""
        CREATE TABLE projects (
            id INTEGER PRIMARY KEY,
            name VARCHAR(100) UNIQUE NOT NULL,
            emoji VARCHAR(10) NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    print("Seeding default projects...")
    cursor.executemany(
        "INSERT INTO projects (name, emoji) VALUES (?, ?)",
        DEFAULT_PROJECTS,
    )

    print("Adding project_id column to tasks...")
    cursor.execute("ALTER TABLE tasks ADD COLUMN project_id INTEGER REFERENCES projects(id)")

    conn.commit()
    conn.close()
    print("Migration complete!")


if __name__ == "__main__":
    migrate()
