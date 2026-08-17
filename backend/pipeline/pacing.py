"""Stay below a rate limit instead of discovering where it is.

A refusal is not free: it spends a request and returns no answer. Pacing below
a stated ceiling therefore costs less than testing it, which is why this is a
pacer and not a retry.

See docs/decisions/0008-behaviour-at-a-providers-limit.md.
"""
from __future__ import annotations

import threading
import time


class Pacer:
    """Space request starts so a run stays under a per-minute limit.

    One instance is shared by every worker, because a limit belongs to the
    account and not to a thread. Claiming a slot is locked; the wait is not, so
    workers overlap instead of queueing behind each other.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._free_at = 0.0

    def wait(self, per_minute: int) -> float:
        """Block until this caller's slot. Returns the seconds waited.

        Idling does not earn a burst: a slot is claimed from now, never from
        the last one, so a quiet period cannot bank credit and then spend it
        all at once.
        """
        if per_minute <= 0:
            return 0.0
        interval = 60.0 / per_minute
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._free_at)
            self._free_at = slot + interval
        delay = slot - now
        if delay > 0:
            time.sleep(delay)
        return max(delay, 0.0)
