# -*- coding: utf-8 -*-
"""«حساب المالك» — the owner collects from Airbnb on his own account; Ouja BILLS him.

Synthetic Hostaway rows run through the REAL statement engine (build_owner_report →
compute_owner_report), so these tests pin the owner's rules, not a re-implementation:

  * 18% of what Airbnb paid out, VAT 15% on Ouja's fee ONLY, expenses at cost;
    fee and VAT rounded per unit, totals = sums (the PDF table adds up);
  * the LISTING decides whose money a booking was (old listings never billed);
  * expenses go by DATE (old listing on/after the switch date → the claim, and the
    old statement stops deducting it);
  * approval is impossible without the Daftra number, before month end, or with a
    booking whose money we can't prove; an approved month is frozen;
  * the old units are pinned to their OLD listing ids, once.
"""
import datetime
import unittest

import bot
from finance import api as FAPI
from finance import ownerbill as OB
from finance import ownerbill_pdf as OBPDF

FAPI.B = FAPI.B or bot

CFG = OB.BUILDINGS["nuzha"]
U = {u["code"]: u for u in CFG["units"]}
OWNER = CFG["owner"]


def _raw(rid, unit, arrive, leave, payout, *, new=True, channel="airbnb", status="new",
         guest="Sara Ali", refund=None):
    """One raw Hostaway reservation, shaped like the live API."""
    lid = U[unit]["new_lid"] if new else U[unit]["old_lid"]
    r = {"id": rid, "listingMapId": lid, "channelName": channel, "status": status,
         "arrivalDate": arrive, "departureDate": leave, "guestName": guest,
         "totalPrice": payout}
    if channel == "airbnb" and payout is not None:
        r["airbnbExpectedPayoutAmount"] = payout
    if refund:
        r["refundAmount"] = refund
    return r


def _exp(eid, unit, day, amount, *, new=False):
    lid = U[unit]["new_lid"] if new else U[unit]["old_lid"]
    return {"id": eid, "listing_id": lid, "apartment": unit, "amount": amount,
            "expense_date": day, "hostaway_verified": True, "category": "صيانة",
            "note": "مكيف"}


class Req(dict):
    pass


ADMIN = Req(role="admin")
ACCT = Req(role="accountant")


class _Base(unittest.TestCase):
    TODAY = datetime.date(2026, 10, 5)

    def setUp(self):
        self.saved = {}
        self._orig = {k: getattr(bot, k) for k in (
            "fetch_reservations_window", "get_listings_map", "_save_json", "_load_json",
            "_req_actor", "_req_role", "_pdf_font")}
        self._exp_backup = dict(bot._expenses)
        self._reg_backup = {k: dict(v) for k, v in bot._owner_registry.items()}
        bot._expenses.clear()
        self.rows = []
        bot.fetch_reservations_window = lambda s, e, pad_days=45: list(self.rows)
        names = {}
        for u in CFG["units"]:
            names[u["old_lid"]] = u["code"]
            names[u["new_lid"]] = u["code"] + "-O"
        bot.get_listings_map = lambda: dict(names)
        bot._save_json = lambda name, data: self.saved.__setitem__(name, data)
        bot._load_json = lambda name, default=None: default
        bot._req_actor = lambda r: "tester"
        bot._req_role = lambda r: (r or {}).get("role", "accountant")
        OB._cache["v"] = None
        OB._month_cache.clear()
        self._today = OB._today
        OB._today = lambda: self.TODAY

    def tearDown(self):
        for k, v in self._orig.items():
            setattr(bot, k, v)
        bot._expenses.clear()
        bot._expenses.update(self._exp_backup)
        bot._owner_registry.clear()
        bot._owner_registry.update(self._reg_backup)
        bot._ownerbill_moved_hook = None
        OB._today = self._today
        OB._cache["v"] = None
        OB._month_cache.clear()

    def set_switch(self, **dates):
        st = OB._store()
        for code, d in dates.items():
            st["switch"].setdefault("nuzha", {})[code] = {"date": d, "source": "auto"}


class MathTest(_Base):
    def test_fee_and_vat_per_unit_and_totals_add_up(self):
        self.rows = [
            _raw(1, "101B", "2026-09-18", "2026-09-19", 315.02),
            _raw(2, "101B", "2026-09-19", "2026-09-20", 295.41),
            _raw(3, "202B", "2026-09-16", "2026-09-18", 333.33),
        ]
        comp = OB.compute_month("nuzha", "2026-09")
        u = {x["code"]: x for x in comp["units"]}
        self.assertEqual(u["101B"]["income"], 610.43)
        self.assertEqual(u["101B"]["fee"], 109.88)          # 610.43 × 18% = 109.8774
        self.assertEqual(u["101B"]["vat"], 16.48)           # 109.88 × 15% = 16.482
        self.assertEqual(u["202B"]["fee"], 60.0)            # 333.33 × 18% = 59.9994
        self.assertEqual(u["202B"]["vat"], 9.0)
        tot = OB.apply_lines(comp, [], CFG)
        self.assertEqual(tot["fee"], round(109.88 + 60.0, 2))
        self.assertEqual(tot["vat"], round(16.48 + 9.0, 2))
        self.assertEqual(tot["due"], round(109.88 + 60.0 + 16.48 + 9.0, 2))
        self.assertEqual(tot["bookings"], 3)
        self.assertEqual(tot["nights"], 4)
        self.assertEqual(comp["blockers"], [])

    def test_old_listing_bookings_are_never_billed(self):
        self.rows = [_raw(1, "101A", "2026-09-03", "2026-09-05", 900, new=False),
                     _raw(2, "101A", "2026-09-20", "2026-09-21", 300)]
        comp = OB.compute_month("nuzha", "2026-09")
        u = {x["code"]: x for x in comp["units"]}
        self.assertEqual(u["101A"]["income"], 300.0)
        self.assertEqual([b["id"] for b in u["101A"]["bookings"]], [2])

    def test_refund_reduces_income(self):
        self.rows = [_raw(1, "102A", "2026-09-20", "2026-09-22", 500, refund=100)]
        comp = OB.compute_month("nuzha", "2026-09")
        self.assertEqual({x["code"]: x for x in comp["units"]}["102A"]["income"], 400.0)

    def test_cancelled_is_listed_not_counted(self):
        self.rows = [_raw(1, "101B", "2026-09-23", "2026-09-25", 835.47, status="cancelled")]
        comp = OB.compute_month("nuzha", "2026-09")
        u = {x["code"]: x for x in comp["units"]}["101B"]
        self.assertEqual(u["income"], 0.0)
        self.assertEqual(len(u["excluded"]), 1)
        self.assertEqual(comp["blockers"], [])

    def test_missing_payout_and_non_airbnb_block_approval(self):
        self.rows = [_raw(1, "201A", "2026-09-20", "2026-09-21", None),
                     _raw(2, "201B", "2026-09-20", "2026-09-21", 400, channel="Booking.com")]
        comp = OB.compute_month("nuzha", "2026-09")
        codes = sorted(b["code"] for b in comp["blockers"])
        self.assertEqual(codes, ["missing_payout", "needs_channel_rule"])
        self.assertEqual(OB.apply_lines(comp, [], CFG)["due"], 0.0)

    def test_manual_lines(self):
        self.rows = [_raw(1, "101A", "2026-09-20", "2026-09-21", 1000)]
        comp = OB.compute_month("nuzha", "2026-09")
        lines = [{"kind": "income", "amount": 200}, {"kind": "expense", "amount": 50.5},
                 {"kind": "credit", "amount": 30}]
        t = OB.apply_lines(comp, lines, CFG)
        # Airbnb 1000 → fee 180, vat 27; manual income 200 → fee 36, vat 5.40
        self.assertEqual(t["fee"], 216.0)
        self.assertEqual(t["vat"], 32.4)
        self.assertEqual(t["expenses"], 50.5)
        self.assertEqual(t["due"], round(216 + 32.4 + 50.5 - 30, 2))


class ExpenseByDateTest(_Base):
    def test_claim_takes_old_listing_expenses_only_after_switch(self):
        self.set_switch(**{"101B": "2026-09-18"})
        bot._expenses.update({
            "e1": _exp("e1", "101B", "2026-09-10", 100),            # before switch → old statement
            "e2": _exp("e2", "101B", "2026-09-20", 250),            # after switch → claim
            "e3": _exp("e3", "101B", "2026-09-05", 80, new=True),   # tagged to the new listing → claim
            "e4": _exp("e4", "102B", "2026-09-25", 60),             # 102B has no switch yet → old
        })
        comp = OB.compute_month("nuzha", "2026-09")
        u = {x["code"]: x for x in comp["units"]}
        self.assertEqual(sorted(e["id"] for e in u["101B"]["expenses"]), ["e2", "e3"])
        self.assertEqual(u["101B"]["expenses_total"], 330.0)
        self.assertEqual(u["102B"]["expenses"], [])

    def test_compute_detects_switch_dates_itself(self):
        # approving straight away (board never opened) must still see the switch date
        self.rows = [_raw(1, "101B", "2026-09-18", "2026-09-19", 300)]
        bot._expenses["e2"] = _exp("e2", "101B", "2026-09-22", 240)
        comp = OB.compute_month("nuzha", "2026-09")
        u = {x["code"]: x for x in comp["units"]}
        self.assertEqual(u["101B"]["switch_date"], "2026-09-18")
        self.assertEqual(u["101B"]["expenses_total"], 240.0)

    def test_old_statement_stops_deducting_moved_expenses(self):
        self.set_switch(**{"101B": "2026-09-18"})
        bot._expenses.update({
            "e1": _exp("e1", "101B", "2026-09-10", 100),
            "e2": _exp("e2", "101B", "2026-09-20", 250),
        })
        old = U["101B"]["old_lid"]
        s, e = datetime.date(2026, 9, 1), datetime.date(2026, 9, 30)
        bot._ownerbill_moved_hook = None
        before = bot.build_owner_report(old, s, e, 18.0, None, adjust={})
        self.assertEqual(before["expenses"], 350.0)                 # no hook → old behaviour
        bot._ownerbill_moved_hook = OB.expense_moved
        after = bot.build_owner_report(old, s, e, 18.0, None, adjust={})
        self.assertEqual(after["expenses"], 100.0)                  # e2 now lives on the claim
        self.assertEqual([x["id"] for x in after["exp_lines"]], ["e1"])

    def test_portfolio_report_and_text_ids(self):
        self.set_switch(**{"101B": "2026-09-18"})
        e2 = _exp("e2", "101B", "2026-09-20", 250)
        e2["listing_id"] = str(e2["listing_id"])                  # stored as text
        bot._expenses["e2"] = e2
        self.assertTrue(OB.expense_moved(e2["listing_id"], e2["expense_date"]))
        comp = OB.compute_month("nuzha", "2026-09")
        self.assertEqual({x["code"]: x for x in comp["units"]}["101B"]["expenses_total"], 250.0)
        bot._expenses["e2"]["listing_id"] = U["101B"]["old_lid"]
        bot._ownerbill_moved_hook = OB.expense_moved
        s, e = datetime.date(2026, 9, 1), datetime.date(2026, 9, 30)
        allrep = bot.build_owner_report(None, s, e, 18.0, None, adjust={})
        self.assertEqual(allrep["expenses"], 250.0)                 # company-wide keeps it

    def test_hook_failure_falls_back_to_old_behaviour(self):
        def boom(lid, d):
            raise RuntimeError("x")
        bot._ownerbill_moved_hook = boom
        self.assertFalse(bot._ownerbill_expense_moved({"listing_id": 1, "expense_date": "2026-09-01"}))


class SwitchDetectionTest(_Base):
    def test_first_checkin_on_new_listing_is_stored(self):
        self.rows = [_raw(1, "202A", "2026-09-13", "2026-09-14", 200),
                     _raw(2, "202A", "2026-09-20", "2026-09-21", 200),
                     _raw(3, "102B", "2026-09-30", "2026-10-01", 200, status="cancelled"),
                     _raw(4, "101A", "2026-09-05", "2026-09-06", 200, new=False)]
        n = OB.detect_switch_dates("nuzha")
        self.assertEqual(n, 1)
        sw = OB.switch_dates("nuzha")
        self.assertEqual(sw["202A"], datetime.date(2026, 9, 13))
        self.assertIsNone(sw["102B"])                               # a cancellation is not a switch
        self.assertIsNone(sw["101A"])                               # old listing doesn't count
        # stored: the first booking being cancelled later does not move it
        self.rows = [_raw(2, "202A", "2026-09-20", "2026-09-21", 200)]
        OB.detect_switch_dates("nuzha")
        self.assertEqual(OB.switch_dates("nuzha")["202A"], datetime.date(2026, 9, 13))

    def test_manual_switch_needs_reason(self):
        d, st = OB.switch_set(ACCT, {"b": "nuzha", "unit": "102B", "date": "2026-10-10"})
        self.assertEqual(st, 400)
        d, st = OB.switch_set(ACCT, {"b": "nuzha", "unit": "102B", "date": "2026-10-10",
                                     "reason": "أول ضيف بعد خروج الساكن"})
        self.assertEqual(st, 200)
        self.assertEqual(OB.switch_dates("nuzha")["102B"], datetime.date(2026, 10, 10))


class WorkflowTest(_Base):
    def setUp(self):
        super().setUp()
        self.rows = [_raw(1, "101A", "2026-09-20", "2026-09-21", 1000)]

    def test_approve_gates(self):
        d, st = OB.approve(ACCT, {"b": "nuzha", "m": "2026-10"})
        self.assertEqual(st, 409)
        self.assertIn("month_not_over", d["problems"])
        self.assertIn("daftra_missing", d["problems"])
        d, st = OB.approve(ACCT, {"b": "nuzha", "m": "2026-09"})
        self.assertEqual(d["problems"], ["daftra_missing"])
        OB.daftra_set(ACCT, {"b": "nuzha", "m": "2026-09", "number": "INV-1042"})
        d, st = OB.approve(ACCT, {"b": "nuzha", "m": "2026-09"})
        self.assertEqual(st, 200)
        v = d["view"]
        self.assertTrue(v["frozen"])
        self.assertEqual(v["version"], 1)
        self.assertEqual(v["status"], "approved")
        self.assertEqual(v["totals"]["due"], 207.0)                 # 180 + 27

    def test_blockers_refuse_approval(self):
        self.rows.append(_raw(2, "201A", "2026-09-20", "2026-09-21", None))
        OB.daftra_set(ACCT, {"b": "nuzha", "m": "2026-09", "number": "INV-1"})
        d, st = OB.approve(ACCT, {"b": "nuzha", "m": "2026-09"})
        self.assertEqual(st, 409)
        self.assertEqual(d["problems"], ["blockers"])
        self.assertEqual(OB.month_view("nuzha", "2026-09")["status"], "needs_review")

    def test_frozen_version_survives_a_hostaway_change(self):
        OB.daftra_set(ACCT, {"b": "nuzha", "m": "2026-09", "number": "INV-1"})
        OB.approve(ACCT, {"b": "nuzha", "m": "2026-09"})
        self.rows = [_raw(1, "101A", "2026-09-20", "2026-09-21", 5000)]
        OB._month_cache.clear()
        self.assertEqual(OB.month_view("nuzha", "2026-09")["totals"]["due"], 207.0)
        d, st = OB.line_add(ACCT, {"b": "nuzha", "m": "2026-09", "kind": "expense", "label": "x",
                                   "amount": 10, "reason": "سبب"})
        self.assertEqual(st, 409)                                   # locked
        d, st = OB.daftra_set(ACCT, {"b": "nuzha", "m": "2026-09", "number": "INV-2"})
        self.assertEqual(st, 409)

    def test_sent_due_overdue_paid(self):
        OB.daftra_set(ACCT, {"b": "nuzha", "m": "2026-09", "number": "INV-1"})
        d, st = OB.status_set(ACCT, {"b": "nuzha", "m": "2026-09", "action": "sent"})
        self.assertEqual(st, 409)                                   # not approved yet
        OB.approve(ACCT, {"b": "nuzha", "m": "2026-09"})
        d, st = OB.status_set(ACCT, {"b": "nuzha", "m": "2026-09", "action": "sent"})
        self.assertEqual(d["view"]["due"], "2026-10-15")
        self.assertEqual(d["view"]["status"], "sent")
        OB._today = lambda: datetime.date(2026, 10, 16)
        self.assertEqual(OB.month_view("nuzha", "2026-09")["status"], "overdue")
        d, st = OB.status_set(ACCT, {"b": "nuzha", "m": "2026-09", "action": "paid", "ref": "TRX-9"})
        self.assertEqual(d["view"]["status"], "paid")
        self.assertEqual(d["view"]["paid_ref"], "TRX-9")

    def test_reopen_is_admin_only_and_keeps_versions(self):
        OB.daftra_set(ACCT, {"b": "nuzha", "m": "2026-09", "number": "INV-1"})
        OB.approve(ACCT, {"b": "nuzha", "m": "2026-09"})
        d, st = OB.status_set(ACCT, {"b": "nuzha", "m": "2026-09", "action": "reopen", "reason": "خطأ"})
        self.assertEqual(st, 403)
        d, st = OB.status_set(ADMIN, {"b": "nuzha", "m": "2026-09", "action": "reopen"})
        self.assertEqual(st, 400)                                   # reason required
        d, st = OB.status_set(ADMIN, {"b": "nuzha", "m": "2026-09", "action": "reopen",
                                      "reason": "مصروف ناقص"})
        self.assertEqual(st, 200)
        self.assertFalse(d["view"]["frozen"])
        OB.approve(ACCT, {"b": "nuzha", "m": "2026-09"})
        v = OB.month_view("nuzha", "2026-09")
        self.assertEqual(v["version"], 2)
        self.assertEqual([x["v"] for x in v["versions"]], [1, 2])

    def test_lines_need_reason_and_positive_amount(self):
        base = {"b": "nuzha", "m": "2026-09", "kind": "expense", "label": "سباكة"}
        self.assertEqual(OB.line_add(ACCT, dict(base, amount=10))[1], 400)
        self.assertEqual(OB.line_add(ACCT, dict(base, amount=0, reason="فاتورة"))[1], 400)
        self.assertEqual(OB.line_add(ACCT, dict(base, amount=10, reason="فاتورة", unit="999"))[1], 400)
        d, st = OB.line_add(ACCT, dict(base, amount=10, reason="فاتورة", unit="101A"))
        self.assertEqual(st, 200)
        self.assertEqual(d["view"]["totals"]["due"], 217.0)
        lid = d["line"]["id"]
        self.assertEqual(OB.line_del(ACCT, {"b": "nuzha", "m": "2026-09", "id": lid})[1], 400)
        d, st = OB.line_del(ACCT, {"b": "nuzha", "m": "2026-09", "id": lid, "reason": "مكرر"})
        self.assertEqual(d["view"]["totals"]["due"], 207.0)


class PinTest(_Base):
    def test_pins_only_the_owners_unpinned_rows_once(self):
        key = bot._owner_key
        bot._owner_registry.clear()
        bot._owner_registry.update({
            key("101A"): {"apartment": "101A", "owner": OWNER, "mgmt_pct": 18.0, "lid": 490890},
            key("101B"): {"apartment": "101B", "owner": OWNER, "mgmt_pct": 18.0},
            key("202B"): {"apartment": "202B", "owner": OWNER, "mgmt_pct": 18.0},
            key("13 JOOD"): {"apartment": "13 JOOD", "owner": "غيره", "mgmt_pct": 18.0},
        })
        self.assertTrue(OB.ensure_pinned())
        self.assertEqual(bot._owner_registry[key("101B")]["lid"], 477748)
        self.assertEqual(bot._owner_registry[key("202B")]["lid"], 473608)
        self.assertEqual(bot._owner_registry[key("101A")]["lid"], 490890)
        self.assertNotIn("lid", bot._owner_registry[key("13 JOOD")])
        self.assertIn("owner_registry.json", self.saved)
        bot._owner_registry[key("101B")]["lid"] = 999                # a later deliberate change
        self.assertFalse(OB.ensure_pinned())                        # marker: never re-applied
        self.assertEqual(bot._owner_registry[key("101B")]["lid"], 999)

    def test_guard_flags_a_new_listing_inside_a_statement(self):
        key = bot._owner_key
        bot._owner_registry.clear()
        bot._owner_registry.update({
            key(u["code"]): {"apartment": u["code"], "owner": OWNER, "mgmt_pct": 18.0, "lid": u["old_lid"]}
            for u in CFG["units"]})
        self.assertEqual([g for g in OB.guards("nuzha") if g["level"] == "bad"], [])
        bot._owner_registry[key("101B")]["lid"] = U["101B"]["new_lid"]
        bad = [g for g in OB.guards("nuzha") if g["level"] == "bad"]
        self.assertEqual([g["unit"] for g in bad], ["101B"])


class PdfTest(_Base):
    def test_draft_and_approved_render(self):
        self.rows = [_raw(i, "101B", "2026-09-%02d" % (10 + i), "2026-09-%02d" % (11 + i), 300 + i,
                          guest="نورة المبارك") for i in range(1, 15)]
        bot._expenses["e9"] = _exp("e9", "101B", "2026-09-25", 120, new=True)
        self.set_switch(**{"101B": "2026-09-11"})
        OB.line_add(ACCT, {"b": "nuzha", "m": "2026-09", "kind": "credit", "label": "تعويض ليلة",
                           "amount": 50, "reason": "تأخر تسليم", "unit": "101B"})
        draft = OBPDF.render(OB.month_view("nuzha", "2026-09"))
        self.assertTrue(draft.startswith(b"%PDF"))
        OB.daftra_set(ACCT, {"b": "nuzha", "m": "2026-09", "number": "INV-77"})
        d, st = OB.approve(ACCT, {"b": "nuzha", "m": "2026-09"})
        self.assertEqual(st, 200)
        final = OBPDF.render(OB.month_view("nuzha", "2026-09"))
        self.assertTrue(final.startswith(b"%PDF"))
        self.assertGreater(len(final), 5000)

    def test_month_label(self):
        self.assertEqual(OBPDF.month_label("2026-09"), "سبتمبر 2026")

    def test_dates_are_words_not_iso(self):
        # an ISO date inside Arabic text is reordered by bidi («15-10-2026»)
        self.assertEqual(OBPDF.ar_date("2026-10-15"), "15 أكتوبر 2026")
        self.assertEqual(OBPDF.ar_date("2026-10-05T12:00:00+03:00"), "5 أكتوبر 2026")


if __name__ == "__main__":
    unittest.main()
