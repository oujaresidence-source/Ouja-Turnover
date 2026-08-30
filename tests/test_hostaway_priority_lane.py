# -*- coding: utf-8 -*-
"""§4.8 — the Hostaway throttle's priority lane.

There was no priority lane: a background warmer and a human waiting on a page
competed for the same 11 calls / 10s on equal terms. That is why the delay was
erratic — 40 seconds sometimes, minutes when the revenue loop and the owner warm
loop happened to be running as Wejdan clicked.

Background callers may now fill the bucket only to (max - reserve). The reserve is
kept for whoever is actually waiting.

Run: python3 -m unittest tests.test_hostaway_priority_lane -v
"""
import os
import shutil
import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_STATE = "/tmp/ouja-test-state-prio"
shutil.rmtree(_STATE, ignore_errors=True)
os.makedirs(_STATE, exist_ok=True)
os.environ["STATE_DIR"] = _STATE

import bot  # noqa: E402


class PriorityLaneTest(unittest.TestCase):
    def setUp(self):
        bot._ha_bucket_times.clear()

    def tearDown(self):
        bot._ha_bucket_times.clear()

    def _fill(self, n):
        now = time.time()
        for _ in range(n):
            bot._ha_bucket_times.append(now)

    def _acquire_blocks(self, priority, timeout=0.4):
        """True when the acquire did NOT complete within `timeout`."""
        done = threading.Event()

        def run():
            bot._ha_throttle_acquire(priority=priority)
            done.set()
        t = threading.Thread(target=run, daemon=True)
        t.start()
        return not done.wait(timeout)

    def test_background_is_capped_below_the_ceiling(self):
        cap = bot.HOSTAWAY_MAX_PER_10S - bot.HOSTAWAY_USER_RESERVE
        self._fill(cap)
        self.assertTrue(self._acquire_blocks("background"),
                        "background used the reserve it is supposed to leave alone")

    def test_a_user_still_gets_the_reserved_slots(self):
        cap = bot.HOSTAWAY_MAX_PER_10S - bot.HOSTAWAY_USER_RESERVE
        self._fill(cap)
        self.assertFalse(self._acquire_blocks("user"),
                         "a waiting human was blocked out of the reserved slots")

    def test_a_user_is_still_bounded_by_the_real_ceiling(self):
        """The reserve is a priority lane, not an exemption — the IP ceiling still
        applies, or we are back to the 429 backoff spiral this throttle exists to
        prevent."""
        self._fill(bot.HOSTAWAY_MAX_PER_10S)
        self.assertTrue(self._acquire_blocks("user"),
                        "user priority must not exceed the Hostaway ceiling")

    def test_the_ambient_default_is_background(self):
        self.assertEqual(bot.current_priority(), "background",
                         "anything that has not declared itself is housekeeping")

    def test_priority_propagates_into_a_to_thread_worker(self):
        """The whole design rests on contextvars surviving asyncio.to_thread — if
        that ever stops being true, the lane silently stops working."""
        import asyncio

        async def main():
            bot.set_priority("user")
            return await asyncio.to_thread(bot.current_priority)
        self.assertEqual(asyncio.run(main()), "user",
                         "priority did not reach the worker thread")


if __name__ == "__main__":
    unittest.main(verbosity=2)
