# -*- coding: utf-8 -*-
"""Editing a manual statement expense — including MOVING it to another month.

Owner request 2026-08-05: manual («تسوية يدوية») expense rows only offered «حذف».
The accountant needs «تعديل» — above all to change the date so a line booked in
July lands in August instead: out of July's reports, into August's, counted once.

The month is not a label on the row — it is the STORE the row lives in
(`bot._finance_adjust[key(lid, month_start, month_end)]` for a per-apartment line,
`owner_statements[owner|month].edits.exp_manual` for an owner-level one). Since
2.7.1 a manual line always counts in the month it is stored in, whatever its date
says, so a date change must physically RELOCATE the row or the statement would
show a July date while July's total still carried it.

Run: python3 tests/test_stmt_manual_exp_edit.py
"""
import os
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_STATE = "/tmp/ouja-test-state-manualexpedit"
shutil.rmtree(_STATE, ignore_errors=True)
os.makedirs(_STATE, exist_ok=True)
os.environ["STATE_DIR"] = _STATE

import bot  # noqa: E402
from finance import api as fapi, owners as OW  # noqa: E402

fapi.attach(bot)

JUL, AUG = "2026-07", "2026-08"
OWNER = "حاصل الاسمري"
LID = 4101


class _Req:
    query = {}
    headers = {}
    remote = "test"


class ManualExpenseEditTest(unittest.TestCase):
    def setUp(self):
        OW._terms_cache["v"] = None
        OW._stmt_cache["v"] = None
        bot._save_json("owner_terms.json", {"owners": {}, "units": {}, "versions": []})
        bot._save_json("owner_statements.json", {})
        bot._owner_registry.clear()
        bot._owner_registry[bot._owner_key("4101")] = {
            "apartment": "4101", "owner": OWNER, "mgmt_pct": 22.0, "lid": LID,
            "cleaning": {"type": "ours", "amount": 0}}
        self._patched = (bot.fetch_reservations_window, bot.fetch_reservations_window_checked,
                         bot.get_listings_map)
        bot.fetch_reservations_window = lambda s, e, pad_days=45: []
        bot.fetch_reservations_window_checked = lambda s, e: ([], False)
        bot.get_listings_map = lambda: {LID: "4101"}
        bot._expenses.clear()
        bot._owner_portal_cache.clear()
        bot._finance_adjust.clear()

    def tearDown(self):
        (bot.fetch_reservations_window, bot.fetch_reservations_window_checked,
         bot.get_listings_map) = self._patched

    # ---- helpers ----
    def _add(self, m=JUL, amount=300, date="2026-07-07", desc="نقل اثاث", lid=LID):
        body = {"owner": OWNER, "m": m, "op": "exp_manual_add", "amount": amount,
                "date": date, "description": desc, "reason": desc}
        if lid is not None:
            body["lid"] = str(lid)
        return OW.statement_edit(_Req(), body)

    def _edit(self, eid, m=JUL, lid=LID, **fields):
        body = {"owner": OWNER, "m": m, "op": "exp_manual_edit", "id": eid,
                "reason": fields.pop("reason", "تصحيح")}
        if lid is not None:
            body["lid"] = str(lid)
        body.update(fields)
        return OW.statement_edit(_Req(), body)

    def _exp(self, m):
        s = OW.compute_owner_statement(OWNER, m) or {}
        return [(x.get("description"), x.get("amount"), x.get("date"))
                for x in (s.get("exp_lines") or [])]

    def _total(self, m):
        return (OW.compute_owner_statement(OWNER, m) or {}).get("expenses")

    # ---- editing in place ----
    def test_edit_amount_and_description_in_place(self):
        self._add()
        r = self._edit("exp-adj-0", amount=450, description="نقل اثاث + عمالة")
        self.assertEqual(r[1], 200)
        self.assertEqual(self._exp(JUL), [("نقل اثاث + عمالة", 450.0, "2026-07-07")])
        self.assertEqual(self._total(JUL), 450.0)

    def test_edit_date_inside_the_same_month_does_not_move_it(self):
        self._add()
        self._edit("exp-adj-0", date="2026-07-22")
        self.assertEqual(self._exp(JUL), [("نقل اثاث", 300.0, "2026-07-22")])
        self.assertEqual(self._total(AUG), 0.0)

    # ---- the point of the request: move it to another month ----
    def test_changing_the_date_moves_it_to_the_new_month(self):
        self._add()
        self.assertEqual(self._total(JUL), 300.0)
        r = self._edit("exp-adj-0", date="2026-08-03")
        self.assertEqual(r[0].get("moved_to"), AUG)
        self.assertEqual(self._exp(JUL), [], "the line is still on July's report")
        self.assertEqual(self._total(JUL), 0.0)
        self.assertEqual(self._exp(AUG), [("نقل اثاث", 300.0, "2026-08-03")])
        self.assertEqual(self._total(AUG), 300.0)

    def test_moved_line_lands_on_the_same_apartment(self):
        self._add()
        self._edit("exp-adj-0", date="2026-08-03")
        aug = OW.compute_owner_statement(OWNER, AUG)
        self.assertEqual([(p["apartment"], p["expenses"]) for p in aug["apartments"]],
                         [("4101", 300.0)])

    def test_move_carries_an_amount_edit_with_it(self):
        self._add()
        self._edit("exp-adj-0", date="2026-08-03", amount=999)
        self.assertEqual(self._total(JUL), 0.0)
        self.assertEqual(self._total(AUG), 999.0)

    def test_moving_back_returns_it(self):
        self._add()
        self._edit("exp-adj-0", date="2026-08-03")
        self._edit("exp-adj-0", m=AUG, date="2026-07-09")
        self.assertEqual(self._total(AUG), 0.0)
        self.assertEqual(self._exp(JUL), [("نقل اثاث", 300.0, "2026-07-09")])

    def test_only_the_edited_line_moves(self):
        self._add(amount=300, date="2026-07-07", desc="نقل اثاث")
        self._add(amount=150, date="2026-07-09", desc="تركيب شاشه")
        self._edit("exp-adj-0", date="2026-08-03")
        self.assertEqual(self._exp(JUL), [("تركيب شاشه", 150.0, "2026-07-09")])
        self.assertEqual(self._exp(AUG), [("نقل اثاث", 300.0, "2026-08-03")])

    # ---- owner-level rows (no apartment picked) move too ----
    def test_owner_level_row_moves(self):
        self._add(lid=None, amount=200, date="2026-07-05", desc="بدون شقة")
        rec = OW.stmt_rec(OWNER, JUL) or {}
        rid = ((rec.get("edits") or {}).get("exp_manual") or [])[0]["id"]
        r = self._edit(rid, lid=None, date="2026-08-08")
        self.assertEqual(r[0].get("moved_to"), AUG)
        self.assertEqual(self._total(JUL), 0.0)
        self.assertEqual(self._total(AUG), 200.0)

    # ---- guards ----
    def test_reason_is_required(self):
        self._add()
        r = OW.statement_edit(_Req(), {"owner": OWNER, "m": JUL, "op": "exp_manual_edit",
                                       "id": "exp-adj-0", "lid": str(LID), "amount": 10})
        self.assertEqual(r[1], 400)
        self.assertEqual(self._total(JUL), 300.0)

    def test_an_income_line_is_never_edited_as_an_expense(self):
        OW.statement_edit(_Req(), {"owner": OWNER, "m": JUL, "op": "inc_manual_add",
                                   "amount": 500, "lid": str(LID), "label": "إيراد",
                                   "reason": "إيراد"})
        r = self._edit("exp-adj-0", amount=1)
        self.assertEqual(r[1], 404)

    def test_unknown_row_is_refused(self):
        r = self._edit("exp-adj-9", amount=1)
        self.assertEqual(r[1], 404)

    def test_both_months_record_the_move_in_their_audit(self):
        self._add()
        self._edit("exp-adj-0", date="2026-08-03", reason="الفاتورة تخص أغسطس")
        for m in (JUL, AUG):
            audit = (OW.stmt_rec(OWNER, m) or {}).get("audit") or []
            self.assertTrue(any(a.get("action") == "exp_manual_edit" for a in audit),
                            "%s has no record of the move" % m)


if __name__ == "__main__":
    unittest.main(verbosity=2)
