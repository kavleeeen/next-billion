"""One test per defect found in review. Each fails if the defect returns."""
import pytest

from pipeline.models import Company
from pipeline.normalize import looks_like_company_name, parse_hn_title
from pipeline.repository import companies as repo
from pipeline.sources import hackernews, yc
from pipeline.sync import sync


class TestParseDedupe:
    """#1 — deduplication lives in parse(), the single path into the database.
    Overlapping searches previously stored 928 records where 738 were distinct."""

    def _overlapping(self):
        hit = {"objectID": "1", "title": "Show HN: Semble - Code search", "url": "https://s.dev"}
        other = {"objectID": "2", "title": "Show HN: Nia - Agent memory", "url": "https://n.ai"}
        return [{"hits": [hit, other]}, {"hits": [hit]}]   # story 1 in two searches

    def test_hn_parse_dedupes_across_payloads(self):
        assert [c.source_key for c in hackernews.parse(self._overlapping())] == [
            "semble", "nia"
        ]

    def test_a_story_seen_twice_is_stored_once(self):
        company = hackernews.parse(self._overlapping())[0]
        assert [s.story_id for s in company.stories] == ["1"]

    def test_yc_parse_dedupes_across_pages(self):
        page = {"companies": [{"slug": "acme", "name": "Acme"}]}
        assert len(yc.parse([page, page])) == 1

    def test_sync_stores_each_story_once(self, settings, stub_sources):
        """parse() is the only path into the database, so dedupe always applies."""
        report = sync(settings=settings)
        assert report.total_rows == 4          # Browser Use appears in both sources
        assert all(r.fetched == r.usable for r in report.sources)


class TestNameQuality:
    """#4 — a Show HN sentence must not become a company."""

    @pytest.mark.parametrize("title, expected", [
        ("Show HN: I built a sub-500ms latency voice agent from scratch", False),
        ("Show HN: We made a faster database", False),
        ("Show HN: How I shipped a compiler in a weekend", False),
        ("Launch HN: Browser Use (YC W25) - Open-source web agent", True),
        ("Show HN: Semble - Code search for agents", True),
    ])
    def test_sentence_titles_are_rejected(self, title, expected):
        name, _ = parse_hn_title(title)
        assert looks_like_company_name(name) is expected

    def test_rejects_overlong_name(self):
        assert not looks_like_company_name("A" * 41)

    def test_accepts_longest_real_name_seen(self):
        assert looks_like_company_name("Discovered Materials")


class TestBatchCodes:
    """#4b — batch codes are not only W/S/F; real data has P26 and X25."""

    @pytest.mark.parametrize("code", ["W25", "S25", "F24", "P26", "X25"])
    def test_all_batch_letters_parse(self, code):
        name, batch = parse_hn_title(f"Launch HN: Airweave (YC {code}) - Sync engine")
        assert (name, batch) == ("Airweave", code)

    def test_double_space_separator(self):
        """'ProvenMetal  delivers circuit boards' has no dash separator."""
        name, _ = parse_hn_title("Launch HN: ProvenMetal (YC S26)  delivers circuit boards")
        assert name == "ProvenMetal"


class TestSearchEscaping:
    """#10 — % and _ in a term acted as LIKE wildcards."""

    def _seed(self, conn):
        repo.upsert(conn, [
            Company(source="yc", source_key="1", name="Growth 50% Co"),
            Company(source="yc", source_key="2", name="Unrelated"),
            Company(source="yc", source_key="3", name="a_b tools"),
        ])

    def test_percent_is_literal(self, conn):
        self._seed(conn)
        assert [r["name"] for r in repo.search(conn, "50%")] == ["Growth 50% Co"]

    def test_underscore_is_literal(self, conn):
        self._seed(conn)
        assert [r["name"] for r in repo.search(conn, "a_b")] == ["a_b tools"]

    def test_bare_percent_does_not_match_everything(self, conn):
        self._seed(conn)
        assert len(repo.search(conn, "%")) == 1


class TestHttpInjection:
    """#7 — timeout and retries were module globals, so tests could not fail fast."""

    def test_get_json_accepts_overrides(self):
        import inspect

        from pipeline.http import get_json

        params = inspect.signature(get_json).parameters
        assert "timeout" in params and "retries" in params


class TestOneCompanyManyStories:
    """A company can launch more than once. Rowboat posted three times across
    eleven months; storing one row per story split its traction three ways."""

    def _payloads(self):
        return [{"hits": [
            {"objectID": "1", "title": "Show HN: Rowboat - agents",
             "url": "https://rowboat.dev", "points": 66, "num_comments": 10,
             "created_at_i": 1757000000},
            {"objectID": "2", "title": "Show HN: Rowboat - now faster",
             "url": "https://rowboat.dev", "points": 219, "num_comments": 80,
             "created_at_i": 1767000000},
            {"objectID": "3", "title": "Launch HN: Onyx (YC W24) - chat",
             "url": None, "points": 254, "num_comments": 160,
             "created_at_i": 1764000000},
        ]}]

    def test_three_stories_become_two_companies(self):
        assert len(hackernews.parse(self._payloads())) == 2

    def test_all_stories_are_kept(self):
        rowboat = hackernews.parse(self._payloads())[0]
        assert sorted(s.points for s in rowboat.stories) == [66, 219]

    def test_company_takes_its_best_story_title(self):
        rowboat = hackernews.parse(self._payloads())[0]
        assert "now faster" in rowboat.one_liner

    def test_traction_view_sums_the_stories(self, settings, conn):
        from pipeline.repository import companies as companies_repo
        from pipeline.repository import hn_stories as stories_repo

        rowboat = hackernews.parse(self._payloads())[0]
        companies_repo.upsert(conn, [rowboat])
        company_id = companies_repo.id_for(conn, "hn", rowboat.source_key)
        stories_repo.upsert(conn, company_id, rowboat.stories)

        traction = stories_repo.traction(conn, company_id)
        assert traction["story_count"] == 2
        assert traction["points"] == 285
        assert traction["first_posted_at"] < traction["last_posted_at"]


class TestBestStoryMergeKeepsFields:
    """The best-story swap replaced the whole Company, dropping any field the
    winning title lacked. `website` is the only input to the PDL search
    fallback, so a company whose top post is a text post could never be
    enriched — leaving metric 1 uncited and override 4 pinning it at Watch."""

    def _payloads(self):
        return [{"hits": [
            {"objectID": "1", "title": "Launch HN: Acme (YC W25) - the thing",
             "url": "https://acme.dev", "points": 40, "num_comments": 5,
             "created_at_i": 1757000000},
            {"objectID": "2", "title": "Show HN: Acme - now faster",
             "url": None, "points": 300, "num_comments": 90,
             "created_at_i": 1767000000},
        ]}]

    def _company(self):
        return hackernews.parse(self._payloads())[0]

    def test_batch_survives_a_higher_scoring_post(self):
        assert self._company().batch == "W25"

    def test_website_survives_a_higher_scoring_text_post(self):
        assert self._company().website == "https://acme.dev"

    def test_best_story_still_wins_the_one_liner(self):
        assert "now faster" in self._company().one_liner

    def test_all_stories_are_kept(self):
        assert sorted(s.points for s in self._company().stories) == [40, 300]

    def test_order_does_not_matter(self):
        reversed_payloads = [{"hits": list(reversed(self._payloads()[0]["hits"]))}]
        company = hackernews.parse(reversed_payloads)[0]
        assert (company.batch, company.website) == ("W25", "https://acme.dev")
        assert "now faster" in company.one_liner


class TestEnrichCreditGuards:
    """On-demand enrichment bypassed the "needs founders" query, so each POST
    re-bought founders already paid for. max_calls_per_run was also a local, so
    N requests allowed N x that against a shared monthly plan."""

    def _company(self, conn):
        from pipeline.models import Company
        from pipeline.repository import companies as repo
        repo.upsert(conn, [Company(source="yc", source_key="acme", name="Acme",
                                   website="https://acme.dev")])
        return repo.id_for(conn, "yc", "acme")

    def _stub(self, monkeypatch, calls):
        """No network: YC page returns one slug, PDL returns a person."""
        from pipeline.enrich import pdl, yc_page
        monkeypatch.setattr(yc_page, "founder_slugs", lambda slug: ["someone"])
        monkeypatch.setattr(
            pdl, "enrich_person",
            lambda slug, s: calls.append(slug) or {"full_name": "Some One", "experience": []},
        )

    def test_second_call_on_the_same_company_spends_nothing(
        self, settings, conn, monkeypatch
    ):
        from pipeline.enrich import enrich
        company_id = self._company(conn)
        conn.commit()
        calls: list[str] = []
        self._stub(monkeypatch, calls)

        first = enrich(settings=settings, company_ids=[company_id])
        second = enrich(settings=settings, company_ids=[company_id])

        assert (first.pdl_calls, second.pdl_calls) == (1, 0)
        assert second.skipped_existing == 1
        assert len(calls) == 1

    def test_force_re_buys(self, settings, conn, monkeypatch):
        from pipeline.enrich import enrich
        company_id = self._company(conn)
        conn.commit()
        calls: list[str] = []
        self._stub(monkeypatch, calls)

        enrich(settings=settings, company_ids=[company_id])
        forced = enrich(settings=settings, company_ids=[company_id], force=True)

        assert forced.pdl_calls == 1
        assert len(calls) == 2

    def test_monthly_cap_survives_separate_runs(self, settings, conn, monkeypatch):
        """The cap is stored, not a local, so a second run cannot get a fresh one."""
        from dataclasses import replace

        from pipeline.enrich import enrich
        from pipeline.models import Company
        from pipeline.repository import companies as repo

        repo.upsert(conn, [
            Company(source="yc", source_key=f"c{i}", name=f"Co {i}") for i in range(4)
        ])
        conn.commit()
        self._stub(monkeypatch, [])
        capped = replace(settings, pdl=replace(settings.pdl, monthly_credit_cap=2))

        one = enrich(settings=capped, limit=2)
        two = enrich(settings=capped, limit=2)

        assert one.pdl_calls + two.pdl_calls == 2
        assert two.stopped == "monthly_cap"

    def test_missing_token_raises_before_spending(self, settings, monkeypatch):
        from pipeline.enrich import enrich, pdl

        monkeypatch.delenv(settings.pdl.token_env, raising=False)
        monkeypatch.setattr(
            pdl, "enrich_person",
            lambda *a: (_ for _ in ()).throw(AssertionError("must not be called")),
        )
        with pytest.raises(pdl.MissingToken):
            enrich(settings=settings, limit=1)


class TestPdlDomainAllowlist:
    """The domain is interpolated into SQL and originates in a scraped record."""

    @pytest.mark.parametrize("domain, allowed", [
        ("browser-use.com", True),
        ("a.b-c.dev", True),
        ("evil' OR '1'='1", False),
        ("has space.com", False),
        ("", False),
        ("semi;colon.com", False),
    ])
    def test_only_hostname_characters_pass(self, domain, allowed):
        from pipeline.enrich.pdl import _SAFE_DOMAIN
        assert bool(_SAFE_DOMAIN.match(domain.strip().lower())) is allowed

    def test_rejected_domain_makes_no_request(self, monkeypatch):
        from pipeline.config import settings as real
        from pipeline.enrich import pdl

        monkeypatch.setattr(
            pdl, "get_json",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not be called")),
        )
        assert pdl.search_founders("evil' OR '1'='1", real.pdl) == []


class TestCrossSourceMerge:
    """The two sources carry disjoint evidence: YC has descriptions and team
    size, HN has launch traction. Stored separately, no company had both."""

    def _rows(self, conn):
        return conn.execute(
            "SELECT * FROM companies ORDER BY name"
        ).fetchall()

    def test_a_company_in_both_sources_becomes_one_row(self, settings, stub_sources):
        from pipeline.db import connect

        report = sync(settings=settings)
        assert report.merged == 1

        with connect(settings.db_path) as conn:
            names = [r["name"] for r in self._rows(conn)]
        assert names.count("Browser Use") == 1

    def test_the_surviving_row_has_both_signals(self, settings, stub_sources):
        from pipeline.db import connect
        from pipeline.repository import hn_stories as stories_repo

        sync(settings=settings)
        with connect(settings.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM companies WHERE name = 'Browser Use'"
            ).fetchone()
            traction = stories_repo.traction(conn, row["id"])

        assert row["source"] == "yc"          # the richer row survives
        assert row["team_size"] == 4          # YC evidence
        assert traction["points"] == 259      # HN evidence, on the same company

    def test_a_conflicting_batch_blocks_the_merge(self, settings, conn):
        """A name match alone is too loose. Two companies can share a name."""
        from pipeline.merge import merge_cross_source
        from pipeline.models import Company
        from pipeline.repository import companies as repo

        repo.upsert(conn, [
            Company(source="yc", source_key="acme", name="Acme", batch="W25"),
            Company(source="hn", source_key="acme", name="Acme", batch="S21"),
        ])
        assert merge_cross_source(conn) == 0
        assert repo.count(conn) == 2

    def test_no_batch_on_the_hn_row_still_merges(self, settings, conn):
        from pipeline.merge import merge_cross_source
        from pipeline.models import Company
        from pipeline.repository import companies as repo

        repo.upsert(conn, [
            Company(source="yc", source_key="acme", name="Acme", batch="W25"),
            Company(source="hn", source_key="acme", name="Acme"),
        ])
        assert merge_cross_source(conn) == 1
        assert repo.count(conn) == 1


class TestIndustries:
    """YC tags every company. It was in the payload and never extracted."""

    def test_industries_are_stored(self, conn):
        from pipeline.repository import companies as repo
        from pipeline.sources import yc

        company = yc._to_company(
            {"slug": "x", "name": "X", "industries": ["B2B", "Engineering"]}
        )
        repo.upsert(conn, [company])
        stored = conn.execute("SELECT industries FROM companies").fetchone()
        assert stored["industries"] == '["B2B", "Engineering"]'

    def test_missing_industries_become_an_empty_list(self):
        from pipeline.sources import yc
        assert yc._to_company({"slug": "x", "name": "X"}).industries == []


class TestMergeDoesNotDestroyPaidData:
    """`UPDATE OR REPLACE` deletes the row already on the surviving company and
    keeps the incoming one — discarding a yc_page founder with paid-for prior
    roles in favour of an inferred pdl_search row with none."""

    def _pair(self, conn):
        from pipeline.models import Company, Founder
        from pipeline.repository import companies as repo
        from pipeline.repository import founders as founders_repo

        repo.upsert(conn, [
            Company(source="yc", source_key="acme", name="Acme", batch="W25"),
            Company(source="hn", source_key="acme", name="Acme", batch="W25"),
        ])
        keep = repo.id_for(conn, "yc", "acme")
        drop = repo.id_for(conn, "hn", "acme")

        founders_repo.upsert(conn, [
            Founder(company_id=keep, linkedin_slug="jane", source_url="https://yc",
                    discovered_via="yc_page", name="Jane", pdl_matched=True,
                    current_title="co-founder", prior_roles=[{"title": "eng"}]),
            Founder(company_id=drop, linkedin_slug="jane", source_url="https://acme.dev",
                    discovered_via="pdl_search", name="Jane"),
        ])
        return keep

    def test_the_paid_founder_row_survives(self, conn):
        from pipeline.merge import merge_cross_source
        from pipeline.repository import founders as founders_repo

        keep = self._pair(conn)
        merge_cross_source(conn)
        rows = founders_repo.for_company(conn, keep)

        assert len(rows) == 1
        assert rows[0]["discovered_via"] == "yc_page"
        assert rows[0]["pdl_matched"] == 1
        assert rows[0]["current_title"] == "co-founder"


class TestMergeAmbiguity:
    """A batch-less HN row matched every same-named YC row, so the loop folded
    twice and the stories landed on whichever the join returned first. Live
    data holds one such case: candor and candor-security are both "Candor",
    both W25."""

    def test_two_yc_rows_with_one_name_block_the_merge(self, conn):
        from pipeline.merge import merge_cross_source
        from pipeline.models import Company
        from pipeline.repository import companies as repo

        repo.upsert(conn, [
            Company(source="yc", source_key="acme", name="Acme", batch="W25"),
            Company(source="yc", source_key="acme-labs", name="Acme", batch="W25"),
            Company(source="hn", source_key="acme", name="Acme"),
        ])
        assert merge_cross_source(conn) == 0
        assert repo.count(conn) == 3

    def test_a_single_yc_row_still_merges(self, conn):
        from pipeline.merge import merge_cross_source
        from pipeline.models import Company
        from pipeline.repository import companies as repo

        repo.upsert(conn, [
            Company(source="yc", source_key="acme", name="Acme", batch="W25"),
            Company(source="hn", source_key="acme", name="Acme"),
        ])
        assert merge_cross_source(conn) == 1
        assert repo.count(conn) == 1


class TestMergeIsRecorded:
    """The fold has to outlive the run, or sync re-creates the row forever."""

    def test_a_folded_row_is_not_recreated(self, settings, stub_sources):
        from pipeline.db import connect
        from pipeline.repository import merged_rows as merged_repo

        sync(settings=settings)
        with connect(settings.db_path) as conn:
            assert merged_repo.count(conn) == 1
            assert merged_repo.keys_for(conn, "hn") == {"browser use"}

        second = sync(settings=settings)
        assert second.merged == 0
        assert sum(r.added for r in second.sources) == 0

    def test_stories_still_reach_the_surviving_company(self, settings, stub_sources):
        """The folded row has no id of its own, so its stories must be
        attached to the company that absorbed it."""
        from pipeline.db import connect
        from pipeline.repository import hn_stories as stories_repo

        sync(settings=settings)
        sync(settings=settings)          # second run: the row is suppressed

        with connect(settings.db_path) as conn:
            row = conn.execute(
                "SELECT id FROM companies WHERE name = 'Browser Use'"
            ).fetchone()
            traction = stories_repo.traction(conn, row["id"])

        assert traction["points"] == 259
