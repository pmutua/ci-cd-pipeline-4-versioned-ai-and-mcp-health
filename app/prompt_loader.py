# prompt_loader.py - Deliverable 1: the single place that resolves WHICH
# triage system prompt a request uses and WHAT its SHA-256 is, so
# app/main.py's /health and app/triage_model.py's actual model call always
# agree on the same answer instead of drifting apart.
#
# Three ways the active version is chosen, in priority order:
#   1. PROMPT_VERSION env var - the rollback/pin escape hatch. Set this and
#      every request uses exactly that prompt, canary or not. This is the
#      lever clinical_ops_change_brief.md's "Rollback" line sets.
#   2. config/triage.yaml's canary block - if a candidate_prompt_version is
#      configured with candidate_traffic_percent > 0, ab_prompt_flag.py
#      deterministically buckets each caller (by JWT subject) into
#      "active" or "candidate" so the same user always lands on the same
#      side of the canary within one prompt rollout.
#   3. config/triage.yaml's prompt_version - the default when there is no
#      canary in flight.

from __future__ import annotations

import hashlib
import sys
from functools import cache
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = REPO_ROOT / "prompts"
CONFIG_PATH = REPO_ROOT / "config" / "triage.yaml"

# ab_prompt_flag.py lives at the repo root (Thursday Lab 1), not inside the
# app/ package - uvicorn's console-script entrypoint doesn't put the repo
# root on sys.path the way `python -m` would, so this module makes sure it
# is importable regardless of how the process was launched.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ab_prompt_flag import assign_variant  # noqa: E402


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


@cache
def _read_prompt(version: str) -> tuple[str, str]:
    """Return (text, sha256) for prompts/triage_system_v<version>.txt.

    Cached per version for the life of the process: prompt files are
    immutable once tagged (a changed prompt gets a new version string,
    never an edit-in-place), so re-reading on every request buys nothing.
    """
    path = PROMPTS_DIR / f"triage_system_v{version}.txt"
    text = path.read_text(encoding="utf-8")
    sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return text, sha256


def resolve_prompt_version(user_key: str | None, overrides: dict | None = None) -> str:
    """Decide which prompt version a given caller should get this request."""
    import os

    cfg = overrides if overrides is not None else load_config()
    pinned = os.getenv("PROMPT_VERSION")
    if pinned:
        return pinned

    canary = cfg.get("canary") or {}
    candidate = canary.get("candidate_prompt_version")
    percent = int(canary.get("candidate_traffic_percent", 0) or 0)
    if candidate and percent > 0 and user_key:
        variant = assign_variant(user_key, percent)
        return candidate if variant == "candidate" else cfg["prompt_version"]
    return cfg["prompt_version"]


def get_prompt(version: str) -> dict:
    text, sha256 = _read_prompt(version)
    return {"version": version, "sha256": sha256, "text": text}


def active_prompt_info() -> dict:
    """What /health reports: the default version plus the candidate in
    flight (if any), each with its file SHA-256 - the versions-at-runtime
    evidence Deliverable 1 asks for."""
    cfg = load_config()
    info = {"active": get_prompt(cfg["prompt_version"])}
    canary = cfg.get("canary") or {}
    candidate_version = canary.get("candidate_prompt_version")
    if candidate_version:
        info["candidate"] = get_prompt(candidate_version)
        info["candidate_traffic_percent"] = int(canary.get("candidate_traffic_percent", 0) or 0)
    return info
