# -*- coding: utf-8 -*-
"""Manual income: the accountant decides whether it carries the management fee,
and the printed % is the contract rate — not fee ÷ ALL income.

Owner-reported 2026-10-04 (moustafa, Discord), two bugs on the same screen:

1. «رسوم عوجا (21.1%)» on a 22% unit (4101, also 4010 / hue 9 / 4511). The money
   was right (9,539.61 × 22% = 2,098.71); the LABEL divided the fee by total
   income INCLUDING a fee-exempt manual line (408): 2,098.71 ÷ 9,947.61 = 21.1%.
2. الغدير B03 printed «رسوم الإدارة 0» — the whole month (a 25,850 monthly
   tenant) was entered as manual income, and manual income was fee-exempt BY
   DESIGN with no way to say otherwise.

Owner ruling (2026-10-05): every new manual income line must carry an explicit
choice — «عليه رسوم الإدارة» or «بدون رسوم» — with NO default. Lines entered
before this change stay fee-exempt until someone flips them (inc_manual_fee).

Run: python3 -m unittest tests.test_manual_income_fee -v
"""
import os
import shutil
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_STATE = "/tmp/ouja-test-state-manualfee"
shutil.rmtree(_STATE, ignore_errors=True)
os.makedirs(_STATE, exist_ok=True)
os.environ["STATE_DIR"] = _STATE

import bot  # noqa: E402
from finance import api as fapi, owners as OW  # noqa: E402

fapi.attach(bot)

SEP = "2026-09"
B03_OWNER, B03_LID = "عبدالله الحربي", 41
H_OWNER, H_LID = "حاصل الاسمري", 42           # 4101: one booking + a 408 manual line
MIX_OWNER = "مالك بنسبتين"                    # two units, 20% and 25%


def _resv(rid, lid, checkin, checkout, price):
    return {"id": rid, "listingMapId": lid, "arrivalDate": checkin,
            "departureDate": checkout, "nights": 1, "totalPrice": price,
            "guestName": "ضيف " + str(rid), "status": "new",
            "channelName": "airbnb", "airbnbExpectedPayoutAmount": price,
            "alreadyPaid": price, "paymentStatus": "paid"}


class _Req:
    query = {}
    headers = {}
    remote = "test"


class ManualIncomeFeeTest(unittest.TestCase):
    def setUp(self):
        OW._terms_cache["v"] = None
        OW._stmt_cache["v"] = None
        bot._save_json("owner_terms.json", {"owners": {}, "units": {}, "versions": []})
        bot._save_json("owner_statements.json", {})
        bot._owner_registry.clear()
        for apt, owner, lid, pct in (("B03", B03_OWNER, B03_LID, 22.0),
                                     ("4101", H_OWNER, H_LID, 22.0),
                                     ("M-20", MIX_OWNER, 51, 20.0),
                                     ("M-25", MIX_OWNER, 52, 25.0)):
            bot._owner_registry[bot._owner_key(apt)] = {
                "apartment": apt, "owner": owner, "mgmt_pct": pct, "lid": lid,
                "cleaning": {"type": "ours", "amount": 0}}
        rows = [_resv(9001, H_LID, "2026-09-03", "2026-09-04", 9539.61),
                _resv(9101, 51, "2026-09-05", "2026-09-06", 1000.0),
                _resv(9102, 52, "2026-09-07", "2026-09-08", 1000.0)]
        self._patched = (bot.fetch_reservations_window, bot.fetch_reservations_window_checked,
                         bot.get_listings_map)
        bot.fetch_reservations_window = lambda s, e, pad_days=45: list(rows)
        bot.fetch_reservations_window_checked = lambda s, e: (list(rows), False)
        bot.get_listings_map = lambda: {B03_LID: "B03", H_LID: "4101", 51: "M-20", 52: "M-25"}
        bot._expenses.clear()
        bot._owner_portal_cache.clear()
        bot._finance_adjust.clear()

    def tearDown(self):
        (bot.fetch_reservations_window, bot.fetch_reservations_window_checked,
         bot.get_listings_map) = self._patched
        bot._finance_adjust.clear()
        OW._terms_cache["v"] = None
        OW._stmt_cache["v"] = None

    # ---- helpers ----
    def _add(self, owner, lid, amount, fee, label="إيراد"):
        body = {"owner": owner, "m": SEP, "op": "inc_manual_add", "lid": lid,
                "amount": amount, "label": label, "reason": "اختبار"}
        if fee is not None:
            body["fee"] = fee
        return OW.statement_edit(_Req(), body)

    def _legacy_line(self, lid, amount):
        """A line entered BEFORE this change: no `fee` key at all."""
        k = bot._finance_adjust_key(lid, "2026-09-01", "2026-09-30")
        bot._finance_adjust[k] = {"expense_overrides": {}, "line_overrides": {}, "comment": "",
                                  "extra_lines": [{"kind": "income", "label": "قديم", "amount": amount}]}

    def _part(self, agg, lid):
        return next(p for p in agg["apartments"] if str(p.get("lid")) == str(lid))

    # ================= 1) the printed % =================
    def test_4101_label_is_the_contract_rate_not_21_1(self):
        self._add(H_OWNER, H_LID, 408.0, False)
        s = OW.compute_owner_statement(H_OWNER, SEP)
        self.assertEqual(s["ouja_fee"], 2098.71)                 # the money never changed
        self.assertEqual(s["total_income"], 9947.61)
        self.assertEqual(s["management_pct"], 22.0, "fee ÷ ALL income printed 21.1%")

    def test_4101_range_report_label(self):
        self._add(H_OWNER, H_LID, 408.0, False)
        rep, err = OW.compute_owner_range(H_OWNER, date(2026, 9, 1), date(2026, 9, 30), apt="4101")
        self.assertIsNone(err)
        self.assertEqual(rep["ouja_fee"], 2098.71)
        self.assertEqual(rep["management_pct"], 22.0)

    def test_all_income_exempt_still_prints_the_contract_rate(self):
        self._legacy_line(B03_LID, 25850.0)
        s = OW.compute_owner_statement(B03_OWNER, SEP)
        self.assertEqual(s["ouja_fee"], 0.0)
        self.assertEqual(s["management_pct"], 22.0, "a 22% unit must never print «0.0%»")

    def test_mixed_rates_blend_over_fee_bearing_income_only(self):
        self._add(MIX_OWNER, 51, 5000.0, False)                 # exempt: must not dilute
        s = OW.compute_owner_statement(MIX_OWNER, SEP)
        self.assertEqual(s["ouja_fee"], 450.0)                   # 200 + 250
        self.assertEqual(s["management_pct"], 22.5)              # 450 ÷ 2000, not ÷ 7000

    # ================= 2) the explicit choice =================
    def test_add_without_a_choice_is_refused(self):
        data, code = self._add(B03_OWNER, B03_LID, 25850.0, None)
        self.assertEqual(code, 400)
        self.assertEqual(data["error"], "fee_choice_required")
        s = OW.compute_owner_statement(B03_OWNER, SEP)
        self.assertEqual(s["manual_income"], 0.0, "a refused add must store nothing")

    def test_b03_fee_bearing_line_charges_22_percent_everywhere(self):
        data, code = self._add(B03_OWNER, B03_LID, 25850.0, True, "مستأجر شهري")
        self.assertEqual(code, 200, data)
        s = OW.compute_owner_statement(B03_OWNER, SEP)
        self.assertEqual(s["ouja_fee"], 5687.0)                  # 22% × 25,850
        self.assertEqual(s["owner_net"], 20163.0)
        self.assertEqual(s["management_pct"], 22.0)
        self.assertEqual(self._part(s, B03_LID)["ouja_fee"], 5687.0)
        line = s["manual_income_lines"][0]
        self.assertTrue(line["fee_applies"])
        self.assertEqual(line["mgmt_pct_applied"], 22.0)
        # the unit engine (bulk PDFs, apartment print) agrees
        rep = bot.build_owner_report(B03_LID, date(2026, 9, 1), date(2026, 9, 30), 0, {})
        self.assertEqual(rep["ouja_fee"], 5687.0)
        # …and the custom-range report the accountant actually printed
        rng, err = OW.compute_owner_range(B03_OWNER, date(2026, 8, 1), date(2026, 9, 30))
        self.assertIsNone(err)
        self.assertEqual(rng["ouja_fee"], 5687.0)
        self.assertEqual(rng["management_pct"], 22.0)

    def test_exempt_choice_keeps_the_old_behavior(self):
        self._add(H_OWNER, H_LID, 408.0, False)
        s = OW.compute_owner_statement(H_OWNER, SEP)
        self.assertFalse(s["manual_income_lines"][0]["fee_applies"])
        self.assertEqual(s["owner_net"], round(9947.61 - 2098.71, 2))

    def test_legacy_line_without_a_flag_stays_exempt(self):
        self._legacy_line(B03_LID, 25850.0)
        s = OW.compute_owner_statement(B03_OWNER, SEP)
        self.assertEqual(s["ouja_fee"], 0.0)
        self.assertFalse(s["manual_income_lines"][0]["fee_applies"])

    # ================= 3) flipping an existing line =================
    def _flip(self, fee, reason="تصحيح"):
        return OW.statement_edit(_Req(), {"owner": B03_OWNER, "m": SEP, "op": "inc_manual_fee",
                                          "lid": B03_LID, "id": "inc-0", "fee": fee,
                                          "reason": reason})

    def test_flip_legacy_line_to_fee_bearing_and_back(self):
        self._legacy_line(B03_LID, 25850.0)
        data, code = self._flip(True)
        self.assertEqual(code, 200, data)
        self.assertEqual(data["statement"]["ouja_fee"], 5687.0)
        rep = bot.build_owner_report(B03_LID, date(2026, 9, 1), date(2026, 9, 30), 0, {})
        self.assertEqual(rep["ouja_fee"], 5687.0)
        data, code = self._flip(False)
        self.assertEqual(code, 200, data)
        self.assertEqual(data["statement"]["ouja_fee"], 0.0)

    def test_flip_needs_a_reason_and_a_real_line(self):
        self._legacy_line(B03_LID, 25850.0)
        self.assertEqual(self._flip(True, reason="")[1], 400)
        data, code = OW.statement_edit(_Req(), {"owner": B03_OWNER, "m": SEP, "op": "inc_manual_fee",
                                                "lid": B03_LID, "id": "inc-7", "fee": True,
                                                "reason": "x"})
        self.assertEqual(code, 404)
        data, code = OW.statement_edit(_Req(), {"owner": B03_OWNER, "m": SEP, "op": "inc_manual_fee",
                                                "lid": B03_LID, "id": "inc-0", "reason": "x"})
        self.assertEqual(code, 400)                              # no explicit fee value

    def test_flip_is_audited(self):
        self._legacy_line(B03_LID, 25850.0)
        self._flip(True)
        rec = OW.stmt_rec(B03_OWNER, SEP)
        last = rec["audit"][-1]
        self.assertEqual(last["action"], "inc_manual_fee")
        self.assertEqual((last.get("after") or {}).get("fee"), True)

    # ================= 4) the edit + re-derive paths keep the fee =================
    def test_fee_survives_other_editor_decisions(self):
        # any booking edit switches on force_rederive + _apply_stmt_edits —
        # both re-derive the fee from lines and used to see bookings only
        self._add(MIX_OWNER, 51, 1000.0, True)
        OW.statement_edit(_Req(), {"owner": MIX_OWNER, "m": SEP, "op": "resv_exclude",
                                   "id": "9102", "reason": "مو حق المالك"})
        s = OW.compute_owner_statement(MIX_OWNER, SEP)
        self.assertEqual(s["ouja_fee"], 400.0)                   # 20% × (1000 booking + 1000 manual)
        self.assertEqual(self._part(s, 51)["ouja_fee"], 400.0)
        self.assertEqual(self._part(s, 52)["ouja_fee"], 0.0)
        self.assertEqual(s["management_pct"], 20.0)

    def test_health_and_explain_agree(self):
        self._add(B03_OWNER, B03_LID, 25850.0, True)
        h = OW.statement_health(B03_OWNER, SEP)
        self.assertTrue(h["ok"], h["problems"])
        s = OW.compute_owner_statement(B03_OWNER, SEP)
        ex = OW._build_explain(s)
        self.assertEqual(round(sum(g["fee"] for g in ex["fees"]["groups"]), 2), s["ouja_fee"])

    def test_units_sum_to_owner_total(self):
        self._add(MIX_OWNER, 52, 400.0, True)
        s = OW.compute_owner_statement(MIX_OWNER, SEP)
        self.assertEqual(s["ouja_fee"], 550.0)                   # 200 + 250 + 25% × 400
        self.assertEqual(round(sum(p["ouja_fee"] for p in s["apartments"]), 2), s["ouja_fee"])
        self.assertEqual(round(sum(p["owner_net"] for p in s["apartments"]), 2), s["owner_net"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
