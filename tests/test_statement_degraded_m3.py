# -*- coding: utf-8 -*-
"""M3 regression — when the targeted window pull fails and falls back to the
truncated cache, owner statements must SAY so, and publish must refuse.

The bug: fetch_reservations_window silently substituted the truncated
full-history cache on failure, so a statement could show a plausible-but-wrong
(undercounted) number with no warning.

Run: python3 tests/test_statement_degraded_m3.py
"""
import os
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("STATE_DIR", "/tmp/ouja-test-state-m3")
os.makedirs("/tmp/ouja-test-state-m3", exist_ok=True)

import bot  # noqa: E402
from finance import owners as OW  # noqa: E402

# a far-future month so the window cache can never already hold this key
M_START, M_END = date(2031, 1, 1), date(2031, 1, 31)


class WindowDegradedM3Test(unittest.TestCase):
    def setUp(self):
        self._api_get = bot.api_get
        self._cached = bot.get_reservations_cached
        self._lm = bot.get_listings_map
        bot.get_listings_map = lambda: {1: "Ouja | 101A"}
        bot.get_reservations_cached = lambda ttl=1800: []

    def tearDown(self):
        bot.api_get = self._api_get
        bot.get_reservations_cached = self._cached
        bot.get_listings_map = self._lm

    def test_checked_variant_reports_degraded(self):
        def boom(path, params=None):
            raise RuntimeError("hostaway down")
        bot.api_get = boom
        rows, degraded = bot.fetch_reservations_window_checked(M_START, M_END)
        self.assertTrue(degraded)
        self.assertEqual(rows, [])

    def test_build_owner_report_flags_degraded(self):
        def boom(path, params=None):
            raise RuntimeError("hostaway down")
        bot.api_get = boom
        rep = bot.build_owner_report(1, M_START, M_END, 18.0, {})
        self.assertTrue(rep.get("degraded"),
                        "a statement computed from the fallback must be flagged")

    def test_healthy_pull_is_not_flagged(self):
        bot.api_get = lambda path, params=None: {"status": "success", "result": []}
        rep = bot.build_owner_report(1, M_START, M_END, 18.0, {})
        self.assertFalse(rep.get("degraded"))

    def test_publish_refuses_degraded_statement(self):
        orig = OW.compute_owner_statement
        OW.compute_owner_statement = lambda owner, mkey: {"degraded": True, "owner_net": 0}
        try:
            data, status = OW.statement_publish(None, {"owner": "x", "m": "2026-06"})
            self.assertEqual(status, 503)
            self.assertEqual(data.get("error"), "degraded_data")
        finally:
            OW.compute_owner_statement = orig


if __name__ == "__main__":
    unittest.main()
