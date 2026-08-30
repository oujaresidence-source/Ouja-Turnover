# -*- coding: utf-8 -*-
"""G8 — the statement editor memo, and its invalidation.

statement_payload had NO cache at all: every open of «الملاك» recomputed the whole
owner-month, up to three times (live, the published-basis compare, and the partial
window month_meta needs). That is the «تعذّر تحميل البيانات» card.

Caching a money surface is only safe if invalidation is exact. An edit the
accountant makes and cannot see on the next read is a correctness bug, not a
caching trade-off — so every path that changes the numbers is tested here through
its REAL endpoint, not by poking the cache.

Run: python3 -m unittest tests.test_owner_stmt_cache -v
"""
import os
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_STATE = "/tmp/ouja-test-state-stmtcache"
shutil.rmtree(_STATE, ignore_errors=True)
os.makedirs(_STATE, exist_ok=True)
os.environ["STATE_DIR"] = _STATE

import bot  # noqa: E402
from finance import api as fapi, owners as OW  # noqa: E402

fapi.attach(bot)

LID = 88
OWNER = "مالك الكاش"
MK = "2026-06"


class _Req(object):
    headers = {}
    query = {}


def _resv(rid, payout, arrival):
    return {"id": rid, "listingMapId": LID, "status": "new", "channelName": "Airbnb",
            "arrivalDate": arrival, "departureDate": arrival[:8] + "28", "nights": 2,
            "guestName": "G" + str(rid), "airbnbExpectedPayoutAmount": payout,
            "totalPrice": payout + 200, "refundAmount": None}


class StmtCacheTest(unittest.TestCase):
    def setUp(self):
        OW._terms_cache["v"] = None
        OW._stmt_cache["v"] = None
        bot._save_json("owner_terms.json", {"owners": {}, "units": {}, "versions": []})
        bot._save_json("owner_statements.json", {})
        bot._owner_registry.clear()
        bot._owner_registry[bot._owner_key("K1")] = {
            "apartment": "K1", "owner": OWNER, "mgmt_pct": 20.0, "lid": LID,
            "cleaning": {"type": "ours", "amount": 0}}
        bot._owner_links.clear()
        bot._expenses.clear()
        self._patches = (bot.fetch_reservations_window, bot.get_listings_map)
        bot.fetch_reservations_window = lambda s, e, pad_days=45: [
            _resv("k1", 1000.0, MK + "-05"), _resv("k2", 2000.0, MK + "-15")]
        bot.get_listings_map = lambda: {LID: "Ouja | K1"}
        self._actor = fapi.actor
        fapi.actor = lambda r: "tester"
        self._clear()
        # count real recomputes
        self._real_compute = OW.compute_owner_statement
        self.computes = [0]

        def counting(owner, mkey, apply_edits=True, settings=None):
            self.computes[0] += 1
            return self._real_compute(owner, mkey, apply_edits=apply_edits, settings=settings)
        OW.compute_owner_statement = counting

    def tearDown(self):
        OW.compute_owner_statement = self._real_compute
        bot.fetch_reservations_window, bot.get_listings_map = self._patches
        fapi.actor = self._actor
        self._clear()
        bot._owner_links.clear()

    def _clear(self):
        bot._owner_portal_cache.clear()
        bot._owner_partial_cache.clear()
        bot._res_window_cache.clear()
        bot._res_span_cache.clear()
        OW._stmt_payload_cache.clear()
        OW._stmt_compare_cache.clear()

    def _net(self):
        return OW.statement_payload(OWNER, MK)["statement"]["owner_net"]

    # ---- the memo actually memoizes ---------------------------------------
    def test_warm_open_does_not_recompute(self):
        first = OW.statement_payload(OWNER, MK)
        self.assertTrue(first.get("ok"), first)
        after_first = self.computes[0]
        self.assertGreater(after_first, 0, "cold open must compute at least once")
        OW.statement_payload(OWNER, MK)
        self.assertEqual(self.computes[0], after_first,
                         "warm open recomputed the statement — the memo is not working")

    def test_an_error_payload_is_never_cached(self):
        bad = OW.statement_payload("مالك ما هو موجود", MK)
        self.assertIn("error", bad)
        self.assertEqual(len(OW._stmt_payload_cache), 0,
                         "a failure must never be memoized")

    # ---- G8: invalidation is exact ----------------------------------------
    def test_an_edit_is_visible_on_the_very_next_read(self):
        before = self._net()
        r = OW.statement_edit(_Req(), {"owner": OWNER, "m": MK, "op": "adj_add",
                                       "amount": -750.0, "label": "تسوية",
                                       "reason": "اختبار الإبطال"})
        self.assertNotIn("error", r if isinstance(r, dict) else r[0], r)
        after = self._net()
        self.assertNotEqual(before, after,
                            "the adjustment did not reach the next statement read")
        self.assertAlmostEqual(after, before - 750.0, places=2)

    def test_publish_is_visible_on_the_very_next_read(self):
        p0 = OW.statement_payload(OWNER, MK)
        self.assertIsNone(p0.get("published"))
        OW.statement_publish(_Req(), {"owner": OWNER, "m": MK, "basis": "normal"})
        p1 = OW.statement_payload(OWNER, MK)
        self.assertIsNotNone(p1.get("published"),
                             "the published snapshot did not reach the next read")
        self.assertEqual(p1["published"]["version"], 1)

    def test_a_contract_change_is_visible_on_the_very_next_read(self):
        before = self._net()
        r = OW.unit_terms_set(_Req(), {"apartment": "K1", "from": "2026-01-01",
                                       "mgmt_pct": 40.0})
        self.assertNotIn("error", r if isinstance(r, dict) else r[0], r)
        after = self._net()
        self.assertNotEqual(before, after,
                            "the new management % did not reach the next statement read")

    def test_a_broad_bust_clears_the_memo(self):
        OW.statement_payload(OWNER, MK)
        self.assertGreater(len(OW._stmt_payload_cache), 0)
        bot._owner_cache_bust()
        self.assertEqual(len(OW._stmt_payload_cache), 0,
                         "a registry-wide bust must drop the statement memo too")

    def test_a_bust_for_another_month_leaves_this_one_alone(self):
        OW.statement_payload(OWNER, MK)
        n = len(OW._stmt_payload_cache)
        bot._owner_cache_bust(owner=OWNER, mkey="2026-01")
        self.assertEqual(len(OW._stmt_payload_cache), n,
                         "a month-scoped bust must not evict other months")


    def test_creating_an_owner_link_changes_the_next_read(self):
        """Regression: the receipt-proxy rewrite depends on the owner's live link
        token. Caching the payload without that in the key served the pre-link
        URLs forever (caught by test_receipts_v21 when this memo landed)."""
        bot._expenses["E777"] = {
            "id": "E777", "apartment": "K1", "listing_id": LID, "amount": 100.0,
            "expense_date": MK + "-10", "hostaway_verified": True,
            "hostaway_expense_id": "H777", "receipt_link": "https://drive.example/x",
            "category": "صيانة", "note": "اختبار"}
        before = OW.statement_payload(OWNER, MK)
        raw = [x.get("receipt_url") for x in before["statement"].get("exp_lines") or []]
        rec = bot._owner_link_get_or_create(OWNER, "tester")
        after = OW.statement_payload(OWNER, MK)
        proxied = [x.get("receipt_url") for x in after["statement"].get("exp_lines") or []]
        self.assertNotEqual(raw, proxied,
                            "activating an owner link must change the next payload read")
        self.assertTrue(any((u or "").startswith("/fin/receipt/") for u in proxied),
                        "receipt links did not switch to the owner-scoped proxy")
        self.assertIn(rec["token"], " ".join(u or "" for u in proxied))


if __name__ == "__main__":
    unittest.main(verbosity=2)
