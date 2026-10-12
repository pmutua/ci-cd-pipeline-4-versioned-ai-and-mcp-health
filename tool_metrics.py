# tool_metrics.py - Thursday: one shared, in-memory counter store for both
# MCP tool calls (logistics_mcp_versioned.py) and prompt-variant usage
# (app/triage_model.py), so mcp_dashboard_sketch.py has a single place to
# read from instead of two unrelated counters.
#
# In-memory and per-process by design, same tradeoff rate_limit.py already
# makes in this codebase: fine for a lab-scale service or a single CI run,
# not a substitute for a real metrics backend (Prometheus, etc.) behind
# more than one replica - see runbook.md's observability section.

from __future__ import annotations

import threading
from collections import Counter

_lock = threading.Lock()
_counts: Counter[str] = Counter()


def increment(key: str) -> None:
    with _lock:
        _counts[key] += 1


def snapshot() -> dict[str, int]:
    with _lock:
        return dict(_counts)


def reset() -> None:
    """Test-only: clear all counters between test cases."""
    with _lock:
        _counts.clear()
