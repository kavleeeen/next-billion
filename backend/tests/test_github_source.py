"""Connecting a company to a repository is a matching problem, and a wrong
match is worse than no match: it would attribute somebody else's traction.

The verification rule is what makes tiers 2 and 3 safe. Searching by name and
believing the first hit is what these tests exist to prevent.
"""
from __future__ import annotations

import pytest

from pipeline.sources.github import owners_in, parse_repo_url, same_company


class TestParseRepoUrl:
    @pytest.mark.parametrize("url,expected", [
        ("https://github.com/airweave-ai/airweave", ("airweave-ai", "airweave")),
        ("http://github.com/org/repo/", ("org", "repo")),
        ("https://github.com/org/repo.git", ("org", "repo")),
        ("https://www.github.com/org/repo/tree/main", ("org", "repo")),
        ("https://github.com/just-an-org", ("just-an-org", None)),
    ])
    def test_owner_and_repo(self, url, expected):
        assert parse_repo_url(url) == expected

    @pytest.mark.parametrize("url", [
        None, "", "https://example.com", "https://gitlab.com/org/repo",
        # GitHub's own furniture is not an account.
        "https://github.com/features/actions", "https://github.com/pricing",
        "https://github.com/topics/python",
    ])
    def test_not_a_company_repo(self, url):
        assert parse_repo_url(url) is None


class TestOwnersIn:
    def test_finds_accounts_in_page_html(self):
        html = '<a href="https://github.com/luminal-ai/luminal">code</a>'
        assert owners_in(html) == ["luminal-ai"]

    def test_skips_github_furniture(self):
        html = ('<a href="https://github.com/features">f</a>'
                '<a href="https://github.com/login">l</a>'
                '<a href="https://github.com/realorg/repo">r</a>')
        assert owners_in(html) == ["realorg"]

    def test_keeps_order_and_drops_duplicates(self):
        html = ("github.com/first/a github.com/second/b github.com/first/c")
        assert owners_in(html) == ["first", "second"]

    @pytest.mark.parametrize("html", ["", None, "<p>no links here</p>"])
    def test_nothing_to_find(self, html):
        assert owners_in(html) == []


class TestSameCompany:
    """The test that makes a name match safe."""

    @pytest.mark.parametrize("a,b", [
        ("https://airweave.ai", "https://github.com/airweave-ai/airweave"),
    ])
    def test_a_repo_url_is_not_a_company_domain(self, a, b):
        # github.com never equals a company's own domain, so tier 1 cannot be
        # confirmed this way - and does not need to be.
        assert not same_company(a, b)

    @pytest.mark.parametrize("a,b", [
        ("https://app.emergent.sh", "https://emergent.sh"),
        ("https://www.luminal.com", "https://luminal.com/"),
        ("http://acme.co.uk/x", "https://shop.acme.co.uk"),
    ])
    def test_subdomains_still_match(self, a, b):
        assert same_company(a, b)

    @pytest.mark.parametrize("a,b", [
        ("https://emersim.org", "https://emergent.sh"),
        ("https://emergentmethods.ai", "https://emergent.sh"),
        # The real failure this rule prevents: an org with the right name and
        # no way to check it.
        (None, "https://emergent.sh"),
        ("", "https://emergent.sh"),
        ("https://emergent.sh", None),
    ])
    def test_a_name_alike_does_not_pass(self, a, b):
        assert not same_company(a, b)

    def test_two_unknowns_do_not_match(self):
        # Absent must never equal absent, or every unverifiable org passes.
        assert not same_company(None, None)
