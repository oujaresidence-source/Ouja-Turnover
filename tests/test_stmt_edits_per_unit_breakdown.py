# -*- coding: utf-8 -*-
"""Editor decisions about BOOKINGS must reach the apartment breakdown + PDF.

Owner-reported 2026-08-04 (ابو فهد عبدالحمن الخطيب / 2026-07, apartment 202A): two
cancelled bookings were force-included in the editor with «حجز ملغي» + an amount.
They showed on screen and in the owner total — but the apartment's PDF ignored
them and still listed both under «حركات بدون فلوس».

Live data at the time proved it exactly:

    statement total_income ........ 64,941.83   (includes 2 x 255.56)
    apartments[] «202A» ...........  5,839.38   <- pre-edit, and what the PDF printed
    correct 202A ..................  6,350.50

Two gaps, both here:
1. `_apply_stmt_edits` patched the owner top-level but left `apartments[]` exactly
   as `_finance_aggregate` built it — from the UNEDITED per-unit reports.
2. `compute_owner_range(apt=…)` for a multi-unit owner skipped the statement
   entirely and re-ran the raw engine, so no editor decision could survive.

Run: python3 tests/test_stmt_edits_per_unit_breakdown.py
"""
import os
import shutil
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_STATE = "/tmp/ouja-test-state-unitbreakdown"
shutil.rmtree(_STATE, ignore_errors=True)
os.makedirs(_STATE, exist_ok=True)
os.environ["STATE_DIR"] = _STATE

import bot  # noqa: E402
from finance import api as fapi, owners as OW  # noqa: E402

fapi.attach(bot)

MONTH = "2026-07"
OWNER = "ابو فهد"
LID_A = 473607          # 202A — the apartment in the report
LID_B = 473608          # a second unit, so an apt filter is NOT owner-level


def _resv(rid, lid, checkin, checkout, price, status="new"):
    return {"id": rid, "listingMapId": lid, "arrivalDate": checkin,
            "departureDate": checkout, "nights": 1, "totalPrice": price,
            "guestName": "ضيف " + str(rid), "status": status,
            "channelName": "airbnb", "airbnbExpectedPayoutAmount": price,
            "alreadyPaid": price, "paymentStatus": "paid"}


class _Req:
    query = {}
    headers = {}
    remote = "test"


class UnitBreakdownReflectsEditsTest(unittest.TestCase):
    def setUp(self):
        OW._terms_cache["v"] = None
        OW._stmt_cache["v"] = None
        bot._save_json("owner_terms.json", {"owners": {}, "units": {}, "versions": []})
        bot._save_json("owner_statements.json", {})
        bot._owner_registry.clear()
        for apt, lid in (("202A", LID_A), ("303B", LID_B)):
            bot._owner_registry[bot._owner_key(apt)] = {
                "apartment": apt, "owner": OWNER, "mgmt_pct": 18.0, "lid": lid,
                "cleaning": {"type": "ours", "amount": 0}}
        self._patched = (bot.fetch_reservations_window, bot.fetch_reservations_window_checked,
                         bot.get_listings_map)
        rows = [
            _resv(1001, LID_A, "2026-07-05", "2026-07-06", 1000.0),          # counts
            _resv(1002, LID_A, "2026-07-26", "2026-07-27", 255.56, "cancelled"),  # refunded
            _resv(2001, LID_B, "2026-07-08", "2026-07-09", 500.0),           # other unit
        ]
        bot.fetch_reservations_window = lambda s, e, pad_days=45: list(rows)
        bot.fetch_reservations_window_checked = lambda s, e: (list(rows), False)
        bot.get_listings_map = lambda: {LID_A: "202A", LID_B: "303B"}
        bot._expenses.clear()
        bot._owner_portal_cache.clear()
        bot._finance_adjust.clear()

    def tearDown(self):
        (bot.fetch_reservations_window, bot.fetch_reservations_window_checked,
         bot.get_listings_map) = self._patched

    def _part(self, agg, lid=LID_A):
        for p in agg.get("apartments") or []:
            if str(p.get("lid")) == str(lid):
                return p
        return {}

    def _range_apt(self, apt="202A"):
        rep, err = OW.compute_owner_range(OWNER, date(2026, 7, 1), date(2026, 7, 31), apt=apt)
        self.assertIsNone(err, "range report failed: %s" % err)
        return rep

    # ---- baseline: the fixture behaves as expected before any edit ----
    def test_baseline_cancelled_booking_is_not_income(self):
        agg = OW.compute_owner_statement(OWNER, MONTH)
        self.assertEqual(self._part(agg)["total_income"], 1000.0)
        self.assertTrue(any(str(l.get("id")) == "1002" for l in agg.get("refunded_lines") or []))

    # ---- the reported bug ----
    def test_forced_include_reaches_the_apartment_breakdown(self):
        OW.statement_edit(_Req(), {"owner": OWNER, "m": MONTH, "op": "resv_include",
                                   "id": "1002", "amount": 255.56, "reason": "حجز ملغي"})
        agg = OW.compute_owner_statement(OWNER, MONTH)
        self.assertEqual(agg["total_income"], 1755.56)          # owner total was always right
        self.assertEqual(self._part(agg)["total_income"], 1255.56,
                         "the apartment breakdown ignored the forced include")
        self.assertEqual(self._part(agg)["ouja_fee"], 226.0)    # 18% of 1255.56
        self.assertEqual(self._part(agg)["owner_net"], 1029.56)

    def test_forced_include_reaches_the_apartment_pdf(self):
        OW.statement_edit(_Req(), {"owner": OWNER, "m": MONTH, "op": "resv_include",
                                   "id": "1002", "amount": 255.56, "reason": "حجز ملغي"})
        rep = self._range_apt()
        self.assertEqual(rep["total_income"], 1255.56,
                         "the apartment PDF/range report ignored the forced include")
        self.assertFalse(any(str(l.get("id")) == "1002" for l in rep.get("refunded_lines") or []),
                         "an included booking must not still print as «حركات بدون فلوس»")

    # ---- the mirror image: an exclusion must also reach the unit ----
    def test_exclusion_reaches_the_apartment_breakdown_and_pdf(self):
        OW.statement_edit(_Req(), {"owner": OWNER, "m": MONTH, "op": "resv_exclude",
                                   "id": "1001", "reason": "مو حق المالك"})
        agg = OW.compute_owner_statement(OWNER, MONTH)
        self.assertEqual(self._part(agg)["total_income"], 0.0,
                         "the excluded booking is still counted on the apartment")
        self.assertEqual(self._range_apt()["total_income"], 0.0)

    # ---- the OTHER unit must not be disturbed ----
    def test_other_unit_is_untouched(self):
        OW.statement_edit(_Req(), {"owner": OWNER, "m": MONTH, "op": "resv_include",
                                   "id": "1002", "amount": 255.56, "reason": "حجز ملغي"})
        agg = OW.compute_owner_statement(OWNER, MONTH)
        self.assertEqual(self._part(agg, LID_B)["total_income"], 500.0)
        self.assertEqual(self._range_apt("303B")["total_income"], 500.0)

    # ---- the unit subtotals must still sum to the owner total ----
    def test_units_sum_to_the_owner_total(self):
        OW.statement_edit(_Req(), {"owner": OWNER, "m": MONTH, "op": "resv_include",
                                   "id": "1002", "amount": 255.56, "reason": "حجز ملغي"})
        agg = OW.compute_owner_statement(OWNER, MONTH)
        parts = agg.get("apartments") or []
        self.assertEqual(round(sum(float(p.get("total_income") or 0) for p in parts), 2),
                         agg["total_income"])
        self.assertEqual(round(sum(float(p.get("owner_net") or 0) for p in parts), 2),
                         agg["owner_net"])

    # ---- a per-apartment manual expense still lands on its own unit ----
    def test_manual_expense_still_lands_on_its_unit(self):
        OW.statement_edit(_Req(), {"owner": OWNER, "m": MONTH, "op": "exp_manual_add",
                                   "amount": 120, "date": "2026-07-09", "lid": str(LID_A),
                                   "description": "صيانة", "reason": "صيانة"})
        agg = OW.compute_owner_statement(OWNER, MONTH)
        self.assertEqual(self._part(agg)["expenses"], 120.0)
        self.assertEqual(self._part(agg, LID_B)["expenses"], 0.0)
        self.assertEqual(self._range_apt()["expenses"], 120.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
