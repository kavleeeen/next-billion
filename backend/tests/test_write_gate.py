"""Who may spend money through the viewer.

POST collects, buys PDL credits and spends Gemini quota. On loopback the only
caller is the person who started the process. Bound to anything else the URL is
reachable by strangers, so it needs the token.
"""
from __future__ import annotations

import pytest

from pipeline.server import LOOPBACK, WRITE_TOKEN_ENV, _write_allowed

HOSTED = "0.0.0.0"


@pytest.fixture
def token(monkeypatch):
    monkeypatch.setenv(WRITE_TOKEN_ENV, "s3cret")
    return "s3cret"


class TestLoopbackIsOpen:
    @pytest.mark.parametrize("host", sorted(LOOPBACK))
    def test_no_token_is_needed_locally(self, monkeypatch, host):
        # Requiring one would break the local viewer for its only user.
        monkeypatch.delenv(WRITE_TOKEN_ENV, raising=False)
        assert _write_allowed(None, host)

    def test_a_wrong_token_locally_is_still_fine(self, token):
        assert _write_allowed("nonsense", "127.0.0.1")


class TestHostedNeedsTheToken:
    def test_the_right_token_passes(self, token):
        assert _write_allowed(token, HOSTED)

    @pytest.mark.parametrize("sent", ["", "wrong", "s3cre", "s3cret ", None])
    def test_anything_else_is_refused(self, token, sent):
        assert not _write_allowed(sent, HOSTED)

    def test_no_token_configured_refuses_everything(self, monkeypatch):
        # An unset variable is a read-only deployment, not an open one.
        monkeypatch.delenv(WRITE_TOKEN_ENV, raising=False)
        for sent in (None, "", "anything"):
            assert not _write_allowed(sent, HOSTED)

    def test_an_empty_configured_token_does_not_open_the_door(self, monkeypatch):
        # "" is falsy, so it must read as unset rather than as "match empty".
        monkeypatch.setenv(WRITE_TOKEN_ENV, "")
        assert not _write_allowed("", HOSTED)

    @pytest.mark.parametrize("host", ["0.0.0.0", "10.0.0.5", "example.com", ""])
    def test_any_non_loopback_bind_is_gated(self, monkeypatch, host):
        monkeypatch.delenv(WRITE_TOKEN_ENV, raising=False)
        assert not _write_allowed(None, host)
