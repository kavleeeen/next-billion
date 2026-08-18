"""The bundle is the only thing the model sees, and its ids are the id space a
citation is checked against.

Two properties matter most: an id resolves to the URL it came from, and a
missing kind of evidence is absent rather than invented.
"""
from __future__ import annotations

import json

import pytest

from pipeline.db import connect, utcnow
from pipeline.evidence import MAX_COMMENT_CHARS, MAX_COMMENTS, build


@pytest.fixture()
def conn(tmp_path):
    with connect(tmp_path / "t.db") as c:
        yield c


def add_company(conn, **kw) -> int:
    now = utcnow()
    fields = {
        "source": "yc", "source_key": "acme", "name": "Acme",
        "website": "https://acme.com", "one_liner": "A thing",
        "description": "Acme builds a thing.", "batch": "W25", "team_size": 4,
        "industries": json.dumps(["B2B", "Engineering"]),
        "raw_json": "{}", "created_at": now, "updated_at": now, **kw,
    }
    cols = ",".join(fields)
    marks = ",".join("?" * len(fields))
    return int(conn.execute(
        f"INSERT INTO companies ({cols}) VALUES ({marks})", list(fields.values())
    ).lastrowid)


def add_story(conn, company_id, story_id, points=100, posted_at="2025-01-01", comments=5):
    now = utcnow()
    conn.execute(
        "INSERT INTO hn_stories (company_id, story_id, title, points, comments,"
        " posted_at, author, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (company_id, story_id, f"Launch HN: Acme {story_id}", points, comments,
         posted_at, "founder", now, now),
    )


def add_founder(conn, company_id, slug, roles=None, name="Ada"):
    now = utcnow()
    conn.execute(
        "INSERT INTO founders (company_id, linkedin_slug, name, source_url,"
        " discovered_via, pdl_matched, prior_roles_json, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (company_id, slug, name, "https://yc/acme", "yc_page", 1,
         json.dumps(roles or []), now, now),
    )


def add_comment(conn, story_id, comment_id, text="We built this because…", is_op=1):
    conn.execute(
        "INSERT INTO hn_comments (story_id, comment_id, author, text, is_op,"
        " posted_at, created_at) VALUES (?,?,?,?,?,?,?)",
        (story_id, comment_id, "founder", text, is_op, "2025-01-02", utcnow()),
    )


class TestIdSpace:
    def test_every_id_resolves_to_its_url(self, conn):
        company_id = add_company(conn)
        add_story(conn, company_id, "111")
        add_founder(conn, company_id, "ada")
        add_comment(conn, "111", "222")

        bundle = build(conn, company_id)
        assert bundle.ids()
        for item_id in bundle.ids():
            assert bundle.url_for(item_id), f"{item_id} has no source url"

    def test_an_unknown_id_resolves_to_nothing(self, conn):
        bundle = build(conn, add_company(conn))
        assert bundle.url_for("crunchbase-1") is None

    def test_ids_are_unique(self, conn):
        company_id = add_company(conn)
        add_story(conn, company_id, "111")
        add_story(conn, company_id, "222", posted_at="2025-06-01")
        add_founder(conn, company_id, "ada")
        add_founder(conn, company_id, "grace", name="Grace")

        bundle = build(conn, company_id)
        assert len(bundle.ids()) == len(bundle.items)


class TestWhatIsIncluded:
    def test_a_bare_company_still_has_a_profile(self, conn):
        bundle = build(conn, add_company(conn))
        assert bundle.has("profile")
        assert not bundle.has("founder")
        assert not bundle.has("traction")

    def test_no_founder_means_no_founder_item(self, conn):
        # Rule 4 reads exactly this, so it must not be faked by an empty item.
        bundle = build(conn, add_company(conn))
        assert not bundle.has("founder")

    def test_traction_totals_are_added_by_python(self, conn):
        company_id = add_company(conn)
        add_story(conn, company_id, "111", points=100, comments=10)
        add_story(conn, company_id, "222", points=64, comments=20, posted_at="2025-06-01")

        text = next(i.text for i in build(conn, company_id).items if i.kind == "traction")
        assert "2 launch(es)" in text
        assert "164 points" in text and "30 comments" in text

    def test_stories_run_oldest_first(self, conn):
        company_id = add_company(conn)
        add_story(conn, company_id, "new", posted_at="2025-06-01")
        add_story(conn, company_id, "old", posted_at="2025-01-01")

        stories = [i for i in build(conn, company_id).items if i.kind == "story"]
        assert stories[0].id == "story-1"
        assert "2025-01-01" in stories[0].text

    def test_a_founder_without_prior_roles_says_so(self, conn):
        company_id = add_company(conn)
        add_founder(conn, company_id, "ada", roles=[])
        text = next(i.text for i in build(conn, company_id).items if i.kind == "founder")
        assert "No prior-role record" in text
        assert "fallback" in text

    def test_prior_roles_are_listed(self, conn):
        company_id = add_company(conn)
        add_founder(conn, company_id, "ada", roles=[
            {"title": "Engineer", "company": "Palantir", "start": "2019", "end": "2023"},
        ])
        text = next(i.text for i in build(conn, company_id).items if i.kind == "founder")
        assert "Engineer, Palantir (2019 to 2023)" in text


class TestLimits:
    def test_comments_are_capped(self, conn):
        company_id = add_company(conn)
        add_story(conn, company_id, "111")
        for n in range(MAX_COMMENTS + 10):
            add_comment(conn, "111", f"c{n}")

        comments = [i for i in build(conn, company_id).items if i.kind == "comment"]
        assert len(comments) == MAX_COMMENTS

    def test_a_long_comment_is_shortened(self, conn):
        company_id = add_company(conn)
        add_story(conn, company_id, "111")
        add_comment(conn, "111", "big", text="word " * 800)

        text = next(i.text for i in build(conn, company_id).items if i.kind == "comment")
        assert len(text) < MAX_COMMENT_CHARS + 120
        assert text.endswith("[…]")


class TestRender:
    def test_every_item_appears_with_its_id(self, conn):
        company_id = add_company(conn)
        add_story(conn, company_id, "111")
        add_founder(conn, company_id, "ada")

        rendered = build(conn, company_id).render()
        for item in build(conn, company_id).items:
            assert f"### {item.id}" in rendered

    def test_no_url_reaches_the_rendered_evidence(self, conn):
        # The model cites ids. A URL in the prompt invites it to cite a URL.
        company_id = add_company(conn, website="https://acme.com")
        add_story(conn, company_id, "111")
        add_founder(conn, company_id, "ada")
        rendered = build(conn, company_id).render()
        assert "news.ycombinator.com" not in rendered
        assert "ycombinator.com/companies" not in rendered

    def test_an_unknown_company_raises(self, conn):
        with pytest.raises(ValueError):
            build(conn, 9999)


# The GitHub item, which carries metric 2's evidence.
class TestEvidenceItem:
    def _row(self, **kw):
        base = dict(missing=0, full_name="org/repo", owner="org", description="A thing",
                    stars=10, forks=2, contributors=3, open_issues=1, org_followers=0,
                    pushed_at="2026-08-01T00:00:00Z", gh_created_at="2025-01-01T00:00:00Z",
                    language="Python", is_fork=0, archived=0)
        return {**base, **kw}

    def _text(self, **kw):
        from pipeline.evidence import _github
        return _github(self._row(**kw)).text

    def test_absence_is_stated_as_a_fact(self):
        text = self._text(missing=1)
        assert "No public repository" in text
        assert "not a traction signal" in text

    def test_the_numbers_that_matter_are_present(self):
        text = self._text(stars=6556, contributors=46)
        assert "6556 stars" in text
        assert "46 contributors" in text

    def test_account_followers_appear_when_they_exist(self):
        # Emergent: 6 stars, 455 followers. Stars alone call it dead.
        assert "455 followers" in self._text(stars=6, org_followers=455)

    def test_followers_are_omitted_when_zero(self):
        assert "followers" not in self._text(org_followers=0)

    @pytest.mark.parametrize("flag,phrase", [
        ("is_fork", "fork of somebody else"),
        ("archived", "archived"),
    ])
    def test_warnings_are_stated(self, flag, phrase):
        assert phrase in self._text(**{flag: 1})


class TestEveryCitationResolves:
    """A citation that 404s defeats the whole point of the id space (0011).

    An HN company's source_key is its normalised name, so the profile item
    linked `item?id=statewright` and Hacker News answered "No such item". Every
    one of the 1,606 HN companies was affected, and profile is the most-cited
    item in the bundle.
    """

    def _company(self, **over):
        base = dict(id=1, source="hn", source_key="statewright", name="Statewright",
                    one_liner="State machines for agents", description=None,
                    batch=None, team_size=None, industries="[]",
                    website="https://statewright.ai")
        return {**base, **over}

    def test_an_hn_profile_points_at_the_thread(self):
        from pipeline.evidence import _profile
        item = _profile(self._company(), "48108778")
        assert item.source_url == "https://news.ycombinator.com/item?id=48108778"

    def test_it_never_uses_the_source_key(self):
        from pipeline.evidence import _profile
        assert "statewright" not in _profile(self._company(), "48108778").source_url

    def test_an_hn_company_with_no_thread_falls_back_to_its_site(self):
        from pipeline.evidence import _profile
        assert _profile(self._company(), None).source_url == "https://statewright.ai"

    def test_no_thread_and_no_site_gives_no_link(self):
        from pipeline.evidence import _profile
        assert _profile(self._company(website=None), None).source_url == ""

    def test_a_yc_profile_still_uses_its_slug(self):
        from pipeline.evidence import _profile
        url = _profile(self._company(source="yc", source_key="airweave"), None).source_url
        assert "ycombinator.com/companies/airweave" in url

    def test_every_hn_item_id_in_a_real_bundle_is_numeric(self, tmp_path):
        # The class of bug: an HN permalink id is always digits.
        import re
        from pipeline.db import connect
        from pipeline.models import Company, HNStory
        from pipeline.repository import companies as companies_repo
        from pipeline.repository import hn_stories as stories_repo
        from pipeline.evidence import build

        with connect(tmp_path / "t.db") as conn:
            companies_repo.upsert(conn, [Company(source="hn", source_key="acme-co",
                                                 name="Acme", website="https://acme.dev")])
            cid = companies_repo.id_for(conn, "hn", "acme-co")
            stories_repo.upsert(conn, cid, [HNStory(story_id="44100001",
                                                    title="Show HN: Acme", points=99,
                                                    comments=5, posted_at="2026-01-01")])
            conn.commit()
            for item in build(conn, cid).items:
                if "news.ycombinator.com/item?id=" in item.source_url:
                    got = item.source_url.rsplit("=", 1)[1]
                    assert re.fullmatch(r"\d+", got), f"{item.id} -> {got}"
