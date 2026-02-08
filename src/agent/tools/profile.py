from src.db import session_scope
from src.db.queries import get_user_profile, upsert_user_profile
from src.integrations.weather import fetch_weather, format_weather


def update_profile(
    name: str | None = None,
    city: str | None = None,
    timezone: str | None = None,
    work_start_hour: int | None = None,
    work_end_hour: int | None = None,
) -> str:
    """Update the user profile with personal info.

    Args:
        name: Display name.
        city: City name (will be geocoded to lat/lon automatically).
        timezone: Timezone string like "America/Sao_Paulo".
        work_start_hour: Work day start hour (0-23, e.g. 9).
        work_end_hour: Work day end hour (0-23, e.g. 18).

    Returns:
        Confirmation message with updated profile info.
    """
    fields: dict = {}
    if name is not None:
        fields["display_name"] = name
    if timezone is not None:
        fields["timezone_str"] = timezone
    if work_start_hour is not None:
        fields["work_start_hour"] = work_start_hour
    if work_end_hour is not None:
        fields["work_end_hour"] = work_end_hour

    # Geocode city if provided
    if city is not None:
        fields["city"] = city
        try:
            from geopy.geocoders import Nominatim

            geolocator = Nominatim(user_agent="minion-bot")
            location = geolocator.geocode(city)
            if location:
                fields["latitude"] = location.latitude
                fields["longitude"] = location.longitude
        except Exception:
            pass  # Geocoding failed, save city name without coords

    with session_scope() as session:
        profile = upsert_user_profile(session, **fields)

        parts = ["✓ <b>Profile updated</b>"]
        if profile.display_name:
            parts.append(f"• Name: {profile.display_name}")
        if profile.city:
            parts.append(f"• City: {profile.city}")
        if profile.latitude and profile.longitude:
            parts.append(f"• Coords: {profile.latitude:.2f}, {profile.longitude:.2f}")
        if profile.timezone_str:
            parts.append(f"• Timezone: {profile.timezone_str}")
        if profile.work_start_hour is not None and profile.work_end_hour is not None:
            parts.append(f"• Work hours: {profile.work_start_hour}:00–{profile.work_end_hour}:00")

        return "\n".join(parts)


def show_profile() -> str:
    """Show the current user profile.

    Returns:
        Formatted profile info or message if not set up yet.
    """
    with session_scope() as session:
        profile = get_user_profile(session)

        if not profile:
            return "<i>No profile set up yet. Tell me your name, city, or work hours to get started.</i>"

        parts = ["<b>👤 Profile</b>"]
        if profile.display_name:
            parts.append(f"• Name: {profile.display_name}")
        if profile.city:
            parts.append(f"• City: {profile.city}")
        if profile.latitude and profile.longitude:
            parts.append(f"• Coords: {profile.latitude:.2f}, {profile.longitude:.2f}")
        if profile.timezone_str:
            parts.append(f"• Timezone: {profile.timezone_str}")
        if profile.work_start_hour is not None:
            end = profile.work_end_hour or 18
            parts.append(f"• Work hours: {profile.work_start_hour}:00–{end}:00")

        return "\n".join(parts)


def get_weather() -> str:
    """Get current weather for the user's location.

    Returns:
        Formatted weather info or error if location not set.
    """
    with session_scope() as session:
        profile = get_user_profile(session)

        if not profile or not profile.latitude or not profile.longitude:
            return "No location set. Use update_profile with a city name first."

        data = fetch_weather(profile.latitude, profile.longitude)
        if not data:
            return "Could not fetch weather data."

        city = profile.city or "your location"
        return f"{format_weather(data)} | {city}"
