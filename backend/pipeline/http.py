"""Minimal JSON fetcher; standard library only, so there are no runtime deps.

Called by every source module's fetch(). Timeout and retries are arguments, not
globals, so tests can fail fast.
"""
from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.request
from typing import Any

from .config import settings as default_settings

log = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "next-billion/0.1 (investment pipeline; contact via repo)"}
_RETRYABLE_STATUS = (429, 500, 502, 503, 504)

# Gemini takes its key in the query string, and every retry logs the URL. A
# rate-limited run would otherwise print the key on each attempt.
_SECRET_PARAM = re.compile(r"([?&](?:key|api_key|token|access_token)=)[^&\s]*", re.I)


def safe_url(url: str) -> str:
    """A URL fit for a log line or an error message."""
    return _SECRET_PARAM.sub(r"\1<redacted>", url)


_RETRY_DELAY = re.compile(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"')
_DAILY_QUOTA = re.compile(r'"quotaId"\s*:\s*"[^"]*PerDay[^"]*"')
MAX_BACKOFF = 65.0


def is_daily_quota(body: str) -> bool:
    """Does this refusal name a per-day ceiling?

    A per-minute window refills, so waiting works. A day does not refill inside
    a run, so each retry spends another request from the allowance that just
    ran out. Four retries for 15 companies is 60 requests bought for nothing.
    """
    return bool(_DAILY_QUOTA.search(body))


class FetchError(RuntimeError):
    """Raised when a URL still fails after every retry.

    `status` carries the HTTP code so a caller can act on it. Matching on the
    message text instead would break the moment the wording changed.
    """

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _reason(body: str) -> str:
    """The API's own explanation, short enough for one log line.

    The quota ids are appended because they say *which* ceiling was reached.
    Truncating the body hid them once, and the run could not be diagnosed.
    """
    try:
        error = json.loads(body)["error"]
    except (ValueError, KeyError, TypeError):
        return body.strip()[:200]

    text = " ".join(str(error.get("message", "")).split())[:160]
    quotas = sorted({
        violation.get("quotaId", "")
        for detail in error.get("details", [])
        if detail.get("@type", "").endswith("QuotaFailure")
        for violation in detail.get("violations", [])
    } - {""})
    return f"{text} [{', '.join(quotas)}]" if quotas else text


def _retry_after(exc: urllib.error.HTTPError, body: str) -> float:
    """How long the server asked us to wait, in seconds.

    Google returns it as a RetryInfo entry in the body rather than a header,
    so the header alone finds nothing on a Gemini 429.
    """
    header = exc.headers.get("Retry-After") if exc.headers else None
    if header and header.strip().isdigit():
        return min(float(header.strip()), MAX_BACKOFF)
    found = _RETRY_DELAY.search(body)
    return min(float(found.group(1)), MAX_BACKOFF) if found else 0.0


def _json_with_retry(
    url: str,
    *,
    data: bytes | None,
    headers: dict[str, str] | None,
    timeout: float | None,
    retries: int | None,
) -> Any:
    """The retry ladder both verbs share. data=None sends a GET.

    Body text is read out of an HTTPError before it is discarded: an API that
    refuses a request usually explains why, and that reason is worth logging.
    """
    timeout = default_settings.http_timeout if timeout is None else timeout
    retries = default_settings.http_retries if retries is None else retries

    request = urllib.request.Request(
        url, data=data, headers={**_HEADERS, **(headers or {})}
    )
    delay = 1.0

    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            detail = _reason(body)
            if (exc.code not in _RETRYABLE_STATUS
                    or attempt == retries
                    or is_daily_quota(body)):
                raise FetchError(
                    f"HTTP {exc.code} from {safe_url(url)}: {detail}", status=exc.code
                ) from exc
            log.warning("HTTP %s from %s, retry %s of %s: %s",
                        exc.code, safe_url(url), attempt, retries, detail)
            # A rate limiter knows when it will let us back in; our own guess
            # of one second never does. Prefer the server's number.
            delay = max(delay, _retry_after(exc, body))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            if attempt == retries:
                raise FetchError(f"{safe_url(url)} -> {exc}") from exc
            log.warning("%s -> %s, retry %s of %s", safe_url(url), exc, attempt, retries)

        time.sleep(delay)
        delay *= 2

    raise FetchError(url)  # unreachable; keeps type checkers happy


def get_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float | None = None,
    retries: int | None = None,
) -> Any:
    """GET and parse JSON; retries on 429, 5xx and network errors."""
    return _json_with_retry(
        url, data=None, headers=headers, timeout=timeout, retries=retries
    )


def post_json(
    url: str,
    payload: dict,
    *,
    headers: dict[str, str] | None = None,
    timeout: float | None = None,
    retries: int | None = None,
) -> Any:
    """POST JSON and parse the JSON reply; same retry rules as get_json.

    Exists so the Gemini call needs no vendor SDK. A 429 or a 503 from a free
    tier is normal, and the shared ladder already backs off on both.
    """
    return _json_with_retry(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        timeout=timeout,
        retries=retries,
    )


def get_text(url: str, *, headers: dict[str, str] | None = None,
             timeout: float | None = None) -> str:
    """GET a URL and return the body as text. Used for HTML pages.

    Returns "" on any failure: a missing company page is a normal outcome,
    not an error worth aborting a run for.
    """
    timeout = default_settings.http_timeout if timeout is None else timeout
    request = urllib.request.Request(url, headers={**_HEADERS, **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001 - deliberately broad, see docstring
        log.warning("%s -> %s", url, exc)
        return ""
