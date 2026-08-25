# -*- coding: utf-8 -*-
"""H3 regression — full-history truncation must drop the OLDEST months, never
the newest, and any truncation must be flagged.

The bug: fetch_all_reservations paginated forward from offset 0 and stopped at
REVENUE_MAX_PAGES, silently cutting off the NEWEST months. Every recent-window
consumer (rev_30 tiles, weekly Discord report, demand factors, stale-unit
emergency discounts) computed wrong numbers from that pull.

Run: python3 tests/test_fetch_all_newest_first_h3.py
"""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("STATE_DIR", "/tmp/ouja-test-state-h3")
os.makedirs("/tmp/ouja-test-state-h3", exist_ok=True)

import bot  # noqa: E402

# 250 rows, oldest-first (row i = i-th oldest) — like the live account.
ROWS = [{"id": i, "arrivalDate": "2026-%02d-01" % (1 + i // 40)} for i in range(250)]


def _fake_api(rows, with_count=True):
    def api_get(path, params=None):
        p = params or {}
        off, lim = int(p.get("offset", 0)), int(p.get("limit", 100))
        out = {"status": "success", "result": rows[off:off + lim]}
        if with_count:
            out["count"] = len(rows)
        return out
    return api_get


class FetchAllNewestFirstH3Test(unittest.TestCase):
    def setUp(self):
        self._api_get = bot.api_get
        self._trunc = bot._res_cache.get("truncated")

    def tearDown(self):
        bot.api_get = self._api_get
        bot._res_cache["truncated"] = self._trunc

    def test_over_budget_keeps_the_newest_rows(self):
        bot.api_get = _fake_api(ROWS)                 # 250 rows, budget = 2×100
        out = bot.fetch_all_reservations(max_pages=2)
        self.assertEqual(len(out), 200)
        self.assertEqual(out[-1]["id"], 249, "the NEWEST row must survive truncation")
        self.assertEqual(out[0]["id"], 50, "the OLDEST rows are what gets dropped")
        self.assertTrue(bot._res_cache["truncated"])

    def test_under_budget_returns_everything_unflagged(self):
        bot.api_get = _fake_api(ROWS)
        out = bot.fetch_all_reservations(max_pages=5)  # budget 500 > 250
        self.assertEqual(len(out), 250)
        self.assertFalse(bot._res_cache["truncated"])

    def test_no_count_falls_back_but_still_flags_truncation(self):
        bot.api_get = _fake_api(ROWS, with_count=False)
        out = bot.fetch_all_reservations(max_pages=2)
        self.assertEqual(len(out), 200)                # old forward behavior — never worse
        self.assertTrue(bot._res_cache["truncated"], "budget exhaustion must be flagged")

    def test_overview_surfaces_the_flag(self):
        _cached, _lm = bot.get_reservations_cached, bot.get_listings_map
        bot.get_reservations_cached = lambda ttl=1800: []
        bot.get_listings_map = lambda: {}
        try:
            bot._res_cache["truncated"] = True
            self.assertTrue(bot._compute_overview()["res_truncated"])
            bot._res_cache["truncated"] = False
            self.assertFalse(bot._compute_overview()["res_truncated"])
        finally:
            bot.get_reservations_cached = _cached
            bot.get_listings_map = _lm


if __name__ == "__main__":
    unittest.main()
