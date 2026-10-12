#!/usr/bin/env bash
# local_ci_dry_run.sh - runs the exact same stage sequence as
# .github/workflows/ci.yml / azure-pipelines.yml (lint_test -> eval ->
# mcp_health -> build), on a laptop with no GitHub Actions minutes and no
# Azure DevOps account, per the capstone's declared fallback path. `set -e`
# so this script itself fails closed, the same way the real pipeline's
# `needs:` / `dependsOn:` chain does -- one stage failing stops the rest.
#
# Run it from the repo root with the venv already created:
#   bash scripts/local_ci_dry_run.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PY=".venv/Scripts/python.exe"
if [ ! -x "$PY" ]; then PY="python"; fi

echo "=== stage: lint_test ==="
"$PY" -m ruff check .
"$PY" check_prompt_pin.py
"$PY" -m pytest tests/ -q

echo ""
echo "=== stage: eval ==="
"$PY" eval_prompts.py --version 1.2.0
"$PY" eval_prompts.py --version 1.3.0-candidate

echo ""
echo "=== stage: mcp_health ==="
"$PY" scripts/check_mcp_health.py

echo ""
echo "=== stage: build ==="
IMAGE_TAG="local-dry-run"
docker build -t afyaplus-platform:"$IMAGE_TAG" --build-arg IMAGE_TAG="$IMAGE_TAG" .
docker images afyaplus-platform

echo ""
echo "=== stage: build (deploy stub) ==="
cp -n .env.example .env || true
docker run -d --rm --name afyaplus-ci-dry-run -p 8000:8000 --env-file .env \
  -e IMAGE_TAG="$IMAGE_TAG" afyaplus-platform:"$IMAGE_TAG"
for i in $(seq 1 10); do
  if curl -sf http://localhost:8000/health; then break; fi
  sleep 2
done
echo ""
docker stop afyaplus-ci-dry-run

echo ""
echo "ALL STAGES PASSED (local dry run)"
