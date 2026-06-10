# -*- coding: utf-8 -*-
"""ERP v2 statements + budget math regression tests (pure finance/statements.py).

Includes the LIVE production scenario from 2026-06-10: a fully UNTYPED Daftra
chart (0% typed) where bank accounts carry credit balances and the untyped
bucket holds the counterpart — the accounting equation must read gap=0.00
(books balance; classification is merely incomplete), and «رسوم بنكية» must
never be treated as a cash/asset account through the «بنك» substring.

Run: python3 tests/test_erp_statements.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from finance import statements as ST  # noqa: E402


def _acc(aid, name, code, payload=None):
    return {"source_id": aid, "display_name": name, "code": code,
            "source_payload": payload or {}}


def _line(aid, name, debit="0.00", credit="0.00", cc=None, ccn=""):
    return {"line_id": aid + "-" + debit + "-" + credit, "account_id": aid,
            "account_name": name, "debit": debit, "credit": credit,
            "cost_center_id": cc, "cost_center_name": ccn}


class CashWordDetectionTest(unittest.TestCase):
    def test_bank_fees_are_not_cash(self):
        self.assertFalse(ST._name_is_cash("رسوم بنكية"))
        self.assertFalse(ST._name_is_cash("عمولات بنكية"))

    def test_real_banks_are_cash_including_ya_variants(self):
        self.assertTrue(ST._name_is_cash("البنك الاهلى السعودى-407"))
        self.assertTrue(ST._name_is_cash("الراجحى 1039"))
        self.assertTrue(ST._name_is_cash("صندوق النقدية"))
        self.assertTrue(ST._name_is_cash("Al Rajhi Bank"))


class LiveUntypedBooksTest(unittest.TestCase):
    """The screenshot scenario: 0% typed chart, banks in credit, untyped
    counterpart — equation balances, completeness banner carries the warning."""

    def setUp(self):
        self.accounts = [
            _acc("1", "البنك الاهلى السعودى-407", "12001001"),
            _acc("2", "الراجحى 1039", "12001002"),
            _acc("3", "رسوم بنكية", "302002"),
            _acc("4", "مصروفات تشغيل غامضة", "500100"),
        ]
        # one journal: Dr fees 1,998.38 + Dr untyped 543,141.94 / Cr banks 545,140.32
        self.journals = {
            "j1": {"entry_id": "j1", "date": "2026-06-05", "number": 1, "description": "x",
                   "lines": [
                       _line("3", "رسوم بنكية", debit="1998.38"),
                       _line("4", "مصروفات تشغيل غامضة", debit="543141.94"),
                       _line("1", "البنك الاهلى السعودى-407", credit="181957.99"),
                       _line("2", "الراجحى 1039", credit="363182.33"),
                   ]},
        }

    def test_equation_balances_with_untyped_counterpart(self):
        res = ST.build_statements(self.journals, self.accounts,
                                  "2026-06-01", "2026-06-30")
        bs = res["balance_sheet"]
        # banks (cash-inferred assets) net to −545,140.32
        self.assertAlmostEqual(bs["totals"]["assets"], -545140.32, places=2)
        # the untyped bucket holds the +545,140.32 counterpart
        self.assertAlmostEqual(bs["totals"]["untyped_net_debit"], 545140.32, places=2)
        # double-entry holds → gap 0, balanced (completeness is a separate signal)
        self.assertAlmostEqual(bs["totals"]["gap"], 0.0, places=2)
        self.assertTrue(bs["balanced"])

    def test_fees_account_lands_in_untyped_not_assets(self):
        res = ST.build_statements(self.journals, self.accounts,
                                  "2026-06-01", "2026-06-30")
        bs = res["balance_sheet"]
        asset_ids = {r["account_id"] for r in bs["rows"]["asset"]}
        untyped_ids = {r["account_id"] for r in bs["rows"]["untyped"]}
        self.assertNotIn("3", asset_ids)
        self.assertIn("3", untyped_ids)

    def test_coverage_banner_reports_zero_typed(self):
        res = ST.build_statements(self.journals, self.accounts,
                                  "2026-06-01", "2026-06-30")
        self.assertEqual(res["coverage"]["typed_by_daftra"], 0)
        self.assertEqual(res["coverage"]["pct"], 0)


class TypedBooksTest(unittest.TestCase):
    def setUp(self):
        self.accounts = [
            _acc("100", "بنك الراجحي", "1010", {"type": "Asset"}),
            _acc("200", "قرض قصير", "2010", {"category": "Liabilities"}),
            _acc("300", "رأس المال", "3010", {"account_type": "Equity"}),
            _acc("400", "إيراد حجوزات", "4010", {"type": "Income"}),
            _acc("500", "مصاريف تشغيل", "5010", {"type": "Expenses"}),
        ]
        self.journals = {
            "j1": {"entry_id": "j1", "date": "2026-05-02", "number": 1, "description": "رأس مال",
                   "lines": [_line("100", "بنك", debit="10000.00"),
                             _line("300", "رأس المال", credit="10000.00")]},
            "j2": {"entry_id": "j2", "date": "2026-06-05", "number": 2, "description": "إيراد",
                   "lines": [_line("100", "بنك", debit="5000.00"),
                             _line("400", "إيراد", credit="5000.00", cc="CC1", ccn="Ouja | A1")]},
            "j3": {"entry_id": "j3", "date": "2026-06-09", "number": 3, "description": "مصروف",
                   "lines": [_line("500", "مصاريف", debit="2000.00", cc="CC1", ccn="Ouja | A1"),
                             _line("100", "بنك", credit="2000.00")]},
            "j4": {"entry_id": "j4", "date": "2026-06-12", "number": 4, "description": "قرض",
                   "lines": [_line("100", "بنك", debit="1000.00"),
                             _line("200", "قرض", credit="1000.00")]},
        }

    def test_full_statements_balance_tie_and_cash_tie(self):
        res = ST.build_statements(self.journals, self.accounts,
                                  "2026-06-01", "2026-06-30",
                                  "2026-05-01", "2026-05-31",
                                  bank_account_ids={"100"},
                                  bank_register_delta="4000.00")
        bs, inc, eq, cf = (res["balance_sheet"], res["income"],
                           res["equity"], res["cash_flow"])
        self.assertEqual(bs["totals"]["assets"], 14000.0)
        self.assertEqual(bs["totals"]["current_earnings"], 3000.0)
        self.assertTrue(bs["balanced"])
        self.assertEqual(inc["totals"]["net"], 3000.0)
        self.assertEqual(inc["by_cost_center"][0]["net"], 3000.0)
        self.assertEqual(eq["closing"], 13000.0)
        self.assertTrue(eq["ties_to_balance_sheet"])
        self.assertEqual(cf["net_cash"], 4000.0)
        self.assertTrue(cf["ties_internal"])
        self.assertTrue(cf["ties_bank_register"])

    def test_one_sided_entry_shows_honest_gap(self):
        j = dict(self.journals)
        j["bad"] = {"entry_id": "bad", "date": "2026-06-20", "number": 9, "description": "نص قيد",
                    "lines": [_line("100", "بنك", debit="500.00")]}
        res = ST.build_statements(j, self.accounts, "2026-06-01", "2026-06-30")
        self.assertFalse(res["balance_sheet"]["balanced"])
        self.assertEqual(res["balance_sheet"]["totals"]["gap"], 500.0)


class BudgetMathTest(unittest.TestCase):
    def test_acceptance_f_numbers(self):
        row = ST.budget_row(10000, 9200)
        self.assertEqual(row, {"budget": 10000.0, "actual": 9200.0,
                               "remaining": 800.0, "pct": 92, "alert": "warn"})
        self.assertEqual(ST.budget_row(1000, 1001)["alert"], "over")
        self.assertIsNone(ST.budget_row(1000, 100)["alert"])

    def test_weekly_split_sums_exactly(self):
        parts = ST.split_weekly("1000.00", weeks=3)
        self.assertEqual(sum(parts), 1000.0)
        self.assertTrue(ST.weekly_sums_ok(parts, 1000))
        self.assertFalse(ST.weekly_sums_ok([300, 300], 1000))


if __name__ == "__main__":
    unittest.main()
