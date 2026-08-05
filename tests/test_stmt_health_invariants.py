# -*- coding: utf-8 -*-
"""A statement must never contradict itself — and we must be able to prove it
for EVERY owner, not just the one that got reported.

Owner-reported 2026-08-04 (ثامر ال جربوع / 2026-07): a cancelled booking was
force-included, the total moved, but «تفصيل الدخل» on the very same PDF page kept
the old figure — total 8,860.88 vs airbnb+direct 8,424.54, a gap of exactly the
included 436.34. `_apply_stmt_edits` recomputed the totals and left the channel
split behind.

That was the fourth «الرقم على الشاشة مو نفسه في التقرير» in three days, each one
a different surface reading a value the editor's decisions never reached. So the
invariants live here now, and `audit_all` sweeps the whole book on demand.

Run: python3 tests/test_stmt_health_invariants.py
"""
import os
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_STATE = "/tmp/ouja-test-state-stmthealth"
shutil.rmtree(_STATE, ignore_errors=True)
os.makedirs(_STATE, exist_ok=True)
os.environ["STATE_DIR"] = _STATE

import bot  # noqa: E402
from finance import api as fapi, owners as OW  # noqa: E402

fapi.attach(bot)

MONTH = "2026-07"
OWNER = "ثامر"
LID = 4511


def _resv(rid, checkin, price, status="new", channel="airbnb"):
    r = {"id": rid, "listingMapId": LID, "arrivalDate": checkin, "departureDate": checkin,
         "nights": 1, "totalPrice": price, "guestName": "ضيف " + str(rid),
         "status": status, "channelName": channel, "alreadyPaid": price,
         "paymentStatus": "paid"}
    if channel == "airbnb":
        r["airbnbExpectedPayoutAmount"] = price
    return r


class _Req:
    query = {}
    headers = {}
    remote = "test"


class StatementHealthTest(unittest.TestCase):
    def setUp(self):
        OW._terms_cache["v"] = None
        OW._stmt_cache["v"] = None
        bot._save_json("owner_terms.json", {"owners": {}, "units": {}, "versions": []})
        bot._save_json("owner_statements.json", {})
        bot._owner_registry.clear()
        bot._owner_registry[bot._owner_key("4511")] = {
            "apartment": "4511", "owner": OWNER, "mgmt_pct": 20.0, "lid": LID,
            "cleaning": {"type": "ours", "amount": 0}}
        self._patched = (bot.fetch_reservations_window, bot.fetch_reservations_window_checked,
                         bot.get_listings_map)
        rows = [_resv(9001, "2026-07-05", 1000.0),
                _resv(9002, "2026-07-28", 436.34, status="cancelled")]
        bot.fetch_reservations_window = lambda s, e, pad_days=45: list(rows)
        bot.fetch_reservations_window_checked = lambda s, e: (list(rows), False)
        bot.get_listings_map = lambda: {LID: "4511"}
        bot._expenses.clear()
        bot._owner_portal_cache.clear()
        bot._finance_adjust.clear()

    def tearDown(self):
        (bot.fetch_reservations_window, bot.fetch_reservations_window_checked,
         bot.get_listings_map) = self._patched

    def _include(self):
        return OW.statement_edit(_Req(), {"owner": OWNER, "m": MONTH, "op": "resv_include",
                                          "id": "9002", "amount": 436.34, "reason": "حجز ملغي"})

    # ---- the reported bug ----
    def test_income_split_follows_a_forced_include(self):
        self._include()
        s = OW.compute_owner_statement(OWNER, MONTH)
        self.assertEqual(s["total_income"], 1436.34)
        self.assertEqual(round(s["income_airbnb"] + s["income_direct"]
                               + s["extras"] + (s.get("manual_income") or 0), 2),
                         s["total_income"],
                         "«تفصيل الدخل» does not add up to «إجمالي الدخل»")

    def test_income_split_follows_an_exclude(self):
        OW.statement_edit(_Req(), {"owner": OWNER, "m": MONTH, "op": "resv_exclude",
                                   "id": "9001", "reason": "مو حقه"})
        s = OW.compute_owner_statement(OWNER, MONTH)
        self.assertEqual(s["total_income"], 0.0)
        self.assertEqual(s["income_airbnb"], 0.0)

    # ---- the invariant checker itself ----
    def test_health_is_clean_before_and_after_editing(self):
        self.assertTrue(OW.statement_health(OWNER, MONTH)["ok"])
        self._include()
        h = OW.statement_health(OWNER, MONTH)
        self.assertTrue(h["ok"], "health flagged a healthy statement: %r" % (h["problems"],))

    def test_health_catches_a_broken_split(self):
        s = OW.compute_owner_statement(OWNER, MONTH)
        s = dict(s)
        s["income_airbnb"] = 1.0                      # simulate the shipped bug
        h = OW.statement_health(OWNER, MONTH, rep=s)
        self.assertFalse(h["ok"])
        self.assertTrue(any(p["kind"] == "income_split" for p in h["problems"]))

    def test_health_catches_a_stale_published_copy(self):
        OW.statement_publish(_Req(), {"owner": OWNER, "m": MONTH, "reason": "أول نشر"})
        self.assertTrue(OW.statement_health(OWNER, MONTH)["ok"])
        self._include()                                # edit AFTER publishing
        h = OW.statement_health(OWNER, MONTH)
        self.assertFalse(h["ok"])
        self.assertTrue(any(p["kind"] == "published_stale" for p in h["problems"]))

    def test_health_catches_an_included_row_left_in_the_excluded_list(self):
        s = dict(OW.compute_owner_statement(OWNER, MONTH))
        s["refunded_lines"] = [{"id": 9002, "guest": "ضيف", "manual_included": True}]
        h = OW.statement_health(OWNER, MONTH, rep=s)
        self.assertTrue(any(p["kind"] == "included_still_excluded" for p in h["problems"]))

    # ---- the sweep ----
    def test_audit_all_covers_every_owner_and_reports_clean(self):
        self._include()
        rep = OW.audit_all(months=[MONTH])
        self.assertEqual(rep["checked_owners"], 1)
        self.assertEqual(rep["statements_with_problems"], 0, rep["rows"])

    def test_audit_all_surfaces_a_broken_statement(self):
        OW.statement_publish(_Req(), {"owner": OWNER, "m": MONTH, "reason": "نشر"})
        self._include()
        rep = OW.audit_all(months=[MONTH])
        self.assertEqual(rep["statements_with_problems"], 1)
        self.assertEqual(rep["rows"][0]["owner"], OWNER)

    def test_audit_never_raises_on_an_unknown_owner(self):
        rep = OW.audit_all(months=[MONTH], owner="مالك ما هو موجود")
        self.assertEqual(rep["statements_with_problems"], 0)


class OutsideContractSplitTest(unittest.TestCase):
    """A unit outside its contract window zeroes the income — the channel split
    must follow. Found by the 2026-08-04 sweep on عبدالمحسن: «إجمالي الدخل 0.00»
    printed beside «دخل Airbnb 9,232.32», for four months, unreported by anyone."""

    def setUp(self):
        OW._terms_cache["v"] = None
        OW._stmt_cache["v"] = None
        bot._save_json("owner_statements.json", {})
        bot._save_json("owner_terms.json", {
            "owners": {},
            "units": {bot._owner_key("1 MLQ"): {"contract_from": "2026-09-01",
                                                "terms": [{"from": "2026-01-01", "mgmt_pct": 20.0}]}},
            "versions": []})
        bot._owner_registry.clear()
        bot._owner_registry[bot._owner_key("1 MLQ")] = {
            "apartment": "1 MLQ", "owner": "عبدالمحسن", "mgmt_pct": 20.0, "lid": 8801,
            "cleaning": {"type": "ours", "amount": 0}}
        self._patched = (bot.fetch_reservations_window, bot.fetch_reservations_window_checked,
                         bot.get_listings_map)
        rows = [{"id": 7001, "listingMapId": 8801, "arrivalDate": "2026-07-05",
                 "departureDate": "2026-07-06", "nights": 1, "totalPrice": 9232.32,
                 "guestName": "ضيف", "status": "new", "channelName": "airbnb",
                 "airbnbExpectedPayoutAmount": 9232.32, "alreadyPaid": 9232.32,
                 "paymentStatus": "paid"}]
        bot.fetch_reservations_window = lambda s, e, pad_days=45: list(rows)
        bot.fetch_reservations_window_checked = lambda s, e: (list(rows), False)
        bot.get_listings_map = lambda: {8801: "1 MLQ"}
        bot._expenses.clear()
        bot._owner_portal_cache.clear()
        bot._finance_adjust.clear()

    def tearDown(self):
        (bot.fetch_reservations_window, bot.fetch_reservations_window_checked,
         bot.get_listings_map) = self._patched

    def test_split_is_zero_when_the_month_is_outside_the_contract(self):
        s = OW.compute_owner_statement("عبدالمحسن", MONTH)
        self.assertEqual(s["total_income"], 0.0)
        self.assertEqual(s["income_airbnb"], 0.0,
                         "the channel split kept income the contract window excluded")
        self.assertTrue(OW.statement_health("عبدالمحسن", MONTH)["ok"])

    def test_rounding_drift_is_not_reported_as_a_problem(self):
        s = dict(OW.compute_owner_statement("عبدالمحسن", MONTH))
        s["owner_net"] = round(float(s["owner_net"]) + 0.01, 2)      # a halala of drift
        self.assertTrue(OW.statement_health("عبدالمحسن", MONTH, rep=s)["ok"])
        s["owner_net"] = round(float(s["owner_net"]) + 5.0, 2)       # real money
        self.assertFalse(OW.statement_health("عبدالمحسن", MONTH, rep=s)["ok"])

if __name__ == "__main__":
    unittest.main(verbosity=2)
