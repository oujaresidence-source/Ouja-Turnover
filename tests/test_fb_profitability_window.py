# -*- coding: utf-8 -*-
"""C1 regression — Finance Board profitability must NOT read the truncated
full-history cache.

get_reservations_cached() stops at REVENUE_MAX_PAGES (~6,000 rows) and silently
drops the NEWEST months (CLAUDE.md trap #4 — the 18,842-vs-48,114 owner-statement
bug class). _fb_unit_profitability / _fb_company_profitability showed the owner
money computed from that truncated pull. They must use fetch_reservations_window.

Scenario: the truncated cache is missing the newest June reservations; the
targeted window pull has them. Profitability must include them.

Run: python3 tests/test_fb_profitability_window.py
"""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("STATE_DIR", "/tmp/ouja-test-state-fbprofit")
os.makedirs("/tmp/ouja-test-state-fbprofit", exist_ok=True)

import bot  # noqa: E402


def _resv(rid, lid, payout, checkin, checkout):
    return {"id": rid, "listingMapId": lid, "status": "new",
            "channelName": "Airbnb", "arrivalDate": checkin, "departureDate": checkout,
            "nights": 3, "guestName": "Guest " + str(rid),
            "airbnbExpectedPayoutAmount": payout, "totalPrice": None,
            "refundAmount": None}


# June 2026: two early-month rows survive the truncated cache; the two
# NEWEST rows (mid/late June) are exactly what the cache drops.
FULL_SET = [
    _resv("a1", 1, 3000.00, "2026-06-02", "2026-06-05"),
    _resv("a2", 1, 2000.00, "2026-06-06", "2026-06-09"),
    _resv("a3", 1, 4000.00, "2026-06-15", "2026-06-18"),   # NEWER — truncated away
    _resv("a4", 1, 1000.00, "2026-06-25", "2026-06-28"),   # NEWEST — truncated away
]
TRUNCATED_CACHE = [r for r in FULL_SET if r["id"] in ("a1", "a2")]


class FBProfitabilityWindowTest(unittest.TestCase):
    def setUp(self):
        self._window = bot.fetch_reservations_window
        self._cached = bot.get_reservations_cached
        self._listings = bot.get_listings_map
        self._contracts = dict(bot._fb_contracts)
        self._ledger = dict(bot._fb_ledger)
        self._bank = dict(bot._fb_bank)
        self.window_calls = []
        bot.fetch_reservations_window = self._fake_window
        bot.get_reservations_cached = lambda ttl=1800: TRUNCATED_CACHE
        bot.get_listings_map = lambda: {1: "Ouja | 101A"}
        bot._fb_contracts.clear()
        bot._fb_ledger.clear()
        bot._fb_bank.clear()
        bot._fb_contracts["101a"] = {
            "apartment_name": "101A", "apartment_code": "101A",
            "hostaway_listing_id": "1", "unit_type": "owner_managed",
            "ouja_percentage": 18.0, "cleaning_rule": "ours",
            "cleaning_monthly_amount": 0, "daftra_cost_center_id": "cc-1",
            "validation_status": "ok",
        }

    def tearDown(self):
        bot.fetch_reservations_window = self._window
        bot.get_reservations_cached = self._cached
        bot.get_listings_map = self._listings
        bot._fb_contracts.clear(); bot._fb_contracts.update(self._contracts)
        bot._fb_ledger.clear(); bot._fb_ledger.update(self._ledger)
        bot._fb_bank.clear(); bot._fb_bank.update(self._bank)

    def _fake_window(self, start, end, pad_days=45):
        self.window_calls.append((start, end))
        return FULL_SET

    def test_unit_profitability_sees_newest_month_rows(self):
        up = bot._fb_unit_profitability(month="2026-06")
        self.assertTrue(self.window_calls, "profitability must use fetch_reservations_window")
        unit = next(u for u in up["units"] if u["apartment"] == "101A")
        self.assertEqual(unit["reservations"], 4)
        self.assertEqual(unit["revenue"], "10000.00")   # 3000+2000+4000+1000 — NOT 5000
        self.assertEqual(up["total_revenue"], "10000.00")

    def test_company_profitability_rides_the_window_pull(self):
        cp = bot._fb_company_profitability(month="2026-06")
        self.assertEqual(cp["portfolio_revenue"], "10000.00")

    def test_truncated_cache_alone_would_undercount(self):
        # Guard the guard: prove the synthetic truncation actually undercounts,
        # so the assertions above stay meaningful.
        bot.fetch_reservations_window = lambda s, e, pad_days=45: TRUNCATED_CACHE
        up = bot._fb_unit_profitability(month="2026-06")
        unit = next(u for u in up["units"] if u["apartment"] == "101A")
        self.assertEqual(unit["revenue"], "5000.00")


if __name__ == "__main__":
    unittest.main()
