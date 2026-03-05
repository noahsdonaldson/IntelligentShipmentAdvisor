"""
infrastructure/weather_mcp_server.py
======================================
MCP Server — Weather Domain  (third-party provider)
----------------------------------------------------
Wraps the Weather FastAPI mock. In production this would be a thin adapter
in front of a commercial weather API (Tomorrow.io, The Weather Company,
Open-Meteo, etc.) that the third party themselves may publish as a public
MCP server.

This is ONE of TWO MCP servers in this study. The other is logistics_mcp_server.py.

Start with:
    python infrastructure/weather_mcp_server.py

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
KEY BLOG POINT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The ReAct agent connects to both this server AND logistics_mcp_server.py.
It receives a unified tool catalogue and reasons across tools from both
sources — without any bespoke integration code gluing them together.

In a REST-API world you'd write a custom aggregation layer to combine your
internal data with third-party weather data. With MCP, the protocol is
the integration layer.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

WEATHER_API = os.getenv("WEATHER_API_URL", "http://localhost:8002")

mcp = FastMCP(
    name="weather-provider",
    instructions=(
        "Third-party weather intelligence provider. Returns current conditions "
        "and a delivery risk level (low/medium/high) for any city. "
        "Use get_weather for the origin AND destination city of every shipment "
        "you are assessing. High risk_level strongly correlates with carrier delays."
    ),
)


def _get(path: str, params: dict | None = None) -> dict | list:
    with httpx.Client(timeout=10.0) as client:
        r = client.get(f"{WEATHER_API}{path}", params=params or {})
    r.raise_for_status()
    return r.json()


@mcp.tool()
def get_weather(city: str) -> dict[str, Any]:
    """
    Get current weather conditions and delivery risk level for a city.

    Returns: city, temperature_f, condition, wind_mph, visibility_miles,
    risk_level (low/medium/high), risk_reason, advisory.

    Call this for BOTH origin and destination of every shipment you are
    evaluating. A high risk_level at the destination strongly predicts
    carrier delays — cross-reference with get_carrier_status.

    Args:
        city: City name (e.g. 'Denver', 'Miami'). Case-insensitive.
    """
    return _get(f"/weather/{city}")


@mcp.tool()
def get_weather_multi(cities: list[str]) -> dict[str, Any]:
    """
    Get weather for multiple cities in one call.

    Convenience tool when you need to check several cities at once (e.g.
    origins and destinations of multiple shipments). Returns a dict keyed
    by city name.

    Args:
        cities: List of city names (e.g. ['Denver', 'Miami', 'New York']).
    """
    results: dict[str, Any] = {}
    for city in cities:
        try:
            results[city] = _get(f"/weather/{city}")
        except Exception as e:
            results[city] = {"error": str(e), "city": city}
    return results


if __name__ == "__main__":
    print("Starting MCP Server: weather-provider (stdio)")
    print(f"  Weather API: {WEATHER_API}")
    print("  Tools: get_weather, get_weather_multi")
    mcp.run()
