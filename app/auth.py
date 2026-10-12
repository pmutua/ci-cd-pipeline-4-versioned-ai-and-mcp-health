# auth.py - JWT authentication module shared by every protected route in
# this service (app/main.py's /triage and /ask-logistics both depend on
# current_user). One module, imported everywhere auth is needed, so the
# agent endpoint (Deliverable 4) enforces exactly the same rules as the
# triage endpoint (Deliverable 1) instead of re-implementing them.
#
# JWT_SECRET is read from the environment (.env, loaded via python-dotenv)
# with a dev-only fallback so the module still imports for a first read
# without secrets configured. The fallback must never be relied on outside
# a laptop demo — see Dockerfile / docs/STAKEHOLDER_MEMO.md for how a real
# deployment injects a real secret at runtime instead.

from __future__ import annotations

import os
import time

import bcrypt
import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

load_dotenv()

SECRET_KEY = os.getenv("JWT_SECRET", "dev-only-secret-please-change-me-32chars!")
ALGORITHM = "HS256"
TOKEN_LIFETIME_SECONDS = 30 * 60  # 30 minutes

# Two demo accounts, matching the two roles the API distinguishes between:
#   - mercy (coordinator): may triage patients and request reorders
#   - guest (viewer): may authenticate and ask read-only questions, but a
#     valid guest token still earns a 403 on /triage — see
#     evidence/curl_transcript.md for the 401 -> 403 -> 200 ladder.
# Passwords are hashed at import time; the plaintext is never stored.
USERS: dict[str, dict[str, object]] = {
    "mercy": {
        "password_hash": bcrypt.hashpw(b"logistics2026", bcrypt.gensalt()),
        "role": "coordinator",
    },
    "guest": {
        "password_hash": bcrypt.hashpw(b"lookaround", bcrypt.gensalt()),
        "role": "viewer",
    },
}


def check_password(username: str, password: str) -> bool:
    user = USERS.get(username)
    if user is None:
        return False
    return bcrypt.checkpw(password.encode(), user["password_hash"])


def create_token(username: str) -> str:
    payload = {
        "sub": username,
        "role": USERS[username]["role"],
        "exp": int(time.time()) + TOKEN_LIFETIME_SECONDS,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


bearer = HTTPBearer()


def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    """FastAPI dependency: verifies the Bearer token before the endpoint body runs.

    A missing Authorization header is rejected by HTTPBearer itself (401)
    before this function is even called. A present-but-bad token (expired,
    or altered so its signature no longer matches) is turned into a clean
    401 here instead of leaking a jwt.decode exception as an unhandled 500.
    """
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired. Log in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token.")
    return payload


def require_role(role: str):
    """Dependency factory: current_user() answers WHO is calling; this
    answers what that identity is ALLOWED to do. A valid token for the
    wrong role earns 403, not 401 — those are different failures with
    different fixes."""

    def _check(user: dict = Depends(current_user)) -> dict:
        if user["role"] != role:
            raise HTTPException(status_code=403, detail=f"Your role may not use this endpoint (requires '{role}').")
        return user

    return _check
