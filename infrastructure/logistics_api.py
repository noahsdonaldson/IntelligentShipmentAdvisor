"""
infrastructure/logistics_api.py
================================
Mock FastAPI — Logistics Domain
Serves accounts, shipments, and carrier status.

Start with:
    uvicorn infrastructure.logistics_api:app --port 8001 --reload

Edge cases deliberately baked in:
  • ACC-002 has TWO shipments going to DIFFERENT cities  ← breaks rigid API chains
  • CARR-B is marked 'disrupted'                        ← triggers backtrack logic
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(
    title="Logistics Mock API",
    description="Mock logistics data for the API-vs-MCP study.",
    version="1.0.0",
)

# ──────────────────────────────────────────────────────────────────────────────
# Pydantic Models
# ──────────────────────────────────────────────────────────────────────────────

class Account(BaseModel):
    account_id: str
    name: str
    tier: str          # Gold / Standard / Platinum
    home_city: str
    email: str


class Shipment(BaseModel):
    shipment_id: str
    account_id: str
    origin_city: str
    destination_city: str
    carrier_id: str
    status: str        # in_transit / delivered / held
    eta_days: int      # estimated days remaining
    eta_date: str
    weight_kg: float
    description: str


class Carrier(BaseModel):
    carrier_id: str
    name: str
    status: str        # on_time / delayed / disrupted
    delay_hours: Optional[int] = 0
    disruption_note: Optional[str] = None


# ──────────────────────────────────────────────────────────────────────────────
# Mock Data Store
# ──────────────────────────────────────────────────────────────────────────────

_TODAY = datetime.now()

ACCOUNTS: dict[str, Account] = {
    "ACC-001": Account(
        account_id="ACC-001",
        name="Alice Chen",
        tier="Gold",
        home_city="Chicago",
        email="alice.chen@example.com",
    ),
    # ← THE EDGE CASE ACCOUNT: two shipments, two destinations
    "ACC-002": Account(
        account_id="ACC-002",
        name="Bob Martinez",
        tier="Standard",
        home_city="New York",
        email="bob.martinez@example.com",
    ),
    "ACC-003": Account(
        account_id="ACC-003",
        name="Carol White",
        tier="Platinum",
        home_city="Seattle",
        email="carol.white@example.com",
    ),
}

SHIPMENTS: dict[str, Shipment] = {
    # ── Happy-path shipment (single, no issues) ──────────────────────────────
    "SHP-001": Shipment(
        shipment_id="SHP-001",
        account_id="ACC-001",
        origin_city="Chicago",
        destination_city="Atlanta",
        carrier_id="CARR-A",
        status="in_transit",
        eta_days=2,
        eta_date=(_TODAY + timedelta(days=2)).strftime("%Y-%m-%d"),
        weight_kg=3.2,
        description="Electronics — laptop accessories",
    ),
    # ── Edge-case shipments for ACC-002 ──────────────────────────────────────
    "SHP-101": Shipment(
        shipment_id="SHP-101",
        account_id="ACC-002",
        origin_city="New York",
        destination_city="Miami",
        carrier_id="CARR-A",      # ← CARR-A is fine
        status="in_transit",
        eta_days=2,
        eta_date=(_TODAY + timedelta(days=2)).strftime("%Y-%m-%d"),
        weight_kg=1.5,
        description="Clothing — summer wardrobe",
    ),
    "SHP-102": Shipment(
        shipment_id="SHP-102",
        account_id="ACC-002",
        origin_city="New York",
        destination_city="Denver",
        carrier_id="CARR-B",      # ← CARR-B is DISRUPTED + Denver has blizzard
        status="in_transit",
        eta_days=3,
        eta_date=(_TODAY + timedelta(days=3)).strftime("%Y-%m-%d"),
        weight_kg=8.0,
        description="Furniture parts — bookshelf",
    ),
    # ── Platinum account — one held shipment ─────────────────────────────────
    "SHP-201": Shipment(
        shipment_id="SHP-201",
        account_id="ACC-003",
        origin_city="Seattle",
        destination_city="Portland",
        carrier_id="CARR-C",
        status="held",
        eta_days=5,
        eta_date=(_TODAY + timedelta(days=5)).strftime("%Y-%m-%d"),
        weight_kg=12.0,
        description="Medical equipment — held at customs",
    ),
}

CARRIERS: dict[str, Carrier] = {
    "CARR-A": Carrier(
        carrier_id="CARR-A",
        name="SwiftShip Express",
        status="on_time",
        delay_hours=0,
        disruption_note=None,
    ),
    # ← THE DISRUPTED CARRIER
    "CARR-B": Carrier(
        carrier_id="CARR-B",
        name="MountainRoute Freight",
        status="disrupted",
        delay_hours=48,
        disruption_note=(
            "Major hub delay affecting Denver region. "
            "I-70 corridor closed due to winter storm. "
            "Estimated 48-hour delay on all Denver-bound shipments."
        ),
    ),
    "CARR-C": Carrier(
        carrier_id="CARR-C",
        name="PacificCoast Logistics",
        status="delayed",
        delay_hours=12,
        disruption_note="Port congestion in Seattle causing minor delays.",
    ),
}


# ──────────────────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
def root():
    return {"service": "Logistics Mock API", "status": "running", "version": "1.0.0"}


@app.get("/accounts/{account_id}", response_model=Account, tags=["Accounts"])
def get_account(account_id: str):
    """
    Retrieve account information by account ID.

    Returns name, tier (Gold/Standard/Platinum), and home city.
    Raise 404 if account not found.
    """
    account = ACCOUNTS.get(account_id)
    if not account:
        raise HTTPException(status_code=404, detail=f"Account '{account_id}' not found.")
    return account


@app.get("/shipments", response_model=List[Shipment], tags=["Shipments"])
def get_shipments(account_id: str):
    """
    Retrieve all active shipments for a given account ID.

    **Key edge case:** ACC-002 returns TWO shipments with DIFFERENT destinations.
    A rigid API chain that assumes a single shipment will silently drop one.
    """
    results = [s for s in SHIPMENTS.values() if s.account_id == account_id]
    if not results:
        raise HTTPException(
            status_code=404,
            detail=f"No shipments found for account '{account_id}'.",
        )
    return results


@app.get("/shipments/{shipment_id}", response_model=Shipment, tags=["Shipments"])
def get_shipment_by_id(shipment_id: str):
    """Retrieve a single shipment by its shipment ID."""
    shipment = SHIPMENTS.get(shipment_id)
    if not shipment:
        raise HTTPException(status_code=404, detail=f"Shipment '{shipment_id}' not found.")
    return shipment


@app.get("/carriers/{carrier_id}", response_model=Carrier, tags=["Carriers"])
def get_carrier_status(carrier_id: str):
    """
    Retrieve carrier operational status.

    Status values:
    - `on_time`   — no known delays
    - `delayed`   — minor delays (< 24 hrs)
    - `disrupted` — major disruption, check disruption_note for details
    """
    carrier = CARRIERS.get(carrier_id)
    if not carrier:
        raise HTTPException(status_code=404, detail=f"Carrier '{carrier_id}' not found.")
    return carrier
