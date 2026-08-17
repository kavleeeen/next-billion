"""A URL goes into every log line and every error message. The Gemini key
travels in that URL, so it must never be written out.

The backoff is tested too. The first live run gave up after about three
seconds against a per-minute quota, so all three companies failed. Guessing a
delay does not work when the server states one.
"""
from __future__ import annotations

import json
import urllib.error

import pytest

from pipeline.http import MAX_BACKOFF, _reason, _retry_after, safe_url

QUOTA_BODY = json.dumps({
    "error": {
        "code": 429,
        "message": "You exceeded your current quota, please check your plan and billing details.",
        "details": [
            {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
             "violations": [
                 {"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"},
                 {"quotaId": "GenerateContentInputTokensPerModelPerMinute-FreeTier"},
             ]},
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "10.3s"},
        ],
    }
})

KEYED_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-3.6-flash:generateContent?key=AIzaSyREDACTEDSECRETVALUE123"
)


class TestSafeUrl:
    def test_the_key_is_removed(self):
        out = safe_url(KEYED_URL)
        assert "AIzaSyREDACTEDSECRETVALUE123" not in out
        assert "key=<redacted>" in out

    def test_the_rest_of_the_url_survives(self):
        out = safe_url(KEYED_URL)
        assert "gemini-3.6-flash:generateContent" in out

    @pytest.mark.parametrize("param", ["key", "api_key", "token", "access_token", "API_KEY"])
    def test_every_secret_parameter_name(self, param):
        assert "s3cret" not in safe_url(f"https://x.test/a?{param}=s3cret")

    def test_a_secret_between_other_parameters(self):
        out = safe_url("https://x.test/a?alt=json&key=s3cret&pretty=1")
        assert "s3cret" not in out
        assert "alt=json" in out and "pretty=1" in out

    def test_a_url_with_no_secret_is_unchanged(self):
        url = "https://hn.algolia.com/api/v1/search?tags=story"
        assert safe_url(url) == url


class TestReason:
    def test_the_message_is_kept(self):
        assert "exceeded your current quota" in _reason(QUOTA_BODY)

    def test_the_quota_ids_are_named(self):
        # Which ceiling was reached is the whole diagnosis. Truncating the
        # body hid these once, and the run could not be explained.
        out = _reason(QUOTA_BODY)
        assert "GenerateRequestsPerMinutePerProjectPerModel-FreeTier" in out
        assert "GenerateContentInputTokensPerModelPerMinute-FreeTier" in out

    def test_a_body_that_is_not_json_still_reports_something(self):
        assert _reason("<html>502 Bad Gateway</html>").startswith("<html>")

    def test_an_empty_body_does_not_raise(self):
        assert _reason("") == ""


class _Err(urllib.error.HTTPError):
    def __init__(self, headers=None):
        self.headers = headers or {}
        self.code = 429


class TestRetryAfter:
    def test_the_body_delay_is_used(self):
        # Google puts the delay in a RetryInfo entry, not in a header, so a
        # header-only reader finds nothing on a Gemini 429.
        assert _retry_after(_Err(), QUOTA_BODY) == pytest.approx(10.3)

    def test_a_header_is_preferred_when_present(self):
        assert _retry_after(_Err({"Retry-After": "30"}), QUOTA_BODY) == 30.0

    def test_no_delay_anywhere_gives_zero(self):
        # The caller then keeps its own doubling delay.
        assert _retry_after(_Err(), '{"error": {"message": "boom"}}') == 0.0

    def test_a_very_long_delay_is_capped(self):
        body = '{"error":{"details":[{"@type":"...RetryInfo","retryDelay":"3600s"}]}}'
        assert _retry_after(_Err(), body) == MAX_BACKOFF

    def test_the_cap_still_outlasts_a_one_minute_window(self):
        assert MAX_BACKOFF > 60
