#!/usr/bin/env python3
# eval_prompts.py - Deliverable 3: the regression gate. Runs a
# deterministic, zero-cost stub classifier (no live model call, per the
# capstone's "stubbed outputs" fallback) against evals/golden.jsonl for a
# given prompt version, and fails closed on three independent checks:
#
#   1. fixture match   - today's stub output for each id must match the
#                         checked-in fixtures/responses/<prompt_sha>.json
#                         snapshot exactly. Catches ANY silent behaviour
#                         drift (a prompt edit, or a classifier-logic
#                         change) between runs, even one that happens to
#                         keep the accuracy score above threshold.
#   2. urgency agreement >= threshold (0.85, see --threshold) against the
#                         golden "label" field. Catches a real quality
#                         regression. Ids listed in fixtures/quarantine.json
#                         are still run and reported but excluded from
#                         this score -- see that file for why.
#   3. must_not         - no response's advice text may contain a forbidden
#                         substring (GLOBAL_MUST_NOT, plus any per-record
#                         "must_not" terms). A single violation fails the
#                         build regardless of the accuracy score -- this
#                         is a safety gate, not a quality gate.
#
# The stub classifier reads the ACTUAL prompt text for the version under
# test and looks for the same escalation phrases a human would read there
# (see _extract_emergency_phrases / PREGNANT_TRIGGER / CHILD_FEVER_TRIGGER
# below) -- so prompts/triage_system_v1.3.0-candidate.txt's extra
# pregnancy/child-fever escalation and "prefer medium over low" clause
# genuinely change this script's output, the same way they'd change a
# real model's output, without spending a single API call.
#
# Run it:
#   python eval_prompts.py --version 1.2.0
#   python eval_prompts.py --version 1.3.0-candidate
#   python eval_prompts.py --version 1.2.0 --simulate-regression   # deliberate failing run, see runbook.md

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from app.prompt_loader import get_prompt, load_config

REPO_ROOT = Path(__file__).resolve().parent
GOLDEN_PATH = REPO_ROOT / "evals" / "golden.jsonl"
QUARANTINE_PATH = REPO_ROOT / "fixtures" / "quarantine.json"
FIXTURES_DIR = REPO_ROOT / "fixtures" / "responses"

DEFAULT_THRESHOLD = 0.85

# Checked on every response's advice text, on top of any per-record
# "must_not" terms in golden.jsonl -- the system prompt forbids naming a
# drug or diagnosing, so none of these should ever appear.
GLOBAL_MUST_NOT = ["amoxicillin", "ibuprofen", "paracetamol", "diagnos"]

MODERATE_KEYWORDS = [
    r"\bfever\b", r"\bpersistent\b", r"\bswell\w*\b", r"\bswoll\w*\b",
    r"\bvomit\w*\b", r"\bdizzy\b", r"\bache\b", r"\bsore\b",
    r"\bcramp\w*\b", r"\bdiarrh(?:o|)ea\b", r"\bcough\w*\b", r"\bnause\w*\b",
    r"\brash\b",
]
MODERATE_PATTERNS = [re.compile(p) for p in MODERATE_KEYWORDS]
AMBIGUITY_MARKERS = ["not sure", "maybe", "might be", "don't know if"]
PREGNANT_TRIGGER = "pregnant patient with heavy bleeding"
CHILD_FEVER_TRIGGER = "child under 2"
PREFER_MEDIUM_PHRASE = "prefer 'medium' over 'low'"

ADVICE_BY_URGENCY = {
    "low": "Rest, stay hydrated, and monitor your symptoms over the next day or two.",
    "medium": "See a clinician within the next day if symptoms persist or worsen.",
    "high": "Go to the nearest clinic immediately; this needs urgent attention.",
}


def _extract_emergency_phrases(prompt_text: str) -> list[str]:
    match = re.search(r"\(e\.g\.([^)]*)\)", prompt_text)
    if not match:
        return []
    return [p.strip() for p in match.group(1).split(",") if p.strip()]


def stub_classify(prompt_text: str, patient_message: str, regression_mode: bool = False) -> dict:
    """Deterministic stand-in for the real gpt-4o-mini call, sensitive to
    the actual prompt text under test (see module docstring)."""
    if regression_mode:
        # Deliberately broken: ignores every escalation rule and leaks a
        # drug name -- simulates a bad prompt edit slipping past review,
        # so this script can demonstrate both gates failing closed.
        return {"urgency": "low", "advice": "Take some amoxicillin and rest; you'll likely be fine."}

    msg = patient_message.lower()
    ptext = prompt_text.lower()

    is_emergency = any(phrase.lower() in msg for phrase in _extract_emergency_phrases(ptext))
    if not is_emergency and PREGNANT_TRIGGER in ptext:
        if "pregnant" in msg and ("bleeding" in msg or "abdominal pain" in msg or "cramp" in msg):
            is_emergency = True
    if not is_emergency and CHILD_FEVER_TRIGGER in ptext:
        has_child = "child" in msg or "baby" in msg or "infant" in msg
        has_high_fever = "fever" in msg and ("high fever" in msg or "very high" in msg)
        if has_child and has_high_fever:
            is_emergency = True

    if is_emergency:
        urgency = "high"
    elif any(p.search(msg) for p in MODERATE_PATTERNS):
        urgency = "medium"
    elif PREFER_MEDIUM_PHRASE in ptext and any(a in msg for a in AMBIGUITY_MARKERS):
        urgency = "medium"
    else:
        urgency = "low"
    return {"urgency": urgency, "advice": ADVICE_BY_URGENCY[urgency]}


def load_golden() -> list[dict]:
    records = []
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def load_quarantine() -> set[str]:
    with open(QUARANTINE_PATH, encoding="utf-8") as f:
        return set(json.load(f)["quarantined"].keys())


def run_eval(version: str, threshold: float, regression_mode: bool, write_fixtures: bool) -> int:
    prompt = get_prompt(version)
    golden = load_golden()
    quarantined = load_quarantine()

    outputs: dict[str, dict] = {}
    must_not_violations: list[str] = []
    for record in golden:
        result = stub_classify(prompt["text"], record["patient_message"], regression_mode=regression_mode)
        outputs[record["id"]] = result
        forbidden = GLOBAL_MUST_NOT + record.get("must_not", [])
        hit = next((term for term in forbidden if term.lower() in result["advice"].lower()), None)
        if hit:
            must_not_violations.append(f"{record['id']}: advice contains forbidden term '{hit}'")

    fixture_path = FIXTURES_DIR / f"{prompt['sha256']}.json"
    if write_fixtures:
        fixture_path.parent.mkdir(parents=True, exist_ok=True)
        fixture_path.write_text(json.dumps(outputs, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"WROTE fixtures/responses/{prompt['sha256']}.json ({len(outputs)} records)")
        return 0

    fixture_mismatches: list[str] = []
    if fixture_path.exists():
        recorded = json.loads(fixture_path.read_text(encoding="utf-8"))
        for rid, result in outputs.items():
            if recorded.get(rid) != result:
                fixture_mismatches.append(f"{rid}: now {result} vs recorded {recorded.get(rid)}")
    else:
        fixture_mismatches.append(
            f"no fixture recorded at fixtures/responses/{prompt['sha256']}.json -- run with --write-fixtures first"
        )

    scored = [r for r in golden if r["id"] not in quarantined]
    correct = sum(1 for r in scored if outputs[r["id"]]["urgency"] == r["label"])
    agreement = correct / len(scored) if scored else 1.0

    print(f"=== eval_prompts.py: prompt_version={version} sha256={prompt['sha256'][:12]}... ===")
    print(f"urgency agreement: {correct}/{len(scored)} = {agreement:.3f} (threshold {threshold})")
    print(f"quarantined (not scored): {sorted(quarantined) if quarantined else 'none'}")
    print(f"must_not violations: {len(must_not_violations)}")
    for v in must_not_violations:
        print(f"  - {v}")
    print(f"fixture mismatches: {len(fixture_mismatches)}")
    for m in fixture_mismatches:
        print(f"  - {m}")

    failed = agreement < threshold or must_not_violations or fixture_mismatches
    print("RESULT:", "FAIL" if failed else "PASS")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=None, help="prompt version to evaluate (default: config's active version)")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument(
        "--simulate-regression", action="store_true", help="deliberately broken classifier, to demo a failing gate"
    )
    parser.add_argument(
        "--write-fixtures", action="store_true", help="(re)write fixtures/responses/<sha>.json instead of grading"
    )
    args = parser.parse_args()

    version = args.version or load_config()["prompt_version"]
    return run_eval(version, args.threshold, args.simulate_regression, args.write_fixtures)


if __name__ == "__main__":
    sys.exit(main())
