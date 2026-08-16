from pipeline.models import Company
from pipeline.repository import companies as repo


def make(source="yc", key="acme", name="Acme", **kw) -> Company:
    return Company(source=source, source_key=key, name=name, **kw)


class TestUpsert:
    def test_inserts_new_rows(self, conn):
        added, updated = repo.upsert(conn, [make(key="a"), make(key="b")])
        assert (added, updated) == (2, 0)
        assert repo.count(conn) == 2

    def test_second_run_updates_instead_of_duplicating(self, conn):
        repo.upsert(conn, [make(key="a", name="Old")])
        added, updated = repo.upsert(conn, [make(key="a", name="New")])

        assert (added, updated) == (0, 1)
        assert repo.count(conn) == 1
        assert conn.execute("SELECT name FROM companies").fetchone()["name"] == "New"

    def test_same_key_different_source_is_a_different_row(self, conn):
        repo.upsert(conn, [make(source="yc", key="x"), make(source="hn", key="x")])
        assert repo.count(conn) == 2

    def test_stores_website_as_submitted(self, conn):
        repo.upsert(conn, [make(website="https://www.acme.dev/pricing")])
        row = conn.execute("SELECT website FROM companies").fetchone()
        assert row["website"] == "https://www.acme.dev/pricing"

    def test_keeps_row_without_website(self, conn):
        repo.upsert(conn, [make(website=None)])
        assert conn.execute("SELECT website FROM companies").fetchone()["website"] is None

    def test_preserves_raw_payload(self, conn):
        repo.upsert(conn, [make(raw={"teamSize": 4})])
        stored = conn.execute("SELECT raw_json FROM companies").fetchone()["raw_json"]
        assert '"teamSize": 4' in stored


class TestSearch:
    def _seed(self, conn):
        repo.upsert(conn, [
            make(key="1", name="Browser Use", one_liner="web agent", batch="W25"),
            make(key="2", name="Acme", description="agent infrastructure", batch="S25"),
            make(key="3", name="Unrelated", one_liner="pet food", batch="W25"),
        ])

    def test_matches_name(self, conn):
        self._seed(conn)
        assert [r["name"] for r in repo.search(conn, "Browser")] == ["Browser Use"]

    def test_matches_one_liner_and_description(self, conn):
        self._seed(conn)
        assert {r["name"] for r in repo.search(conn, "agent")} == {"Browser Use", "Acme"}

    def test_is_case_insensitive(self, conn):
        self._seed(conn)
        assert len(repo.search(conn, "AGENT")) == 2

    def test_respects_limit(self, conn):
        self._seed(conn)
        assert len(repo.search(conn, "a", limit=1)) == 1

    def test_returns_empty_on_no_match(self, conn):
        self._seed(conn)
        assert repo.search(conn, "zzznothing") == []


class TestGet:
    def test_returns_row(self, conn):
        repo.upsert(conn, [make(name="Acme")])
        row_id = conn.execute("SELECT id FROM companies").fetchone()["id"]
        assert repo.get(conn, row_id)["name"] == "Acme"

    def test_returns_none_when_missing(self, conn):
        assert repo.get(conn, 999) is None
