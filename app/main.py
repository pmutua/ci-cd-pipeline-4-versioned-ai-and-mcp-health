# main.py - the AfyaPlus Service Platform's FastAPI app (Deliverable 1 +
# the authenticated agent endpoint from Deliverable 4). One app, one auth
# module (app/auth.py) enforced identically on every protected route.
#
# Routes:
#   GET  /health           - unprotected; monitoring probes don't log in
#   POST /token             - login, returns a signed JWT
#   POST /triage             - protected + role-gated (coordinator only)
#   POST /ask-logistics       - protected; runs the LangChain/MCP agent
#
# Run it:
#   uvicorn app.main:app --reload --port 8000
#
# Prove all four outcomes with curl (see evidence/curl_transcript.md for
# the captured run):
#   1. No token on /triage           -> 401
#   2. Bad body on /token             -> 422
#   3. guest token on /triage          -> 403
#   4. mercy token on /triage           -> 200

from __future__ import annotations

import logging
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
    return HealthResponse(service=SERVICE_NAME, version=SERVICE_VERSION, status="ok")


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
        result = triage_model(request.patient_message)
    except RuntimeError as exc:
        # The caller's request was fine; the model behind us is what
        # broke (missing key, provider outage, off-schema response) — a
        # 503 the caller can retry, not a raw 500 they can't act on.
        log.info("route=/triage user=%s status=model_unavailable", user["sub"])
        raise HTTPException(status_code=503, detail=f"The AI model is unavailable. Try again shortly. ({exc})")
    log.info("route=/triage user=%s county=%s urgency=%s", user["sub"], request.county, result["urgency"])
    return TriageResponse(
        urgency=result["urgency"],
        advice=result["advice"],
        handled_for=user["sub"],
        model_used=result["model_used"],
    )


@app.post("/ask-logistics", response_model=AskResponse)
async def ask_logistics(body: AskRequest, user: dict = Depends(current_user)) -> AskResponse:
    # trace_id is generated at the door and threaded into the agent call
    # and this end-of-request log line, then correlated against
    # mcp_server/logistics_mcp.py's own log lines by timestamp — see
    # docs/TRACE_RECONSTRUCTION.md for a worked example.
    trace_id = uuid4().hex[:8]
    started = time.perf_counter()
    try:
        answer = await run_logistics_agent(body.question, trace_id=trace_id)
        return AskResponse(question=body.question, answer=answer, trace_id=trace_id, asked_by=user["sub"])
    finally:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        # Metadata only, never the question text itself — questions can
        # carry sensitive logistics/health context.
        log.info(
            "route=/ask-logistics trace=%s user=%s ms=%s question_chars=%s",
            trace_id,
            user["sub"],
            elapsed_ms,
            len(body.question),
        )
