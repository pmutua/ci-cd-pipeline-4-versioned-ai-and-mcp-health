#!/usr/bin/env python3
# check_prompt_pin.py - CI lint-stage gate (Deliverable 1). Recomputes the
# SHA-256 of every prompt file listed in prompts/pin.json and fails closed
# if any pinned file's hash doesn't match what's on disk -- the one way a
# prompt change could otherwise slip into a build without a version bump
# and without the eval gate ever seeing it, since eval_prompts.py keys its
# fixtures off the version string, not the file content.
#
# Run it:
#   python check_prompt_pin.py
# Exit 0: every pin matches. Exit 1: at least one mismatch, printed to stderr.

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
PROMPTS_DIR = REPO_ROOT / "prompts"
PIN_PATH = PROMPTS_DIR / "pin.json"


def check_pins() -> list[str]:
    """Return a list of human-readable mismatch descriptions (empty = all pinned files verified)."""
    with open(PIN_PATH, encoding="utf-8") as f:
        pins = json.load(f)["pins"]

    errors = []
    for version, pin in pins.items():
        path = PROMPTS_DIR / pin["file"]
        if not path.exists():
            errors.append(f"version {version}: pinned file {pin['file']} does not exist")
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != pin["sha256"]:
            errors.append(
                f"version {version}: {pin['file']} hash mismatch "
                f"(pinned {pin['sha256'][:12]}..., on-disk {actual[:12]}...) "
                f"-- bump the version and re-pin instead of editing in place"
            )
    return errors


def main() -> int:
    errors = check_pins()
    if errors:
        print("FAIL: prompt pin check found drift:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    with open(PIN_PATH, encoding="utf-8") as f:
        pin_count = len(json.load(f)["pins"])
    print(f"PASS: all {pin_count} pinned prompt(s) match prompts/pin.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
