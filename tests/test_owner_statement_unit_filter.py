# -*- coding: utf-8 -*-
"""Per-unit statement filtering must key off the Hostaway LISTING ID, not the
apartment NAME text.

The bug (فوزيه, تسريب سخان 30 ر.س): an expense / reservation is tied to a unit by
`listing_id` and is therefore counted in the owner total, but the management
window's per-apartment view filtered the displayed line list by the apartment
NAME string. When the stored apartment text differs from the Hostaway listing
name (e.g. «شقة 7» vs «Ouja | ... شقة 7 - الماجديه»), the correctly-attributed
line was hidden — present in the owner total, invisible on the apartment.

The erp.js filter now matches on `lid`; this suite pins the server-side contract
it depends on: every reservation AND expense line carries a `lid`, and it is the
real listing id even when the apartment name text does not match.

Run: python3 tests/test_owner_statement_unit_filter.py
"""
import os
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("STATE_DIR", "/tmp/ouja-test-state-uf")
os.makedirs("/tmp/ouja-test-state-uf", exist_ok=True)

import bot  # noqa: E402

JUNE_S, JUNE_E = date(2026, 6, 1), date(2026, 6, 30)


def _norm_resv(rid, lid, payout, apartment):
    """A normalized finance row (the shape compute_owner_report consumes)."""
    return {"id": rid, "channel": "airbnb", "status": "new", "lid": lid,
            "apartment": apartment, "checkin": "2026-06-05", "checkout": "2026-06-08",
            "nights": 3, "airbnb_payout": payout, "total_price": None,
            "refund": 0, "extras": 0}


class ResvLineCarriesLidTest(unittest.TestCase):
    def test_income_line_exposes_lid(self):
        rows = [_norm_resv("r1", 4321, 1000.0, "Ouja | شقة 7 - الماجديه")]
        rep = bot.compute_owner_report(rows, [], JUNE_S, JUNE_E, 18.0)
        line = rep["resv_lines"][0]
        self.assertEqual(line["lid"], 4321)          # the id, so the UI can filter by it
        self.assertEqual(line["income"], 1000.0)

    def test_needs_review_and_refunded_lines_also_carry_lid(self):
        rows = [
            _norm_resv("r2", 77, None, "unit-77"),                # missing payout → needs_review
            dict(_norm_resv("r3", 88, 500.0, "unit-88"), status="cancelled"),  # refunded footer
        ]
        rep = bot.compute_owner_report(rows, [], JUNE_S, JUNE_E, 18.0)
        nr = [l for l in rep["resv_lines"] if l.get("needs_review")]
        self.assertEqual(nr[0]["lid"], 77)
        self.assertEqual(rep["refunded_lines"][0]["lid"], 88)


class ExpenseLineCarriesLidTest(unittest.TestCase):
    def test_expense_line_keeps_its_listing_id_despite_name_mismatch(self):
        # expense stored with a SHORT apartment text, but tied to lid 4321
        rows = [_norm_resv("r1", 4321, 1000.0, "Ouja | شقة 7 - الماجديه")]
        exp = [{"id": "e1", "apartment": "شقة 7", "lid": 4321, "amount": 30.0,
                "date": "2026-06-12", "matched": True, "category": "صيانة",
                "description": "تسريب سخان"}]
        rep = bot.compute_owner_report(rows, exp, JUNE_S, JUNE_E, 18.0)
        self.assertEqual(len(rep["exp_lines"]), 1)
        line = rep["exp_lines"][0]
        self.assertEqual(line["lid"], 4321)          # id survives → per-unit view can match it
        self.assertEqual(line["amount"], 30.0)
        self.assertEqual(rep["expenses"], 30.0)      # and it is counted in the total


if __name__ == "__main__":
    unittest.main(verbosity=2)
