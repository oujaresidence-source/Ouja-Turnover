# -*- coding: utf-8 -*-
"""Re-verify VERIFIED expenses against Hostaway and demote the ones that are gone.

Root cause this guards: 'verified' was a one-way latch — once set, nothing re-checked it,
so an expense deleted/changed in Hostaway stayed متحققة forever (271-not-in-Hostaway bug).
The fix must be SAFE: demote ONLY on a definite direct id-GET 'not found'. List-miss alone
(the list is paginated/capped) and an unreachable Hostaway must change NOTHING.
"""
import asyncio
import unittest

import bot


def mk(eid, ref, **kw):
    e = {"id": eid, "ref": "OJ-EXP-" + eid, "amount": 250.0, "expense_date": "2026-05-01",
         "apartment": "Ouja | شقة 7", "listing_id": 7001, "category": "صيانة",
         "hostaway_ref": ref, "hostaway_expense_id": ref, "hostaway_verified": True,
         "approval_status": "approved", "status": "verified"}
    e.update(kw)
    return e


class Reverify(unittest.TestCase):
    def setUp(self):
        bot._expenses.clear()
        self._orig_fetch = bot._exp_fetch_hostaway
        self._orig_one = bot._exp_fetch_hostaway_one

    def tearDown(self):
        bot._exp_fetch_hostaway = self._orig_fetch
        bot._exp_fetch_hostaway_one = self._orig_one
        bot._expenses.clear()

    def _stub(self, list_items, by_id):
        bot._exp_fetch_hostaway = lambda *a, **k: (list_items, True, None)
        bot._exp_fetch_hostaway_one = lambda r: ((by_id.get(str(r)), True, None) if str(r) in by_id
                                                 else (None, True, "empty_response"))

    def _run(self, apply):
        return asyncio.run(bot._exp4_reverify_verified(apply=apply, by="t"))

    def test_present_in_list_is_kept(self):
        bot._expenses["a"] = mk("a", "100")
        self._stub([{"id": 100}], {"100": {"id": 100}})
        r = self._run(apply=True)
        self.assertEqual(r["present"], 1)
        self.assertEqual(r["absent"], 0)
        self.assertEqual(bot._exp4_tab(bot._expenses["a"]), "verified")

    def test_absent_is_demoted_back_to_pending(self):
        bot._expenses["b"] = mk("b", "200")
        # list has a different id (so the direct-GET probe succeeds); 200 is gone
        self._stub([{"id": 999}], {"999": {"id": 999}})
        r = self._run(apply=True)
        self.assertEqual(r["absent"], 1)
        self.assertIn("OJ-EXP-b", r["demoted"])
        e = bot._expenses["b"]
        self.assertFalse(e.get("hostaway_verified"))
        self.assertEqual(bot._exp4_tab(e), "pending")

    def test_beyond_list_window_but_direct_get_resolves_is_kept(self):
        bot._expenses["c"] = mk("c", "300")
        # 300 not in the (truncated) list, but a direct GET resolves it -> still present
        self._stub([{"id": 999}], {"999": {"id": 999}, "300": {"id": 300}})
        r = self._run(apply=True)
        self.assertEqual(r["present"], 1)
        self.assertEqual(r["absent"], 0)
        self.assertEqual(bot._exp4_tab(bot._expenses["c"]), "verified")

    def test_hostaway_unreachable_changes_nothing(self):
        bot._expenses["d"] = mk("d", "400")
        bot._exp_fetch_hostaway = lambda *a, **k: ([], False, "401")
        r = self._run(apply=True)
        self.assertFalse(r["ok"])
        self.assertTrue(bot._expenses["d"].get("hostaway_verified"))
        self.assertEqual(bot._exp4_tab(bot._expenses["d"]), "verified")

    def test_incomplete_list_never_demotes(self):
        # if the Hostaway fetch hit its page cap (list may be truncated), a no-match expense
        # stays inconclusive — we never demote on a list-miss we can't trust (the المصاريف-0 trap)
        orig = bot.EXPENSE_HA_MAX_PAGES
        bot.EXPENSE_HA_MAX_PAGES = 1
        try:
            bot._expenses["e"] = mk("e", "500")
            big = [{"id": 10000 + i} for i in range(100)]      # exactly cap*page -> complete=False
            self._stub(big, {"10000": {"id": 10000}})
            r = self._run(apply=True)
            self.assertFalse(r["complete"])
            self.assertEqual(r["absent"], 0)
            self.assertEqual(r["inconclusive"], 1)
            self.assertTrue(bot._expenses["e"].get("hostaway_verified"))
        finally:
            bot.EXPENSE_HA_MAX_PAGES = orig

    def test_dryrun_reports_without_changing(self):
        bot._expenses["f"] = mk("f", "600")
        self._stub([{"id": 999}], {"999": {"id": 999}})
        r = self._run(apply=False)
        self.assertEqual(r["absent"], 1)
        self.assertFalse(r["applied"])
        self.assertTrue(bot._expenses["f"].get("hostaway_verified"))  # unchanged in dry-run

    def test_present_but_under_a_different_listing_is_flagged_not_demoted(self):
        # the expense id resolves in Hostaway, but it's filed under a DIFFERENT listing than ours
        bot._expenses["g"] = mk("g", "700", listing_id=7001)
        self._stub([{"id": 700, "listingMapId": 9999}], {"700": {"id": 700, "listingMapId": 9999}})
        r = self._run(apply=True)
        self.assertEqual(r["present"], 1)
        self.assertEqual(r["listing_diff"], 1)
        self.assertEqual(r["absent"], 0)
        self.assertEqual(bot._exp4_tab(bot._expenses["g"]), "verified")   # it IS in Hostaway -> keep, just flag
        self.assertEqual(r["mismatches"][0]["ref"], "OJ-EXP-g")

    def test_noref_phantom_with_no_match_anywhere_is_demoted(self):
        # verified but NO real Hostaway ref, and nothing in a COMPLETE Hostaway list resembles it
        e = mk("h", None, listing_id=7001, amount=250.0, expense_date="2026-05-01")
        e["hostaway_ref"] = None
        e["hostaway_expense_id"] = None
        bot._expenses["h"] = e
        self._stub([{"id": 999, "listingMapId": 1, "amount": -1, "expenseDate": "2020-01-01"}],
                   {"999": {"id": 999}})
        r = self._run(apply=True)
        self.assertEqual(r["absent"], 1)
        self.assertFalse(bot._expenses["h"].get("hostaway_verified"))
        self.assertEqual(bot._exp4_tab(bot._expenses["h"]), "pending")

    def test_noref_kept_when_same_amount_and_date_exist_somewhere(self):
        # no ref, but Hostaway has a matching amount+date (perhaps under another listing) -> keep, don't demote
        e = mk("i", None, listing_id=7001, amount=250.0, expense_date="2026-05-01")
        e["hostaway_ref"] = None
        e["hostaway_expense_id"] = None
        bot._expenses["i"] = e
        self._stub([{"id": 999, "listingMapId": 8888, "amount": -250.0, "expenseDate": "2026-05-01"}],
                   {"999": {"id": 999}})
        r = self._run(apply=True)
        self.assertEqual(r["absent"], 0)
        self.assertTrue(bot._expenses["i"].get("hostaway_verified"))


if __name__ == "__main__":
    unittest.main()
