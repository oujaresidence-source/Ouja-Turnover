# -*- coding: utf-8 -*-
"""Cleaning-type label must survive aggregation (نواف الوهيبي bug, 2026-07-05).

Owner-reported: terms say cleaning «يدفعها المالك (شهري) · 950» and the statement
correctly DEDUCTS 950 — but the PDF header says «النظافة: على عوجا (مشمولة)».
Cause: both aggregators (bot._finance_aggregate for the owner month,
owners._aggregate_period for the range report) hardcoded cleaning type "mixed",
so every `type == "owner"` label check downstream (PDF header, editor explain)
fell to the على-عوجا branch even for a single-unit owner-paid statement.

Run: python3 tests/test_cleaning_label_aggregate.py
"""
import os
import shutil
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_STATE = "/tmp/ouja-test-state-cllabel"
shutil.rmtree(_STATE, ignore_errors=True)
os.makedirs(_STATE, exist_ok=True)
os.environ["STATE_DIR"] = _STATE

import bot  # noqa: E402
from finance import api as fapi, owners as OW  # noqa: E402

fapi.attach(bot)

JUNE = "2026-06"


class CleaningLabelAggregateTest(unittest.TestCase):
    def setUp(self):
        OW._terms_cache["v"] = None
        OW._stmt_cache["v"] = None
        bot._save_json("owner_terms.json", {"owners": {}, "units": {}, "versions": []})
        bot._save_json("owner_statements.json", {})
        bot._owner_registry.clear()
        bot._owner_registry[bot._owner_key("C2")] = {
            "apartment": "C2", "owner": "نواف الوهيبي", "mgmt_pct": 15.0, "lid": 41,
            "cleaning": {"type": "owner", "amount": 950.0}}
        bot._owner_registry[bot._owner_key("MX1")] = {
            "apartment": "MX1", "owner": "مالك مختلط", "mgmt_pct": 20.0, "lid": 51,
            "cleaning": {"type": "owner", "amount": 500.0}}
        bot._owner_registry[bot._owner_key("MX2")] = {
            "apartment": "MX2", "owner": "مالك مختلط", "mgmt_pct": 20.0, "lid": 52,
            "cleaning": {"type": "ours", "amount": 0}}
        self._patches = (bot.fetch_reservations_window, bot.get_listings_map)
        bot.fetch_reservations_window = lambda s, e, pad_days=45: []
        bot.get_listings_map = lambda: {41: "Ouja | C2", 51: "Ouja | MX1", 52: "Ouja | MX2"}
        bot._expenses.clear()
        bot._owner_portal_cache.clear()
        bot._finance_adjust.clear()

    def tearDown(self):
        bot.fetch_reservations_window, bot.get_listings_map = self._patches
        OW._terms_cache["v"] = None
        OW._stmt_cache["v"] = None

    def test_single_unit_owner_paid_keeps_type(self):
        s = OW.compute_owner_statement("نواف الوهيبي", JUNE)
        cl = s["cleaning"]
        self.assertEqual(cl["total"], 950.0)               # the math (was already right)
        self.assertEqual(cl["type"], "owner")              # the LABEL source (was "mixed")
        self.assertEqual(cl["amount"], 950.0)

    def test_range_report_keeps_type(self):
        rep, err = OW.compute_owner_range("نواف الوهيبي", date(2026, 5, 1), date(2026, 6, 30))
        self.assertIsNone(err)
        cl = rep["cleaning"]
        self.assertEqual(cl["type"], "owner")
        self.assertEqual(cl["amount"], 950.0)
        self.assertEqual(cl["total"], 1900.0)              # two owner-paid months

    def test_genuinely_mixed_owner_stays_mixed(self):
        s = OW.compute_owner_statement("مالك مختلط", JUNE)
        cl = s["cleaning"]
        self.assertEqual(cl["type"], "mixed")
        self.assertEqual(cl["total"], 500.0)               # only the owner-paid unit

    def test_pdf_header_label(self):
        self.assertIn("يدفعها المالك", bot._pdf_cleaning_label(
            {"type": "owner", "amount": 950.0, "total": 950.0}))
        self.assertIn("950", bot._pdf_cleaning_label(
            {"type": "owner", "amount": 950.0, "total": 950.0}))
        # mixed with money deducted must NOT claim «على عوجا (مشمولة)»
        self.assertNotIn("مشمولة", bot._pdf_cleaning_label(
            {"type": "mixed", "amount": None, "total": 500.0}))
        self.assertIn("مشمولة", bot._pdf_cleaning_label(
            {"type": "ours", "amount": 0, "total": 0}))
        self.assertIn("مشمولة", bot._pdf_cleaning_label(
            {"type": "mixed", "amount": None, "total": 0}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
