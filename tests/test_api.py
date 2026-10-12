# test_api.py - offline, repeatable proof of Deliverable 1's 200/401/403/422
# behaviour (curl evidence lives in evidence/curl_transcript.md; this is the
# fast version that runs in CI without a live server or network access).
# app.triage_model.triage_model is monkeypatched so these tests never make
# a real, billed API call -- same "monkeypatch the model" pattern as the
# Week 6 Monday lab's further_challenge_a_timeout.py.

from __future__ import annotations

import app.main as main_module
from fastapi.testclient import TestClient

client = TestClient(main_module.app)


def _login(username: str, password: str) -> str:
    resp = client.post("/token", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_health_is_unprotected() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "afyaplus-service-platform"
    assert body["status"] == "ok"


def test_triage_without_token_is_401() -> None:
    resp = client.post("/triage", json={"patient_message": "I feel unwell", "county": "Kisumu"})
    assert resp.status_code == 401


def test_token_with_invalid_body_is_422() -> None:
    # password shorter than models.LoginRequest's min_length=6
    resp = client.post("/token", json={"username": "mercy", "password": "ab"})
    assert resp.status_code == 422


def test_token_with_wrong_password_is_401() -> None:
    resp = client.post("/token", json={"username": "mercy", "password": "wrongpassword"})
    assert resp.status_code == 401


def test_triage_with_guest_token_is_403() -> None:
    token = _login("guest", "lookaround")
    resp = client.post(
        "/triage",
        json={"patient_message": "I feel unwell", "county": "Kisumu"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_triage_with_coordinator_token_is_200(monkeypatch) -> None:
    monkeypatch.setattr(
        main_module,
        "triage_model",
        lambda message: {"urgency": "low", "advice": "Rest and drink fluids.", "model_used": "stub-for-test"},
    )
    token = _login("mercy", "logistics2026")
    resp = client.post(
        "/triage",
        json={"patient_message": "I feel a bit tired", "county": "Kisumu"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["urgency"] == "low"
    assert body["handled_for"] == "mercy"


def test_triage_request_too_short_is_422() -> None:
    token = _login("mercy", "logistics2026")
    resp = client.post(
        "/triage",
        json={"patient_message": "hi", "county": "Kisumu"},  # below min_length=5
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_triage_model_unavailable_is_503(monkeypatch) -> None:
    def _boom(message: str) -> dict[str, str]:
        raise RuntimeError("OPENAI_API_KEY is not configured.")

    monkeypatch.setattr(main_module, "triage_model", _boom)
    token = _login("mercy", "logistics2026")
    resp = client.post(
        "/triage",
        json={"patient_message": "I feel unwell", "county": "Kisumu"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 503
