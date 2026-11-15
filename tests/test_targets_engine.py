# -*- coding: utf-8 -*-
"""Rules of targets.engine. Run: python3 -m unittest discover -s tests -p 'test_targets*.py'"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from targets import engine as E   # noqa: E402


def res(a, b, total, status="new"):
    return {"arrival": a, "departure": b, "total": total, "status": status}


class Occupancy(unittest.TestCase):
    def test_stay_split_across_months(self):
        self.assertEqual(E.nights_in_month("2026-10-29", "2026-11-03", "2026-10"), 3)
        self.assertEqual(E.nights_in_month("2026-10-29", "2026-11-03", "2026-11"), 2)

    def test_night_below_floor_does_not_count(self):
        u = E.unit_month([res("2026-11-01", "2026-11-11", 2000)], 0, "2026-11", floor=300, typical=500)
        self.assertEqual(u["nights"], 10)
        self.assertEqual(u["weighted"], 0)
        self.assertEqual(u["below_floor"], 10)

    def test_cheap_night_counts_half_and_full_price_counts_full(self):
        u = E.unit_month([res("2026-11-01", "2026-11-11", 4000), res("2026-11-11", "2026-11-21", 6000)],
                         0, "2026-11", floor=300, typical=500)
        self.assertEqual(u["weighted"], 10 * 0.5 + 10 * 1.0)
        self.assertAlmostEqual(u["occupancy"], 15 / 30)

    def test_blocked_nights_leave_the_denominator(self):
        u = E.unit_month([res("2026-11-01", "2026-11-11", 6000)], 10, "2026-11")
        self.assertEqual(u["available"], 20)
        self.assertAlmostEqual(u["occupancy"], 0.5)

    def test_unit_open_too_little_is_left_out_not_zero(self):
        self.assertIsNone(E.unit_month([], 20, "2026-11"))

    def test_cancelled_booking_ignored(self):
        u = E.unit_month([res("2026-11-01", "2026-11-11", 6000, "cancelled")], 0, "2026-11")
        self.assertEqual(u["nights"], 0)


class Targets(unittest.TestCase):
    def test_baseline_blend_and_fallbacks(self):
        self.assertAlmostEqual(E.baseline([0.6, 0.6], [0.8]), 0.7)
        self.assertAlmostEqual(E.baseline([], [0.5, None, 0.7]), 0.6)
        self.assertIsNone(E.baseline([], [None]))

    def test_tiers_inside_band_and_monotone(self):
        t = E.tiers(0.40)
        self.assertAlmostEqual(t["bronze"], 0.60)           # floor lifts bronze
        self.assertTrue(t["bronze"] <= t["silver"] <= t["gold"])
        t = E.tiers(0.90)
        self.assertEqual(t["gold"], 0.92)                   # ceiling
        self.assertTrue(t["bronze"] <= t["silver"] <= t["gold"])

    def test_tier_reached(self):
        t = E.tiers(0.60)
        self.assertIsNone(E.tier_reached(0.64, t))
        self.assertEqual(E.tier_reached(0.65, t), "bronze")
        self.assertEqual(E.tier_reached(0.80, t), "gold")

    def test_gate_has_no_cliff(self):
        self.assertEqual(E.gate_factor(3, 10), 0.0)
        self.assertEqual(E.gate_factor(4, 10), 0.0)
        self.assertAlmostEqual(E.gate_factor(5, 10), 0.5)
        self.assertEqual(E.gate_factor(6, 10), 1.0)
        self.assertEqual(E.gate_factor(0, 0), 0.0)

    def test_share_moves_between_base_and_max_only(self):
        self.assertAlmostEqual(E.employee_share(0, 10), E.SHARE_BASE)
        self.assertAlmostEqual(E.employee_share(10, 10), E.SHARE_MAX)


class ClientBook(unittest.TestCase):
    def test_phone_formats_are_one_guest(self):
        self.assertEqual(E.phone_key("0505783355"), E.phone_key("+966 50 578 3355"))
        self.assertEqual(E.phone_key("123"), "")

    def test_holdout_is_stable_and_near_twenty_percent(self):
        phones = ["05%08d" % i for i in range(5000)]
        inside = [p for p in phones if E.in_holdout(p, "2027-Q1")]
        self.assertTrue(0.17 < len(inside) / 5000 < 0.23)
        self.assertEqual(inside, [p for p in phones if E.in_holdout(p, "2027-Q1")])

    def test_callable_rules(self):
        g = {"phone": "0500000001", "last_checkout": "2026-09-01", "consent": True}
        self.assertEqual(E.callable_guest(g, "2026-11-01"), (True, ""))
        self.assertEqual(E.callable_guest(dict(g, consent=False), "2026-11-01")[1], "no_consent")
        self.assertEqual(E.callable_guest(dict(g, do_not_contact=True), "2026-11-01")[1], "do_not_contact")
        self.assertEqual(E.callable_guest(dict(g, last_checkout="2026-10-20"), "2026-11-01")[1], "too_recent")
        self.assertEqual(E.callable_guest(dict(g, has_future_booking=True), "2026-11-01")[1], "already_booked")
        self.assertEqual(E.callable_guest(dict(g, last_contact="2026-10-10"), "2026-11-01")[1], "cooldown")

    def test_first_logger_wins_and_window_is_enforced(self):
        contacts = [{"id": 2, "employee": "B", "phone": "0500000001", "at": "2026-11-03"},
                    {"id": 1, "employee": "A", "phone": "0500000001", "at": "2026-11-01"}]
        bookings = [{"id": "x", "phone": "+966500000001", "created": "2026-11-05"},
                    {"id": "late", "phone": "0500000001", "created": "2026-11-30"},
                    {"id": "before", "phone": "0500000001", "created": "2026-10-30"}]
        got = E.attribute(contacts, bookings)
        self.assertEqual(got["x"]["employee"], "A")
        self.assertNotIn("late", got)
        self.assertNotIn("before", got)


class Money(unittest.TestCase):
    B = {"arrival": "2026-11-01", "departure": "2026-11-05", "total": 2000, "status": "new"}   # 500/night

    def test_commission_is_share_of_fee(self):
        self.assertAlmostEqual(E.booking_commission(self.B, 0.30, 0.20), 4 * 500 * 0.20 * 0.30)

    def test_below_floor_pays_nothing(self):
        self.assertEqual(E.booking_commission(self.B, 0.30, 0.20, floor=600), 0.0)

    def test_above_ceiling_pays_double_share_on_the_excess(self):
        got = E.booking_commission(self.B, 0.30, 0.20, ceiling=400)
        self.assertAlmostEqual(got, 4 * 0.20 * (400 * 0.30 + 100 * 0.60))

    def test_commission_never_exceeds_ouja_fee(self):
        got = E.booking_commission(self.B, 0.40, 0.20, ceiling=1)
        self.assertLessEqual(got, 4 * 500 * 0.20)

    def test_cancelled_pays_nothing(self):
        self.assertEqual(E.booking_commission(dict(self.B, status="cancelled"), 0.3, 0.2), 0.0)

    def test_no_uplift_means_empty_pool(self):
        p = E.uplift_pool(contacted=1000, contacted_bookings=14, holdout=2000, holdout_bookings=28, avg_fee=200)
        self.assertEqual(p["pool"], 0.0)

    def test_pool_is_half_of_measured_uplift(self):
        p = E.uplift_pool(contacted=1000, contacted_bookings=54, holdout=2000, holdout_bookings=28, avg_fee=200)
        self.assertAlmostEqual(p["incremental_bookings"], 40)
        self.assertAlmostEqual(p["pool"], 0.5 * 40 * 200)

    def test_thin_holdout_uses_the_higher_rate(self):
        p = E.uplift_pool(1000, 54, 100, 0, 200, fallback_rate=0.014)
        self.assertAlmostEqual(p["natural_rate"], 0.014)
        p = E.uplift_pool(1000, 54, 100, 5, 200, fallback_rate=0.014)
        self.assertAlmostEqual(p["natural_rate"], 0.05)

    def test_thin_holdout_without_history_pays_nothing(self):
        self.assertEqual(E.uplift_pool(1000, 54, 100, 1, 200)["pool"], 0.0)

    def test_no_evidence_assumes_no_uplift(self):
        self.assertEqual(E.uplift_pool(1000, 54, 0, 0, 200)["pool"], 0.0)

    def test_settle_never_pays_more_than_pool(self):
        s = E.settle({"A": 600, "B": 400}, pool=575, manager={"name": "M", "all_passed_gate": False})
        self.assertAlmostEqual(s["total_paid"], 575, places=1)
        self.assertAlmostEqual(s["employees"]["A"] / s["employees"]["B"], 1.5, places=2)
        self.assertAlmostEqual(s["manager"]["amount"] / s["total_paid"], 0.15 / 1.15, places=2)

    def test_settle_under_pool_pays_in_full(self):
        s = E.settle({"A": 100}, pool=1000, manager={"name": "M", "all_passed_gate": True})
        self.assertEqual(s["employees"]["A"], 100)
        self.assertEqual(s["manager"]["amount"], 20)

    def test_ops_multiplier_cannot_break_the_cap(self):
        s = E.settle({"A": 100}, pool=100, ops_multipliers={"A": 1.5})
        self.assertLessEqual(s["total_paid"], 100)

    def test_zero_pool_pays_zero(self):
        s = E.settle({"A": 500}, pool=0, manager={"name": "M", "all_passed_gate": True})
        self.assertEqual(s["total_paid"], 0)


if __name__ == "__main__":
    unittest.main()
