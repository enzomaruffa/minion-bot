#!/usr/bin/env python3
"""Authorize Google Calendar access (headless mode).

Run with: uv run python scripts/authorize_calendar.py

This will print a URL to visit. Open it in your browser, authorize,
then paste the code back here.
"""
from src.integrations.calendar import get_credentials

if __name__ == "__main__":
    print("Starting Google Calendar authorization...")
    print("A URL will be printed below. Open it in your browser and authorize.\n")
    
    creds = get_credentials(headless=True)
    
    if creds:
        print("\n✓ Authorization successful! Token saved.")
    else:
        print("\n✗ Authorization failed. Check credentials/credentials.json exists.")
