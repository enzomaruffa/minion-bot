"""Open-Meteo weather integration (free, no API key)."""

import logging

import httpx

logger = logging.getLogger(__name__)

# WMO Weather Code → (emoji, description)
_WMO_CODES = {
    0: ("☀️", "Clear sky"),
    1: ("🌤️", "Mainly clear"),
    2: ("⛅", "Partly cloudy"),
    3: ("☁️", "Overcast"),
    45: ("🌫️", "Fog"),
    48: ("🌫️", "Rime fog"),
    51: ("🌦️", "Light drizzle"),
    53: ("🌦️", "Drizzle"),
    55: ("🌦️", "Dense drizzle"),
    61: ("🌧️", "Light rain"),
    63: ("🌧️", "Rain"),
    65: ("🌧️", "Heavy rain"),
    71: ("🌨️", "Light snow"),
    73: ("🌨️", "Snow"),
    75: ("🌨️", "Heavy snow"),
    80: ("🌧️", "Light showers"),
    81: ("🌧️", "Showers"),
    82: ("🌧️", "Heavy showers"),
    95: ("⛈️", "Thunderstorm"),
    96: ("⛈️", "Thunderstorm + hail"),
    99: ("⛈️", "Thunderstorm + heavy hail"),
}


def fetch_weather(lat: float, lon: float) -> dict | None:
    """Fetch current weather from Open-Meteo API."""
    try:
        resp = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,weather_code,relative_humidity_2m,wind_speed_10m",
                "timezone": "auto",
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning(f"Weather fetch failed: {e}")
        return None


def format_weather(data: dict) -> str:
    """Format weather data as a readable string."""
    current = data.get("current", {})
    code = current.get("weather_code", -1)
    temp = current.get("temperature_2m")
    humidity = current.get("relative_humidity_2m")
    wind = current.get("wind_speed_10m")

    emoji, desc = _WMO_CODES.get(code, ("🌡️", "Unknown"))
    parts = [f"{emoji} {temp}°C, {desc}"]
    if humidity is not None:
        parts.append(f"💧 {humidity}%")
    if wind is not None:
        parts.append(f"💨 {wind} km/h")

    return " | ".join(parts)
