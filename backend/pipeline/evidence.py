"""Everything known about one company, as numbered items the model can cite.

The model is never shown a URL. Each item carries a short `id`; the model cites
ids, and `url_for` turns them back into links when the memo is rendered. An id
the model invents cannot resolve, which is what makes a citation checkable.

Building the bundle is deterministic and reads only the database. A run is
therefore repeatable, and the same evidence always produces the same prompt.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from .enrich import yc_page
from .repository import companies as companies_repo
from .repository import founders as founders_repo
from .repository import github_repos as repos_repo
from .repository import hn_comments as comments_repo
from .repository import hn_stories as stories_repo

HN_ITEM = "https://news.ycombinator.com/item?id={id}"

# A launch thread can run to hundreds of comments. These two limits keep the
# prompt affordable; the submitter's own words are ordered first, so a cut
# removes replies from strangers before it removes the founder.
MAX_COMMENTS = 25
MAX_COMMENT_CHARS = 1200


@dataclass(frozen=True)
class Item:
    id: str          # what the model cites
    kind: str        # profile | traction | story | founder | comment
    source_url: str  # what the memo links to
    text: str

    def render(self) -> str:
        return f"### {self.id}\n{self.text}"


@dataclass(frozen=True)
class Bundle:
    company_id: int
    name: str
    items: tuple[Item, ...]

    def ids(self) -> set[str]:
        """The id space. Anything cited outside it was invented."""
        return {item.id for item in self.items}

    def url_for(self, item_id: str) -> str | None:
        for item in self.items:
            if item.id == item_id:
                return item.source_url
        return None

    def render(self) -> str:
        """The block substituted into the prompt."""
        return "\n\n".join(item.render() for item in self.items)

    def has(self, kind: str) -> bool:
        return any(item.kind == kind for item in self.items)


def _profile(company: sqlite3.Row, story_id: str | None) -> Item:
    """The company describing itself. Feeds metrics 3 and 4.

    `story_id` is the company's newest launch thread. A Hacker News company's
    source_key is its normalised name, not an item id, so linking that produced
    `item?id=statewright` and Hacker News answered "No such item".
    """
    lines = [f"{company['name']} — {company['one_liner'] or 'no one-liner'}"]

    facts = []
    if company["batch"]:
        facts.append(f"Batch {company['batch']}")
    if company["team_size"]:
        facts.append(f"Team size {company['team_size']}")
    industries = json.loads(company["industries"] or "[]")
    if industries:
        facts.append("Industries: " + ", ".join(industries))
    if company["website"]:
        facts.append(f"Website {company['website']}")
    if facts:
        lines.append(". ".join(facts) + ".")

    if company["description"]:
        lines.append(company["description"].strip())

    if company["source"] == "yc":
        url = yc_page.page_url(company["source_key"])
    elif story_id:
        url = HN_ITEM.format(id=story_id)
    else:
        # No thread to point at. Its own site is the only honest source left.
        url = company["website"] or ""
    return Item(id="profile", kind="profile", source_url=url, text="\n".join(lines))


def _traction(traction: sqlite3.Row, newest_story_id: str | None) -> Item:
    """Totals across every launch, added by Python.

    The model must not add points itself. It reads a number that the database
    computed, so metric 2 cannot be wrong for arithmetic reasons.
    """
    lines = [
        f"{traction['story_count']} launch(es) on Hacker News. "
        f"{traction['points'] or 0} points and {traction['comments'] or 0} "
        f"comments in total."
    ]
    if traction["first_posted_at"] != traction["last_posted_at"]:
        lines.append(
            f"First launch {traction['first_posted_at']}. "
            f"Most recent {traction['last_posted_at']}."
        )
    else:
        lines.append(f"Launched {traction['last_posted_at']}.")

    url = HN_ITEM.format(id=newest_story_id) if newest_story_id else ""
    return Item(id="traction", kind="traction", source_url=url, text="\n".join(lines))


def _story(index: int, story: sqlite3.Row) -> Item:
    return Item(
        id=f"story-{index}",
        kind="story",
        source_url=HN_ITEM.format(id=story["story_id"]),
        text=(
            f"{story['posted_at']} · {story['points'] or 0} points · "
            f"{story['comments'] or 0} comments\n{story['title']}"
        ),
    )


def _founder(index: int, founder: sqlite3.Row) -> Item:
    """Prior roles are metric 1's primary tier. Their absence is also a finding,
    so a founder with no provider record is still an item."""
    name = founder["name"] or founder["linkedin_slug"]
    lines = [name]

    if founder["current_title"] or founder["current_company"]:
        lines[0] = (
            f"{name} — {founder['current_title'] or 'role unknown'}"
            f" at {founder['current_company'] or 'company unknown'}"
        )

    roles = json.loads(founder["prior_roles_json"] or "[]")
    if roles:
        lines.append("Prior roles:")
        for role in roles:
            span = " to ".join(x for x in (role.get("start"), role.get("end")) if x)
            lines.append(
                f"  - {role.get('title') or 'unknown title'}, "
                f"{role.get('company') or 'unknown company'}"
                + (f" ({span})" if span else "")
            )
    else:
        lines.append(
            "No prior-role record at the provider. "
            "Score this founder on the fallback tier, or not at all."
        )

    return Item(
        id=f"founder-{index}",
        kind="founder",
        source_url=founder["source_url"],
        text="\n".join(lines),
    )


def _github(row: sqlite3.Row) -> Item:
    """The public repository, or a plain statement that there is none.

    Absence is written out rather than left blank. THESIS.md says a missing
    repository means the instrument does not apply, so the model has to read
    that as a fact instead of inferring weakness from silence.
    """
    if row["missing"]:
        return Item(
            id="github", kind="github", source_url="",
            text=("No public repository was found for this company. "
                  "Closed source is a business choice, not a traction signal. "
                  "Score traction on the other evidence."),
        )

    url = f"https://github.com/{row['full_name'] or row['owner']}"
    lines = [f"{row['full_name'] or row['owner']}"]
    if row["description"]:
        lines.append(row["description"].strip())

    lines.append(
        f"{row['stars']} stars · {row['forks']} forks · "
        f"{row['contributors']} contributors · {row['open_issues']} open issues"
    )
    if row["org_followers"]:
        # Emergent has 6 stars and 455 followers. Stars alone call it dead.
        lines.append(f"The owning account has {row['org_followers']} followers.")
    if row["pushed_at"]:
        lines.append(f"Last push {row['pushed_at'][:10]}. Created {(row['gh_created_at'] or '?')[:10]}.")
    if row["language"]:
        lines.append(f"Main language {row['language']}.")
    if row["is_fork"]:
        lines.append("This repository is a fork of somebody else's work.")
    if row["archived"]:
        lines.append("The repository is archived.")

    return Item(id="github", kind="github", source_url=url, text="\n".join(lines))


def _comment(index: int, comment: sqlite3.Row) -> Item:
    who = comment["author"] or "unknown"
    label = f"by {who}" + (" (the submitter)" if comment["is_op"] else "")
    text = comment["text"].strip()
    if len(text) > MAX_COMMENT_CHARS:
        text = text[:MAX_COMMENT_CHARS].rsplit(" ", 1)[0] + " […]"
    return Item(
        id=f"comment-{index}",
        kind="comment",
        source_url=HN_ITEM.format(id=comment["comment_id"]),
        text=f"{label}\n{text}",
    )


def build(conn: sqlite3.Connection, company_id: int) -> Bundle:
    """The bundle for one company. Raises if the company does not exist."""
    company = companies_repo.get(conn, company_id)
    if not company:
        raise ValueError(f"no company with id {company_id}")

    # Newest first, so stories[0] is the thread the profile should point at.
    stories = stories_repo.for_company(conn, company_id)
    items: list[Item] = [_profile(company, stories[0]["story_id"] if stories else None)]

    traction = stories_repo.traction(conn, company_id)
    if traction and traction["story_count"]:
        items.append(_traction(traction, stories[0]["story_id"] if stories else None))

    # Oldest first. A company that launched three times shows what changed
    # between the launches, and that sequence is the signal.
    for index, story in enumerate(reversed(stories), start=1):
        items.append(_story(index, story))

    repo = repos_repo.for_company(conn, company_id)
    if repo:
        items.append(_github(repo))

    for index, founder in enumerate(founders_repo.for_company(conn, company_id), start=1):
        items.append(_founder(index, founder))

    comments = comments_repo.for_company(conn, company_id, MAX_COMMENTS)
    for index, comment in enumerate(comments, start=1):
        items.append(_comment(index, comment))

    return Bundle(company_id=company_id, name=company["name"], items=tuple(items))
