# -*- coding: utf-8 -*-
"""§4.5 / §4.7 — stale-while-revalidate and the bounded cold path.

The owner profile used to render six grey bars and never resolve: there was no
timeout anywhere, so the request hung until the browser or Railway's edge gave up.

The rule this locks down: last night's numbers, LABELLED as last night's, beat a
spinner that never ends — and both beat presenting a half-finished statement as if
it were whole. A partial GRID is honest and useful; a partial STATEMENT is a lie,
so those two take deliberately different exits.

Run: python3 -m unittest tests.test_owner_swr_budget -v
"""
import os
import shutil
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_STATE = "/tmp/ouja-test-state-swr"
shutil.rmtree(_STATE, ignore_errors=True)
os.makedirs(_STATE, exist_ok=True)
os.environ["STATE_DIR"] = _STATE

import bot  # noqa: E402
from finance import api as fapi, owners as OW  # noqa: E402

fapi.attach(bot)

LID = 99
OWNER = "مالك البيانات القديمة"
MK = "2026-06"


class _Req(object):
    headers = {}
    query = {}


def _resv(rid, payout, arrival):
    return {"id": rid, "listingMapId": LID, "status": "new", "channelName": "Airbnb",
            "arrivalDate": arrival, "departureDate": arrival[:8] + "28", "nights": 2,
            "guestName": "G" + str(rid), "airbnbExpectedPayoutAmount": payout,
            "totalPrice": payout + 200, "refundAmount": None}


class SwrBudgetTest(unittest.TestCase):
    def setUp(self):
        OW._terms_cache["v"] = None
        OW._stmt_cache["v"] = None
        bot._save_json("owner_terms.json", {"owners": {}, "units": {}, "versions": []})
        bot._save_json("owner_statements.json", {})
        bot._owner_registry.clear()
        bot._owner_registry[bot._owner_key("S1")] = {
            "apartment": "S1", "owner": OWNER, "mgmt_pct": 20.0, "lid": LID,
            "cleaning": {"type": "ours", "amount": 0}}
        bot._owner_links.clear()
        bot._expenses.clear()
        self._patches = (bot.fetch_reservations_window, bot.get_listings_map)
        bot.fetch_reservations_window = lambda s, e, pad_days=45: [
            _resv("s1", 1000.0, MK + "-05")]
        bot.get_listings_map = lambda: {LID: "Ouja | S1"}
        self._actor = fapi.actor
        fapi.actor = lambda r: "tester"
        self._budget = bot.OWNER_COMPUTE_BUDGET_S
        self._clear()

    def tearDown(self):
        bot.fetch_reservations_window, bot.get_listings_map = self._patches
        fapi.actor = self._actor
        bot.OWNER_COMPUTE_BUDGET_S = self._budget
        self._clear()

    def _clear(self):
        bot._owner_portal_cache.clear()
        bot._owner_partial_cache.clear()
        bot._res_window_cache.clear()
        bot._res_span_cache.clear()
        OW._stmt_payload_cache.clear()
        OW._stmt_compare_cache.clear()

    # ---- §4.5 stale-while-revalidate ---------------------------------------
    def test_an_expired_report_is_served_stale_not_recomputed_inline(self):
        fresh = bot._owner_month_report(OWNER, MK)
        self.assertIsNotNone(fresh)
        self.assertFalse(fresh.get("stale"))
        # age the entry well past its TTL
        rep, _ts = bot._owner_portal_cache[(OWNER, MK)]
        bot._owner_portal_cache[(OWNER, MK)] = (rep, time.time() - 99999)

        t0 = time.time()
        served = bot._owner_month_report(OWNER, MK)
        elapsed = time.time() - t0

        self.assertTrue(served.get("stale"), "an expired report must be served stale")
        self.assertTrue(served.get("refreshing"))
        self.assertGreater(served.get("stale_age_s"), 1000,
                           "the age stamp must state the REAL age, not a guess")
        self.assertEqual(served.get("owner_net"), rep.get("owner_net"),
                         "stale must still be the real previous numbers")
        self.assertLess(elapsed, 1.0, "a stale read must return immediately")

    def test_the_stale_stamp_never_mutates_the_cached_object(self):
        bot._owner_month_report(OWNER, MK)
        rep, _ = bot._owner_portal_cache[(OWNER, MK)]
        bot._owner_portal_cache[(OWNER, MK)] = (rep, time.time() - 99999)
        bot._owner_month_report(OWNER, MK)
        cached_now, _ = bot._owner_portal_cache[(OWNER, MK)]
        self.assertNotIn("stale", cached_now,
                         "stale_stamp leaked into the cached report")

    def test_a_stale_read_refreshes_behind_the_reader(self):
        bot._owner_month_report(OWNER, MK)
        rep, _ = bot._owner_portal_cache[(OWNER, MK)]
        bot._owner_portal_cache[(OWNER, MK)] = (rep, time.time() - 99999)
        bot._owner_month_report(OWNER, MK)          # triggers the background refresh
        for _ in range(100):                        # up to ~2s
            time.sleep(0.02)
            _r, ts = bot._owner_portal_cache[(OWNER, MK)]
            if time.time() - ts < 60:
                break
        _r, ts = bot._owner_portal_cache[(OWNER, MK)]
        self.assertLess(time.time() - ts, 60,
                        "the background refresh never landed — SWR would serve stale forever")

    # ---- §4.7 the bounded cold path ----------------------------------------
    def test_a_statement_over_budget_says_still_computing_never_a_partial(self):
        bot.OWNER_COMPUTE_BUDGET_S = 0.05
        real = OW._statement_payload_compute

        def slow(owner, mkey, settings=None):
            time.sleep(1.0)
            return real(owner, mkey, settings=settings)
        OW._statement_payload_compute = slow
        try:
            out = OW.statement_payload(OWNER, MK)
        finally:
            OW._statement_payload_compute = real
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("reason"), "still_computing")
        self.assertEqual(out.get("retry_after"), 20)
        self.assertNotIn("statement", out,
                         "a statement over budget must NEVER return partial numbers")
        self.assertTrue(out.get("message_ar"))
        self.assertTrue(out.get("message_en"))

    def test_the_background_compute_survives_the_budget_and_warms_the_cache(self):
        """The point of the deadline: the work continues, so the automatic retry
        lands on a warm cache instead of starting over."""
        bot.OWNER_COMPUTE_BUDGET_S = 0.05
        real = OW._statement_payload_compute

        def slow(owner, mkey, settings=None):
            time.sleep(0.4)
            return real(owner, mkey, settings=settings)
        OW._statement_payload_compute = slow
        try:
            first = OW.statement_payload(OWNER, MK)
            self.assertEqual(first.get("reason"), "still_computing")
            time.sleep(1.2)                       # let the background work finish
        finally:
            OW._statement_payload_compute = real
        bot.OWNER_COMPUTE_BUDGET_S = self._budget
        second = OW.statement_payload(OWNER, MK)
        self.assertTrue(second.get("ok"),
                        "the retry did not land on the warmed cache: %r" % second)

    def test_a_profile_over_budget_returns_the_months_it_has(self):
        bot._owner_month_report(OWNER, MK)        # one month is genuinely ready
        bot.OWNER_COMPUTE_BUDGET_S = 0.05
        real = OW._owner_profile_compute

        def slow(owner):
            time.sleep(1.0)
            return real(owner)
        OW._owner_profile_compute = slow
        try:
            out = OW.owner_profile(OWNER)
        finally:
            OW._owner_profile_compute = real
        self.assertTrue(out.get("ok"))
        self.assertTrue(out.get("partial"), "an over-budget profile must say so")
        self.assertTrue(out.get("message_ar"))
        self.assertGreaterEqual(len(out.get("months") or []), 1,
                                "the months already computed must still be shown")


if __name__ == "__main__":
    unittest.main(verbosity=2)
