# -*- coding: utf-8 -*-
"""§4.9 — cache persistence must be cheap, and deletions must still be immediate.

_owner_portal_cache_save used to serialize the ENTIRE cache after every report it
built: up to 400 owner-month reports, each carrying every reservation and expense
line, then an md5 over the whole payload inside _save_json. Tens of megabytes of
work holding the GIL, on a network-attached volume, during every 12-month warm.

Writes are now coalesced onto a timer. The one thing that must NOT be coalesced is
a deletion — a bust that is lost on restart resurrects stale money.

Run: python3 -m unittest tests.test_owner_cache_persist -v
"""
import os
import shutil
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_STATE = "/tmp/ouja-test-state-persist"
shutil.rmtree(_STATE, ignore_errors=True)
os.makedirs(_STATE, exist_ok=True)
os.environ["STATE_DIR"] = _STATE

import bot  # noqa: E402


class CachePersistTest(unittest.TestCase):
    def setUp(self):
        bot._owner_portal_cache.clear()
        bot._owner_partial_cache.clear()
        st = bot._owner_portal_cache_save_state
        if st.get("timer") is not None:
            st["timer"].cancel()
            st["timer"] = None
        self.saves = [0]
        self._real_save = bot._save_json

        def counting(name, data, **kw):
            if name == "owner_portal_cache.json":
                self.saves[0] += 1
            return self._real_save(name, data, **kw)
        bot._save_json = counting

    def tearDown(self):
        bot._save_json = self._real_save
        st = bot._owner_portal_cache_save_state
        if st.get("timer") is not None:
            st["timer"].cancel()
            st["timer"] = None
        bot._owner_portal_cache.clear()
        bot._owner_partial_cache.clear()

    def test_many_report_builds_do_not_each_rewrite_the_whole_cache(self):
        bot._owner_portal_cache[("o", "2026-06")] = ({"owner_net": 1.0}, time.time())
        for _ in range(25):
            bot._owner_portal_cache_save()
        self.assertEqual(self.saves[0], 0,
                         "a warm pass still rewrote the whole cache %d time(s)"
                         % self.saves[0])
        st = bot._owner_portal_cache_save_state
        self.assertTrue(st["dirty"], "the pending write was dropped, not deferred")
        self.assertIsNotNone(st["timer"], "no flush was scheduled — the write is lost")

    def test_a_deletion_flushes_immediately(self):
        """Coalescing a DELETE would resurrect stale money on the next restart."""
        bot._owner_portal_cache[("o", "2026-06")] = ({"owner_net": 1.0}, time.time())
        bot._owner_portal_cache_save(force=True)
        self.assertEqual(self.saves[0], 1)

    def test_the_bust_path_still_forces_a_write(self):
        bot._owner_portal_cache[("o", "2026-06")] = ({"owner_net": 1.0}, time.time())
        bot._owner_cache_bust(owner="o", mkey="2026-06")
        self.assertEqual(bot._owner_portal_cache.get(("o", "2026-06")), None)
        self.assertGreaterEqual(self.saves[0], 1,
                                "a bust must reach disk immediately")

    def test_the_scheduled_flush_actually_writes(self):
        """A deferred write that never lands is just data loss on a timer."""
        real_flush_s = bot.OWNER_CACHE_FLUSH_S
        bot.OWNER_CACHE_FLUSH_S = 0.1
        try:
            bot._owner_portal_cache[("o", "2026-07")] = ({"owner_net": 2.0}, time.time())
            bot._owner_portal_cache_save()
            self.assertEqual(self.saves[0], 0)
            time.sleep(0.5)
            self.assertEqual(self.saves[0], 1,
                             "the scheduled flush never fired — the write was lost")
        finally:
            bot.OWNER_CACHE_FLUSH_S = real_flush_s

    def test_the_editor_partials_survive_a_restart(self):
        """_owner_partial_cache was a bare {} that was never persisted, so every
        Railway restart recomputed the editor's compare window from scratch."""
        bot._owner_partial_cache[("o", "2026-06", 15)] = (123.45, time.time())
        bot._owner_portal_cache_save(force=True)
        bot._owner_partial_cache_boot.clear()
        bot._owner_portal_cache_load()          # simulate boot
        self.assertEqual(bot._owner_partial_cache_boot.get(("o", "2026-06", 15)),
                         (123.45, bot._owner_partial_cache_boot[("o", "2026-06", 15)][1]))

    def test_the_money_rules_guard_still_discards_a_stale_format(self):
        bot._owner_portal_cache[("o", "2026-06")] = ({"owner_net": 1.0}, time.time())
        bot._owner_portal_cache_save(force=True)
        real = bot._MONEY_RULES_VERSION
        bot._MONEY_RULES_VERSION = str(real) + "-changed"
        try:
            self.assertEqual(bot._owner_portal_cache_load(), {},
                             "a rules-version change must start the cache clean")
        finally:
            bot._MONEY_RULES_VERSION = real


if __name__ == "__main__":
    unittest.main(verbosity=2)
