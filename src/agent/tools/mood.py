from datetime import datetime

from src.config import settings
from src.db import session_scope
from src.db.queries import get_mood_history, get_mood_stats
from src.db.queries import log_mood as db_log_mood

_MOOD_EMOJI = {1: "😞", 2: "😕", 3: "😐", 4: "🙂", 5: "😄"}


def log_mood(score: int, note: str | None = None) -> str:
    """Log today's mood on a 1-5 scale.

    Args:
        score: Mood score from 1 (terrible) to 5 (great).
        note: Optional note about why you feel this way.

    Returns:
        Confirmation message.
    """
    if not 1 <= score <= 5:
        return "Score must be between 1 and 5."

    today = datetime.now(settings.timezone).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)

    with session_scope() as session:
        db_log_mood(session, date=today, score=score, note=note)
        emoji = _MOOD_EMOJI.get(score, "")
        note_info = f"\n<i>{note}</i>" if note else ""
        return f"✓ Mood logged: {emoji} {score}/5{note_info}"


def show_mood_history(days: int = 14) -> str:
    """Show mood history for the last N days.

    Args:
        days: Number of days to look back (default 14).

    Returns:
        Formatted mood history with emoji scale.
    """
    with session_scope() as session:
        logs = get_mood_history(session, days=days)

        if not logs:
            return "<i>No mood data yet. Rate your day 1-5 to start tracking!</i>"

        lines = [f"<b>📊 Mood ({days} days)</b>"]
        for m in logs:
            emoji = _MOOD_EMOJI.get(m.score, "")
            bar = "█" * m.score + "░" * (5 - m.score)
            note = f" — <i>{m.note}</i>" if m.note else ""
            lines.append(f"{m.date.strftime('%b %d')} {emoji} {bar}{note}")

        return "\n".join(lines)


def mood_summary(days: int = 30) -> str:
    """Get mood statistics and trends.

    Args:
        days: Number of days to analyze (default 30).

    Returns:
        Mood statistics including average, trend, and best/worst days.
    """
    with session_scope() as session:
        stats = get_mood_stats(session, days=days)

        if stats["count"] == 0:
            return "<i>No mood data yet.</i>"

        avg_emoji = _MOOD_EMOJI.get(round(stats["avg"]), "")
        trend_icon = {"improving": "📈", "declining": "📉", "stable": "➡️"}.get(stats["trend"], "❓")

        lines = [
            f"<b>📊 Mood Summary ({days} days)</b>",
            f"• Entries: {stats['count']}",
            f"• Average: {avg_emoji} {stats['avg']}/5",
            f"• Trend: {trend_icon} {stats['trend']}",
        ]

        if "best_day" in stats:
            best_emoji = _MOOD_EMOJI.get(stats["best_score"], "")
            worst_emoji = _MOOD_EMOJI.get(stats["worst_score"], "")
            lines.append(f"• Best: {stats['best_day']} {best_emoji}")
            lines.append(f"• Worst: {stats['worst_day']} {worst_emoji}")

        return "\n".join(lines)
