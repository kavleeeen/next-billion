"""The freshness test decides whether a company is scored again.

It has to be aware of the model and the prompt version. A score from a
different model is not a fresh score, it is a different opinion, and reusing it
would hide the change.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from pipeline.db import connect, utcnow
from pipeline.repository import analyses as repo


@pytest.fixture()
def conn(tmp_path):
    with connect(tmp_path / "t.db") as c:
        now = utcnow()
        for company_id, name in ((1, "Acme"), (2, "Globex"), (3, "Initech")):
            c.execute(
                "INSERT INTO companies (id, source, source_key, name, created_at,"
                " updated_at) VALUES (?,?,?,?,?,?)",
                (company_id, "yc", f"k{company_id}", name, now, now),
            )
        yield c


def add(conn, company_id, *, total=70.0, verdict="Watch",
        model="gemini-3.6-flash", prompt_version="v1", age_hours=0.0):
    """A row, optionally backdated, so a freshness window can be tested."""
    row_id = repo.insert(
        conn, company_id=company_id, verdict=verdict, total=total,
        scores={"metrics": []}, model=model, prompt_version=prompt_version,
    )
    if age_hours:
        stamp = (
            datetime.now(timezone.utc) - timedelta(hours=age_hours)
        ).isoformat(timespec="seconds")
        conn.execute("UPDATE analyses SET created_at = ? WHERE id = ?", (stamp, row_id))
    return row_id


class TestInsertAndLatest:
    def test_a_row_can_be_read_back(self, conn):
        add(conn, 1, total=73.0, verdict="Take a meeting")
        row = repo.latest(conn, 1)
        assert (row["total"], row["verdict"]) == (73.0, "Take a meeting")
        assert row["model"] == "gemini-3.6-flash"

    def test_no_score_gives_none(self, conn):
        assert repo.latest(conn, 1) is None

    def test_the_newest_row_wins(self, conn):
        add(conn, 1, total=50.0)
        add(conn, 1, total=80.0)
        assert repo.latest(conn, 1)["total"] == 80.0

    def test_history_is_kept(self, conn):
        # A re-score appends. The previous number stays, so a reader can see
        # that a score moved.
        add(conn, 1, total=50.0)
        add(conn, 1, total=80.0)
        assert repo.count(conn) == 2
        assert repo.count_scored(conn) == 1

    def test_rows_from_the_same_second_still_order(self, conn):
        # created_at has one-second resolution, so latest() orders by id.
        first = add(conn, 1, total=10.0)
        second = add(conn, 1, total=90.0)
        assert second > first
        assert repo.latest(conn, 1)["total"] == 90.0


class TestFreshness:
    def _fresh(self, conn, ids, **kw):
        return repo.fresh_company_ids(
            conn, ids,
            model=kw.get("model", "gemini-3.6-flash"),
            prompt_version=kw.get("prompt_version", "v1"),
            within_hours=kw.get("within_hours", 1.0),
        )

    def test_a_recent_score_is_fresh(self, conn):
        add(conn, 1)
        assert self._fresh(conn, [1, 2, 3]) == {1}

    def test_a_score_older_than_the_window_is_not(self, conn):
        add(conn, 1, age_hours=2)
        assert self._fresh(conn, [1]) == set()

    def test_the_boundary_is_inclusive_of_recent(self, conn):
        add(conn, 1, age_hours=0.5)
        assert self._fresh(conn, [1]) == {1}

    def test_a_different_model_is_not_fresh(self, conn):
        # The score exists and is recent, but another model produced it.
        add(conn, 1, model="gemini-2.5-flash")
        assert self._fresh(conn, [1]) == set()

    def test_a_different_prompt_version_is_not_fresh(self, conn):
        add(conn, 1, prompt_version="v2")
        assert self._fresh(conn, [1]) == set()

    def test_zero_hours_makes_nothing_fresh(self, conn):
        add(conn, 1)
        assert self._fresh(conn, [1], within_hours=0) == set()

    def test_an_empty_selection_asks_nothing(self, conn):
        assert self._fresh(conn, []) == set()

    def test_an_old_row_does_not_hide_a_recent_one(self, conn):
        # The test is "does any recent score exist", not "is the newest one
        # recent". latest() then returns the newest row, which is that one.
        add(conn, 1, age_hours=5)
        add(conn, 1, total=88.0)
        assert self._fresh(conn, [1]) == {1}
        assert repo.latest(conn, 1)["total"] == 88.0

    def test_several_companies_are_split_correctly(self, conn):
        add(conn, 1)
        add(conn, 2, age_hours=3)
        assert self._fresh(conn, [1, 2, 3]) == {1}
