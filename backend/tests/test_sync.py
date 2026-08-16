"""End-to-end sync tests. `stub_sources` replaces both fetchers, so no network."""
from pipeline.db import connect
from pipeline.models import Company
from pipeline.repository import companies as repo
from pipeline.sync import sync


class TestSync:
    def test_loads_both_sources(self, settings, stub_sources):
        report = sync(settings=settings)

        assert stub_sources == ["yc", "hn"]
        assert report.total_rows == 5              # 2 from YC, 3 from HN
        assert {r.source for r in report.sources} == {"yc", "hn"}

    def test_is_idempotent(self, settings, stub_sources):
        first = sync(settings=settings)
        second = sync(settings=settings)

        assert sum(r.added for r in first.sources) == 5
        assert sum(r.added for r in second.sources) == 0
        assert second.total_rows == first.total_rows

    def test_limit_caps_each_source(self, settings, stub_sources):
        report = sync(settings=settings, limit=1)

        assert report.total_rows == 2              # 1 per source
        assert all(r.fetched == 1 for r in report.sources)

    def test_keeps_text_posts(self, settings, stub_sources):
        sync(settings=settings)

        with connect(settings.db_path) as conn:
            rows = conn.execute(
                "SELECT name FROM companies WHERE source='hn' AND website IS NULL"
            ).fetchall()

        assert [r["name"] for r in rows] == ["AgentMail"]

    def test_passes_configured_batches_through(self, settings, monkeypatch):
        from pipeline import sync as sync_module

        seen: list[tuple] = []
        monkeypatch.setattr(sync_module.yc, "fetch",
                            lambda batches, limit=None, **kw: seen.append(batches) or [])
        monkeypatch.setattr(sync_module.hackernews, "fetch", lambda *a, **k: [])

        sync(settings=settings, batches=("S24",))
        assert seen == [("S24",)]


class TestSyncReport:
    def test_renders(self, settings, stub_sources):
        rendered = sync(settings=settings).render()
        assert "companies in database: 5" in rendered
        assert "yc" in rendered and "hn" in rendered

    def test_reports_rejected_count(self, settings, monkeypatch):
        """A sentence-like name is fetched but not stored, and the gap is visible."""
        from pipeline import sync as sync_module

        monkeypatch.setattr(sync_module.yc, "fetch", lambda *a, **k: [
            Company(source="yc", source_key="ok", name="Acme"),
            Company(source="yc", source_key="bad", name="I built a voice agent from scratch"),
        ])
        monkeypatch.setattr(sync_module.hackernews, "fetch", lambda *a, **k: [])

        report = sync(settings=settings)
        yc_report = next(r for r in report.sources if r.source == "yc")

        assert (yc_report.fetched, yc_report.usable, yc_report.rejected) == (2, 1, 1)
        with connect(settings.db_path) as conn:
            assert repo.count(conn) == 1
