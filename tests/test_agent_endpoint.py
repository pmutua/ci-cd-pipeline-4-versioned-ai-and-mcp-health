# test_agent_endpoint.py - offline proof that POST /ask-logistics reuses
# app.auth's current_user dependency (401 without a token) and returns the
# agent's answer shape when authenticated. app.main.run_logistics_agent is
# monkeypatched so this test never spawns the MCP subprocess or makes a
# real, billed model call -- the real transcripts live in
# evidence/agent_transcript.md.

from __future__ import annotations

from fastapi.testclient import TestClient

import app.main as main_module

client = TestClient(main_module.app)


def _login(username: str, password: str) -> str:
    resp = client.post("/token", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_ask_logistics_without_token_is_401() -> None:
    resp = client.post("/ask-logistics", json={"question": "Which clinics need a reorder?"})
    assert resp.status_code == 401


async def _fake_agent(question: str, trace_id: str | None = None) -> str:
    return f"stub answer for: {question}"


def test_ask_logistics_with_token_returns_answer(monkeypatch) -> None:
    monkeypatch.setattr(main_module, "run_logistics_agent", _fake_agent)
    token = _login("mercy", "logistics2026")
    resp = client.post(
        "/ask-logistics",
        json={"question": "Which clinics need an amoxicillin reorder?"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["asked_by"] == "mercy"
    assert "trace_id" in body
    assert body["answer"].startswith("stub answer for:")


def test_ask_logistics_question_too_short_is_422() -> None:
    token = _login("mercy", "logistics2026")
    resp = client.post(
        "/ask-logistics",
        json={"question": "hi"},  # below min_length=5
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
