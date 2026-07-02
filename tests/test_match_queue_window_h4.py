# -*- coding: utf-8 -*-
"""H4 regression — matching engine 4 (Hostaway payouts) must use a targeted
window pull, not the truncated full-history cache.

Channel payouts land days AFTER departure — the NEWEST reservations, exactly
the rows get_reservations_cached() drops at REVENUE_MAX_PAGES. The accountant
saw «no candidates» for recent payouts and wasted time or wrongly promoted.

Run: python3 tests/test_match_queue_window_h4.py
"""
import os
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("STATE_DIR", "/tmp/ouja-test-state-h4")
os.makedirs("/tmp/ouja-test-state-h4", exist_ok=True)

import bot  # noqa: E402
from finance import api as fapi  # noqa: E402

fapi.attach(bot)

# The newest reservation — present ONLY in the window pull, never in the cache.
NEWEST = {"id": 777001, "status": "new", "totalPrice": 1000.0,
          "listingMapId": 5, "guestName": "أحمد",
          "arrivalDate": "2026-06-24", "departureDate": "2026-06-27"}


class MatchQueueWindowH4Test(unittest.TestCase):
    def setUp(self):
        self._bank = dict(bot._fb_bank)
        self._window = bot.fetch_reservations_window
        self._cached = bot.get_reservations_cached
        self.window_calls = []
        bot._fb_bank.clear()
        bot._fb_bank["tx1"] = {
            "id": "tx1", "date": "2026-06-29", "credit": 970.0, "debit": 0,
            "category": "channel_payout", "match_status": "unmatched",
            "description": "AIRBNB PAYOUT"}

        def fake_window(start, end, pad_days=45):
            self.window_calls.append((start, end))
            return [NEWEST]
        bot.fetch_reservations_window = fake_window
        bot.get_reservations_cached = lambda ttl=1800: []   # cache is EMPTY of new rows

    def tearDown(self):
        bot._fb_bank.clear(); bot._fb_bank.update(self._bank)
        bot.fetch_reservations_window = self._window
        bot.get_reservations_cached = self._cached

    def test_recent_payout_gets_candidates_from_window_pull(self):
        q = fapi.match_queue({"engine": "hostaway"})
        self.assertTrue(self.window_calls, "match_queue must use fetch_reservations_window")
        start, end = self.window_calls[0]
        self.assertEqual(start, date(2026, 6, 29))
        self.assertEqual(end, date(2026, 6, 29) + timedelta(days=10))
        self.assertEqual(q["counts"]["hostaway"], 1,
                         "the newest reservation must appear as a payout candidate")
        item = q["items"][0]
        keys = [c["key"] for c in item["cands"] if c["engine"] == "hostaway"]
        self.assertIn("777001", keys)

    def test_no_unmatched_payouts_skips_hostaway_pull(self):
        bot._fb_bank["tx1"]["match_status"] = "matched"
        fapi.match_queue({"engine": "all"})
        self.assertFalse(self.window_calls, "no unmatched payouts → no Hostaway pull")


if __name__ == "__main__":
    unittest.main()
