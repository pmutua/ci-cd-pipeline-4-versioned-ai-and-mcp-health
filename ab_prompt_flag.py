# ab_prompt_flag.py - Thursday Lab 1: deterministic traffic-splitting
# between two prompt versions, with no external flag service and no
# stored state. The same key (a JWT subject, i.e. a logged-in user)
# always lands on the same side of a given rollout, so one coordinator's
# triage requests don't flip between the active and candidate prompt
# mid-shift.
#
# This is what makes clinical_ops_change_brief.md's "10% of staging keys"
# line true rather than aspirational: percent=10 means a stable ~10% of
# distinct keys see the candidate prompt, every time, until the rollout
# config changes.

from __future__ import annotations

import hashlib


def assign_variant(key: str, candidate_percent: int) -> str:
    """Bucket `key` into "candidate" or "active".

    Hashes the key into a stable 0-99 bucket; keys below candidate_percent
    get "candidate". hashlib.sha256 (not Python's salted hash()) so the
    assignment is reproducible across processes and restarts.
    """
    if not 0 <= candidate_percent <= 100:
        raise ValueError(f"candidate_percent must be 0-100, got {candidate_percent}")
    bucket = int(hashlib.sha256(key.encode("utf-8")).hexdigest(), 16) % 100
    return "candidate" if bucket < candidate_percent else "active"


if __name__ == "__main__":
    # Quick sanity check: with 1,000 distinct keys and percent=10, the
    # candidate share should land close to 10% (law of large numbers, not
    # an exact cut) - run this if candidate_traffic_percent is ever
    # changed, to eyeball that the bucketing still behaves.
    keys = [f"user-{i}" for i in range(1000)]
    candidate_count = sum(1 for k in keys if assign_variant(k, 10) == "candidate")
    print(f"candidate share over {len(keys)} keys at percent=10: {candidate_count / len(keys):.1%}")
