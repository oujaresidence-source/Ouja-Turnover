# -*- coding: utf-8 -*-
"""A deleted / edited statement expense must disappear from the APARTMENT too.

Owner-reported 2026-08-03 (عبدالله الحربي / 2026-07, unit 487708): the accountant
deleted wrong expenses in the statement editor, gave a reason, and found them still
present in the final report.

Cause — the same structural flaw that hid manual expenses from unit prints in
2026-07-05 ([[exp-manual-per-unit]]), this time on the DELETE side: the editor's
decisions live in `owner_statements.json` and are applied by `_apply_stmt_edits`
*after* `_finance_aggregate` has already summed the per-unit reports. So a delete
patched the owner TOTAL only:

    owner statement total ......... 0     ✅ deleted
    apartments[] breakdown ........ 750   ❌ still there
    build_owner_report(lid) ....... 750   ❌ still there  ← the apartment PDF/print

Manual ADDs were fixed by routing them into the per-lid `_finance_adjust` store;
deletes and edits now take the same road, so every unit surface honours them.

Run: python3 tests/test_stmt_expense_delete_per_unit.py
"""
import os
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_STATE = "/tmp/ouja-test-state-expdelunit"
shutil.rmtree(_STATE, ignore_errors=True)
os.makedirs(_STATE, exist_ok=True)
os.environ["STATE_DIR"] = _STATE

import bot  # noqa: E402
from finance import api as fapi, owners as OW  # noqa: E402

fapi.attach(bot)

MONTH = "2026-07"
OWNER = "عبدالله الحربي"
LID = 487708


class _Req:
    query = {}
    headers = {}
    remote = "test"


class ExpenseDeleteReachesTheUnitTest(unittest.TestCase):
    def setUp(self):
        OW._terms_cache["v"] = None
        OW._stmt_cache["v"] = None
        bot._save_json("owner_terms.json", {"owners": {}, "units": {}, "versions": []})
        bot._save_json("owner_statements.json", {})
        bot._owner_registry.clear()
        bot._owner_registry[bot._owner_key("C3")] = {
            "apartment": "C3", "owner": OWNER, "mgmt_pct": 20.0, "lid": LID,
            "cleaning": {"type": "ours", "amount": 0}}
        self._patched = (bot.fetch_reservations_window, bot.fetch_reservations_window_checked,
                         bot.get_listings_map)
        bot.fetch_reservations_window = lambda s, e, pad_days=45: []
        bot.fetch_reservations_window_checked = lambda s, e: ([], False)
        bot.get_listings_map = lambda: {LID: "Ouja | C3"}
        bot._expenses.clear()
        bot._owner_portal_cache.clear()
        bot._finance_adjust.clear()
        bot._expenses["e9"] = {"id": "e9", "apartment": "C3", "listing_id": LID,
                               "amount": 750, "expense_date": "2026-07-10",
                               "hostaway_verified": True, "category": "صيانة",
                               "note": "مصروف غير صحيح"}

    def tearDown(self):
        (bot.fetch_reservations_window, bot.fetch_reservations_window_checked,
         bot.get_listings_map) = self._patched

    def _unit_report(self):
        start, end = bot._month_bounds(MONTH)
        return bot.build_owner_report(LID, start, end, 20.0, {})

    def _delete(self, eid="e9", reason="مصروف غير صحيح"):
        return OW.statement_edit(_Req(), {"owner": OWNER, "m": MONTH, "op": "exp_delete",
                                          "id": eid, "reason": reason})

    # ---- the reported bug ----
    def test_delete_reaches_the_apartment_report(self):
        self.assertEqual(self._unit_report()["expenses"], 750.0)   # baseline
        self._delete()
        rep = self._unit_report()
        self.assertEqual(rep["expenses"], 0.0,
                         "the apartment report/PDF still carries a deleted expense")
        self.assertEqual([x.get("id") for x in rep.get("exp_lines") or []], [])

    def test_delete_reaches_the_per_apartment_breakdown(self):
        self._delete()
        agg = OW.compute_owner_statement(OWNER, MONTH)
        self.assertEqual(agg["expenses"], 0.0)
        for p in agg.get("apartments") or []:
            self.assertEqual(p.get("expenses"), 0.0,
                             "the unit tab subtotal still counts the deleted expense")
            self.assertEqual(p.get("owner_net"), 0.0)

    def test_delete_counted_once_not_twice(self):
        # the owner total must not double-subtract now that both stores know
        bot._expenses["e10"] = {"id": "e10", "apartment": "C3", "listing_id": LID,
                                "amount": 200, "expense_date": "2026-07-12",
                                "hostaway_verified": True, "category": "صيانة", "note": "صحيح"}
        self._delete()
        agg = OW.compute_owner_statement(OWNER, MONTH)
        self.assertEqual(agg["expenses"], 200.0)
        self.assertEqual([x.get("id") for x in agg.get("exp_lines") or []], ["e10"])

    # ---- an amount/description edit must travel the same road ----
    def test_amount_edit_reaches_the_apartment_report(self):
        OW.statement_edit(_Req(), {"owner": OWNER, "m": MONTH, "op": "exp_override",
                                   "id": "e9", "amount": 300, "reason": "المبلغ الصحيح 300"})
        self.assertEqual(self._unit_report()["expenses"], 300.0,
                         "the apartment report still shows the old amount")
        self.assertEqual(OW.compute_owner_statement(OWNER, MONTH)["expenses"], 300.0)

    # ---- an expense we cannot attribute must still delete at owner level ----
    def test_unattributable_expense_still_deletes_without_crashing(self):
        bot._expenses["e11"] = {"id": "e11", "apartment": "C3", "listing_id": LID,
                                "amount": 90, "expense_date": "2026-07-20",
                                "hostaway_verified": True, "category": "صيانة", "note": "x"}
        bot._expenses["e11"].pop("listing_id")
        res = self._delete("e11")
        self.assertEqual(res[1], 200)

    # ---- deletes recorded BEFORE the mirror shipped must be honoured too ----
    def test_delete_recorded_before_the_fix_is_backfilled(self):
        """Owner-reported «ما انحلت» 2026-08-03: mirroring on WRITE only helps the
        next delete. Every expense the accountant had already deleted still sat in
        the apartment report, because its decision never reached the per-lid store.
        The store is backfilled from owner_statements.json, so old and new behave
        identically."""
        bot._save_json("owner_statements.json", {
            OWNER + "|" + MONTH: {
                "owner": OWNER, "month": MONTH, "status": "draft",
                "edits": {"resv": {}, "exp_manual": [], "adjustments": [],
                          "exp_overrides": {"e9": {"deleted": True, "reason": "مصروف غير صحيح",
                                                   "by": "المحاسب",
                                                   "at": "2026-08-01T10:00:00+03:00"}}},
                "audit": [], "published": None}})
        OW._stmt_cache["v"] = None
        bot._finance_adjust.clear()                     # nothing was ever mirrored
        agg = OW.compute_owner_statement(OWNER, MONTH)
        self.assertEqual(agg["expenses"], 0.0)
        for p in agg.get("apartments") or []:
            self.assertEqual(p.get("expenses"), 0.0,
                             "an OLD delete is still counted in the unit subtotal")
        self.assertEqual(self._unit_report()["expenses"], 0.0,
                         "an OLD delete is still on the apartment report/PDF")

    def test_old_amount_edit_is_backfilled_too(self):
        bot._save_json("owner_statements.json", {
            OWNER + "|" + MONTH: {
                "owner": OWNER, "month": MONTH, "status": "draft",
                "edits": {"resv": {}, "exp_manual": [], "adjustments": [],
                          "exp_overrides": {"e9": {"amount": 300.0, "reason": "الصحيح 300",
                                                   "by": "المحاسب",
                                                   "at": "2026-08-01T10:00:00+03:00"}}},
                "audit": [], "published": None}})
        OW._stmt_cache["v"] = None
        bot._finance_adjust.clear()
        OW.backfill_expense_mirrors()          # what mount() runs at boot
        self.assertEqual(self._unit_report()["expenses"], 300.0)

    def test_backfill_is_idempotent_and_does_not_double_apply(self):
        self._delete()
        first = OW.compute_owner_statement(OWNER, MONTH)["expenses"]
        for _ in range(3):
            OW._stmt_cache["v"] = None
            OW.compute_owner_statement(OWNER, MONTH)
        self.assertEqual(OW.compute_owner_statement(OWNER, MONTH)["expenses"], first)

    # ---- the audit trail survives the new road ----
    def test_reason_is_still_recorded(self):
        self._delete(reason="مكرر")
        rec = OW.stmt_rec(OWNER, MONTH) or {}
        self.assertEqual(((rec.get("edits") or {}).get("exp_overrides") or {})
                         .get("e9", {}).get("reason"), "مكرر")
        self.assertTrue(any(a.get("action") == "exp_delete" for a in rec.get("audit") or []))


if __name__ == "__main__":
    unittest.main(verbosity=2)
