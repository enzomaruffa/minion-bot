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
