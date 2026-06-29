# -*- coding: utf-8 -*-
"""v2.5 — رسوم عوجا lid-resolution fix + per-month variable cleaning.

Pins two behaviors the accountants hit on «تقرير لفترة مخصّصة»:
  1. A unit whose Hostaway listing NAME carries no registry code (e.g.
     «شقة 7 - الماجديه» has no «L-07») still resolves its management % and
     cleaning policy — via the listing id, not the name. Was the «رسوم عوجا = 0»
     bug: build_owner_report silently fell back to 0% / Ouja-paid cleaning.
  2. Cleaning can carry a DIFFERENT amount per month via per-month overrides;
     months without an override use the unit's base amount. Flows through the
     range report (compute_owner_report) and the monthly statement.

Run: python3 tests/test_owner_cleaning_month_v25.py
"""
import os
import shutil
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_STATE = "/tmp/ouja-test-state-clm"
shutil.rmtree(_STATE, ignore_errors=True)
os.makedirs(_STATE, exist_ok=True)
os.environ["STATE_DIR"] = _STATE

import bot  # noqa: E402
from finance import api as fapi, owners as OW  # noqa: E402

fapi.attach(bot)


class _FakeReq:
    """Minimal stand-in so write endpoints can resolve an actor offline."""
    query = {}
    headers = {}
    remote = "test"


def _resv(rid, lid, payout, checkin, checkout):
    return {"id": rid, "listingMapId": lid, "status": "new", "channelName": "Airbnb",
            "arrivalDate": checkin, "departureDate": checkout, "nights": 3,
            "guestName": "G" + str(rid), "airbnbExpectedPayoutAmount": payout,
            "totalPrice": payout + 400, "refundAmount": None}


class LidResolutionTest(unittest.TestCase):
    """The «رسوم عوجا = 0» fix: name-match fails, lid-match wins."""

    def setUp(self):
        OW._terms_cache["v"] = None
        bot._save_json("owner_terms.json", {"owners": {}, "units": {}, "versions": []})
        bot._owner_registry.clear()
        # registry code «L-07» — but the listing name is Arabic, no «L-07» token
        bot._owner_registry[bot._owner_key("L-07")] = {
            "apartment": "L-07", "owner": "احمد الصغير", "mgmt_pct": 15.0, "lid": 7001,
            "cleaning": {"type": "ours", "amount": 0}}
        self._patches = (bot.fetch_reservations_window, bot.get_listings_map)
        bot.fetch_reservations_window = lambda s, e, pad_days=45: [
            _resv("r1", 7001, 10000.0, "2026-04-05", "2026-04-08")]
        bot.get_listings_map = lambda: {7001: "شقة 7 - الماجديه"}   # NO «L-07» in the name
        bot._expenses.clear()
        bot._owner_portal_cache.clear()

    def tearDown(self):
        bot.fetch_reservations_window, bot.get_listings_map = self._patches
        OW._terms_cache["v"] = None

    def test_mgmt_resolves_by_lid_when_name_has_no_code(self):
        rep = bot.build_owner_report(7001, date(2026, 4, 1), date(2026, 4, 30), 0, {})
        self.assertEqual(rep["management_pct"], 15.0)        # was silently 0 → ouja_fee 0
        self.assertEqual(rep["total_income"], 10000.0)
        self.assertEqual(rep["ouja_fee"], 1500.0)            # 15% of 10,000
        self.assertEqual(rep["owner"], "احمد الصغير")

    def test_info_by_lid_helper(self):
        rec = bot._owner_info_by_lid(7001)
        self.assertIsNotNone(rec)
        self.assertEqual(rec["owner"], "احمد الصغير")
        self.assertIsNone(bot._owner_info_by_lid(99999))


class PerMonthCleaningTest(unittest.TestCase):
    """Each month can carry its own cleaning amount."""

    def setUp(self):
        OW._terms_cache["v"] = None
        bot._save_json("owner_terms.json", {"owners": {}, "units": {}, "versions": []})
        bot._owner_registry.clear()
        bot._owner_registry[bot._owner_key("T1")] = {
            "apartment": "T1", "owner": "مالك تجريبي", "mgmt_pct": 20.0, "lid": 11,
            "cleaning": {"type": "owner", "amount": 1000.0,
                         "overrides": {"2026-05": 300.0}}}
        self._patches = (bot.fetch_reservations_window, bot.get_listings_map)
        bot.fetch_reservations_window = lambda s, e, pad_days=45: []   # isolate cleaning math
        bot.get_listings_map = lambda: {11: "Ouja | T1"}
        bot._expenses.clear()
        bot._owner_portal_cache.clear()

    def tearDown(self):
        bot.fetch_reservations_window, bot.get_listings_map = self._patches
        OW._terms_cache["v"] = None

    def test_range_sums_per_month_overrides(self):
        # April (base 1000) + May (override 300) + June (base 1000) = 2300
        rep = bot.build_owner_report(11, date(2026, 4, 1), date(2026, 6, 30), 0, {})
        self.assertEqual(rep["cleaning"]["total"], 2300.0)
        per = {x["m"]: x["amount"] for x in rep["cleaning"]["per_month"]}
        self.assertEqual(per, {"2026-04": 1000.0, "2026-05": 300.0, "2026-06": 1000.0})

    def test_helper_month_amount(self):
        cl = {"type": "owner", "amount": 1000.0, "overrides": {"2026-05": 300.0, "2026-07": 0.0}}
        self.assertEqual(bot._cleaning_month_amount(cl, 2026, 4), 1000.0)   # base
        self.assertEqual(bot._cleaning_month_amount(cl, 2026, 5), 300.0)    # override
        self.assertEqual(bot._cleaning_month_amount(cl, 2026, 7), 0.0)      # override 0 = free
        self.assertEqual(bot._cleaning_month_amount({"type": "ours", "amount": 9}, 2026, 5), 0.0)

    def test_monthly_statement_uses_override(self):
        may = OW.compute_owner_statement("مالك تجريبي", "2026-05")
        self.assertEqual(may["cleaning"]["total"], 300.0)
        apr = OW.compute_owner_statement("مالك تجريبي", "2026-04")
        self.assertEqual(apr["cleaning"]["total"], 1000.0)


class CleaningMonthEndpointTest(unittest.TestCase):
    def setUp(self):
        OW._terms_cache["v"] = None
        bot._save_json("owner_terms.json", {"owners": {}, "units": {}, "versions": []})
        bot._owner_registry.clear()
        bot._owner_registry[bot._owner_key("T1")] = {
            "apartment": "T1", "owner": "مالك تجريبي", "mgmt_pct": 20.0, "lid": 11,
            "cleaning": {"type": "owner", "amount": 1000.0}}
        bot.get_listings_map = lambda: {11: "Ouja | T1"}

    def test_set_then_clear(self):
        data, status = OW.unit_cleaning_month_set(_FakeReq(), {"apartment": "T1", "month": "2026-05", "amount": 250})
        self.assertEqual(status, 200)
        self.assertEqual(data["overrides"]["2026-05"], 250.0)
        # clear it
        data, status = OW.unit_cleaning_month_set(_FakeReq(), {"apartment": "T1", "month": "2026-05", "clear": True})
        self.assertEqual(status, 200)
        self.assertNotIn("2026-05", data["overrides"])

    def test_bad_month_rejected(self):
        _data, status = OW.unit_cleaning_month_set(_FakeReq(), {"apartment": "T1", "month": "2026-13", "amount": 1})
        self.assertEqual(status, 400)

    def test_refuses_when_ouja_paid(self):
        bot._owner_registry[bot._owner_key("T1")]["cleaning"] = {"type": "ours", "amount": 0}
        data, status = OW.unit_cleaning_month_set(_FakeReq(), {"apartment": "T1", "month": "2026-05", "amount": 250})
        self.assertEqual(status, 400)
        self.assertEqual(data["error"], "not_owner_paid")


if __name__ == "__main__":
    unittest.main(verbosity=2)
