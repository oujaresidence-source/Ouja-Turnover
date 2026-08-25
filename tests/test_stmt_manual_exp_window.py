# -*- coding: utf-8 -*-
"""Manual statement expenses must never be silently thrown away.

Owner-reported 2026-08-02 (accountant screenshot, نورة الحساوي / 2026-07):
expenses typed by hand into the statement editor for one apartment showed up in
the editor as GHOST BOOKING rows — no guest, no dates, a red «وحدة خارج فترة
العقد» tag — and were missing from the printed statement, so the owner's net was
overstated by their total.

Three defects, all locked here:

1. `unit_statement` window-filtered EVERY expense line, including the manual ones
   the accountant deliberately attached to this month. An invoice dated outside
   the month (or a unit whose contract window doesn't cover it) was dropped and
   labelled «outside_contract» — a reason that has nothing to do with a hand
   entry. A manual line is an explicit human decision: it always counts.
2. The aggregate merged excluded EXPENSES into `contract_excluded_lines` — the
   RESERVATIONS bucket — so the editor rendered them with the reservation row
   renderer (hence the ghost rows) and offered an «احسبه» button.
3. That button posted `resv_include` with an expense id. The server wrote it into
   `edits.resv`, matched no reservation, recomputed the same numbers and reported
   success: a silent no-op, the worst kind (CLAUDE.md, Finance ERP trap #2).

Run: python3 tests/test_stmt_manual_exp_window.py
"""
import os
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_STATE = "/tmp/ouja-test-state-manualexpwin"
shutil.rmtree(_STATE, ignore_errors=True)
os.makedirs(_STATE, exist_ok=True)
os.environ["STATE_DIR"] = _STATE

import bot  # noqa: E402
from finance import api as fapi, owners as OW  # noqa: E402

fapi.attach(bot)

MONTH = "2026-07"
OWNER = "مالكة اختبار"
LID = 771


class _Req:
    query = {}
    headers = {}
    remote = "test"


class ManualExpenseWindowTest(unittest.TestCase):
    def setUp(self):
        OW._terms_cache["v"] = None
        OW._stmt_cache["v"] = None
        # the unit carries effective-dated terms → unit_statement re-derives
        # (the legacy pass-through is what hid this bug from the older tests)
        bot._save_json("owner_terms.json", {
            "owners": {},
            "units": {bot._owner_key("11B"): {"terms": [{"from": "2026-01-01", "mgmt_pct": 20.0}]}},
            "versions": []})
        bot._save_json("owner_statements.json", {})
        bot._owner_registry.clear()
        bot._owner_registry[bot._owner_key("11B")] = {
            "apartment": "11B", "owner": OWNER, "mgmt_pct": 20.0, "lid": LID,
            "cleaning": {"type": "ours", "amount": 0}}
        self._patched = (bot.fetch_reservations_window, bot.fetch_reservations_window_checked,
                         bot.get_listings_map)
        bot.fetch_reservations_window = lambda s, e, pad_days=45: []
        bot.fetch_reservations_window_checked = lambda s, e: ([], False)
        bot.get_listings_map = lambda: {LID: "Ouja | 11B Royal"}
        bot._expenses.clear()
        bot._owner_portal_cache.clear()
        bot._finance_adjust.clear()

    def tearDown(self):
        (bot.fetch_reservations_window, bot.fetch_reservations_window_checked,
         bot.get_listings_map) = self._patched

    # ---- helpers ----
    def _add(self, amount, date_str, desc, lid=LID):
        body = {"owner": OWNER, "m": MONTH, "op": "exp_manual_add", "amount": amount,
                "date": date_str, "description": desc, "reason": desc}
        if lid is not None:
            body["lid"] = str(lid)
        return OW.statement_edit(_Req(), body)

    def _stmt(self):
        return OW.compute_owner_statement(OWNER, MONTH)

    # ---- 1. the reported bug: an out-of-month invoice date must not delete money ----
    def test_manual_expense_dated_outside_the_month_still_counts(self):
        self._add(500, "2026-07-10", "داخل الشهر")
        self._add(500, "2026-08-01", "فاتورة مؤرخة بعد الشهر")
        agg = self._stmt()
        self.assertEqual(agg["expenses"], 1000.0,
                         "a hand-entered expense was dropped for its date")
        self.assertEqual(agg["owner_net"], -1000.0)
        ids = [x.get("id") for x in agg.get("exp_lines") or []]
        self.assertEqual(len(ids), 2, "both manual lines must print: %r" % (ids,))

    def test_manual_expense_never_lands_in_the_excluded_bucket(self):
        self._add(500, "2026-08-01", "فاتورة مؤرخة بعد الشهر")
        agg = self._stmt()
        for key in ("contract_excluded_lines", "contract_excluded_expenses"):
            for x in agg.get(key) or []:
                self.assertNotEqual(x.get("kind"), "expense",
                                    "manual expense excluded in %s" % key)

    # ---- 2. an excluded expense is never a ghost BOOKING row ----
    def test_excluded_expenses_stay_out_of_the_reservations_bucket(self):
        # a real (ledger) expense before the contract starts → legitimately excluded
        OW._terms_cache["v"] = None
        bot._save_json("owner_terms.json", {
            "owners": {},
            "units": {bot._owner_key("11B"): {"contract_from": "2026-07-15",
                                              "terms": [{"from": "2026-01-01", "mgmt_pct": 20.0}]}},
            "versions": []})
        bot._expenses["e1"] = {"id": "e1", "apartment": "11B", "listing_id": LID,
                               "amount": 300, "expense_date": "2026-07-05",
                               "hostaway_verified": True, "category": "صيانة", "note": "قبل العقد"}
        agg = self._stmt()
        for l in agg.get("contract_excluded_lines") or []:
            self.assertIsNone(l.get("kind") == "expense" or None,
                              "an expense is rendered as an excluded BOOKING row")
            self.assertNotEqual(l.get("kind"), "expense")
        self.assertTrue(any(x.get("id") == "e1" for x in agg.get("contract_excluded_expenses") or []),
                        "the excluded expense must still be visible, in its own bucket")

    # ---- 3. no silent no-op: include/exclude only accept reservation ids ----
    def test_resv_include_refuses_an_expense_id(self):
        self._add(500, "2026-08-01", "فاتورة")
        res = OW.statement_edit(_Req(), {"owner": OWNER, "m": MONTH, "op": "resv_include",
                                         "id": "exp-adj-0", "reason": "احسبها"})
        self.assertIsInstance(res, tuple, "an expense id must be refused, not silently saved")
        self.assertEqual(res[1], 400)
        rec = OW.stmt_rec(OWNER, MONTH) or {}
        self.assertEqual((rec.get("edits") or {}).get("resv") or {}, {},
                         "a refused edit must leave no garbage behind")

    def test_resv_exclude_refuses_an_expense_id(self):
        res = OW.statement_edit(_Req(), {"owner": OWNER, "m": MONTH, "op": "resv_exclude",
                                         "id": "man-abc12345", "reason": "لا"})
        self.assertIsInstance(res, tuple)
        self.assertEqual(res[1], 400)

    # ---- 4. an empty date never becomes the description ----
    def test_empty_date_falls_back_to_the_statement_month(self):
        self._add(500, "", "بدون تاريخ")
        agg = self._stmt()
        line = (agg.get("exp_lines") or [])[0]
        self.assertEqual(line.get("date"), "2026-07-31",
                         "an empty date must become a real date inside the month, not text")
        self.assertEqual(agg["expenses"], 500.0)

    def test_owner_level_manual_expense_also_gets_a_real_date(self):
        self._add(400, "", "بدون تاريخ — على مستوى المالك", lid=None)
        rec = OW.stmt_rec(OWNER, MONTH) or {}
        rows = (rec.get("edits") or {}).get("exp_manual") or []
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["date"], "2026-07-31")

    # ---- 5. still exactly once in the owner total (the v2.5.0 guarantee) ----
    def test_counted_exactly_once_in_the_owner_total(self):
        self._add(250, "2026-08-01", "مرة وحدة بس")
        agg = self._stmt()
        self.assertEqual(agg["expenses"], 250.0)
        self.assertEqual(sum(1 for x in agg.get("exp_lines") or []
                             if (x.get("edit_reason") or "") == "مرة وحدة بس"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
