"""Minimal JSON fetcher; standard library only, so there are no runtime deps.

Called by every source module's fetch(). Timeout and retries are arguments, not
globals, so tests can fail fast.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any

from .config import settings as default_settings

log = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "next-billion/0.1 (investment pipeline; contact via repo)"}
_RETRYABLE_STATUS = (429, 500, 502, 503, 504)


class FetchError(RuntimeError):
    """Raised when a URL still fails after every retry."""


def get_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float | None = None,
    retries: int | None = None,
) -> Any:
    """GET and parse JSON; retries on 429, 5xx and network errors."""
    timeout = default_settings.http_timeout if timeout is None else timeout
    retries = default_settings.http_retries if retries is None else retries

    request = urllib.request.Request(url, headers={**_HEADERS, **(headers or {})})
    delay = 1.0

    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            if exc.code not in _RETRYABLE_STATUS or attempt == retries:
                raise FetchError(f"{url} -> HTTP {exc.code}") from exc
            log.warning("%s -> HTTP %s, retry %s of %s", url, exc.code, attempt, retries)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            if attempt == retries:
                raise FetchError(f"{url} -> {exc}") from exc
            log.warning("%s -> %s, retry %s of %s", url, exc, attempt, retries)

        time.sleep(delay)
        delay *= 2

    raise FetchError(url)  # unreachable; keeps type checkers happy


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
