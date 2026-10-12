# Change-control brief (for clinical_ops)

This is a plain-language summary of one change to the AfyaPlus triage
assistant. No code, no YAML - just what changed, what we checked, and how
to undo it if something looks wrong.

**What changed:** The message AfyaPlus's AI assistant reads before
answering a patient ("the triage prompt") was updated from version
**1.2.0 to a candidate version 1.3.0**, currently shown to **10% of
staging user accounts** only - not everyone, and not production patients.
The new version is stricter about two situations the old version
sometimes under-called: a pregnant patient reporting heavy bleeding, and
an infant with a very high fever. Both now get flagged as urgent
automatically, where before they could be marked as lower priority. It
also leans toward "see a clinician soon" instead of "rest at home" when a
message is genuinely too vague to tell.

**What was tested:** We ran a fixed set of 15 realistic patient messages
with pre-agreed correct urgency labels (`evals/golden.jsonl`) through both
the old and new prompt. The new version matched the correct label on
**14 out of 14** scored messages (one message is set aside - a clinician
disagreement over a borderline case, tracked separately, not hidden). The
old version matched **12 out of 14**, missing exactly the two emergency
cases described above. We also checked that neither version's advice
ever names a specific drug or gives a diagnosis - zero violations, both
versions. The automated system that ran this check (`eval_prompts.py`)
prints an `eval_score` and fails the build outright if a future change
drops below our agreed floor of 85% agreement - see "Go or no-go" below.

**Rollback:** If anything looks wrong after this ships, set the
environment variable `PROMPT_VERSION=1.2.0` on the running service (no
code change, no new image, no redeploy - just that one setting) and every
request immediately goes back to the old prompt. The underlying image and
git tag (`v1.2.0`) are unchanged and still available if a full revert is
ever needed.

**Who approved:** Requires sign-off from **CODEOWNERS: clinical_ops and
ml-eng** on the pull request before it can merge (enforced by
`.github/CODEOWNERS` + branch protection - not optional, not
self-approvable). PR #__ (fill in at submission time).

**Go or no-go:**

- **Go** if all three hold: the automated eval is green (≥85% agreement,
  zero unsafe-content violations), the MCP handshake check lists
  `check_stock` among the tools it finds (proving the logistics assistant
  can actually reach stock data, not just answer from guesswork), and the
  observed error rate for triage requests stays under **10%**.
- **No-go** - and automatic rollback per the lever above - if the eval
  drops below 85%, a forbidden term (a named drug or a diagnosis) appears
  in any response, the MCP handshake fails or is missing a required
  tool, or the error rate crosses 10%.

As of this brief, all three "go" conditions hold: eval is green (see
`evidence/eval_run.log`), the MCP handshake lists `check_stock` (see
`evidence/mcp_health_pass.log`), and no error-rate data yet exists
because the candidate has not been exposed to production traffic - only
staging, per the 10% canary above.
