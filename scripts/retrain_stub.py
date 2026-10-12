#!/usr/bin/env python3
# retrain_stub.py - the capstone's documented "no GPU" fallback: retraining
# is simulated, not performed. This script reads no training data, touches
# no model weights, and makes no API call -- it only bumps
# config/triage.yaml's model_version label (a simulation-generation tag,
# not a real model identifier) and appends one line to CHANGELOG.md saying
# exactly that, so the distinction between "a new simulated generation was
# recorded" and "a model was actually retrained" stays visible to anyone
# reading the history.
#
# Wired into .github/workflows/ci.yml as a workflow_dispatch-only job
# (never on every push/PR) -- a real retrain job would be gated the same
# way, behind an explicit human trigger, not an automatic one.
#
# Run it:
#   python scripts/retrain_stub.py --note "simulated nightly retrain, no GPU available"

from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "triage.yaml"
CHANGELOG_PATH = REPO_ROOT / "CHANGELOG.md"

MODEL_VERSION_RE = re.compile(r"^model_version:\s*(\S+)\s*$", re.MULTILINE)


def _bump(current: str) -> str:
    """sim-2026.10.0 -> sim-2026.10.1 (increments the trailing counter;
    everything before the last '.' is left untouched)."""
    prefix, _, counter = current.rpartition(".")
    if not prefix or not counter.isdigit():
        raise ValueError(f"model_version {current!r} doesn't match the expected sim-<date>.<counter> shape")
    return f"{prefix}.{int(counter) + 1}"


def bump_model_version(note: str) -> str:
    text = CONFIG_PATH.read_text(encoding="utf-8")
    match = MODEL_VERSION_RE.search(text)
    if not match:
        raise RuntimeError("model_version line not found in config/triage.yaml")
    old_version = match.group(1)
    new_version = _bump(old_version)
    CONFIG_PATH.write_text(MODEL_VERSION_RE.sub(f"model_version: {new_version}", text, count=1), encoding="utf-8")

    today = datetime.date.today().isoformat()
    entry = (
        f"\n## {new_version} - {today}\n\n"
        f"- **Simulated retrain (no weights trained):** model_version bumped "
        f"{old_version} -> {new_version}. {note}\n"
    )
    changelog = CHANGELOG_PATH.read_text(encoding="utf-8") if CHANGELOG_PATH.exists() else "# Changelog\n"
    CHANGELOG_PATH.write_text(changelog + entry, encoding="utf-8")
    return new_version


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--note", default="No GPU available in this environment; retraining is simulated per the fallback path."
    )
    args = parser.parse_args()
    new_version = bump_model_version(args.note)
    print(f"Simulated retrain complete (no weights trained). New model_version: {new_version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
