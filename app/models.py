# models.py - typed Pydantic request/response models with field constraints
# for every route in app/main.py. Centralised here so the constraints (and
# therefore the 422 behaviour proven in evidence/curl_transcript.md) are
# defined in exactly one place.

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    service: str
    version: str
    status: str


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=100)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TriageRequest(BaseModel):
    patient_message: str = Field(min_length=5, max_length=1000)
    county: str = Field(min_length=2, max_length=40)


class TriageResponse(BaseModel):
    urgency: str
    advice: str
    handled_for: str
    model_used: str


class AskRequest(BaseModel):
    question: str = Field(min_length=5, max_length=500)


class AskResponse(BaseModel):
    question: str
    answer: str
    trace_id: str
    asked_by: str
