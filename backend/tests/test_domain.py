"""`_domain` decides whether a company gets a founder search, and each search
costs credits. A wrong domain buys the wrong people.

The shared-host rule came from a live failure: Airweave's stored website is a
GitHub repository URL, so the search ran against github.com and returned ten
people who work at GitHub. 289 of 1171 companies with a website point there.
"""
from __future__ import annotations

import pytest

from pipeline.enrich import _domain


class TestRegistrableDomain:
    @pytest.mark.parametrize("url,expected", [
        ("https://www.browser-use.com", "browser-use.com"),
        ("http://propolis.tech/", "propolis.tech"),
        # A Launch HN post links to a subdomain; the provider stores the root.
        ("https://app.propolis.tech", "propolis.tech"),
        ("https://deep.sub.example.ai/path?x=1", "example.ai"),
        ("example.com", "example.com"),
        ("https://example.com:8443", "example.com"),
        ("HTTPS://Example.COM", "example.com"),
    ])
    def test_strips_to_the_registrable_domain(self, url, expected):
        assert _domain(url) == expected

    @pytest.mark.parametrize("url,expected", [
        ("https://acme.co.uk", "acme.co.uk"),
        ("https://shop.acme.co.uk", "acme.co.uk"),
        ("https://acme.com.au", "acme.com.au"),
    ])
    def test_two_label_suffixes_keep_three_labels(self, url, expected):
        assert _domain(url) == expected

    @pytest.mark.parametrize("url", [None, "", "   ", "https://"])
    def test_no_url_gives_no_domain(self, url):
        assert _domain(url) is None


class TestSharedHosts:
    @pytest.mark.parametrize("url", [
        "https://github.com/airweave-ai/airweave",
        "https://www.github.com/org/repo",
        "https://someproject.github.io",
        "https://my-app.vercel.app",
        "https://www.npmjs.com/package/thing",
        "https://huggingface.co/org/model",
        "https://x.com/founder",
        "https://notion.site/page",
        "https://apps.apple.com/app/id123",
    ])
    def test_a_platform_host_gives_no_domain(self, url):
        # None means no search runs, so no credit is spent and no stranger is
        # recorded as a founder.
        assert _domain(url) is None

    def test_a_company_domain_containing_a_host_name_still_works(self):
        # The rule matches the whole registrable domain, never a substring.
        assert _domain("https://github-tools.io") == "github-tools.io"
        assert _domain("https://mygithub.com") == "mygithub.com"
