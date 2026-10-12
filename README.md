# Week 8, CI/CD for Versioned AI + MCP Health

## Overview

This repo versions the AfyaPlus triage AI's three moving parts — the
system **prompt**, the serving **config**, and the **MCP server** — and
gates every change behind a pipeline that must pass lint/tests, a
golden-set regression eval, and a real MCP protocol handshake, in that
order, before a Docker image is built and run. A failure at any stage
stops the pipeline; nothing downstream runs. `GET /health` reports the
exact prompt version + SHA-256, candidate canary, MCP server version, and
model-version label a running container is serving, so "what's actually
deployed" is one `curl` away rather than a question you have to go read
source code to answer.

## Versions

- **prompts:** `1.2.0` (active, default) and `1.3.0-candidate` (10%
  canary) — `prompts/triage_system_v*.txt`, pinned by SHA-256 in
  `prompts/pin.json`, checked for drift by `check_prompt_pin.py`.
- **config / model_version:** `config/triage.yaml` — `model_version:
  sim-2026.10.1` (a simulated-generation label, not a real model id; see
  "Fallbacks declared" below), `prompt_version: "1.2.0"`, canary block.
- **mcp server:** `logistics_mcp_versioned.py`, `SERVER_VERSION = "1.0.0"`.
- **image tag:** set via `IMAGE_TAG` build-arg/env var, surfaced at
  `GET /health`. `evidence/compose_up.log` shows a real build+run tagged
  `v1.3.0-candidate`, with the image digest and `/health`'s version
  fields captured together — the tag-alignment evidence Deliverable 1
  asks for.

## Pipeline

`.github/workflows/ci.yml` (GitHub Actions) and `azure-pipelines.yml`
(Azure DevOps config-as-code twin) both run four stages in strict
dependency order: **lint-test** -> **eval** -> **mcp-health** -> **build**
(docker build + a deploy-stub run with a `/health` check). Triggers: every
PR into `main`, every push to `main`, plus an optional
`workflow_dispatch`-gated `retrain-stub` job (see "Fallbacks declared").

Local-equivalent evidence, captured end-to-end on a laptop with the exact
same stage sequence and commands as the YAML (`scripts/local_ci_dry_run.sh`):

- `evidence/local_ci_dry_run.log` — all four stages, one real run,
  ending in a real `docker build` + container `/health` check.
- `evidence/compose_up.log` — `docker compose up --build` tagged
  `v1.3.0-candidate`, `docker compose ps`, the image digest, and
  `docker compose down`.

## Eval gate

**Metric:** urgency-label agreement against `evals/golden.jsonl` (15
labelled cases). **Threshold:** `0.85`. One id (`g09`) is quarantined
pending a clinician's input (`fixtures/quarantine.json`) — still run and
reported every time, just excluded from the score, so quarantining can't
hide a real regression. A second, independent gate checks every
response's advice text against a `must_not` list (no drug names, no
diagnosis language) — a single violation fails the build regardless of
the accuracy score. A third gate diffs today's output against the
checked-in `fixtures/responses/<prompt_sha>.json` snapshot, catching any
silent behaviour drift even if accuracy alone wouldn't.

- **Passing runs:** `evidence/eval_run.log` — `1.2.0` scores `12/14`
  (`0.857`, passes), `1.3.0-candidate` scores `14/14` (`1.000`), fixing
  exactly the two emergency cases `1.2.0` missed (a pregnant patient with
  heavy bleeding, an infant with a high fever).
- **Deliberate failing run:** `evidence/eval_fail_demo.log` —
  `python eval_prompts.py --version 1.2.0 --simulate-regression` swaps in
  a deliberately broken classifier (ignores every escalation rule, leaks
  a drug name into every response). Result: `1/14` agreement, 15
  `must_not` violations, 15 fixture mismatches, exit code `1` — proving
  the gate fails closed on both an accuracy regression and a safety
  violation, not just one or the other.

## MCP health

`scripts/check_mcp_health.py` does a real stdio handshake (initialize ->
list tools -> call `check_stock`) against `logistics_mcp_versioned.py`
using the official `mcp` SDK's client, and exits non-zero if the
handshake fails, a required tool is missing, or the tool call doesn't
round-trip cleanly.

- **Pass:** `evidence/mcp_health_pass.log` — real handshake against the
  real server, exit `0`.
- **Fail:** `evidence/mcp_health_fail.log` — same probe pointed at
  `scripts/broken_mcp_stub.py` (a deliberately incomplete demo server,
  never wired into the real app), exit `1`, missing-tool names printed.

Run it: `python scripts/check_mcp_health.py` (real server) or
`python scripts/check_mcp_health.py --server scripts/broken_mcp_stub.py`
(demo failure).

## Runbook and Definition of Done

[`runbook.md`](runbook.md) — roll forward/back, where traces live
(`logs/app.log`, `logs/mcp.log`, `tool_metrics.py`), who reviews
clinical-adjacent prompts, the simulated-retrain fallback, the eval
quarantine mechanism, a sprint **Definition of Done** checklist for
prompt/MCP PRs, and a **recommend-against-decide** governance note.
[`clinical_ops_change_brief.md`](clinical_ops_change_brief.md) — the
one-page, non-technical change-control brief for the current
`1.2.0 -> 1.3.0-candidate` canary, in the capstone's own template.

## Fallbacks declared

- [x] **GitHub Actions minutes:** not blocked — pushed to a real repo
  (`pmutua/ci-cd-pipeline-4-versioned-ai-and-mcp-health`) so `ci.yml` runs
  for real on GitHub's runners. `scripts/local_ci_dry_run.sh` +
  `evidence/local_ci_dry_run.log` are kept anyway as the account-agnostic
  fallback the brief asks for.
- [x] **Stub retrain:** `scripts/retrain_stub.py` only bumps
  `config/triage.yaml`'s `model_version` label (`sim-2026.10.0 ->
  sim-2026.10.1`) and appends a `CHANGELOG.md` line stating plainly that
  no weights were trained — no GPU in this environment, see `runbook.md`
  §6. Wired into `ci.yml` as a `workflow_dispatch`-only job, never
  automatic.
- [x] **Local MCP health stub:** `scripts/broken_mcp_stub.py` stands in
  for "no live MCP Inspector / no second real MCP server to break on
  purpose" — same exit-code contract (`scripts/check_mcp_health.py --server
  scripts/broken_mcp_stub.py`) a real broken server would trigger.
- [x] **No paid OpenAI / Azure:** `eval_prompts.py`'s golden-set eval runs
  a deterministic, zero-cost stub classifier (reads the actual prompt
  text, no live model call) — see its module docstring. No Azure account
  was used; `azure-pipelines.yml` is submitted as config-as-code only.
- [x] **No Kubernetes / cloud deploy:** the pipeline ends in
  `docker build` + `docker compose up`, with the image digest recorded
  in `evidence/compose_up.log` and `runbook.md` §1.

## Weeks 6 and 7 reuse

- **`app/`** (`main.py`, `auth.py`, `models.py`, `rate_limit.py`,
  `triage_model.py`, `agent_service.py`) and the **`Dockerfile`** are the
  Week 6 FastAPI + JWT + Docker triage service, carried over via Week 7's
  `cost-optimized-deployment-and-exec-brief/api/` with no logic changes
  to auth, rate limiting, or the agent loop — only `triage_model.py` and
  `app/main.py` were extended (prompt versioning + canary bucketing,
  richer `/health`), and `logistics_mcp_versioned.py` moved from
  `mcp_server/logistics_mcp.py` to the repo root with an added
  `SERVER_VERSION`.
- **Cost/observability hooks:** `docker-compose.yml`'s FinOps labels
  (`finops.cost-center`, `finops.owner`, ...) reuse the exact tag
  vocabulary from Week 7's `deploy/docker-compose.cost.yml`.
- **MCP-aware agent (Week 6):** `app/agent_service.py`'s LangChain/
  LangGraph ReAct agent over the logistics MCP server is unchanged;
  `scripts/check_mcp_health.py` is new (Week 8's health-check
  requirement) and probes the same server the agent already depends on.

## Repo layout

Matches the capstone's target layout; two intentional renames, both
explained above and in `runbook.md`:

- `app/main.py` plays the role the brief's template calls `prompt_app.py`
  — the real Week 6/7 FastAPI service, extended with `/health`'s
  version/SHA reporting, rather than a separate toy file duplicating it.
- `requirements-api.txt` + `requirements.txt` (instead of one file) —
  carried over from Week 7 so the Docker image installs only what the
  running service needs; `requirements.txt` adds `pytest`/`httpx`/`ruff`.

Everything else matches the brief's tree 1:1: `prompts/`, `config/`,
`check_prompt_pin.py`, `evals/`, `fixtures/`, `eval_prompts.py`,
`tests/`, `.github/workflows/ci.yml`, `.github/CODEOWNERS`,
`azure-pipelines.yml`, `logistics_mcp_versioned.py`,
`scripts/check_mcp_health.py`, `clinics.json`, `ab_prompt_flag.py`,
`tool_metrics.py`, `mcp_dashboard_sketch.py`, `CHANGELOG.md`,
`runbook.md`, `clinical_ops_change_brief.md`.

## Checklist

- [x] Tag alignment evidenced — `evidence/compose_up.log`
- [x] Eval fails closed — `evidence/eval_fail_demo.log`
- [x] MCP health in the pipeline — `.github/workflows/ci.yml`'s
  `mcp-health` job, `evidence/mcp_health_pass.log` /
  `evidence/mcp_health_fail.log`
- [x] Runbook and Definition of Done complete — `runbook.md`
- [x] Weeks 6 and 7 reuse documented — above
