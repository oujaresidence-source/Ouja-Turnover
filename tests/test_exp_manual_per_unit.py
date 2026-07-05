# -*- coding: utf-8 -*-
"""Per-apartment manual expenses (the inc_manual_add pattern, applied to expenses).

Owner-reported 2026-07-05: a multi-apartment owner enters expenses «لكل شقة على
حدة» in the statement editor, the per-APARTMENT print shows no expense, but the
owner TOTAL shows it. Cause: exp_manual_add stored the row owner-level with no
apartment/lid, so build_owner_report(lid) — the engine behind every per-unit
surface (unit PDF, range report with apt filter, unit tab subtotals) — could
never attribute it. Manual INCOME had the same bug and was fixed in v2.2 slice 3
by landing in the per-lid _finance_adjust store; this locks the same fix for
expenses.

Run: python3 tests/test_exp_manual_per_unit.py
"""
import os
import shutil
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_STATE = "/tmp/ouja-test-state-expunit"
shutil.rmtree(_STATE, ignore_errors=True)
os.makedirs(_STATE, exist_ok=True)
os.environ["STATE_DIR"] = _STATE

import bot  # noqa: E402
from finance import api as fapi, owners as OW  # noqa: E402

fapi.attach(bot)

JUNE = "2026-06"
OWNER = "مالك متعدد"


class _Req:
    query = {}
    headers = {}
    remote = "test"


class PerUnitManualExpenseTest(unittest.TestCase):
    def setUp(self):
        OW._terms_cache["v"] = None
        OW._stmt_cache["v"] = None
        bot._save_json("owner_terms.json", {"owners": {}, "units": {}, "versions": []})
        bot._save_json("owner_statements.json", {})
        bot._owner_registry.clear()
        for apt, lid in (("M-01", 31), ("M-02", 32)):
            bot._owner_registry[bot._owner_key(apt)] = {
                "apartment": apt, "owner": OWNER, "mgmt_pct": 20.0, "lid": lid,
                "cleaning": {"type": "ours", "amount": 0}}
        self._patches = (bot.fetch_reservations_window, bot.get_listings_map)
        bot.fetch_reservations_window = lambda s, e, pad_days=45: []   # isolate expenses
        bot.get_listings_map = lambda: {31: "Ouja | M-01", 32: "Ouja | M-02"}
        bot._expenses.clear()
        bot._owner_portal_cache.clear()
        bot._finance_adjust.clear()

    def tearDown(self):
        bot.fetch_reservations_window, bot.get_listings_map = self._patches
        bot._finance_adjust.clear()
        OW._terms_cache["v"] = None
        OW._stmt_cache["v"] = None

    def _add(self, lid=None, amount=100.0):
        body = {"owner": OWNER, "m": JUNE, "op": "exp_manual_add",
                "amount": amount, "date": "2026-06-15",
                "description": "غيار قفل", "reason": "فاتورة ورقية"}
        if lid is not None:
            body["lid"] = lid
        return OW.statement_edit(_Req(), body)

    def test_unit_report_shows_the_expense(self):
        # THE user-reported bug: the per-apartment print must show the expense
        data, code = self._add(lid=31)
        self.assertEqual(code, 200, data)
        rep = bot.build_owner_report(31, date(2026, 6, 1), date(2026, 6, 30), 0, {})
        self.assertEqual(rep["expenses"], 100.0)
        line = [x for x in rep["exp_lines"] if x.get("manual")][0]
        self.assertEqual(line["description"], "غيار قفل")
        self.assertEqual(line["date"], "2026-06-15")
        self.assertEqual(line["lid"], 31)
        self.assertEqual(line["apartment"], "Ouja | M-01")
        # …and ONLY on its own unit
        other = bot.build_owner_report(32, date(2026, 6, 1), date(2026, 6, 30), 0, {})
        self.assertEqual(other["expenses"], 0.0)

    def test_owner_total_counts_it_exactly_once(self):
        self._add(lid=31)
        s = OW.compute_owner_statement(OWNER, JUNE)
        self.assertEqual(s["expenses"], 100.0)
        self.assertEqual(s["owner_net"], -100.0)
        parts = {p["lid"]: p for p in s["apartments"]}
        self.assertEqual(parts[31]["expenses"], 100.0)   # unit subtotal carries it too
        self.assertEqual(parts[32]["expenses"], 0.0)

    def test_range_report_apt_slice_shows_it(self):
        # the «تقرير لفترة مخصّصة» filtered to one apartment — the print the owner uses
        self._add(lid=31)
        rep, err = OW.compute_owner_range(OWNER, date(2026, 6, 1), date(2026, 6, 30), apt="M-01")
        self.assertIsNone(err)
        self.assertEqual(rep["expenses"], 100.0)
        rep2, _ = OW.compute_owner_range(OWNER, date(2026, 6, 1), date(2026, 6, 30), apt="M-02")
        self.assertEqual(rep2["expenses"], 0.0)

    def test_delete_removes_it_everywhere(self):
        data, _ = self._add(lid=31)
        line = [x for x in data["statement"]["exp_lines"] if x.get("manual")][0]
        data, code = OW.statement_edit(_Req(), {
            "owner": OWNER, "m": JUNE, "op": "exp_manual_del",
            "id": line["id"], "lid": 31})
        self.assertEqual(code, 200, data)
        self.assertEqual(data["statement"]["expenses"], 0.0)
        rep = bot.build_owner_report(31, date(2026, 6, 1), date(2026, 6, 30), 0, {})
        self.assertEqual(rep["expenses"], 0.0)

    def test_delete_never_touches_income_lines(self):
        OW.statement_edit(_Req(), {"owner": OWNER, "m": JUNE, "op": "inc_manual_add",
                                   "lid": 31, "amount": 500.0, "label": "إيراد",
                                   "reason": "اختبار"})
        data, code = OW.statement_edit(_Req(), {
            "owner": OWNER, "m": JUNE, "op": "exp_manual_del",
            "id": "exp-adj-0", "lid": 31})
        self.assertEqual(code, 404)                      # index 0 is an income line
        s = OW.compute_owner_statement(OWNER, JUNE)
        self.assertEqual(s["manual_income"], 500.0)      # untouched

    def test_no_lid_stays_owner_level(self):
        # legacy path unchanged: no apartment → owner statement only (footnoted
        # behavior the range-report test pinned for single-unit owners)
        data, code = self._add(lid=None)
        self.assertEqual(code, 200, data)
        self.assertEqual(data["statement"]["expenses"], 100.0)
        rep = bot.build_owner_report(31, date(2026, 6, 1), date(2026, 6, 30), 0, {})
        self.assertEqual(rep["expenses"], 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
