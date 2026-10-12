# Changelog

Format loosely follows [Keep a Changelog](https://keepachangelog.com/).
Versions tracked here are **prompt releases** (`prompts/triage_system_v*.txt`
+ `config/triage.yaml`'s `prompt_version`/`canary` block), not the service's
own `SERVICE_VERSION` in `app/main.py` (unchanged at `1.0.0` since Week 6) -
see `runbook.md` for why those two version lines are tracked separately.

## [1.3.0-candidate] - 2026-10-12 (canary: 10% of traffic, see config/triage.yaml)

### Added

- New triage prompt escalates two cases `1.2.0` missed to `urgency: "high"`:
  a pregnant patient reporting heavy bleeding or severe abdominal pain, and
  a child under 2 with a high fever. Also biases genuinely ambiguous
  messages toward `medium` rather than defaulting to `low`.
- `evals/golden.jsonl` agreement: `14/14` scored cases (vs `12/14` for
  `1.2.0`) - see `evidence/eval_run.log`.

### Rollout

- 10% of staging traffic, bucketed deterministically by JWT subject via
  `ab_prompt_flag.py` (same key always lands on the same side for the life
  of this rollout).
- Rollback: unset the canary or set `PROMPT_VERSION=1.2.0` - see
  `clinical_ops_change_brief.md` and `runbook.md`.

## [1.2.0] - active baseline

- The deployed default. Carried over unchanged from the Week 6/7 spine's
  `SYSTEM_PROMPT` constant, now externalised to
  `prompts/triage_system_v1.2.0.txt` and pinned in `prompts/pin.json`.
- `evals/golden.jsonl` agreement: `12/14` scored cases, above the `0.85`
  threshold - see `evidence/eval_run.log`.

## [1.0.0] - service baseline (Week 6/7, unchanged)

- FastAPI + JWT + Docker triage service (`app/`), carried over from
  `afyaplus-service-platform` (Week 6) via `cost-optimized-deployment-and-exec-brief`
  (Week 7) with no logic changes - see the top-level README's "Weeks 6 and 7
  reuse" section.
- LangChain/MCP logistics agent (`app/agent_service.py`) over
  `logistics_mcp_versioned.py`'s four tools (`check_stock`,
  `plan_delivery_route`, `get_delivery_eta`, `request_reorder`) and one
  resource (`clinics://directory`).

<!--
  scripts/retrain_stub.py appends entries below this line when run. Each
  entry it adds explicitly says "no weights trained" -- there is no GPU in
  this environment, so "retraining" here only bumps config/triage.yaml's
  model_version label. See the capstone brief's GPU fallback and
  runbook.md's "Simulated retrain" section.
-->

## sim-2026.10.1 - 2026-10-12

- **Simulated retrain (no weights trained):** model_version bumped sim-2026.10.0 -> sim-2026.10.1. Nightly simulated retrain demo for Week 8 capstone evidence; no GPU, no weights touched.
