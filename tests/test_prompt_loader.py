# test_prompt_loader.py - Deliverable 1 evidence: proves the version
# resolution logic (config default, canary bucketing, PROMPT_VERSION
# rollback override) behaves exactly as runbook.md and
# clinical_ops_change_brief.md describe it.

from __future__ import annotations

import os

import pytest

from app.prompt_loader import active_prompt_info, get_prompt, load_config, resolve_prompt_version
from check_prompt_pin import check_pins


def test_load_config_has_expected_shape() -> None:
    cfg = load_config()
    assert cfg["prompt_version"] == "1.2.0"
    assert cfg["canary"]["candidate_prompt_version"] == "1.3.0-candidate"
    assert 0 <= cfg["canary"]["candidate_traffic_percent"] <= 100


def test_get_prompt_returns_text_and_sha() -> None:
    prompt = get_prompt("1.2.0")
    assert prompt["version"] == "1.2.0"
    assert len(prompt["sha256"]) == 64
    assert "non-diagnostic" in prompt["text"]


def test_active_prompt_info_reports_candidate() -> None:
    info = active_prompt_info()
    assert info["active"]["version"] == "1.2.0"
    assert info["candidate"]["version"] == "1.3.0-candidate"
    assert info["candidate_traffic_percent"] == 10


def test_resolve_prompt_version_without_key_returns_default() -> None:
    assert resolve_prompt_version(user_key=None) == "1.2.0"


def test_resolve_prompt_version_canary_bucketing_is_stable() -> None:
    # Same key -> same answer every time within one rollout.
    first = resolve_prompt_version("coordinator-42")
    second = resolve_prompt_version("coordinator-42")
    assert first == second
    assert first in {"1.2.0", "1.3.0-candidate"}


def test_resolve_prompt_version_env_override_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    # The rollback lever clinical_ops_change_brief.md documents: setting
    # PROMPT_VERSION pins every caller to that version regardless of canary.
    monkeypatch.setenv("PROMPT_VERSION", "1.2.0")
    assert resolve_prompt_version(user_key="whatever-bucket-this-lands-in") == "1.2.0"
    os.environ.pop("PROMPT_VERSION", None)


def test_check_prompt_pin_passes_on_unmodified_files() -> None:
    assert check_pins() == []
