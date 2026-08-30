# -*- coding: utf-8 -*-
"""Owner-section performance budget — the gates from the Owners speed work.

The complaint this locks down: the owner profile page fanned out to ~15 distinct
month reports, each its own paginated Hostaway pull (~60 calls), against a global
ceiling of 11 calls / 10s. That is minutes of pure throttle wait for one screen.

G4 — cold profile costs <= 10 Hostaway calls (was ~60).
G5 — warm profile costs 0.
Both assert the NETS ARE UNCHANGED against the same synthetic data, because a fast
wrong number is worse than a slow right one.

Run: python3 -m unittest tests.test_owner_perf_budget -v
"""
import os
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_STATE = "/tmp/ouja-test-state-perfbudget"
shutil.rmtree(_STATE, ignore_errors=True)
os.makedirs(_STATE, exist_ok=True)
os.environ["STATE_DIR"] = _STATE
os.environ["RES_SPAN_ENABLED"] = "1"      # force the span layer on: no creds in tests

import bot  # noqa: E402
from finance import api as fapi, owners as OW  # noqa: E402

fapi.attach(bot)

LID = 77
OWNER = "مالك الأداء"


def _resv(rid, payout, arrival):
    """One synthetic Airbnb reservation, shaped like a real Hostaway row."""
    return {"id": rid, "listingMapId": LID, "status": "new", "channelName": "Airbnb",
            "arrivalDate": arrival, "departureDate": arrival[:8] + "28", "nights": 2,
            "guestName": "G" + str(rid), "airbnbExpectedPayoutAmount": payout,
            "totalPrice": payout + 200, "refundAmount": None}


def _synthetic_rows():
    """Two bookings a month across a 20-month span — wide enough that the 12-month
    grid and its 3-month look-back are all inside one span pull."""
    rows = []
    y, m = 2025, 1
    for i in range(30):
        mk = "%04d-%02d" % (y, m)
        rows.append(_resv("r%d-a" % i, 1000.0, mk + "-05"))
        rows.append(_resv("r%d-b" % i, 1500.0, mk + "-15"))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return rows


ALL_ROWS = _synthetic_rows()


class _Counter(object):
    """Counting stub for bot.api_get. Serves /reservations from ALL_ROWS, honouring
    the same arrivalStartDate/arrivalEndDate/limit/offset contract the real API has,
    so paging behaves the way production paging does."""

    def __init__(self):
        self.calls = 0
        self.paths = []

    def __call__(self, path, params=None, _retry=0):
        self.calls += 1
        self.paths.append(path)
        params = params or {}
        if path == "/reservations":
            lo = params.get("arrivalStartDate") or "0000-00-00"
            hi = params.get("arrivalEndDate") or "9999-99-99"
            sel = [r for r in ALL_ROWS if lo <= r["arrivalDate"][:10] <= hi]
            off = int(params.get("offset") or 0)
            lim = int(params.get("limit") or 200)
            return {"result": sel[off:off + lim]}
        return {"result": []}


class OwnerPerfBudgetTest(unittest.TestCase):
    def setUp(self):
        OW._terms_cache["v"] = None
        OW._stmt_cache["v"] = None
        bot._save_json("owner_terms.json", {"owners": {}, "units": {}, "versions": []})
        bot._save_json("owner_statements.json", {})
        bot._owner_registry.clear()
        bot._owner_registry[bot._owner_key("P1")] = {
            "apartment": "P1", "owner": OWNER, "mgmt_pct": 20.0, "lid": LID,
            "cleaning": {"type": "ours", "amount": 0}}
        bot._owner_links.clear()
        bot._expenses.clear()
        self._orig_api = bot.api_get
        self._orig_listings = bot.get_listings_map
        bot.get_listings_map = lambda: {LID: "Ouja | P1"}
        self.counter = _Counter()
        bot.api_get = self.counter
        self._clear_caches()

    def tearDown(self):
        bot.api_get = self._orig_api
        bot.get_listings_map = self._orig_listings
        self._clear_caches()
        bot._owner_links.clear()

    def _clear_caches(self):
        bot._owner_portal_cache.clear()
        bot._res_window_cache.clear()
        bot._res_span_cache.clear()
        bot._res_window_degraded.clear()
        bot._owner_partial_cache.clear()
        bot._listings["map"] = {}
        bot._listings["ts"] = 0

    # ---- G4 ----------------------------------------------------------------
    def test_g4_cold_profile_stays_within_ten_hostaway_calls(self):
        d = OW.owner_profile(OWNER)
        self.assertTrue(d.get("ok"), d)
        self.assertEqual(len(d["months"]), 12, "the grid must still be 12 months")
        self.assertLessEqual(
            self.counter.calls, 10,
            "cold owner profile made %d Hostaway calls (budget 10); paths=%r"
            % (self.counter.calls, self.counter.paths))

    # ---- G5 ----------------------------------------------------------------
    def test_g5_warm_profile_makes_no_hostaway_calls(self):
        OW.owner_profile(OWNER)
        before = self.counter.calls
        d2 = OW.owner_profile(OWNER)
        self.assertTrue(d2.get("ok"), d2)
        self.assertEqual(self.counter.calls - before, 0,
                         "warm owner profile must not touch Hostaway")

    # ---- the numbers must not move -----------------------------------------
    def test_nets_are_identical_with_and_without_the_span_layer(self):
        """The whole point: the span pull must return exactly what per-month pulls
        returned. Same synthetic data, span ON vs span OFF -> identical nets."""
        d_span = OW.owner_profile(OWNER)
        nets_span = [(m["m"], m["net"]) for m in d_span["months"]]

        os.environ["RES_SPAN_ENABLED"] = "0"
        try:
            self._clear_caches()
            d_plain = OW.owner_profile(OWNER)
            nets_plain = [(m["m"], m["net"]) for m in d_plain["months"]]
        finally:
            os.environ["RES_SPAN_ENABLED"] = "1"

        self.assertEqual(nets_span, nets_plain,
                         "span slicing changed the numbers — that is a correctness bug")
        self.assertTrue(any(n for _, n in nets_span), "fixture produced no income at all")


if __name__ == "__main__":
    unittest.main(verbosity=2)
