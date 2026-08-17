"""End-to-end sync tests. `stub_sources` replaces both fetchers, so no network."""
from pipeline.db import connect
from pipeline.models import Company
from pipeline.repository import companies as repo
from pipeline.sources.coverage import Coverage
from pipeline.sync import sync

TOPIC = "AI agents for SMBs"


class TestSync:
    def test_loads_both_sources(self, settings, stub_sources):
        report = sync(TOPIC, settings=settings)

        assert stub_sources == ["yc", "hn"]
        # 2 from YC + 3 from HN, less Browser Use which is in both.
        assert report.total_rows == 4
        assert report.merged == 1
        assert {r.source for r in report.sources} == {"yc", "hn"}

    def test_is_idempotent(self, settings, stub_sources):
        first = sync(TOPIC, settings=settings)
        second = sync(TOPIC, settings=settings)

        assert sum(r.added for r in first.sources) == 5   # before the merge folds one
        # The property sync() advertises: a second run inserts nothing. The
        # merge deletes the HN twin, so without a record of the fold the next
        # run would re-create it and merge it again, every time.
        assert sum(r.added for r in second.sources) == 0
        assert second.merged == 0
        assert second.total_rows == first.total_rows == 4

    def test_limit_caps_each_source(self, settings, stub_sources):
        report = sync(TOPIC, settings=settings, limit=1)

        # One per source, and both are Browser Use, so they fold into one.
        assert all(r.fetched == 1 for r in report.sources)
        assert report.total_rows == 1

    def test_keeps_text_posts(self, settings, stub_sources):
        sync(TOPIC, settings=settings)

        with connect(settings.db_path) as conn:
            rows = conn.execute(
                "SELECT name FROM companies WHERE source='hn' AND website IS NULL"
            ).fetchall()

        assert [r["name"] for r in rows] == ["AgentMail"]

    def test_passes_configured_batches_through(self, settings, monkeypatch):
        from pipeline import sync as sync_module

        seen: list[tuple] = []
        empty = ([], Coverage.whole(0))
        monkeypatch.setattr(sync_module.yc, "fetch",
                            lambda topic, batches, limit=None, **kw:
                                (seen.append((topic, batches)), empty)[1])
        monkeypatch.setattr(sync_module.hackernews, "fetch", lambda *a, **k: empty)

        sync(TOPIC, settings=settings, batches=("S24",))
        assert seen == [(TOPIC, ("S24",))]


class TestSyncReport:
    def test_renders(self, settings, stub_sources):
        rendered = sync(TOPIC, settings=settings).render()
        assert "companies in database: 4" in rendered
        assert "yc" in rendered and "hn" in rendered

    def test_reports_rejected_count(self, settings, monkeypatch):
        """A sentence-like name is fetched but not stored, and the gap is visible."""
        from pipeline import sync as sync_module

        monkeypatch.setattr(sync_module.yc, "fetch", lambda *a, **k: ([
            Company(source="yc", source_key="ok", name="Acme"),
            Company(source="yc", source_key="bad", name="I built a voice agent from scratch"),
        ], Coverage.whole(2)))
        monkeypatch.setattr(sync_module.hackernews, "fetch",
                            lambda *a, **k: ([], Coverage.whole(0)))

        report = sync(TOPIC, settings=settings)
        yc_report = next(r for r in report.sources if r.source == "yc")

        assert (yc_report.fetched, yc_report.usable, yc_report.rejected) == (2, 1, 1)
        with connect(settings.db_path) as conn:
            assert repo.count(conn) == 1
