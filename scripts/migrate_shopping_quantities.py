#!/usr/bin/env python3
"""Migration: Add quantity tracking to shopping items.

Run with: uv run python scripts/migrate_shopping_quantities.py

"""
import sqlite3
from pathlib import Path

# Default database path
DB_PATH = Path("data/minion.db")


def migrate(db_path: Path = DB_PATH) -> None:
    if not db_path.exists():
        print(f"Database {db_path} does not exist. Nothing to migrate.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if quantity_target column already exists
    cursor.execute("PRAGMA table_info(shopping_items)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if "quantity_target" in columns:
        print("Quantity columns already exist. Skipping migration.")
        conn.close()
        return

    print("Adding quantity_target column...")
    cursor.execute(
        "ALTER TABLE shopping_items ADD COLUMN quantity_target INTEGER DEFAULT 1"
    )

    print("Adding quantity_purchased column...")
    cursor.execute(
        "ALTER TABLE shopping_items ADD COLUMN quantity_purchased INTEGER DEFAULT 0"
    )

    conn.commit()
    conn.close()
    print("Migration complete!")


if __name__ == "__main__":
    migrate()
