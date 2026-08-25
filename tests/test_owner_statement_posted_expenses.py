# -*- coding: utf-8 -*-
"""Regression: expenses the owner POSTED to Hostaway must appear on owner statements,
even when the fragile secondary 'verify' step never set hostaway_verified=True.

Root cause of the 'المصاريف 0' bug:
  - build_owner_report counted ONLY canonical 'verified' (hostaway_verified True).
  - Verify itself is fragile at scale: _exp_fetch_hostaway silently capped at 1000
    rows, and _exp4_verify only scanned that capped list (never the direct id GET),
    so a freshly-posted expense beyond the window never verified.
"""
import asyncio
import unittest

import bot

LID = 7001
OTHER = 7002
APT = "Ouja | شقة 7 - الماجديه"


def _exp(eid, *, amount, date, status, verified=False, ref=None, lid=LID, dry=False):
    return {
        "id": eid, "ref": "OJ-EXP-" + eid, "apartment": APT, "listing_id": lid,
        "amount": amount, "expense_date": date, "category": "صيانة وإصلاحات",
        "maintenance_type": "سباكة", "note": "test", "receipt_link": "",
        "status": status, "hostaway_verified": verified,
        "hostaway_ref": ref, "hostaway_expense_id": ref,
        "approval_status": "approved", "dry": dry,
        "sent_at": "2026-05-20T00:00:00", "status_entered_at": "2026-05-20T00:00:00",
        "updated_at": "2026-05-20T00:00:00",
    }


class PostedExpensePredicate(unittest.TestCase):
    def test_verified_counts(self):
        self.assertTrue(bot._exp_posted_to_hostaway(_exp("a", amount=1, date="2026-05-01",
                                                          status="verified", verified=True, ref="1")))

    def test_posted_unverified_with_real_ref_counts(self):
        self.assertTrue(bot._exp_posted_to_hostaway(_exp("b", amount=1, date="2026-05-01",
                                                          status="sent_unverified", ref="55502")))

    def test_no_real_ref_does_not_count(self):
        self.assertFalse(bot._exp_posted_to_hostaway(_exp("c", amount=1, date="2026-05-01",
                                                           status="sent_unverified", ref="ok")))

    def test_dryrun_does_not_count(self):
        self.assertFalse(bot._exp_posted_to_hostaway(_exp("d", amount=1, date="2026-05-01",
                                                           status="sent_unverified", ref="DRYRUN", dry=True)))

    def test_draft_does_not_count(self):
        self.assertFalse(bot._exp_posted_to_hostaway(_exp("e", amount=1, date="2026-05-01",
                                                           status="draft", ref=None)))


class OwnerStatementIncludesPostedExpenses(unittest.TestCase):
    def setUp(self):
        self._orig = (bot.get_listings_map, bot.fetch_reservations_window,
                      bot._owner_info, bot._expenses, dict(bot._finance_adjust))
        bot.get_listings_map = lambda *a, **k: {LID: APT, OTHER: "Ouja | other"}
        bot.fetch_reservations_window = lambda *a, **k: []
        bot._owner_info = lambda name: None
        bot._finance_adjust.clear()
        bot._expenses = {
            "E1": _exp("E1", amount=100.0, date="2026-05-10", status="verified", verified=True, ref="55501"),
            "E2": _exp("E2", amount=200.0, date="2026-05-12", status="sent_unverified", ref="55502"),
            "E3": _exp("E3", amount=300.0, date="2026-05-13", status="sent_unverified", ref="ok"),
            "E4": _exp("E4", amount=400.0, date="2026-05-14", status="sent_unverified", ref="DRYRUN", dry=True),
            "E5": _exp("E5", amount=500.0, date="2026-05-15", status="draft", ref=None),
            "E6": _exp("E6", amount=600.0, date="2026-05-16", status="verified", verified=True, ref="55506", lid=OTHER),
            "E7": _exp("E7", amount=700.0, date="2026-04-20", status="sent_unverified", ref="55507"),
        }

    def tearDown(self):
        (bot.get_listings_map, bot.fetch_reservations_window, bot._owner_info,
         bot._expenses, adj) = self._orig
        bot._finance_adjust.clear(); bot._finance_adjust.update(adj)

    def test_statement_counts_posted_and_verified_only(self):
        start, end = bot._month_bounds("2026-05")
        rep = bot.build_owner_report(LID, start, end, 0, {}, adjust={})
        ids = {l.get("id") for l in rep.get("exp_lines", [])}
        self.assertEqual(ids, {"E1", "E2"})
        self.assertAlmostEqual(rep.get("expenses"), 300.0, places=2)
        self.assertEqual(rep.get("counts", {}).get("expenses"), 2)


class FetchNotCappedAt1000(unittest.TestCase):
    def test_fetch_reaches_every_expense(self):
        TOTAL = 1500

        def fake_api_get(path, params=None):
            params = params or {}
            off = int(params.get("offset", 0)); lim = int(params.get("limit", 100))
            return {"result": [{"id": str(i), "amount": -1.0, "expenseDate": "2026-05-01",
                                "listingMapId": LID} for i in range(off, min(off + lim, TOTAL))]}

        orig = bot.api_get
        bot.api_get = fake_api_get
        bot._exp_ha_cache.update({"items": None, "ts": 0})
        try:
            items, ok, err = bot._exp_fetch_hostaway(force=True)
            self.assertTrue(ok, err)
            self.assertEqual(len(items), TOTAL)
        finally:
            bot.api_get = orig
            bot._exp_ha_cache.update({"items": None, "ts": 0})


class VerifyUsesDirectById(unittest.TestCase):
    def test_direct_id_verifies_when_bulk_list_misses_it(self):
        exp = {"id": "X1", "ref": "OJ-EXP-X1", "listing_id": LID, "amount": 250.0,
               "expense_date": "2026-05-01", "hostaway_ref": "999999",
               "hostaway_expense_id": "999999", "status": "sent_unverified",
               "hostaway_verified": False, "approval_status": "approved"}
        orig = (bot._exp_fetch_hostaway, bot._exp_fetch_hostaway_one, bot.EXPENSE_POST_DRYRUN)
        bot._exp_fetch_hostaway = lambda *a, **k: ([], True, None)
        bot._exp_fetch_hostaway_one = lambda hid: ({"id": "999999", "listingMapId": LID,
                                                    "amount": -250.0, "expenseDate": "2026-05-01"}, True, None)
        bot.EXPENSE_POST_DRYRUN = False
        try:
            ok = asyncio.run(bot._exp4_verify(exp))
            self.assertTrue(ok)
            self.assertTrue(exp.get("hostaway_verified"))
        finally:
            (bot._exp_fetch_hostaway, bot._exp_fetch_hostaway_one, bot.EXPENSE_POST_DRYRUN) = orig


if __name__ == "__main__":
    unittest.main()
