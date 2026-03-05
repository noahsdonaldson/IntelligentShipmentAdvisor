"""
infrastructure/logistics_mcp_server.py
========================================
MCP Server — Logistics Domain  (your internal system)
------------------------------------------------------
Wraps the internal Logistics FastAPI mock. In a real deployment this would
sit in front of your order-management / WMS system, behind your auth layer.

This is ONE of TWO MCP servers in this study. The other is weather_mcp_server.py.
An MCP client (the ReAct agent) connects to BOTH at runtime and receives a
unified tool catalogue — without knowing or caring which server owns which tool.

Start with:
    python infrastructure/logistics_mcp_server.py

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ARCHITECTURE NOTE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Real-world parallel:
  • This server = your company's internal MCP server
    (data you own: accounts, shipments, carrier relationships)
  • weather_mcp_server.py = a third-party provider's MCP server
    (e.g. Tomorrow.io, The Weather Company — data you license)

The agent connects to both. It doesn't know or care which server a tool
came from. That's the power of the protocol abstraction.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

LOGISTICS_API = os.getenv("LOGISTICS_API_URL", "http://localhost:8001")

mcp = FastMCP(
    name="logistics-internal",
    instructions=(
        "Internal logistics system. Provides account lookup, shipment tracking, "
        "and carrier status. Use these tools to find what packages a customer has "
        "and which carriers are handling them. Combine with weather data from the "
        "weather MCP server to assess delivery risk."
    ),
)


def _get(path: str, params: dict | None = None) -> dict | list:
    with httpx.Client(timeout=10.0) as client:
        r = client.get(f"{LOGISTICS_API}{path}", params=params or {})
    if r.status_code == 404:
        raise ValueError(r.json().get("detail", "Not found"))
    r.raise_for_status()
    return r.json()


@mcp.tool()
def get_account(account_id: str) -> dict[str, Any]:
    """
    Look up a customer account by ID.

    Returns: account_id, name, tier (Gold/Standard/Platinum), home_city, email.
    Always call this first when a customer asks about their shipments.

    Args:
        account_id: Customer account identifier (e.g. 'ACC-002').
    """
    return _get(f"/accounts/{account_id}")


@mcp.tool()
def get_shipments(account_id: str) -> list[dict[str, Any]]:
    """
    Get ALL active shipments for a customer account.

    Returns a LIST — accounts can have one shipment or many. Always process
    every item in the list. Never assume there is only one.

    Each shipment includes: shipment_id, origin_city, destination_city,
    carrier_id, status (in_transit/delivered/held), eta_days, eta_date.

    Args:
        account_id: Customer account identifier (e.g. 'ACC-002').
    """
    return _get("/shipments", params={"account_id": account_id})


@mcp.tool()
def get_carrier_status(carrier_id: str) -> dict[str, Any]:
    """
    Check the operational status of a shipping carrier.

    Returns: carrier_id, name, status (on_time/delayed/disrupted),
    delay_hours, disruption_note.

    If status is 'disrupted', read disruption_note — it explains cause and scope.
    Factor delay_hours into your ETA estimate.

    Args:
        carrier_id: Carrier identifier (e.g. 'CARR-B').
    """
    return _get(f"/carriers/{carrier_id}")


@mcp.tool()
def assess_delivery_risk(shipment_id: str) -> dict[str, Any]:
    """
    Composite risk assessment for a single shipment.

    Internally calls carrier status, origin weather, and destination weather
    then scores and summarises the result. Returns overall_risk (low/medium/
    high/critical) and a human-readable assessment string.

    Use this when you want a single-call summary for a known shipment_id.
    Use the individual tools when you need to reason step by step or cross-
    reference data across multiple shipments.

    Args:
        shipment_id: Shipment identifier (e.g. 'SHP-102').
    """
    from infrastructure.logistics_api import SHIPMENTS, CARRIERS  # type: ignore
    from infrastructure.weather_api   import WEATHER               # type: ignore

    ship    = _get(f"/shipments/{shipment_id}")
    carrier = _get(f"/carriers/{ship['carrier_id']}")

    # Call the weather API directly (cross-server composite)
    weather_base = os.getenv("WEATHER_API_URL", "http://localhost:8002")
    with httpx.Client(timeout=10.0) as client:
        orig_wx = client.get(f"{weather_base}/weather/{ship['origin_city']}").json()
        dest_wx = client.get(f"{weather_base}/weather/{ship['destination_city']}").json()

    # Score
    score = 0
    if carrier["status"] == "disrupted": score += 3
    elif carrier["status"] == "delayed": score += 1
    if dest_wx["risk_level"] == "high":   score += 3
    elif dest_wx["risk_level"] == "medium": score += 1
    if orig_wx["risk_level"] == "high":   score += 2
    elif orig_wx["risk_level"] == "medium": score += 1
    if ship["status"] == "held":           score += 2

    overall = ("critical" if score >= 5 else
               "high"     if score >= 3 else
               "medium"   if score >= 1 else "low")

    issues = []
    if carrier["status"] != "on_time":
        issues.append(f"Carrier {carrier['name']} is {carrier['status']} "
                      f"(+{carrier.get('delay_hours',0)}h). {carrier.get('disruption_note','')}")
    if dest_wx["risk_level"] != "low":
        issues.append(f"Destination {ship['destination_city']} weather: "
                      f"{dest_wx['risk_level']} risk — {dest_wx.get('risk_reason', dest_wx['condition'])}")
    if orig_wx["risk_level"] != "low":
        issues.append(f"Origin {ship['origin_city']} weather: "
                      f"{orig_wx['risk_level']} risk — {orig_wx.get('risk_reason', orig_wx['condition'])}")

    summary = (f"Shipment {shipment_id} ({ship['origin_city']} → {ship['destination_city']}) "
               f"has {overall.upper()} risk. ETA {ship['eta_date']}. "
               + ("Issues: " + " | ".join(issues) if issues else "No significant risk factors."))

    return {"shipment_id": shipment_id, "overall_risk": overall, "risk_score": score,
            "assessment": summary, "carrier": carrier,
            "origin_weather": orig_wx, "destination_weather": dest_wx, "shipment": ship}


if __name__ == "__main__":
    print("Starting MCP Server: logistics-internal (stdio)")
    print(f"  Logistics API: {LOGISTICS_API}")
    print("  Tools: get_account, get_shipments, get_carrier_status, assess_delivery_risk")
    mcp.run()
