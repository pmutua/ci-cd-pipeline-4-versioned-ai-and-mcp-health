# logistics_mcp.py - the AfyaPlus logistics MCP server (Deliverable 3).
# Four tools plus one resource, all built on the Python MCP SDK's FastMCP.
#
# Production standards applied throughout, per the capstone rubric:
#   - input checking: every tool validates its arguments against CLINICS /
#     VALID_ITEMS before doing anything else
#   - errors as instructive data: a bad argument returns a JSON object with
#     an "error" key naming the valid options, never a raised exception —
#     an LLM agent can read a returned string and recover; it cannot read a
#     stack trace
#   - one log line per call: every tool logs its name and arguments to
#     logs/mcp.log (see LOG_PATH below) before doing any work, so a
#     request's tool activity can be reconstructed after the fact — see
#     docs/TRACE_RECONSTRUCTION.md
#
# Run it standalone:
#   python mcp_server/logistics_mcp.py
# Fastest first test (no agent, no protocol):
#   python -c "
#   import mcp_server.logistics_mcp as m
#   print(m.check_stock('amoxicillin'))
#   print(m.check_stock('bandages'))
#   "
# Interactive testing with the official developer tool:
#   npx @modelcontextprotocol/inspector python mcp_server/logistics_mcp.py
# Or the offline-friendly equivalent used for this capstone's own evidence:
#   pytest tests/test_mcp_tools.py -v

from __future__ import annotations

import json
import logging
import math
from pathlib import Path

from mcp.server.fastmcp import FastMCP

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = REPO_ROOT / "logs" / "mcp.log"
LOG_PATH.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler()],
)
log = logging.getLogger("logistics_mcp")

server = FastMCP("afyaplus-logistics")

CLINICS_PATH = Path(__file__).resolve().parent / "clinics.json"
with open(CLINICS_PATH) as f:
    CLINICS = json.load(f)["clinics"]

VALID_ITEMS = ["amoxicillin", "ors_sachets", "malaria_kits"]
MAX_REORDER_UNITS = 500


def _clinic(clinic_id: str) -> dict | None:
    return next((c for c in CLINICS if c["id"] == clinic_id), None)


def distance_km(a: dict, b: dict) -> float:
    """Rough distance between two clinics in kilometres (equirectangular approximation)."""
    dx = (a["lon"] - b["lon"]) * 111.32 * math.cos(math.radians((a["lat"] + b["lat"]) / 2))
    dy = (a["lat"] - b["lat"]) * 110.57
    return round(math.sqrt(dx * dx + dy * dy), 1)


@server.tool()
def check_stock(item: str) -> str:
    """Check how many units of a medical item each clinic holds.
    Valid items: amoxicillin, ors_sachets, malaria_kits. Stock counts are
    units on hand, not prices or orders — this tool has no price data and
    cannot answer cost questions."""
    log.info("tool=check_stock item=%s", item)
    if item not in VALID_ITEMS:
        return json.dumps({"error": f"Unknown item '{item}'. Valid items: {VALID_ITEMS}"})
    rows = [
        {
            "clinic": c["name"],
            "clinic_id": c["id"],
            "county": c["county"],
            "units": c["stock"][item],
            "reorder_needed": c["stock"][item] < 10,
        }
        for c in CLINICS
    ]
    return json.dumps({"item": item, "stock": rows})


@server.tool()
def plan_delivery_route(start_clinic_id: str) -> str:
    """Plan a delivery route visiting every clinic, starting from one clinic.
    Uses the nearest-neighbour rule: always drive to the closest unvisited
    clinic next. This is quick decision support, not a guaranteed-shortest
    route. Valid clinic ids: C01-C05 (see the clinics://directory resource
    for the full list with names)."""
    log.info("tool=plan_delivery_route start=%s", start_clinic_id)
    start = _clinic(start_clinic_id)
    if start is None:
        ids = [c["id"] for c in CLINICS]
        return json.dumps({"error": f"Unknown clinic id '{start_clinic_id}'. Valid ids: {ids}"})
    route, remaining, total = [start], [c for c in CLINICS if c["id"] != start_clinic_id], 0.0
    while remaining:
        here = route[-1]
        nearest = min(remaining, key=lambda c: distance_km(here, c))
        total += distance_km(here, nearest)
        route.append(nearest)
        remaining.remove(nearest)
    return json.dumps(
        {
            "route": [c["name"] for c in route],
            "total_km": round(total, 1),
            "method": "nearest-neighbour heuristic",
        }
    )


@server.tool()
def get_delivery_eta(from_clinic_id: str, to_clinic_id: str) -> str:
    """Estimate driving distance (km) and time (minutes) between two clinics,
    assuming a 40 km/h average speed on regional roads. This is a planning
    estimate, not a commitment — actual travel time depends on road
    conditions and traffic this tool has no data about."""
    log.info("tool=get_delivery_eta from=%s to=%s", from_clinic_id, to_clinic_id)
    a, b = _clinic(from_clinic_id), _clinic(to_clinic_id)
    if a is None or b is None:
        ids = [c["id"] for c in CLINICS]
        return json.dumps({"error": f"Unknown clinic id. Valid ids: {ids}"})
    km = distance_km(a, b)
    return json.dumps(
        {
            "from": a["name"],
            "to": b["name"],
            "km": km,
            "eta_minutes": round(km / 40 * 60),
            "assumed_speed_kmh": 40,
        }
    )


@server.tool()
def request_reorder(clinic_id: str, item: str, units: int) -> str:
    """Plan a reorder of a medical item for one clinic. Validates the clinic
    id, item name, and unit count (1-500) but does not commit or dispatch
    anything — this tool only returns a planned request for a human to act
    on; it has no order-placement or pricing capability. Valid items:
    amoxicillin, ors_sachets, malaria_kits."""
    log.info("tool=request_reorder clinic=%s item=%s units=%s", clinic_id, item, units)
    clinic = _clinic(clinic_id)
    if clinic is None:
        ids = [c["id"] for c in CLINICS]
        return json.dumps({"error": f"Unknown clinic id '{clinic_id}'. Valid ids: {ids}"})
    if item not in VALID_ITEMS:
        return json.dumps({"error": f"Unknown item '{item}'. Valid items: {VALID_ITEMS}"})
    if not isinstance(units, int) or units < 1 or units > MAX_REORDER_UNITS:
        return json.dumps({"error": f"units must be an integer between 1 and {MAX_REORDER_UNITS}, got {units!r}"})
    return json.dumps(
        {
            "status": "planned",
            "clinic": clinic["name"],
            "clinic_id": clinic_id,
            "item": item,
            "units": units,
            "note": "Not yet approved or dispatched — a human coordinator must confirm this request.",
        }
    )


@server.resource("clinics://directory")
def clinic_directory() -> str:
    """Read-only directory of all AfyaPlus partner clinics: id, name, county."""
    log.info("resource=clinics://directory")
    return json.dumps([{"id": c["id"], "name": c["name"], "county": c["county"]} for c in CLINICS])


if __name__ == "__main__":
    server.run()
