# LLMOps Runbook - AfyaPlus Triage CI/CD

Audience: whoever is on call when a prompt or MCP change needs to roll
forward or back. Written so a reasonably careful engineer who has never
seen this repo before can follow it at 01:00.

## 1. What's versioned, and where

| Thing | Where | Current |
|---|---|---|
| Triage system prompt | `prompts/triage_system_v<version>.txt`, pinned in `prompts/pin.json` | active `1.2.0`, candidate `1.3.0-candidate` |
| Serving config (model, limits, which prompt is active, canary %) | `config/triage.yaml` | `prompt_version: "1.2.0"`, canary 10% -> `1.3.0-candidate` |
| MCP server | `logistics_mcp_versioned.py` (`SERVER_VERSION`) | `1.0.0` |
| Simulated model generation | `config/triage.yaml`'s `model_version` (bumped only by `scripts/retrain_stub.py` - see §6) | `sim-2026.10.1` |
| Service/image | `app/main.py`'s `SERVICE_VERSION`; Docker image tag = git tag | `1.0.0` service, image tag tracks the git tag being released |
| All of the above, live | `GET /health` | reports every row in this table at once |

Tag alignment: a release is "the git tag, the image tag, and the prompt
bundle all point at the same state." In practice: tag the commit
(`git tag v1.3.0-candidate`), build the image with that same string as
`IMAGE_TAG` (`docker build --build-arg IMAGE_TAG=v1.3.0-candidate ...`,
or `IMAGE_TAG=v1.3.0-candidate docker compose up --build`), and confirm
`GET /health`'s `image_tag` and `prompt_version`/`candidate_prompt_version`
match what you intended to ship. `evidence/compose_up.log` captures exactly
this for the `v1.3.0-candidate` release: image digest
`sha256:79e4e04eb07338712cc492ad901d178498ee876de800bc47b48d63912c4eab39`,
`/health` reporting `"image_tag":"v1.3.0-candidate"`,
`"prompt_version":"1.2.0"`, `"candidate_prompt_version":"1.3.0-candidate"`.

## 2. Roll forward (ship a new or candidate prompt)

1. Add `prompts/triage_system_v<new>.txt`. Never edit an existing pinned
   file in place - a prompt version is immutable once tagged.
2. Add its SHA-256 to `prompts/pin.json` (`python -c "import hashlib,
   sys; print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())"
   prompts/triage_system_v<new>.txt`).
3. Generate its fixture: `python eval_prompts.py --version <new>
   --write-fixtures`, then review the fixture diff by eye - this is the
   human-reviewed "golden" snapshot future runs are checked against.
4. Point `config/triage.yaml`'s `canary.candidate_prompt_version` at it,
   pick `candidate_traffic_percent` (10% is the current convention - see
   `clinical_ops_change_brief.md`).
5. Open a PR. CODEOWNERS (`.github/CODEOWNERS`) requires clinical_ops +
   ml-eng sign-off on anything under `prompts/`, `config/`,
   `logistics_mcp_versioned.py`, `clinics.json`, or `evals/`.
6. CI must go green in order: `lint-test` -> `eval` (both the active and
   candidate versions) -> `mcp-health` -> `build`. Any stage failing
   blocks the merge - see §4.
7. Merge to `main`. Tag the release (`git tag v<new>`) and build/deploy
   with `IMAGE_TAG=v<new>` so the image tag matches.
8. Watch the candidate's real-traffic share and error rate (see §5) for
   at least one full day before raising `candidate_traffic_percent`
   further or promoting it to `prompt_version`.

## 3. Roll back

Fastest safe lever, no new image needed: set `PROMPT_VERSION=<known-good>`
in the running environment (env var, not a file edit) and restart the
process. `app/prompt_loader.resolve_prompt_version` checks this env var
*before* consulting the canary config or `config/triage.yaml` at all, so
it overrides everything, instantly, for every caller - this is exactly
what `clinical_ops_change_brief.md`'s "Rollback: set
`PROMPT_VERSION=1.2.0`" line means in practice.

If the canary itself is the problem (not just the candidate prompt text),
set `config/triage.yaml`'s `candidate_traffic_percent: 0` and merge that
as its own PR - this is a config change, so it still goes through
CODEOWNERS + CI like any other.

To fully revert a bad release: `git revert` the merge commit (don't force
anything on `main`), then re-tag and redeploy the previous image tag.

## 4. When CI fails

| Stage | What a failure means | What to do |
|---|---|---|
| `lint-test` | ruff, `check_prompt_pin.py`, or `pytest` failed | `check_prompt_pin.py` failing specifically means a pinned prompt file was edited without a version bump - see `evidence/eval_run.log` vs a tampered file for what that looks like; fix the pin or the file, don't force past it |
| `eval` | urgency agreement dropped below `0.85`, a `must_not` term leaked into advice, or output drifted from the recorded fixture | Read the printed report (`eval_prompts.py`'s stdout lists every miss/violation by golden id). `evidence/eval_fail_demo.log` is a worked example (`--simulate-regression`) of exactly this failure mode |
| `mcp-health` | the MCP server didn't complete the stdio handshake, was missing a required tool, or `check_stock` didn't round-trip | `evidence/mcp_health_fail.log` is a worked example against a deliberately broken stub (`scripts/broken_mcp_stub.py`) - same failure shape to expect from a real break |
| `build` | image failed to build, or `/health` never came up after `docker run`/`compose up` | check the Dockerfile layer that changed; `evidence/local_ci_dry_run.log` and `evidence/compose_up.log` are known-good runs to diff against |

No stage is skippable to "just ship it" - `needs:`/`dependsOn:` in
`.github/workflows/ci.yml` / `azure-pipelines.yml` enforces the order, and
there is no manual override path other than fixing the thing that failed.

## 5. Observability: where traces live

- `logs/app.log` - one line per `/triage` and `/ask-logistics` call
  (user, county/question length, urgency, **prompt_version used**), and
  one line per model-unavailable 503.
- `logs/mcp.log` - one line per MCP tool/resource call
  (`logistics_mcp_versioned.py`), correlated to an API-level request by
  the `trace_id` `app/main.py` generates per `/ask-logistics` call (exact
  correlation method: timestamp proximity between the two log files -
  MCP's protocol doesn't carry a caller-supplied trace id through to the
  tool function itself, so this is an approximation, not a guarantee).
- `tool_metrics.py` - in-memory counters for MCP tool calls and prompt
  variant usage (active vs. candidate), for the life of one process.
  `python mcp_dashboard_sketch.py --demo` renders them. In-memory only:
  restarting the process, or running more than one replica, loses/splits
  the counts - see `levers`/FinOps notes inherited from Week 7 for what a
  real deployment would need instead (a shared metrics backend).
- `error_rate` (the number in the change brief's go/no-go line) is read
  off `logs/app.log`'s 503 rate for `/triage` over the observation
  window - there is no separate error-rate service in this lab-scale
  setup; a real deployment would export this as a proper metric.

## 6. Simulated retrain (no GPU)

`scripts/retrain_stub.py` is the capstone's documented GPU fallback: it
reads no training data and touches no model weights. It only bumps
`config/triage.yaml`'s `model_version` label and appends one line to
`CHANGELOG.md` that explicitly says "no weights were trained." It is
wired into `.github/workflows/ci.yml` as a `workflow_dispatch`-only job
(`simulate_retrain: true`) - never on a normal push or PR, the same way a
real retrain job should require an explicit human trigger, not an
automatic one.

## 7. Eval quarantine

`fixtures/quarantine.json` lists golden-set ids excluded from the
pass/fail threshold because a human reviewer disputes the label (see its
`reason`/`owner` fields). Quarantined ids are still run and reported on
every CI pass - `eval_prompts.py`'s "quarantined (not scored)" line - so
quarantining an id cannot be used to silently hide a real regression; it
only removes that one disputed case from the score until a clinician
resolves it.

## 8. Who reviews clinical-adjacent prompts

Anything touching `prompts/`, `config/`, `logistics_mcp_versioned.py`,
`clinics.json`, or `evals/` requires sign-off from both **clinical_ops**
(the message/advice/urgency wording itself - this is patient-facing
clinical content) and **ml-eng** (the mechanics: eval gate, canary
wiring, rollback levers). `.github/CODEOWNERS` encodes this; in this
single-maintainer repo both roles collapse to `@pmutua` (documented there
as a stand-in, not a recommendation to actually self-review a clinical
change in a real org - see §9).

## 9. Governance note: recommend, don't decide

This pipeline is built to make a prompt or MCP change **safe to review**,
not to make the review unnecessary. Three ways that distinction is
enforced here, deliberately:

- The eval gate (`eval_prompts.py`) can only say "this candidate agrees
  with the labelled golden set at X%" - it cannot say "this candidate is
  clinically correct." The golden set's labels are themselves a human
  judgment call (see the quarantined case in §7) that this pipeline
  assumes was made correctly, not one it can verify.
- The canary (`ab_prompt_flag.py`) limits *how many* patients see an
  unreviewed-at-scale prompt change, but every canary bucket result is
  still a live clinical interaction with a real patient, not a sandboxed
  test.
- CODEOWNERS requires a named human to approve before merge. No score
  this pipeline produces - agreement %, MCP handshake pass, error rate -
  is wired to auto-merge or auto-promote a canary to 100%. A human
  reads the PR's CI results and the change brief, and decides.

For AfyaPlus specifically: an AI system recommending urgency and advice
to a community health triage flow is exactly the kind of decision that
should stay a clinician's call, assisted by tooling, not a model's call,
checked by tooling after the fact. This pipeline's job is to make the
"before" cheap and evidenced (version pinned, eval score visible, MCP
verified, rollback one env var away) so the human reviewing it can decide
quickly and with real information - never to make the decision for them.

## 10. Sprint Definition of Done - prompt and MCP pull requests

A PR touching `prompts/`, `config/`, `logistics_mcp_versioned.py`,
`clinics.json`, or `evals/` is **not** done until every box below is
checked - not as a formality, but because each one maps to a specific
way this kind of change has gone wrong elsewhere (silent prompt drift,
an unreviewed clinical-wording change, an MCP tool silently dropped).

- [ ] Every new/changed prompt file has a bumped version string in its
      filename (`triage_system_v<version>.txt`) - never edited in place.
- [ ] `prompts/pin.json` updated with the new file's SHA-256;
      `python check_prompt_pin.py` passes.
- [ ] `python eval_prompts.py --version <new> --write-fixtures` run once,
      and the fixture diff reviewed by eye (not just regenerated and
      forgotten).
- [ ] `python eval_prompts.py --version <new>` passes: agreement ≥ 0.85
      against `evals/golden.jsonl`, zero `must_not` violations, zero
      fixture mismatches.
- [ ] If this PR changes `logistics_mcp_versioned.py`:
      `python scripts/check_mcp_health.py` passes against the changed
      server, and `pytest tests/test_mcp_tools.py -v` passes.
- [ ] `config/triage.yaml` changes (prompt_version, canary block,
      mcp_server_version) are consistent with what `GET /health` will
      report - spot-check with a local run.
- [ ] CODEOWNERS review from **both** clinical_ops (wording/clinical
      correctness) and ml-eng (mechanics) obtained - not just one.
- [ ] `CHANGELOG.md` has a new entry describing the change in plain
      language, including the rollback lever if this is a canary.
- [ ] If this is a canary rollout: `clinical_ops_change_brief.md` updated
      with the new traffic %, the eval numbers, and the go/no-go
      thresholds - same template as this repo's own.
- [ ] CI (`lint-test` -> `eval` -> `mcp-health` -> `build`) is green on
      the PR, not just locally.
