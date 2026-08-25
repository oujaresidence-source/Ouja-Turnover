# -*- coding: utf-8 -*-
"""Slice 2 regression — statement editor + explainability + publish/versioning.

Pins acceptance D: exclude-with-reason recomputes totals live + lands in the
audit trail; publishing freezes a snapshot the owner link serves (version
bumped); أعد الحساب shows the published-vs-fresh diff before republishing.

Run: python3 tests/test_statement_editor_v21.py
"""
import os
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_STATE = "/tmp/ouja-test-state-s2"
shutil.rmtree(_STATE, ignore_errors=True)
os.makedirs(_STATE, exist_ok=True)
os.environ["STATE_DIR"] = _STATE

import bot  # noqa: E402
from finance import api as fapi, owners as OW  # noqa: E402

fapi.attach(bot)

JUNE = "2026-06"


class _Req:
    """Minimal request stand-in for actor()."""
    headers = {}
    query = {}


def _actor(_req):
    return "tester"


def _resv(rid, payout, checkin):
    return {"id": rid, "listingMapId": 21, "status": "new", "channelName": "Airbnb",
            "arrivalDate": checkin, "departureDate": checkin[:8] + "28", "nights": 3,
            "guestName": "G" + rid, "airbnbExpectedPayoutAmount": payout,
            "totalPrice": (payout or 1800) + 300, "refundAmount": None}


ROWS = [
    _resv("s1", 1000.0, "2026-06-03"),
    _resv("s2", 2000.0, "2026-06-10"),
    _resv("s3", None, "2026-06-20"),       # missing payout → excluded w/ reference
]


class StatementEditorTest(unittest.TestCase):
    def setUp(self):
        OW._terms_cache["v"] = None
        OW._stmt_cache["v"] = None
        bot._save_json("owner_terms.json", {"owners": {}, "units": {}, "versions": []})
        bot._save_json("owner_statements.json", {})
        bot._owner_registry.clear()
        bot._owner_registry[bot._owner_key("E1")] = {
            "apartment": "E1", "owner": "مالك المحرر", "mgmt_pct": 20.0, "lid": 21,
            "cleaning": {"type": "ours", "amount": 0}}
        self._patches = (bot.fetch_reservations_window, bot.get_listings_map)
        bot.fetch_reservations_window = lambda s, e, pad_days=45: ROWS
        bot.get_listings_map = lambda: {21: "Ouja | E1"}
        bot._expenses.clear()
        bot._owner_portal_cache.clear()
        self._actor_orig = fapi.actor
        fapi.actor = _actor

    def tearDown(self):
        bot.fetch_reservations_window, bot.get_listings_map = self._patches
        fapi.actor = self._actor_orig
        OW._terms_cache["v"] = None
        OW._stmt_cache["v"] = None

    def test_exclude_recomputes_and_audits(self):
        base = OW.compute_owner_statement("مالك المحرر", JUNE)
        self.assertEqual(base["total_income"], 3000.0)
        data, code = OW.statement_edit(_Req(), {
            "owner": "مالك المحرر", "m": JUNE, "op": "resv_exclude",
            "id": "s2", "reason": "حجز تجريبي مو حقيقي"})
        self.assertEqual(code, 200)
        s = data["statement"]
        self.assertEqual(s["total_income"], 1000.0)
        self.assertEqual(s["ouja_fee"], 200.0)
        self.assertEqual(s["owner_net"], 800.0)
        self.assertEqual(len(s["manual_excluded_lines"]), 1)
        self.assertEqual(s["manual_excluded_lines"][0]["reference_total"], 2000.0)
        audit = data["audit"]
        self.assertEqual(audit[0]["action"], "resv_exclude")
        self.assertEqual(audit[0]["reason"], "حجز تجريبي مو حقيقي")

    def test_reason_is_mandatory(self):
        data, code = OW.statement_edit(_Req(), {
            "owner": "مالك المحرر", "m": JUNE, "op": "resv_exclude", "id": "s2", "reason": ""})
        self.assertEqual(code, 400)
        self.assertEqual(data["error"], "reason_required")

    def test_include_missing_payout_requires_amount_and_counts(self):
        data, _ = OW.statement_edit(_Req(), {
            "owner": "مالك المحرر", "m": JUNE, "op": "resv_include",
            "id": "s3", "amount": 1500.0, "reason": "وصلنا المبلغ يدويًا من Airbnb"})
        s = data["statement"]
        self.assertEqual(s["total_income"], 4500.0)
        self.assertEqual(s["ouja_fee"], 900.0)            # 20% of all three
        inc = [l for l in s["resv_lines"] if l.get("manual_included")]
        self.assertEqual(len(inc), 1)
        self.assertEqual(inc[0]["income"], 1500.0)
        self.assertEqual(s["excluded_summary"]["needs_review"], 1)  # legacy count before edits…
        # …but the live lines list now has no needs_review row
        self.assertFalse([l for l in s["resv_lines"] if l.get("needs_review")])

    def test_adjustment_and_manual_expense(self):
        OW.statement_edit(_Req(), {"owner": "مالك المحرر", "m": JUNE, "op": "adj_add",
                                   "amount": -250.0, "label": "خصم اتفاق", "reason": "اتفاق هاتفي"})
        data, _ = OW.statement_edit(_Req(), {"owner": "مالك المحرر", "m": JUNE, "op": "exp_manual_add",
                                             "amount": 100.0, "date": "2026-06-15",
                                             "description": "غيار قفل", "reason": "فاتورة ورقية"})
        s = data["statement"]
        # 3000 − 600 fee − 100 exp − 0 cleaning − 250 adj = 2050
        self.assertEqual(s["owner_net"], 2050.0)
        self.assertEqual(s["adjustments_total"], -250.0)
        self.assertEqual(s["expenses"], 100.0)

    def test_publish_freezes_snapshot_and_versions(self):
        bot._owner_statement_hook = OW.statement_for_portal
        try:
            r1, _ = OW.statement_publish(_Req(), {"owner": "مالك المحرر", "m": JUNE})
            self.assertEqual(r1["version"], 1)
            bot._owner_portal_cache.clear()
            served = bot._owner_month_report("مالك المحرر", JUNE)
            self.assertEqual(served["statement_version"], 1)
            self.assertEqual(served["owner_net"], 2400.0)        # 3000 × 0.8
            # edit AFTER publish → live link still serves v1 until republish
            OW.statement_edit(_Req(), {"owner": "مالك المحرر", "m": JUNE, "op": "resv_exclude",
                                       "id": "s2", "reason": "اختبار"})
            bot._owner_portal_cache.clear()
            served2 = bot._owner_month_report("مالك المحرر", JUNE)
            self.assertEqual(served2["owner_net"], 2400.0)       # snapshot stable
            diff = OW.statement_recompute_diff("مالك المحرر", JUNE)
            self.assertTrue(diff["changed"])
            self.assertEqual(diff["delta"]["owner_net"], -1600.0)
            r2, _ = OW.statement_publish(_Req(), {"owner": "مالك المحرر", "m": JUNE})
            self.assertEqual(r2["version"], 2)
            bot._owner_portal_cache.clear()
            served3 = bot._owner_month_report("مالك المحرر", JUNE)
            self.assertEqual(served3["owner_net"], 800.0)
            self.assertEqual(served3["statement_version"], 2)
        finally:
            del bot._owner_statement_hook
            bot._owner_portal_cache.clear()


if __name__ == "__main__":
    unittest.main(verbosity=2)
