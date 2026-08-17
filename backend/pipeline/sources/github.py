"""Find a company's public repository, and read what it says about traction.

Three ways to connect a company to a repository, each with a test that must
pass. The test is the whole point: a name is not an identity.

    website     the company's website IS a github URL      no test needed
    site_link   a github link on the company's own page    repo homepage = domain
    org_search  search organisations by name               org blog = domain

Searching *repositories* by name is not one of them. A search for "emergent"
returns emergent-misalignment, emer/emergent and boson-ai/EmergentTTS-Eval, and
none of them is emergent.sh. Searching *organisations* and then checking the
blog field finds `emergentbase`, whose blog is app.emergent.sh.

Feeds metric 2, and metric 1's fallback tier. See
docs/decisions/0006-github-as-a-source.md.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from ..config import GitHubSettings
from ..http import FetchError, get_json, get_text
from ..normalize import registrable_domain

log = logging.getLogger(__name__)

REPO_URL = re.compile(r"github\.com/([A-Za-z0-9][A-Za-z0-9_.-]{0,38})(?:/([A-Za-z0-9_.-]+))?")

# Paths under github.com that are the site's own furniture, not an account.
NOT_AN_OWNER = frozenset({
    "features", "about", "pricing", "login", "join", "apps", "site", "orgs",
    "topics", "sponsors", "marketplace", "readme", "explore", "settings",
    "notifications", "enterprise", "security", "collections", "events",
    "contact", "customer-stories", "trending", "search", "new", "issues",
    "pulls", "codespaces", "sponsors-explore",
})


@dataclass(frozen=True)
class RepoFacts:
    """What one company's public presence on GitHub says."""

    owner: str
    repo: str | None = None
    full_name: str | None = None
    found_via: str = "website"          # website | site_link | org_search
    homepage: str | None = None         # the company's real address, per GitHub
    description: str | None = None
    language: str | None = None
    stars: int = 0
    forks: int = 0
    open_issues: int = 0
    contributors: int = 0
    org_followers: int = 0
    is_fork: bool = False
    archived: bool = False
    created_at: str | None = None
    pushed_at: str | None = None
    missing: bool = False               # a 404: no public repository
    raw: dict = field(default_factory=dict)

    @property
    def url(self) -> str:
        return f"https://github.com/{self.full_name or self.owner}"


def _api(path: str, settings: GitHubSettings) -> dict | list | None:
    """One GitHub call. None means the request failed or found nothing.

    A token is optional. Without one the limit is 60 an hour, which covers a
    selection of 15; with one it is 5000.
    """
    headers = {"Accept": "application/vnd.github+json"}
    if settings.token:
        headers["Authorization"] = f"Bearer {settings.token}"
    try:
        return get_json(f"{settings.base_url}{path}", headers=headers,
                        timeout=settings.timeout)
    except FetchError as exc:
        if exc.status == 404:
            return None
        log.warning("github %s -> %s", path, exc)
        return None


def owners_in(html: str) -> list[str]:
    """GitHub accounts linked from a page, in order, without duplicates."""
    seen: list[str] = []
    for match in REPO_URL.finditer(html or ""):
        owner = match.group(1)
        if owner.lower() in NOT_AN_OWNER or owner in seen:
            continue
        seen.append(owner)
    return seen


def parse_repo_url(url: str | None) -> tuple[str, str | None] | None:
    """(owner, repo) from a github URL. repo is None for an account link."""
    if not url:
        return None
    match = REPO_URL.search(url)
    if not match:
        return None
    owner = match.group(1)
    if owner.lower() in NOT_AN_OWNER:
        return None
    repo = match.group(2)
    return owner, repo.removesuffix(".git") if repo else None


def same_company(a: str | None, b: str | None) -> bool:
    """Do two addresses point at one company?

    This is the test that makes tiers 2 and 3 safe. Without it, a name match is
    a guess: `emergent-company` carries the name Emergent and belongs to nobody
    we can check.
    """
    left, right = registrable_domain(a), registrable_domain(b)
    return bool(left) and left == right


def _facts(repo: dict, *, owner: str, found_via: str,
           settings: GitHubSettings) -> RepoFacts:
    """Turn one repository payload into facts, with contributors attached."""
    contributors = _api(
        f"/repos/{repo['full_name']}/contributors?per_page=100&anon=1", settings
    )
    org = _api(f"/orgs/{owner}", settings) or {}
    return RepoFacts(
        owner=owner,
        repo=repo.get("name"),
        full_name=repo.get("full_name"),
        found_via=found_via,
        homepage=(repo.get("homepage") or "").strip() or None,
        description=repo.get("description"),
        language=repo.get("language"),
        stars=repo.get("stargazers_count", 0),
        forks=repo.get("forks_count", 0),
        open_issues=repo.get("open_issues_count", 0),
        contributors=len(contributors) if isinstance(contributors, list) else 0,
        # Emergent has 6 stars and 455 followers. Without this number the
        # instrument calls a live company dead.
        org_followers=org.get("followers", 0),
        is_fork=bool(repo.get("fork")),
        archived=bool(repo.get("archived")),
        created_at=repo.get("created_at"),
        pushed_at=repo.get("pushed_at"),
        raw=repo,
    )


def _best_repo(owner: str, settings: GitHubSettings) -> dict | None:
    """The account's most-starred repository that is not a fork.

    A fork is somebody else's work. Ranking by stars rather than by recency
    picks the project the company is known for.
    """
    repos = _api(f"/users/{owner}/repos?per_page=100&sort=pushed", settings)
    if not isinstance(repos, list) or not repos:
        return None
    own = [r for r in repos if not r.get("fork")] or repos
    return max(own, key=lambda r: r.get("stargazers_count", 0))


def find(name: str, website: str | None, *, settings: GitHubSettings) -> RepoFacts | None:
    """The public GitHub presence for one company, or None.

    None is a finding, not a failure: THESIS.md says a missing repository means
    the instrument does not apply, so the caller records it and moves on.
    """
    # Tier 1. The company published the link itself, so nothing to verify.
    parsed = parse_repo_url(website)
    if parsed:
        owner, repo = parsed
        payload = _api(f"/repos/{owner}/{repo}", settings) if repo else None
        if payload:
            return _facts(payload, owner=owner, found_via="website", settings=settings)
        best = _best_repo(owner, settings)
        if best:
            return _facts(best, owner=owner, found_via="website", settings=settings)
        # The URL is real but the repository is gone or private.
        return RepoFacts(owner=owner, repo=repo, found_via="website", missing=True)

    # Tier 2. A link on the company's own page, checked against its domain.
    if website:
        for owner in owners_in(get_text(website, timeout=settings.timeout))[:3]:
            best = _best_repo(owner, settings)
            if best and same_company(best.get("homepage"), website):
                return _facts(best, owner=owner, found_via="site_link", settings=settings)

    # Tier 3. Organisations by name, checked against the company's domain.
    if website and settings.search_orgs:
        found = _api(f"/search/users?q={name.split()[0]}+type:org&per_page=5", settings)
        for item in (found or {}).get("items", [])[:5]:
            org = _api(f"/orgs/{item['login']}", settings) or {}
            if not same_company(org.get("blog"), website):
                continue
            best = _best_repo(item["login"], settings)
            if best:
                return _facts(best, owner=item["login"], found_via="org_search",
                              settings=settings)
            return RepoFacts(owner=item["login"], found_via="org_search",
                             org_followers=org.get("followers", 0),
                             homepage=(org.get("blog") or "").strip() or None)
    return None
