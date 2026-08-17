"""One way to build a query.

Every repository widened its own IN clause and then passed the values in an
order that had to match. A query and its values drifted apart that way once
already: a mixed run of named and positional marks that SQLite accepted and
answered wrongly.
"""
from __future__ import annotations

import sqlite3

import pytest

from pipeline.repository.sql import EmptyList, expand, run


class TestExpand:
    def test_a_scalar_is_left_alone(self):
        assert expand("WHERE a = :a", {"a": 1}) == ("WHERE a = :a", {"a": 1})

    def test_a_list_becomes_one_name_for_each_value(self):
        query, params = expand("IN (:ids)", {"ids": [7, 8]})
        assert query == "IN (:ids__0, :ids__1)"
        assert params == {"ids__0": 7, "ids__1": 8}

    def test_marks_and_values_always_agree(self):
        # The defect this replaces: three values against two marks.
        query, params = expand("IN (:ids)", {"ids": [1, 2, 3]})
        assert query.count(":ids__") == len(params) == 3

    def test_a_scalar_and_a_list_together(self):
        query, params = expand(
            "WHERE at < :at AND id IN (:ids)", {"at": "2026-01-01", "ids": [4]}
        )
        assert query == "WHERE at < :at AND id IN (:ids__0)"
        assert params == {"at": "2026-01-01", "ids__0": 4}

    def test_a_shorter_name_does_not_match_a_longer_one(self):
        # :company must not be found inside :company_ids.
        query, _ = expand(
            "a = :company AND b IN (:company_ids)", {"company": 1, "company_ids": [2]}
        )
        assert query == "a = :company AND b IN (:company_ids__0)"

    def test_an_empty_list_is_refused(self):
        # SQL cannot express IN (), so the caller has to return early.
        with pytest.raises(EmptyList):
            expand("IN (:ids)", {"ids": []})

    def test_a_name_the_query_does_not_use_is_refused(self):
        with pytest.raises(KeyError):
            expand("IN (:ids)", {"other": [1]})

    def test_a_tuple_and_a_set_work_like_a_list(self):
        assert expand("IN (:ids)", {"ids": (1, 2)})[1] == {"ids__0": 1, "ids__1": 2}
        assert len(expand("IN (:ids)", {"ids": {1, 2, 3}})[1]) == 3


class TestRun:
    @pytest.fixture
    def conn(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE t (id INTEGER, at TEXT)")
        conn.executemany("INSERT INTO t VALUES (?, ?)",
                         [(1, "a"), (2, "b"), (3, "c")])
        return conn

    def test_it_selects_every_value_in_the_list(self, conn):
        rows = run(conn, "SELECT id FROM t WHERE id IN (:ids)", {"ids": [1, 3]})
        assert [r[0] for r in rows] == [1, 3]

    def test_a_list_of_one_still_works(self, conn):
        rows = run(conn, "SELECT id FROM t WHERE id IN (:ids)", {"ids": [2]})
        assert [r[0] for r in rows] == [2]

    def test_a_scalar_filter_applies_at_the_same_time(self, conn):
        rows = run(conn, "SELECT id FROM t WHERE at < :at AND id IN (:ids)",
                   {"at": "c", "ids": [1, 2, 3]})
        assert [r[0] for r in rows] == [1, 2]

    def test_a_value_that_looks_like_sql_is_still_a_value(self, conn):
        # Expansion writes marks, never values, so this is data.
        rows = run(conn, "SELECT id FROM t WHERE at IN (:ats)",
                   {"ats": ["a', 'b"]})
        assert list(rows) == []
