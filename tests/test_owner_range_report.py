# -*- coding: utf-8 -*-
"""Custom-range owner report = SUM of the monthly statements.

The «تقرير لفترة مخصّصة» was built from the RAW engine (build_owner_report) and
never read the monthly statement editor overlay (owner_statements.json), so
manual expenses / edits / adjustments entered month-by-month silently vanished
from the range PDF — only Hostaway-matched expenses survived. Owner-reported on
احمد الصغير / L-07: April's matched 250 showed, May's manual 129 + 40 didn't.

Owner's chosen behaviour: the range report must equal the sum of the monthly
statements over the window (manual entries stay owner-level).

Run: python3 tests/test_owner_range_report.py
"""
import os
import shutil
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_STATE = "/tmp/ouja-test-state-range"
shutil.rmtree(_STATE, ignore_errors=True)
os.makedirs(_STATE, exist_ok=True)
os.environ["STATE_DIR"] = _STATE

import bot  # noqa: E402
from finance import api as fapi, owners as OW  # noqa: E402

fapi.attach(bot)


class _FakeReq:
    query = {}
    headers = {}
    remote = "test"


class RangeIncludesMonthlyEditsTest(unittest.TestCase):
    def setUp(self):
        OW._terms_cache["v"] = None
        OW._stmt_cache["v"] = None
        bot._save_json("owner_terms.json", {"owners": {}, "units": {}, "versions": []})
        bot._save_json("owner_statements.json", {})
        bot._owner_registry.clear()
        bot._owner_registry[bot._owner_key("L-07")] = {
            "apartment": "L-07", "owner": "احمد الصغير", "mgmt_pct": 15.0, "lid": 7001,
            "cleaning": {"type": "ours", "amount": 0}}   # cleaning off → isolate expenses
        self._patches = (bot.fetch_reservations_window, bot.get_listings_map)
        bot.fetch_reservations_window = lambda s, e, pad_days=45: []   # no Hostaway income/expenses
        bot.get_listings_map = lambda: {7001: "شقة 7 - الماجديه"}
        bot._expenses.clear()
        bot._owner_portal_cache.clear()
        bot._finance_adjust.clear()
        # two MANUAL expenses entered in the MAY statement editor (the «تسوية يدوية» rows)
        for amt, d, desc in ((129.0, "2026-05-17", "شراء ستائر"), (40.0, "2026-05-18", "تركيب ستائر")):
            data, status = OW.statement_edit(_FakeReq(), {
                "owner": "احمد الصغير", "m": "2026-05", "op": "exp_manual_add",
                "amount": amt, "date": d, "description": desc, "reason": "اختبار"})
            assert status == 200, data

    def tearDown(self):
        bot.fetch_reservations_window, bot.get_listings_map = self._patches
        OW._terms_cache["v"] = None
        OW._stmt_cache["v"] = None

    def test_raw_engine_misses_manual_expenses(self):
        # documents the BUG: the raw range engine never sees the editor overlay
        rep = bot.build_owner_report(7001, date(2026, 4, 1), date(2026, 6, 30), 0, {})
        self.assertEqual(rep["expenses"], 0.0)

    def test_range_includes_manual_expenses(self):
        rep, err = OW.compute_owner_range("احمد الصغير", date(2026, 4, 1), date(2026, 6, 30))
        self.assertIsNone(err)
        self.assertEqual(rep["expenses"], 169.0)                 # 129 + 40
        descs = {x.get("description") for x in (rep.get("exp_lines") or [])}
        self.assertIn("شراء ستائر", descs)
        self.assertIn("تركيب ستائر", descs)
        self.assertEqual(rep["owner_net"], -169.0)               # only the two expenses

    def test_parity_with_sum_of_monthly_statements(self):
        rep, _ = OW.compute_owner_range("احمد الصغير", date(2026, 4, 1), date(2026, 6, 30))
        months = ["2026-04", "2026-05", "2026-06"]
        s_exp = sum(OW.compute_owner_statement("احمد الصغير", m)["expenses"] for m in months)
        s_net = sum(OW.compute_owner_statement("احمد الصغير", m)["owner_net"] for m in months)
        self.assertAlmostEqual(rep["expenses"], s_exp, places=2)
        self.assertAlmostEqual(rep["owner_net"], s_net, places=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
