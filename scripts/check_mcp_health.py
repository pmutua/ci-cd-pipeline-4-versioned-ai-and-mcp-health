#!/usr/bin/env python3
# check_mcp_health.py - Deliverable 4: the pipeline step that proves the
# logistics MCP server actually speaks the protocol and offers the tools
# the agent depends on, BEFORE deploy runs. Does a real stdio handshake
# (initialize -> list_tools -> one real tool call), using the official
# `mcp` SDK's client -- the same exit-code contract the capstone's
# fallback path asks for ("fail on a bad probe") whether this is pointed
# at the real server or a local stub.
#
# Exit 0: handshake succeeded, every required tool is present, and
#         check_stock("amoxicillin") returned a well-formed response.
# Exit 1: anything above failed -- printed to stderr. CI treats this
#         non-zero exit as "mcp_health failed" and does not run the
#         build/deploy stage after it (see .github/workflows/ci.yml).
#
# Run it:
#   python scripts/check_mcp_health.py                   # real server, should PASS
#   python scripts/check_mcp_health.py --server scripts/broken_mcp_stub.py   # demo FAIL
#   python scripts/check_mcp_health.py --timeout 5        # override the default 10s timeout
#
# See evidence/mcp_health_pass.log and evidence/mcp_health_fail.log for
# captured runs of both.

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SERVER = "logistics_mcp_versioned.py"
REQUIRED_TOOLS = {"check_stock", "plan_delivery_route", "get_delivery_eta", "request_reorder"}


async def probe(server_script: str, timeout: float) -> int:
    params = StdioServerParameters(command="python", args=[server_script], cwd=str(REPO_ROOT))
    try:
        async with asyncio.timeout(timeout):
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools_resp = await session.list_tools()
                    names = {t.name for t in tools_resp.tools}
                    missing = REQUIRED_TOOLS - names
                    if missing:
                        print(f"FAIL: server={server_script} missing tool(s): {sorted(missing)}", file=sys.stderr)
                        print(f"      tools present: {sorted(names)}", file=sys.stderr)
                        return 1

                    result = await session.call_tool("check_stock", {"item": "amoxicillin"})
                    text = result.content[0].text if result.content else ""
                    try:
                        payload = json.loads(text)
                    except json.JSONDecodeError:
                        print(f"FAIL: check_stock returned non-JSON content: {text!r}", file=sys.stderr)
                        return 1
                    if "error" in payload:
                        print(f"FAIL: check_stock('amoxicillin') errored: {payload['error']}", file=sys.stderr)
                        return 1
                    if "stock" not in payload:
                        print(f"FAIL: check_stock('amoxicillin') missing 'stock' key: {payload}", file=sys.stderr)
                        return 1

                    print(f"PASS: server={server_script} handshake ok, tools={sorted(names)}, check_stock ok")
                    return 0
    except TimeoutError:
        print(f"FAIL: server={server_script} did not complete handshake within {timeout}s", file=sys.stderr)
        return 1
    except Exception as exc:  # the probe's whole point is to turn ANY handshake failure into exit 1, not a traceback
        print(f"FAIL: server={server_script} handshake error: {exc!r}", file=sys.stderr)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", default=DEFAULT_SERVER, help="MCP server script to probe (default: real server)")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    return asyncio.run(probe(args.server, args.timeout))


if __name__ == "__main__":
    sys.exit(main())
