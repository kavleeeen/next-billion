"""Two guards on the free-tier allowance.

The pacer keeps a run under the model's per-minute limit. A refusal costs a
request and returns nothing, so staying below the ceiling is cheaper than
discovering it.

The daily-quota rule stops a retry that cannot succeed. Retrying a per-day
refusal spends more of the allowance that just ran out.
"""
from __future__ import annotations

import threading
import time

import pytest

from pipeline.http import is_daily_quota
from pipeline.pacing import Pacer

DAILY = '{"error":{"details":[{"violations":[{"quotaId":"GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}]}}'
PER_MINUTE = '{"error":{"details":[{"violations":[{"quotaId":"GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}]}]}}'
TOKENS_PER_MIN = '{"error":{"details":[{"violations":[{"quotaId":"GenerateContentInputTokensPerModelPerMinute-FreeTier"}]}]}}'


class TestDailyQuota:
    def test_a_per_day_refusal_is_recognised(self):
        assert is_daily_quota(DAILY)

    @pytest.mark.parametrize("body", [PER_MINUTE, TOKENS_PER_MIN])
    def test_a_per_minute_refusal_is_not(self, body):
        # These refill, so retrying them is correct.
        assert not is_daily_quota(body)

    def test_a_body_with_both_counts_as_daily(self):
        # The day is the binding one: waiting cannot clear it.
        assert is_daily_quota(PER_MINUTE[:-2] + "," + DAILY[10:])

    @pytest.mark.parametrize("body", ["", "not json", '{"error":{}}'])
    def test_an_unrelated_body_is_not_daily(self, body):
        assert not is_daily_quota(body)


class TestPacer:
    def test_the_first_call_does_not_wait(self):
        assert Pacer().wait(12) == 0.0

    def test_the_second_call_waits_one_interval(self):
        pacer = Pacer()
        pacer.wait(60)                 # 60 a minute, so a 1 second interval
        start = time.monotonic()
        pacer.wait(60)
        assert time.monotonic() - start >= 0.9

    def test_the_rate_is_held_across_threads(self):
        # The limit belongs to the project, so workers must share one pacer.
        pacer = Pacer()
        starts: list[float] = []
        lock = threading.Lock()

        def worker():
            pacer.wait(600)            # 0.1s interval, so the test stays quick
            with lock:
                starts.append(time.monotonic())

        threads = [threading.Thread(target=worker) for _ in range(6)]
        begin = time.monotonic()
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Six slots at 0.1s apart: the last one cannot start before 0.5s.
        assert max(starts) - begin >= 0.45
        assert len(starts) == 6

    def test_zero_disables_pacing(self):
        pacer = Pacer()
        pacer.wait(0)
        assert pacer.wait(0) == 0.0

    def test_an_idle_gap_banks_no_credit(self):
        # Idling past the interval must not earn a burst of free slots: the
        # next call goes at once, and the one after it still waits its turn.
        pacer = Pacer()
        pacer.wait(120)                # 0.5s interval
        time.sleep(0.6)                # idle past it
        assert pacer.wait(120) == 0.0
        start = time.monotonic()
        pacer.wait(120)
        assert time.monotonic() - start >= 0.4
