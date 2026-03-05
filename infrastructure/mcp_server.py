"""
infrastructure/mcp_server.py
=============================
⚠️  SUPERSEDED — this single-server version has been replaced by two purpose-
    built servers that mirror a real-world multi-provider architecture:

    infrastructure/logistics_mcp_server.py   ← your internal system
    infrastructure/weather_mcp_server.py     ← third-party data provider

Why two servers?
  In production you would never own the weather data. It would come from a
  commercial provider (Tomorrow.io, The Weather Company, etc.) that publishes
  its own MCP server. Your internal logistics server and their weather server
  are two completely independent MCP endpoints. The ReAct agent connects to
  both, receives a unified tool catalogue, and reasons across them — without
  any bespoke integration glue. That is the core architectural claim.

This file is kept for reference only. Do not run it.
See notebook 02 for the two-server client pattern.

What IS MCP? (Concept summary)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MCP (Model Context Protocol, Anthropic 2024) standardises how LLMs discover
and invoke external tools. Think USB-C for AI tools:
  • Server   — exposes named tools with JSON Schema parameters
  • Client   — the LLM host that connects and discovers tools at runtime
  • Tool     — a function the model can call, described by its docstring
  • Transport — stdio (local) or HTTP/SSE (remote/production)

REST APIs: developer decides what to call and when.
MCP:       model reads the catalogue and decides at runtime.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────

LOGISTICS_API = os.getenv("LOGISTICS_API_URL", "http://localhost:8001")
WEATHER_API   = os.getenv("WEATHER_API_URL",   "http://localhost:8002")

# ──────────────────────────────────────────────────────────────────────────────
# Create the MCP Server
#
# FastMCP is a high-level wrapper provided by the official Python MCP SDK.
# It handles:
#   • Tool registration        (via @mcp.tool decorator)
#   • JSON Schema generation   (automatically from type hints + docstrings)
#   • Transport negotiation    (stdio by default, HTTP/SSE configurable)
#   • Protocol handshake       (capability negotiation with the LLM client)
# ──────────────────────────────────────────────────────────────────────────────

mcp = FastMCP(
    name="shipment-risk-advisor",
    # The description is sent to the LLM during the tool-discovery handshake.
    # A clear description helps the model decide *when* to use this server.
    instructions=(
        "You are a shipment risk advisor. Use the tools below to look up "
        "customer accounts, their active shipments, carrier status, and "
        "weather at origin/destination cities. Then synthesise a risk "
        "assessment explaining whether each shipment is likely to arrive "
        "on time and what risks exist."
    ),
)

# ──────────────────────────────────────────────────────────────────────────────
# Helper — synchronous HTTP client
#
# MCP tool functions can be sync or async. We use sync httpx here for
# simplicity. In a production MCP server you'd typically use async.
# ──────────────────────────────────────────────────────────────────────────────

def _get(base_url: str, path: str, params: dict | None = None) -> dict | list:
    """Make a GET request and return parsed JSON, or raise with detail."""
    with httpx.Client(timeout=10.0) as client:
        response = client.get(f"{base_url}{path}", params=params or {})
    if response.status_code == 404:
        raise ValueError(response.json().get("detail", "Not found"))
    response.raise_for_status()
    return response.json()


# ──────────────────────────────────────────────────────────────────────────────
# Tool 1 — get_account
#
# TUTORIAL: @mcp.tool
#   • Registers this function as an MCP tool named "get_account".
#   • The function's docstring becomes the tool's description — the LLM reads
#     this to understand *what* the tool does and *when* to call it.
#   • Type annotations are converted to a JSON Schema — the LLM uses this to
#     construct a valid call (e.g. it knows account_id is a string).
# ──────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def get_account(account_id: str) -> dict[str, Any]:
    """
    Look up a customer account by its ID.

    Returns: account_id, name, tier (Gold/Standard/Platinum), home_city, email.
    Use this as the first step when a customer asks about their shipment.

    Args:
        account_id: The customer account identifier (e.g. 'ACC-002').
    """
    return _get(LOGISTICS_API, f"/accounts/{account_id}")


# ──────────────────────────────────────────────────────────────────────────────
# Tool 2 — get_shipments
#
# TUTORIAL: Dynamic return cardinality
#   A REST endpoint always returns what it returns. But the LLM calling this
#   tool receives the *full list* and can reason about it:
#   "I got back 2 shipments — I need to check weather for BOTH destinations."
#   A rigid API chain hard-codes "take shipments[0]" and silently drops the rest.
# ──────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def get_shipments(account_id: str) -> list[dict[str, Any]]:
    """
    Retrieve all active shipments for a customer account.

    Returns a list — accounts can have one shipment OR many. Always process
    every shipment in the list; do not assume there is only one.

    Each shipment includes: shipment_id, origin_city, destination_city,
    carrier_id, status (in_transit/delivered/held), eta_days, eta_date.

    Args:
        account_id: The customer account identifier (e.g. 'ACC-002').
    """
    return _get(LOGISTICS_API, "/shipments", params={"account_id": account_id})


# ──────────────────────────────────────────────────────────────────────────────
# Tool 3 — get_carrier_status
#
# TUTORIAL: Handling disrupted data gracefully
#   When status = 'disrupted', the agent should:
#     1. Note the disruption_note for end-user explanation.
#     2. Check destination weather to corroborate (e.g. CARR-B + Denver blizzard).
#     3. Factor delay_hours into the ETA risk assessment.
#   The MCP agent figures this out from context; a rigid API chain would need
#   explicit conditional branches coded for each scenario.
# ──────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def get_carrier_status(carrier_id: str) -> dict[str, Any]:
    """
    Check the operational status of a shipping carrier.

    Returns: carrier_id, name, status (on_time/delayed/disrupted),
    delay_hours, disruption_note.

    If status is 'disrupted', read disruption_note carefully — it explains the
    cause and scope of the delay. Factor delay_hours into your ETA assessment.

    Args:
        carrier_id: The carrier identifier (e.g. 'CARR-B').
    """
    return _get(LOGISTICS_API, f"/carriers/{carrier_id}")


# ──────────────────────────────────────────────────────────────────────────────
# Tool 4 — get_weather
#
# TUTORIAL: Tool chaining driven by model reasoning
#   The model calls get_shipments, sees two destination cities, then decides
#   on its own to call get_weather TWICE — once per city. No developer wrote
#   "if len(shipments) == 2: call weather twice." The model inferred it.
#   This is the core of what MCP + ReAct enables.
# ──────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def get_weather(city: str) -> dict[str, Any]:
    """
    Get current weather and delivery risk level for a city.

    Returns: city, temperature_f, condition, wind_mph, visibility_miles,
    risk_level (low/medium/high), risk_reason, advisory.

    Call this for BOTH origin and destination cities of each shipment.
    High risk_level strongly correlates with carrier delays.

    Args:
        city: City name (e.g. 'Denver', 'Miami'). Case-insensitive.
    """
    return _get(WEATHER_API, f"/weather/{city}")


# ──────────────────────────────────────────────────────────────────────────────
# Tool 5 — assess_delivery_risk  (COMPOSITE TOOL)
#
# TUTORIAL: Composite / orchestrating tools
#   This tool calls multiple underlying tools internally and returns a
#   synthesised result. The LLM can call this as a shortcut when it knows
#   the shipment_id, OR it can build the picture incrementally using the
#   individual tools above. Having both options demonstrates MCP flexibility:
#   the model chooses the most efficient approach given what it already knows.
# ──────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def assess_delivery_risk(shipment_id: str) -> dict[str, Any]:
    """
    Perform a composite risk assessment for a single shipment.

    Internally fetches: shipment details, carrier status, origin weather,
    and destination weather. Returns a structured risk summary with an
    overall_risk field (low/medium/high/critical) and a human-readable
    assessment string.

    Use this when you already know the shipment_id and want a single-call
    summary. Use the individual tools when you need to reason step by step
    or when you need to cross-reference data across multiple shipments.

    Args:
        shipment_id: The shipment identifier (e.g. 'SHP-102').
    """
    # ── Fetch all data ────────────────────────────────────────────────────────
    shipment = _get(LOGISTICS_API, f"/shipments/{shipment_id}")
    carrier  = _get(LOGISTICS_API, f"/carriers/{shipment['carrier_id']}")
    origin_wx = _get(WEATHER_API, f"/weather/{shipment['origin_city']}")
    dest_wx   = _get(WEATHER_API, f"/weather/{shipment['destination_city']}")

    # ── Score risk ────────────────────────────────────────────────────────────
    risk_score = 0

    carrier_status = carrier["status"]
    if carrier_status == "disrupted":
        risk_score += 3
    elif carrier_status == "delayed":
        risk_score += 1

    dest_risk = dest_wx["risk_level"]
    if dest_risk == "high":
        risk_score += 3
    elif dest_risk == "medium":
        risk_score += 1

    origin_risk = origin_wx["risk_level"]
    if origin_risk == "high":
        risk_score += 2
    elif origin_risk == "medium":
        risk_score += 1

    if shipment["status"] == "held":
        risk_score += 2

    # ── Map score to label ────────────────────────────────────────────────────
    if risk_score >= 5:
        overall_risk = "critical"
    elif risk_score >= 3:
        overall_risk = "high"
    elif risk_score >= 1:
        overall_risk = "medium"
    else:
        overall_risk = "low"

    # ── Build human-readable assessment ──────────────────────────────────────
    issues: list[str] = []
    if carrier_status != "on_time":
        issues.append(
            f"Carrier {carrier['name']} is {carrier_status} "
            f"(+{carrier.get('delay_hours', 0)}h delay). "
            f"{carrier.get('disruption_note', '')}"
        )
    if dest_risk != "low":
        issues.append(
            f"Destination weather in {shipment['destination_city']} is {dest_risk} risk: "
            f"{dest_wx.get('risk_reason', dest_wx['condition'])}."
        )
    if origin_risk != "low":
        issues.append(
            f"Origin weather in {shipment['origin_city']} is {origin_risk} risk: "
            f"{origin_wx.get('risk_reason', origin_wx['condition'])}."
        )
    if shipment["status"] == "held":
        issues.append(f"Shipment is currently HELD — not in transit.")

    assessment = (
        f"Shipment {shipment_id} from {shipment['origin_city']} → "
        f"{shipment['destination_city']} has {overall_risk.upper()} delivery risk. "
        f"ETA: {shipment['eta_date']} ({shipment['eta_days']} days). "
    )
    if issues:
        assessment += "Issues: " + " | ".join(issues)
    else:
        assessment += "No significant delivery risk factors identified."

    return {
        "shipment_id": shipment_id,
        "overall_risk": overall_risk,
        "risk_score": risk_score,
        "assessment": assessment,
        "carrier": carrier,
        "origin_weather": origin_wx,
        "destination_weather": dest_wx,
        "shipment": shipment,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Entry Point
#
# TUTORIAL: Transport layer
#   mcp.run() starts the server using the default STDIO transport.
#   STDIO transport: the client launches this script as a subprocess and
#   communicates via stdin/stdout using JSON-RPC messages. This is the
#   simplest deployment model — ideal for local development and testing.
#
#   For HTTP/SSE transport (production, multi-client):
#       mcp.run(transport="sse", host="0.0.0.0", port=8003)
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Starting MCP Server: shipment-risk-advisor (stdio transport)")
    print(f"  Logistics API: {LOGISTICS_API}")
    print(f"  Weather API:   {WEATHER_API}")
    print("  Tools: get_account, get_shipments, get_carrier_status, get_weather, assess_delivery_risk")
    mcp.run()
