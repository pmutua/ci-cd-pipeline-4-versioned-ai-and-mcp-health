# main.py - the AfyaPlus Service Platform's FastAPI app. This plays the
# role the capstone template calls prompt_app.py: it is the real Week 6/7
# FastAPI + Docker + JWT service (api/app/main.py, reused unchanged in
# structure), extended for Week 8 so GET /health reports the live prompt
# version + SHA-256, the candidate canary (if any), the MCP server
# version, and the image tag - the "versions visible at runtime" evidence
# Deliverable 1 asks for, read straight from app/prompt_loader.py and
# config/triage.yaml rather than hardcoded here.
#
# Routes:
#   GET  /health           - unprotected; monitoring probes don't log in
#   POST /token             - login, returns a signed JWT
#   POST /triage             - protected + role-gated (coordinator only)
#   POST /ask-logistics       - protected; runs the LangChain/MCP agent
#
# Run it:
#   uvicorn app.main:app --reload --port 8000

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException

from app.agent_service import run_logistics_agent
from app.auth import check_password, create_token, current_user, require_role
from app.models import (
    AskRequest,
    AskResponse,
    HealthResponse,
    LoginRequest,
    TokenResponse,
    TriageRequest,
    TriageResponse,
)
from app.prompt_loader import active_prompt_info, load_config
from app.rate_limit import check_rate_limit
from app.triage_model import triage_model

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = REPO_ROOT / "logs" / "app.log"
LOG_PATH.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler()],
)
log = logging.getLogger("afyaplus_api")

SERVICE_NAME = "afyaplus-service-platform"
SERVICE_VERSION = "1.0.0"

app = FastAPI(title="AfyaPlus Service Platform", version=SERVICE_VERSION)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    cfg = load_config()
    prompts = active_prompt_info()
    candidate = prompts.get("candidate")
    return HealthResponse(
        service=SERVICE_NAME,
        version=SERVICE_VERSION,
        status="ok",
        image_tag=os.getenv("IMAGE_TAG", "dev"),
        prompt_version=prompts["active"]["version"],
        prompt_sha256=prompts["active"]["sha256"],
        candidate_prompt_version=candidate["version"] if candidate else None,
        candidate_traffic_percent=prompts.get("candidate_traffic_percent") if candidate else None,
        model_version=cfg["model_version"],
        mcp_server_version=cfg["mcp_server_version"],
    )


@app.post("/token", response_model=TokenResponse)
def login(body: LoginRequest) -> TokenResponse:
    if not check_password(body.username, body.password):
        raise HTTPException(status_code=401, detail="Wrong username or password.")
    return TokenResponse(access_token=create_token(body.username))


@app.post("/triage", response_model=TriageResponse)
def triage(request: TriageRequest, user: dict = Depends(require_role("coordinator"))) -> TriageResponse:
    # require_role already proved WHO is calling (401 otherwise) and that
    # their role may use this route (403 otherwise) before this body runs.
    check_rate_limit(user["sub"])
    try:
        # user["sub"] is the canary bucketing key: the same coordinator
        # always lands on the same side of a prompt rollout (see
        # app/prompt_loader.resolve_prompt_version).
        result = triage_model(request.patient_message, user_key=user["sub"])
    except RuntimeError as exc:
        # The caller's request was fine; the model behind us is what
        # broke (missing key, provider outage, off-schema response) - a
        # 503 the caller can retry, not a raw 500 they can't act on.
        log.info("route=/triage user=%s status=model_unavailable", user["sub"])
        raise HTTPException(status_code=503, detail=f"The AI model is unavailable. Try again shortly. ({exc})")
    log.info(
        "route=/triage user=%s county=%s urgency=%s prompt_version=%s",
        user["sub"],
        request.county,
        result["urgency"],
        result["prompt_version"],
    )
    return TriageResponse(
        urgency=result["urgency"],
        advice=result["advice"],
        handled_for=user["sub"],
        model_used=result["model_used"],
        prompt_version=result["prompt_version"],
        prompt_sha256=result["prompt_sha256"],
    )


@app.post("/ask-logistics", response_model=AskResponse)
async def ask_logistics(body: AskRequest, user: dict = Depends(current_user)) -> AskResponse:
    # trace_id is generated at the door and threaded into the agent call
    # and this end-of-request log line, then correlated against
    # logistics_mcp_versioned.py's own log lines by timestamp.
    trace_id = uuid4().hex[:8]
    started = time.perf_counter()
    try:
        answer = await run_logistics_agent(body.question, trace_id=trace_id)
        return AskResponse(question=body.question, answer=answer, trace_id=trace_id, asked_by=user["sub"])
    finally:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        # Metadata only, never the question text itself - questions can
        # carry sensitive logistics/health context.
        log.info(
            "route=/ask-logistics trace=%s user=%s ms=%s question_chars=%s",
            trace_id,
            user["sub"],
            elapsed_ms,
            len(body.question),
        )
