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
        assert [c.source_key for c in hackernews.parse(self._overlapping())] == ["1", "2"]

    def test_yc_parse_dedupes_across_pages(self):
        page = {"companies": [{"slug": "acme", "name": "Acme"}]}
        assert len(yc.parse([page, page])) == 1

    def test_sync_stores_each_story_once(self, settings, stub_sources):
        """parse() is the only path into the database, so dedupe always applies."""
        report = sync(settings=settings)
        assert report.total_rows == 5
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
