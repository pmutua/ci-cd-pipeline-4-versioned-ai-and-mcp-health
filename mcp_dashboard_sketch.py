#!/usr/bin/env python3
# mcp_dashboard_sketch.py - Thursday Lab 2: a sketch, not a real
# dashboard app. Reads tool_metrics.snapshot() and prints the same
# numbers an operator would otherwise have to grep logs/mcp.log and
# logs/app.log for separately -- MCP tool call counts and prompt-variant
# (active vs. candidate) usage counts, side by side.
#
# --demo generates a little traffic first (a handful of MCP tool calls
# plus a simulated spread of canary bucketing across keys) so running
# this script standalone shows something instead of all zeros. In the
# real service, main.py and logistics_mcp_versioned.py populate these
# counters as requests actually arrive.
#
# Run it:
#   python mcp_dashboard_sketch.py --demo

from __future__ import annotations

import argparse

import tool_metrics
from ab_prompt_flag import assign_variant


def _generate_demo_traffic() -> None:
    import logistics_mcp_versioned as mcp

    mcp.check_stock("amoxicillin")
    mcp.check_stock("amoxicillin")
    mcp.plan_delivery_route("C01")
    mcp.get_delivery_eta("C01", "C04")
    mcp.request_reorder("C02", "amoxicillin", 40)

    for i in range(50):
        variant = assign_variant(f"demo-user-{i}", candidate_percent=10)
        tool_metrics.increment(f"prompt_version:{'1.3.0-candidate' if variant == 'candidate' else '1.2.0'}")


def render(counts: dict[str, int]) -> str:
    if not counts:
        return "(no activity recorded yet -- run with --demo, or run the real service first)"
    width = max(len(k) for k in counts) + 2
    lines = ["AfyaPlus MCP + prompt-variant dashboard (sketch)", "=" * 50]
    tool_rows = {k: v for k, v in counts.items() if k.startswith("mcp_tool") or k.startswith("mcp_resource")}
    prompt_rows = {k: v for k, v in counts.items() if k.startswith("prompt_version")}
    if tool_rows:
        lines.append("\nMCP tool/resource calls:")
        for k, v in sorted(tool_rows.items(), key=lambda kv: -kv[1]):
            lines.append(f"  {k.ljust(width)} {v}")
    if prompt_rows:
        total = sum(prompt_rows.values())
        lines.append("\nPrompt variant usage:")
        for k, v in sorted(prompt_rows.items(), key=lambda kv: -kv[1]):
            lines.append(f"  {k.ljust(width)} {v}  ({v / total:.0%})")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="generate sample traffic before printing")
    args = parser.parse_args()

    if args.demo:
        _generate_demo_traffic()

    print(render(tool_metrics.snapshot()))


if __name__ == "__main__":
    main()
