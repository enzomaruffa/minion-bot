from datetime import datetime
from typing import Optional

import dateparser

from src.config import settings


def parse_date(text: str) -> Optional[datetime]:
    """Parse natural language date/time strings.
    
    Supports formats like:
    - "tomorrow at 3pm"
    - "next Monday"
    - "in 2 hours"
    - "2024-01-15T14:30:00" (ISO format fallback)
    
    Args:
        text: Natural language date string or ISO format
        
    Returns:
        Parsed datetime or None if parsing fails
    """
    if not text:
        return None
    
    # Try ISO format first (fast path)
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    
    # Use dateparser for natural language
    parsed = dateparser.parse(
        text,
        settings={
            "TIMEZONE": str(settings.timezone),
            "RETURN_AS_TIMEZONE_AWARE": False,
            "PREFER_DATES_FROM": "future",
            "PREFER_DAY_OF_MONTH": "first",
        }
    )
    
    return parsed


def format_date(dt: Optional[datetime], include_time: bool = False) -> str:
    """Format a datetime consistently across the application.
    
    Args:
        dt: The datetime to format
        include_time: If True, include time in the output
        
    Returns:
        Formatted date string like "Jan 15" or "Jan 15 14:30"
    """
    if not dt:
        return ""
    
    if include_time:
        return dt.strftime("%b %d %H:%M")
    return dt.strftime("%b %d")
