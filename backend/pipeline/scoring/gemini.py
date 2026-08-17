"""The call to Gemini, and the one correction turn that follows a bad reply.

No vendor SDK. The API is a JSON POST, so `http.post_json` covers it and the
runtime dependency count stays at zero.

`responseSchema` controls the shape of the reply, so this module never parses
loose text. It checks meaning instead: `validate` compares every citation with
the evidence bundle, and a failure goes back to the model exactly once.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from ..config import GeminiSettings
from ..evidence import Bundle
from ..http import post_json
from ..pacing import Pacer
from . import prompt as prompt_builder
from .validate import Problem, repair_message, validate

# Module level: two runs in one process share the account's allowance.
PACER = Pacer()

log = logging.getLogger(__name__)


class MissingToken(RuntimeError):
    """The API key is not set."""


class ScoringError(RuntimeError):
    """The model produced nothing usable, after the correction turn."""


@dataclass(frozen=True)
class Reply:
    payload: dict
    model: str
    prompt_version: str
    attempts: int
    # Problems that survived the correction turn. The caller drops the claims
    # they name rather than discarding the whole reply.
    problems: tuple[Problem, ...] = ()
    usage: dict = field(default_factory=dict)


def _endpoint(settings: GeminiSettings) -> str:
    return f"{settings.base_url}/{settings.model}:generateContent?key={settings.token}"


def _body(contents: list[dict], settings: GeminiSettings) -> dict:
    return {
        "contents": contents,
        "generationConfig": {
            "temperature": settings.temperature,
            "responseMimeType": "application/json",
            "responseSchema": prompt_builder.response_schema(),
        },
    }


def _reply_text(response: dict) -> str:
    """The answer, with any thinking parts removed.

    A finish reason other than STOP means the answer is cut short, so the JSON
    would parse as broken rather than as wrong. Fail loudly instead.
    """
    candidates = response.get("candidates") or []
    if not candidates:
        blocked = (response.get("promptFeedback") or {}).get("blockReason")
        raise ScoringError(f"no candidate returned (blockReason={blocked})")

    candidate = candidates[0]
    reason = candidate.get("finishReason")
    if reason not in (None, "STOP"):
        raise ScoringError(f"model stopped early: {reason}")

    parts = (candidate.get("content") or {}).get("parts") or []
    text = "".join(p["text"] for p in parts if "text" in p and not p.get("thought"))
    if not text.strip():
        raise ScoringError("model returned an empty answer")
    return text


def _ask(contents: list[dict], settings: GeminiSettings) -> tuple[dict, str, dict]:
    """One round trip. Returns (parsed reply, raw text, usage)."""
    PACER.wait(settings.requests_per_minute)
    response = post_json(
        _endpoint(settings),
        _body(contents, settings),
        timeout=settings.timeout,
        retries=settings.retries,
    )
    text = _reply_text(response)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        # responseSchema should make this impossible. If it happens, the reason
        # is worth seeing rather than retrying blindly.
        raise ScoringError(f"reply was not JSON: {exc}") from exc
    return payload, text, response.get("usageMetadata") or {}


def score(bundle: Bundle, *, settings: GeminiSettings) -> Reply:
    """Score one company. Asks once, then once more if the reply fails checks."""
    if not settings.token:
        raise MissingToken(
            f"{settings.token_env} is not set. Put it in .env at the repo root."
        )

    text = prompt_builder.build(bundle)
    contents = [{"role": "user", "parts": [{"text": text}]}]

    payload, raw, usage = _ask(contents, settings)
    problems = validate(payload, bundle.ids())
    if not problems:
        return Reply(payload, settings.model, prompt_builder.VERSION, 1, (), usage)

    log.info("%s: %d problem(s), asking once more", bundle.name, len(problems))
    contents += [
        {"role": "model", "parts": [{"text": raw}]},
        {"role": "user", "parts": [{"text": repair_message(problems)}]},
    ]
    payload, _, usage = _ask(contents, settings)
    problems = validate(payload, bundle.ids())

    if problems:
        log.warning(
            "%s: %d problem(s) remain after the correction turn", bundle.name, len(problems)
        )
    return Reply(
        payload, settings.model, prompt_builder.VERSION, 2, tuple(problems), usage
    )
