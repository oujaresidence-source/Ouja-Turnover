# -*- coding: utf-8 -*-
import pathlib
import unittest

from owner_report import hostaway_fetch as H


def _res(checkout, nights, revenue, channel="Airbnb", lead=5, repeat=False, status="confirmed"):
    return {"checkout": checkout, "nights": nights, "revenue": revenue,
            "channel": channel, "lead_days": lead, "is_repeat": repeat, "status": status}


class TestAggregation(unittest.TestCase):
    def setUp(self):
        self.rows = [
            _res("2026-01-20", 4, 5000, "Airbnb", 6, True),
            _res("2026-01-28", 3, 3000, "Direct (Ouja)", 10, False),
            _res("2026-02-15", 5, 4000, "Airbnb", 4, False),
            _res("2026-02-20", 2, 2000, "Booking.com", 3, False, status="cancelled"),
        ]

    def test_cancelled_excluded_from_revenue(self):
        self.assertEqual(H.reservation_revenue_total(self.rows), 12000)  # 5000+3000+4000

    def test_monthly_rows_reconcile_to_total(self):
        month_defs = [("يناير", "Jan", "2026-01"), ("فبراير", "Feb", "2026-02")]
        cal = {"2026-01": 31, "2026-02": 28}
        rows = H.monthly_rows(self.rows, month_defs, cal)
        self.assertEqual(rows[0], ("يناير", "Jan", 31, 7, 8000))   # Jan: 4+3 nights, 8000
        self.assertEqual(rows[1], ("فبراير", "Feb", 28, 5, 4000))  # Feb: cancelled excluded
        self.assertEqual(sum(r[4] for r in rows), H.reservation_revenue_total(self.rows))

    def test_channel_mix_sums_to_one(self):
        mix = H.channel_mix(self.rows)
        self.assertAlmostEqual(sum(m[2] for m in mix), 1.0, places=2)
        self.assertEqual(mix[0][0], "Airbnb")  # highest revenue share

    def test_booking_behaviour(self):
        bb = H.booking_behaviour(self.rows)
        self.assertEqual(bb["reservations"], 3)
        self.assertEqual(bb["cancellation_pct"], round(1 / 4, 3))
        self.assertGreater(bb["alos"], 0)


class TestVATReconcile(unittest.TestCase):
    def test_detects_vat_inclusive(self):
        r = H.vat_reconcile(1150.0, 1000.0)
        self.assertEqual(r["basis"], "inclusive")
        self.assertTrue(r["consistent"])

    def test_detects_net(self):
        r = H.vat_reconcile(1000.0, 1000.0)
        self.assertEqual(r["basis"], "net")
        self.assertTrue(r["consistent"])

    def test_flags_ambiguous(self):
        r = H.vat_reconcile(1073.0, 1000.0)  # 1.073 — neither
        self.assertIsNone(r["basis"])
        self.assertFalse(r["consistent"])

    def test_no_payout_is_inconclusive(self):
        self.assertFalse(H.vat_reconcile(1000.0, 0)["consistent"])


class TestReadOnlyGuarantee(unittest.TestCase):
    def test_module_calls_no_write_verb(self):
        src = pathlib.Path(H.__file__).read_text(encoding="utf-8")
        H.HostawayReader.assert_read_only(src)  # must not raise

    def test_guard_would_catch_a_write_call(self):
        with self.assertRaises(RuntimeError):
            H.HostawayReader.assert_read_only("x = api_post('/expenses', body)")


if __name__ == "__main__":
    unittest.main()
