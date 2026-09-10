# -*- coding: utf-8 -*-
"""directpay.engine — the PURE rules of the collection ledger (no DB, no HOST, no I/O).

What is locked here:
  * eligibility reuses bot's channel classifier by INJECTION (a copy of _finance_channel is
    the fixture — the package never grows a second classifier); blank channel = direct,
    Booking.com = other, DIRECTPAY_EXTRA_CHANNELS adds a channel without touching it
  * the START-DATE cutoff: booked before the date → never; ON the date → yes
  * variance tolerance: inside passes, outside is refused, outside WITH a reason passes
  * the state machine: verified needs proof+amount+ref; verified→verified is a no-op;
    written_off / void are terminal; verified→open only on a price increase
  * aging buckets + outstanding total on 12 synthetic rows, asserted exactly

Run: python3 -m unittest tests.test_directpay_engine
"""
import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from directpay import engine  # noqa: E402

CONFIRMED = {"new", "modified"}
START = datetime.date(2026, 9, 10)


def finance_channel(r):
    """Verbatim copy of bot._finance_channel (bot.py) — the fixture, not a second classifier."""
    ch = (r.get("channelName") or r.get("channel") or "").strip().lower()
    if "airbnb" in ch:
        return "airbnb"
    if (not ch) or any(w in ch for w in ("direct", "manual", "website", "owner", "walk")):
        return "direct"
    return "other"


def res(rid=1, channel="direct", status="new", booked="2026-09-10 09:00:00", **kw):
    r = {"id": rid, "channelName": channel, "status": status, "reservationDate": booked,
         "listingMapId": 900, "guestName": "أبو خالد", "arrivalDate": "2026-10-01",
         "departureDate": "2026-10-04", "nights": 3, "totalPrice": 1200.0}
    r.update(kw)
    return r


def elig(r, **kw):
    kw.setdefault("finance_channel", finance_channel)
    kw.setdefault("confirmed_statuses", CONFIRMED)
    kw.setdefault("start_date", START)
    return engine.eligibility(r, **kw)


class TestEligibility(unittest.TestCase):
    def test_airbnb_is_not_eligible(self):
        ok, why = elig(res(channel="Airbnb"))
        self.assertFalse(ok)
        self.assertEqual(why, "not_direct")

    def test_blank_channel_is_direct_deliberately(self):
        ok, why = elig(res(channel=""))
        self.assertTrue(ok, why)

    def test_booking_com_is_other_not_direct(self):
        ok, why = elig(res(channel="Booking.com"))
        self.assertFalse(ok)
        self.assertEqual(why, "not_direct")

    def test_extra_channels_add_without_touching_the_classifier(self):
        self.assertFalse(elig(res(channel="Booking.com"))[0])
        ok, why = elig(res(channel="Booking.com"), extra_channels=["booking"])
        self.assertTrue(ok, why)
        # the classifier itself still says "other" — injection, not mutation
        self.assertEqual(finance_channel(res(channel="Booking.com")), "other")

    def test_cancelled_and_inquiry_are_not_eligible(self):
        for st in ("cancelled", "inquiry", "expired", "declined", ""):
            ok, why = elig(res(status=st))
            self.assertFalse(ok, st)
            self.assertEqual(why, "status", st)

    def test_modified_counts_as_confirmed(self):
        self.assertTrue(elig(res(status="modified"))[0])

    def test_booked_before_start_date_never_opens(self):
        ok, why = elig(res(booked="2026-09-09 23:59:59"))
        self.assertFalse(ok)
        self.assertEqual(why, "before_start")

    def test_booked_on_the_boundary_date_opens(self):
        ok, why = elig(res(booked="2026-09-10 00:00:01"))
        self.assertTrue(ok, why)

    def test_booked_date_iso_t_form_and_missing(self):
        self.assertEqual(engine.booked_date({"reservationDate": "2026-09-10T08:00:00+03:00"}), "2026-09-10")
        self.assertIsNone(engine.booked_date({}))
        ok, why = elig(res(booked=None))
        self.assertFalse(ok)
        self.assertEqual(why, "no_booked_at")

    def test_known_ids_are_duplicates(self):
        ok, why = elig(res(rid=77), known_ids={"77"})
        self.assertFalse(ok)
        self.assertEqual(why, "duplicate")

    def test_missing_id_is_refused(self):
        ok, why = elig(res(rid=None))
        self.assertFalse(ok)
        self.assertEqual(why, "no_id")


class TestVariance(unittest.TestCase):
    def test_inside_tolerance_passes(self):
        v = engine.variance(1200.0, 1200.5, abs_tol=1.0, pct_tol=0.01)
        self.assertTrue(v["ok"])
        self.assertAlmostEqual(v["variance"], -0.5)

    def test_tolerance_is_the_larger_of_abs_and_pct(self):
        # 1% of 5000 = 50 > 1.0 → a 40 SAR gap passes
        self.assertTrue(engine.variance(4960.0, 5000.0)["ok"])
        # 1% of 100 = 1.0 = abs → a 1.5 SAR gap fails
        self.assertFalse(engine.variance(98.5, 100.0)["ok"])

    def test_outside_is_refused_without_a_reason(self):
        row = {"status": "open", "total_sar_current": 1200.0}
        ok, why, info = engine.transition(row, "verified", {
            "received_sar": 1000.0, "stayhub_ref": "SH-123", "proof_path": "directpay/x/1_a.jpg"})
        self.assertFalse(ok)
        self.assertEqual(info.get("code"), "variance")
        self.assertIn("1200", why)
        self.assertIn("1000", why)

    def test_outside_with_a_reason_passes(self):
        row = {"status": "open", "total_sar_current": 1200.0}
        ok, why, patch = engine.transition(row, "verified", {
            "received_sar": 1000.0, "stayhub_ref": "SH-123", "proof_path": "directpay/x/1_a.jpg",
            "variance_reason": "الضيف رجع ليلة واسترجعنا له ٢٠٠"})
        self.assertTrue(ok, why)
        self.assertEqual(patch["status"], "verified")
        self.assertAlmostEqual(patch["variance_sar"], -200.0)
        self.assertTrue(patch["variance_reason"])

    def test_a_too_short_variance_reason_is_not_a_reason(self):
        row = {"status": "open", "total_sar_current": 1200.0}
        ok, why, info = engine.transition(row, "verified", {
            "received_sar": 1000.0, "stayhub_ref": "SH-123", "proof_path": "p",
            "variance_reason": "خصم"})
        self.assertFalse(ok)
        self.assertEqual(info.get("code"), "variance")


class TestTransition(unittest.TestCase):
    def open_row(self, **kw):
        r = {"id": "dp_1", "status": "open", "total_sar": 1200.0, "total_sar_current": 1200.0}
        r.update(kw)
        return r

    def good_ctx(self, **kw):
        c = {"received_sar": 1200.0, "stayhub_ref": "SH-77", "proof_path": "directpay/dp_1/1_a.jpg",
             "by": "فيصل", "by_id": "1", "now": "2026-09-12T10:00:00"}
        c.update(kw)
        return c

    def test_open_to_verified_needs_proof_amount_and_ref(self):
        ok, why, info = engine.transition(self.open_row(), "verified", self.good_ctx(proof_path=None))
        self.assertFalse(ok); self.assertEqual(info["code"], "no_proof")
        ok, why, info = engine.transition(self.open_row(), "verified", self.good_ctx(received_sar=0))
        self.assertFalse(ok); self.assertEqual(info["code"], "amount")
        ok, why, info = engine.transition(self.open_row(), "verified", self.good_ctx(stayhub_ref="ab"))
        self.assertFalse(ok); self.assertEqual(info["code"], "ref")
        ok, why, patch = engine.transition(self.open_row(), "verified", self.good_ctx())
        self.assertTrue(ok, why)
        self.assertEqual(patch["status"], "verified")
        self.assertEqual(patch["received_sar"], 1200.0)
        self.assertEqual(patch["stayhub_ref"], "SH-77")
        self.assertEqual(patch["closed_by"], "فيصل")
        self.assertEqual(patch["closed_by_id"], "1")
        self.assertEqual(patch["closed_at"], "2026-09-12T10:00:00")

    def test_verified_to_verified_is_a_noop_not_an_error(self):
        ok, why, patch = engine.transition(self.open_row(status="verified"), "verified", self.good_ctx())
        self.assertTrue(ok)
        self.assertEqual(patch, {})

    def test_written_off_is_terminal(self):
        for target in ("open", "verified", "void", "written_off"):
            ok, why, info = engine.transition(self.open_row(status="written_off"), target, self.good_ctx())
            self.assertFalse(ok, target)
            self.assertEqual(info["code"], "terminal", target)

    def test_void_is_terminal(self):
        for target in ("open", "verified", "written_off"):
            ok, why, info = engine.transition(self.open_row(status="void"), target, self.good_ctx())
            self.assertFalse(ok, target)

    def test_written_off_requires_a_20_char_reason(self):
        ok, why, info = engine.transition(self.open_row(), "written_off", {"reason": "قصير", "by": "x"})
        self.assertFalse(ok); self.assertEqual(info["code"], "reason")
        ok, why, patch = engine.transition(self.open_row(), "written_off",
                                           {"reason": "الضيف دفع كاش للمالك مباشرة وما فيه إيصال", "by": "فيصل", "by_id": "1"})
        self.assertTrue(ok, why)
        self.assertEqual(patch["status"], "written_off")
        self.assertEqual(patch["closed_by"], "فيصل")

    def test_void_requires_a_reason_and_keeps_the_channel_name(self):
        ok, why, info = engine.transition(self.open_row(), "void", {"reason": "", "by": "x"})
        self.assertFalse(ok)
        ok, why, patch = engine.transition(self.open_row(), "void", {"reason": "حجز مالك مو ضيف", "by": "أسيل", "by_id": "2"})
        self.assertTrue(ok, why)
        self.assertEqual(patch["status"], "void")
        self.assertEqual(patch["void_reason"], "حجز مالك مو ضيف")

    def test_verified_to_open_only_on_a_price_increase(self):
        row = self.open_row(status="verified", received_sar=1200.0, total_sar_current=1200.0)
        ok, why, info = engine.transition(row, "open", {"total_sar_current": 1200.0})
        self.assertFalse(ok); self.assertEqual(info["code"], "no_increase")
        ok, why, info = engine.transition(row, "open", {"total_sar_current": 1100.0})
        self.assertFalse(ok)
        ok, why, patch = engine.transition(row, "open", {"total_sar_current": 1500.0})
        self.assertTrue(ok, why)
        self.assertEqual(patch["status"], "open")
        self.assertEqual(patch["total_sar_current"], 1500.0)

    def test_open_to_open_is_a_noop(self):
        ok, why, patch = engine.transition(self.open_row(), "open", {})
        self.assertTrue(ok)
        self.assertEqual(patch, {})

    def test_unknown_target_is_refused(self):
        ok, why, info = engine.transition(self.open_row(), "closed", {})
        self.assertFalse(ok)


class TestAgingAndTotals(unittest.TestCase):
    TODAY = datetime.date(2026, 9, 30)

    def rows(self):
        def r(i, age, status="open", sar=100.0, cur=None):
            d = (self.TODAY - datetime.timedelta(days=age)).isoformat()
            return {"id": "dp_%d" % i, "status": status, "total_sar": sar,
                    "total_sar_current": cur, "created_at": d + "T10:00:00"}
        return [
            r(1, 0, sar=100), r(2, 1, sar=200), r(3, 2, sar=300),          # 0–2 → 3 rows, 600
            r(4, 3, sar=400), r(5, 7, sar=500),                            # 3–7 → 2 rows, 900
            r(6, 8, sar=600), r(7, 14, sar=700, cur=750),                  # 8–14 → 2 rows, 1350 (cur wins)
            r(8, 15, sar=800), r(9, 40, sar=900),                          # 15+ → 2 rows, 1700
            r(10, 5, status="verified", sar=1000),                         # not open → excluded
            r(11, 9, status="written_off", sar=1100),                      # separate total
            r(12, 20, status="void", sar=1200),                            # excluded everywhere
        ]

    def test_buckets_exact(self):
        b = engine.aging_buckets(self.rows(), self.TODAY)
        self.assertEqual(b["b0_2"], {"count": 3, "sar": 600.0})
        self.assertEqual(b["b3_7"], {"count": 2, "sar": 900.0})
        self.assertEqual(b["b8_14"], {"count": 2, "sar": 1350.0})
        self.assertEqual(b["b15p"], {"count": 2, "sar": 1700.0})

    def test_outstanding_total_exact(self):
        self.assertEqual(engine.outstanding_total(self.rows()), 4550.0)

    def test_written_off_total_is_separate(self):
        self.assertEqual(engine.written_off_total(self.rows()), 1100.0)

    def test_age_days(self):
        self.assertEqual(engine.age_days({"created_at": "2026-09-28T23:59:00"}, self.TODAY), 2)
        self.assertEqual(engine.age_days({"created_at": None}, self.TODAY), 0)


class TestNudgeAndSummaryClocks(unittest.TestCase):
    def test_nudge_due_after_two_days_then_every_two(self):
        now = datetime.datetime(2026, 9, 30, 11, 0)
        row = {"status": "open", "created_at": "2026-09-29T10:00:00", "nudge_count": 0, "last_nudge_at": None}
        self.assertFalse(engine.nudge_due(row, now, after_days=2, every_days=2))
        row["created_at"] = "2026-09-28T10:00:00"
        self.assertTrue(engine.nudge_due(row, now, after_days=2, every_days=2))
        row.update(nudge_count=1, last_nudge_at="2026-09-29T11:00:00")
        self.assertFalse(engine.nudge_due(row, now, after_days=2, every_days=2))
        row["last_nudge_at"] = "2026-09-28T11:00:00"
        self.assertTrue(engine.nudge_due(row, now, after_days=2, every_days=2))

    def test_closed_rows_never_nudge(self):
        now = datetime.datetime(2026, 9, 30, 11, 0)
        row = {"status": "verified", "created_at": "2026-09-01T10:00:00", "nudge_count": 0}
        self.assertFalse(engine.nudge_due(row, now, 2, 2))

    def test_summary_due_once_per_day_from_the_hour(self):
        self.assertFalse(engine.summary_due(datetime.datetime(2026, 9, 30, 12, 59), None, 13))
        self.assertTrue(engine.summary_due(datetime.datetime(2026, 9, 30, 13, 0), None, 13))
        self.assertTrue(engine.summary_due(datetime.datetime(2026, 9, 30, 18, 0), "2026-09-29", 13))
        self.assertFalse(engine.summary_due(datetime.datetime(2026, 9, 30, 18, 0), "2026-09-30", 13))


class TestSmallHelpers(unittest.TestCase):
    def test_select_openable_honours_cap_and_reports_the_rest(self):
        take, waiting = engine.select_openable(list(range(12)), 5)
        self.assertEqual(take, [0, 1, 2, 3, 4])
        self.assertEqual(waiting, 7)
        take, waiting = engine.select_openable([1, 2], 5)
        self.assertEqual((take, waiting), ([1, 2], 0))
        take, waiting = engine.select_openable([1, 2], 0)
        self.assertEqual((take, waiting), ([], 2))

    def test_proof_types(self):
        self.assertTrue(engine.is_proof_type("image/png", "a.png"))
        self.assertTrue(engine.is_proof_type("image/jpeg", "a.jpg"))
        self.assertTrue(engine.is_proof_type("application/pdf", "invoice.pdf"))
        self.assertFalse(engine.is_proof_type("text/plain", "notes.txt"))
        self.assertFalse(engine.is_proof_type("", "notes.txt"))
        # no content type but a clear extension — Discord sometimes omits it
        self.assertTrue(engine.is_proof_type(None, "receipt.PDF"))
        self.assertTrue(engine.is_proof_type(None, "shot.jpeg"))

    def test_parse_amount(self):
        self.assertEqual(engine.parse_amount("1200"), 1200.0)
        self.assertEqual(engine.parse_amount(" 1,200.50 "), 1200.5)
        self.assertEqual(engine.parse_amount("١٢٠٠"), 1200.0)
        self.assertEqual(engine.parse_amount("1200 ر.س"), 1200.0)
        self.assertIsNone(engine.parse_amount("abc"))
        self.assertIsNone(engine.parse_amount("-5"))
        self.assertIsNone(engine.parse_amount("0"))
        self.assertIsNone(engine.parse_amount(""))

    def test_is_cancelled(self):
        self.assertTrue(engine.is_cancelled("cancelled"))
        self.assertTrue(engine.is_cancelled("Canceled"))
        self.assertTrue(engine.is_cancelled("cancelledByGuest"))
        self.assertFalse(engine.is_cancelled("modified"))
        self.assertFalse(engine.is_cancelled(None))

    def test_raw_channel_is_verbatim(self):
        self.assertEqual(engine.raw_channel({"channelName": " Direct Booking "}), " Direct Booking ")
        self.assertEqual(engine.raw_channel({}), "")


if __name__ == "__main__":
    unittest.main()
