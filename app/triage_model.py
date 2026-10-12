# triage_model.py - the actual AI model call behind POST /triage
# (Deliverable 1's "endpoint wrapping an AI model call"). A single,
# small, cheap gpt-4o-mini call per request — this is the "triage calls
# and break-tests" line item in the capstone's own cost budget
# ($0.01-0.05 for 5-15 calls), not the agent's multi-tool loop
# (app/agent_service.py), which is a separate, larger spend.
#
# Configurable-provider pattern reused as-is from the Week 6 Monday lab
# (health_tip_api.py): AI_PROVIDER picks OpenAI or OpenRouter so the same
# code works against either without changes. If no key is configured at
# all, triage_model() raises RuntimeError, which app/main.py turns into an
# honest 503 instead of a raw 500 — the caller did nothing wrong; the
# model behind the API is what's unavailable.

from __future__ import annotations

import json
import os

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError

load_dotenv()

OPENAI_BASE_URL = "https://api.openai.com/v1"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

_provider = os.getenv("AI_PROVIDER", "openai").lower()
_base_url = os.getenv("MODEL_BASE_URL") or (OPENROUTER_BASE_URL if _provider == "openrouter" else OPENAI_BASE_URL)
_key_name = "OPENROUTER_API_KEY" if _provider == "openrouter" else "OPENAI_API_KEY"
_api_key = os.getenv(_key_name)
_model_name = os.getenv("MODEL_NAME", "gpt-4o-mini")

_client = OpenAI(base_url=_base_url, api_key=_api_key) if _api_key else None

SYSTEM_PROMPT = (
    "You are a non-diagnostic community health triage assistant for AfyaPlus "
    "clinics in Kenya. Given a patient's plain-language message, classify "
    "urgency and give brief, safe, non-diagnostic advice. Never diagnose a "
    "condition or name a specific drug or dose. If the message describes an "
    "emergency (e.g. chest pain, severe bleeding, unconsciousness, "
    "difficulty breathing), urgency must be 'high' and advice must tell the "
    "patient to go to the nearest clinic immediately. "
    'Respond with ONLY a JSON object: {"urgency": "low"|"medium"|"high", "advice": "<one or two short sentences>"}.'
)


def triage_model(patient_message: str) -> dict[str, str]:
    """Classify a patient message's urgency and return brief advice.

    Returns {"urgency": ..., "advice": ..., "model_used": ...}.
    Raises RuntimeError if no API key is configured, or on any provider/
    parse failure — app/main.py maps this to an honest 503.
    """
    if _client is None:
        raise RuntimeError(f"{_key_name} is not configured.")
    try:
        response = _client.chat.completions.create(
            model=_model_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": patient_message},
            ],
            max_tokens=120,
            temperature=0,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        parsed = json.loads(content)
        urgency = str(parsed["urgency"]).lower()
        advice = str(parsed["advice"])
    except (OpenAIError, KeyError, ValueError, TypeError) as exc:
        raise RuntimeError(f"Triage model call failed: {exc}") from exc
    if urgency not in {"low", "medium", "high"}:
        urgency = "medium"  # model returned something off-schema; fail toward caution, not toward silence
    return {"urgency": urgency, "advice": advice, "model_used": _model_name}
