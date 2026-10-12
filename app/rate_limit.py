# rate_limit.py - a small per-user counter answering "how fast may you go?",
# a separate question from auth.py's "who are you?". In-memory by design for
# this lab-scale service; see docs/STAKEHOLDER_MEMO.md's risk section for
# what changes before running more than one replica behind a load balancer.

from __future__ import annotations

import time

from fastapi import HTTPException

# Conflict resolution (feature/rate-limit-tuning x feature/stricter-window):
# both branches touched these two lines for different, legitimate reasons.
# Taking "theirs" (WINDOW_SECONDS=30, MAX_REQUESTS=5) wholesale would have
# been wrong even though it merges cleanly: halving the window while
# keeping the same count DOUBLES the effective per-minute rate (5 req /
# 30s = 10/min) -- the opposite of the burst-abuse fix it was meant to be.
# Kept the 60-second window and the coordinator-workflow branch's raised
# cap; the abuse-report concern needs a real fix (burst detection within
# the window, not a smaller window) and is tracked separately rather than
# folded in here as a silently-wrong number.
WINDOW_SECONDS = 60
MAX_REQUESTS = 10  # raised from 5: coordinators triaging a queue of patients hit the old limit mid-shift
_counters: dict[str, list[float]] = {}


def check_rate_limit(username: str) -> None:
    """Allow at most MAX_REQUESTS per user per WINDOW_SECONDS. Raise 429 if exceeded."""
    now = time.time()
    recent = [t for t in _counters.get(username, []) if now - t < WINDOW_SECONDS]
    if len(recent) >= MAX_REQUESTS:
        raise HTTPException(status_code=429, detail="Too many requests. Wait a minute and try again.")
    recent.append(now)
    _counters[username] = recent
