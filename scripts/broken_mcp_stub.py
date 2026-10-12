# broken_mcp_stub.py - evidence-only fixture for Deliverable 4. A deliberately
# incomplete MCP server (missing request_reorder, and check_stock always
# errors) so scripts/check_mcp_health.py --server scripts/broken_mcp_stub.py
# has something real to fail against. Never imported by the real app or
# wired into agent_service.py -- see evidence/mcp_health_fail.log for the
# captured failing run this produces.

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

server = FastMCP("afyaplus-logistics-broken-demo")


@server.tool()
def check_stock(item: str) -> str:
    """Deliberately broken: always errors, regardless of input."""
    return json.dumps({"error": "stock database unreachable (demo failure)"})


@server.tool()
def plan_delivery_route(start_clinic_id: str) -> str:
    """Present but request_reorder below is missing entirely -- the probe's
    required-tool-set check should catch that."""
    return json.dumps({"error": "not implemented in this demo stub"})


if __name__ == "__main__":
    server.run()
