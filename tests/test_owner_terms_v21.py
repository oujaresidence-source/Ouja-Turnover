# -*- coding: utf-8 -*-
"""Slice 1 regression — effective-dated owner terms (finance/owners.py).

Pins the acceptance-C behavior:
  • a unit added mid-month contributes ONLY its in-contract reservations,
    with a footnote («من <date> حسب العقد»)
  • a removed unit counts until its end date, then drops out
  • mgmt % changes apply per reservation by its check-in date
  • cleaning (owner-pays, monthly) pro-rates to covered days
  • NO overlay data → the legacy report passes through bit-for-bit

Run: python3 tests/test_owner_terms_v21.py
"""
import os
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_STATE = "/tmp/ouja-test-state-s1"
shutil.rmtree(_STATE, ignore_errors=True)
os.makedirs(_STATE, exist_ok=True)
os.environ["STATE_DIR"] = _STATE

import bot  # noqa: E402
from finance import api as fapi, owners as OW  # noqa: E402

fapi.attach(bot)

JUNE = "2026-06"


def _resv(rid, lid, payout, checkin, checkout):
    return {"id": rid, "listingMapId": lid, "status": "new", "channelName": "Airbnb",
            "arrivalDate": checkin, "departureDate": checkout, "nights": 3,
            "guestName": "G" + str(rid), "airbnbExpectedPayoutAmount": payout,
            "totalPrice": payout + 400, "refundAmount": None}


ROWS = [
    _resv("r1", 11, 1000.0, "2026-06-03", "2026-06-06"),
    _resv("r2", 11, 2000.0, "2026-06-16", "2026-06-19"),
]


class EffectiveDatingTest(unittest.TestCase):
    def setUp(self):
        OW._terms_cache["v"] = None
        bot._save_json("owner_terms.json", {"owners": {}, "units": {}, "versions": []})
        bot._owner_registry.clear()
        bot._owner_registry[bot._owner_key("T1")] = {
            "apartment": "T1", "owner": "مالك تجريبي", "mgmt_pct": 20.0, "lid": 11,
            "cleaning": {"type": "ours", "amount": 0}}
        self._patches = (bot.fetch_reservations_window, bot.get_listings_map)
        bot.fetch_reservations_window = lambda s, e, pad_days=45: ROWS
        bot.get_listings_map = lambda: {11: "Ouja | T1"}
        bot._expenses.clear()
        bot._owner_portal_cache.clear()

    def tearDown(self):
        bot.fetch_reservations_window, bot.get_listings_map = self._patches
        OW._terms_cache["v"] = None

    def test_no_overlay_passes_legacy_through(self):
        rep = OW.compute_owner_statement("مالك تجريبي", JUNE)
        self.assertEqual(rep["total_income"], 3000.0)
        self.assertEqual(rep["ouja_fee"], 600.0)          # flat 20%
        self.assertEqual(rep["owner_net"], 2400.0)
        self.assertNotIn("footnotes", rep)

    def test_unit_added_mid_month_counts_from_contract_start(self):
        st = OW._terms_store()
        st["units"][bot._owner_key("T1")] = {"contract_from": "2026-06-12"}
        rep = OW.compute_owner_statement("مالك تجريبي", JUNE)
        # r1 (June 3) excluded — outside the contract; r2 (June 16) included
        self.assertEqual(rep["total_income"], 2000.0)
        self.assertEqual(rep["owner_net"], 1600.0)
        ex = rep.get("contract_excluded_lines") or []
        self.assertEqual(len(ex), 1)
        self.assertEqual(ex[0]["exclude_reason"], "outside_contract")
        self.assertEqual(ex[0]["reference_total"], 1000.0)
        foots = rep.get("footnotes") or []
        self.assertTrue(any("من 2026-06-12 حسب العقد" in f["text_ar"] for f in foots))

    def test_unit_removed_counts_until_end_date(self):
        st = OW._terms_store()
        st["units"][bot._owner_key("T1")] = {"contract_to": "2026-06-10"}
        rep = OW.compute_owner_statement("مالك تجريبي", JUNE)
        self.assertEqual(rep["total_income"], 1000.0)     # only the June-3 stay
        self.assertTrue(any(f["kind"] == "ends_mid_month" for f in rep.get("footnotes") or []))

    def test_mgmt_change_applies_per_checkin_date(self):
        st = OW._terms_store()
        st["units"][bot._owner_key("T1")] = {
            "terms": [{"from": "2026-06-10", "mgmt_pct": 10.0}]}
        rep = OW.compute_owner_statement("مالك تجريبي", JUNE)
        # r1 checks in June 3 → registry 20% (200); r2 June 16 → 10% (200)
        self.assertEqual(rep["total_income"], 3000.0)
        self.assertEqual(rep["ouja_fee"], 400.0)
        self.assertEqual(rep["owner_net"], 2600.0)

    def test_cleaning_prorated_for_partial_month(self):
        st = OW._terms_store()
        st["units"][bot._owner_key("T1")] = {
            "contract_from": "2026-06-16",
            "terms": [{"from": "2026-06-16", "cleaning": {"type": "owner", "amount": 1000.0}}]}
        rep = OW.compute_owner_statement("مالك تجريبي", JUNE)
        # 15 covered days of 30 → 500.00 cleaning; only r2 income
        self.assertEqual(rep["cleaning"]["total"], 500.0)
        self.assertEqual(rep["total_income"], 2000.0)
        self.assertTrue(any(f["kind"] == "cleaning_prorated" for f in rep.get("footnotes") or []))

    def test_hook_feeds_owner_month_report(self):
        bot._owner_statement_hook = OW.compute_owner_statement
        try:
            st = OW._terms_store()
            st["units"][bot._owner_key("T1")] = {"contract_from": "2026-06-12"}
            bot._owner_portal_cache.clear()
            rep = bot._owner_month_report("مالك تجريبي", JUNE)
            self.assertEqual(rep["total_income"], 2000.0)
        finally:
            del bot._owner_statement_hook
            bot._owner_portal_cache.clear()


if __name__ == "__main__":
    unittest.main(verbosity=2)
