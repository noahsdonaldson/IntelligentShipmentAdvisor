"""
infrastructure/weather_api.py
==============================
Mock FastAPI — Weather Domain
Returns temperature, condition, and risk level by city.

Start with:
    uvicorn infrastructure.weather_api:app --port 8002 --reload

Edge cases deliberately baked in:
  • Denver    → risk_level = 'high'  (blizzard — aligns with CARR-B disruption)
  • Seattle   → risk_level = 'high'  (coastal storm)
  • Chicago   → risk_level = 'medium' (heavy rain)
  • All others → risk_level = 'low'
"""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(
    title="Weather Mock API",
    description="Mock weather data for the API-vs-MCP study.",
    version="1.0.0",
)

# ──────────────────────────────────────────────────────────────────────────────
# Pydantic Models
# ──────────────────────────────────────────────────────────────────────────────

class WeatherReport(BaseModel):
    city: str
    temperature_f: float
    condition: str
    wind_mph: float
    visibility_miles: float
    risk_level: str            # low / medium / high
    risk_reason: Optional[str] = None
    advisory: Optional[str] = None


# ──────────────────────────────────────────────────────────────────────────────
# Mock Data Store
# ──────────────────────────────────────────────────────────────────────────────

WEATHER: dict[str, WeatherReport] = {
    # ── High-risk cities ────────────────────────────────────────────────────
    "denver": WeatherReport(
        city="Denver",
        temperature_f=18.0,
        condition="Blizzard",
        wind_mph=45.0,
        visibility_miles=0.25,
        risk_level="high",
        risk_reason="Active blizzard warning — I-70 corridor closed.",
        advisory=(
            "NWS Denver: BLIZZARD WARNING in effect through Thursday. "
            "Do not travel. All ground transport severely impacted."
        ),
    ),
    "seattle": WeatherReport(
        city="Seattle",
        temperature_f=42.0,
        condition="Coastal Storm",
        wind_mph=55.0,
        visibility_miles=1.0,
        risk_level="high",
        risk_reason="Severe coastal storm with high winds and heavy rainfall.",
        advisory=(
            "NWS Seattle: HIGH WIND WARNING. Gusts up to 65 mph. "
            "Port operations suspended."
        ),
    ),
    # ── Medium-risk cities ───────────────────────────────────────────────────
    "chicago": WeatherReport(
        city="Chicago",
        temperature_f=38.0,
        condition="Heavy Rain",
        wind_mph=22.0,
        visibility_miles=3.0,
        risk_level="medium",
        risk_reason="Heavy rain reducing visibility and slowing ground transport.",
        advisory="NWS Chicago: Flood watch in effect for Cook County.",
    ),
    "new york": WeatherReport(
        city="New York",
        temperature_f=52.0,
        condition="Overcast",
        wind_mph=12.0,
        visibility_miles=8.0,
        risk_level="low",
        risk_reason=None,
        advisory=None,
    ),
    # ── Low-risk cities ──────────────────────────────────────────────────────
    "miami": WeatherReport(
        city="Miami",
        temperature_f=79.0,
        condition="Partly Cloudy",
        wind_mph=8.0,
        visibility_miles=10.0,
        risk_level="low",
        risk_reason=None,
        advisory=None,
    ),
    "atlanta": WeatherReport(
        city="Atlanta",
        temperature_f=63.0,
        condition="Partly Sunny",
        wind_mph=6.0,
        visibility_miles=10.0,
        risk_level="low",
        risk_reason=None,
        advisory=None,
    ),
    "portland": WeatherReport(
        city="Portland",
        temperature_f=48.0,
        condition="Drizzle",
        wind_mph=10.0,
        visibility_miles=6.0,
        risk_level="low",
        risk_reason=None,
        advisory=None,
    ),
    "los angeles": WeatherReport(
        city="Los Angeles",
        temperature_f=68.0,
        condition="Sunny",
        wind_mph=5.0,
        visibility_miles=10.0,
        risk_level="low",
        risk_reason=None,
        advisory=None,
    ),
    "dallas": WeatherReport(
        city="Dallas",
        temperature_f=71.0,
        condition="Clear",
        wind_mph=9.0,
        visibility_miles=10.0,
        risk_level="low",
        risk_reason=None,
        advisory=None,
    ),
}


# ──────────────────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
def root():
    return {"service": "Weather Mock API", "status": "running", "version": "1.0.0"}


@app.get("/weather/{city}", response_model=WeatherReport, tags=["Weather"])
def get_weather(city: str):
    """
    Retrieve current weather conditions and delivery risk level for a city.

    `risk_level` values:
    - `low`    — no weather-related delivery impact expected
    - `medium` — possible minor delays due to weather
    - `high`   — significant delivery disruption likely; carrier may be impacted

    City name matching is case-insensitive.
    """
    normalized = city.lower().strip()
    report = WEATHER.get(normalized)
    if not report:
        # Return a generic "unknown" response rather than 404 —
        # simulates real weather APIs that return a result for any city.
        return WeatherReport(
            city=city.title(),
            temperature_f=55.0,
            condition="Unknown",
            wind_mph=0.0,
            visibility_miles=10.0,
            risk_level="low",
            risk_reason="No weather data on file for this city.",
            advisory=None,
        )
    return report


@app.get("/weather", response_model=list[WeatherReport], tags=["Weather"])
def list_weather():
    """List weather reports for all cities in the mock dataset."""
    return list(WEATHER.values())
