# -*- coding: utf-8 -*-
"""
S8 — the only file that touches Hostaway. Synthetic reservations throughout:
the point of splitting I/O from arithmetic is that both halves stay checkable.

Run: python3 -m unittest tests.test_monthly_data
"""

import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monthly import data                          # noqa: E402


def res(lid, ci, co, total, status="new"):
    return {"id": "%s-%s" % (lid, ci), "listingMapId": lid, "arrivalDate": ci,
            "departureDate": co, "totalPrice": total, "status": status}


class NightCountingTest(unittest.TestCase):
    def test_the_departure_night_is_not_counted(self):
        """The guest does not sleep the night they leave. Counting it inflates
        occupancy on every stay that straddles a month end."""
        r = res(1, "2026-10-01", "2026-10-04", 1500)
        n = data.nights_in_month(r, datetime.date(2026, 10, 1), datetime.date(2026, 10, 31))
        self.assertEqual(n, 3)

    def test_a_stay_straddling_a_month_end_splits_correctly(self):
        r = res(1, "2026-09-28", "2026-10-03", 2500)
        sep = data.nights_in_month(r, datetime.date(2026, 9, 1), datetime.date(2026, 9, 30))
        oct_ = data.nights_in_month(r, datetime.date(2026, 10, 1), datetime.date(2026, 10, 31))
        self.assertEqual(sep, 3)
        self.assertEqual(oct_, 2)
        self.assertEqual(sep + oct_, 5)

    def test_a_stay_entirely_outside_the_month_counts_zero(self):
        r = res(1, "2026-08-01", "2026-08-05", 2000)
        self.assertEqual(data.nights_in_month(
            r, datetime.date(2026, 10, 1), datetime.date(2026, 10, 31)), 0)

    def test_a_zero_night_booking_is_not_a_night(self):
        self.assertEqual(data.nights_in_month(
            res(1, "2026-10-05", "2026-10-05", 500),
            datetime.date(2026, 10, 1), datetime.date(2026, 10, 31)), 0)


class ConfirmedOnlyTest(unittest.TestCase):
    def test_cancelled_and_declined_are_not_revenue(self):
        for st in ("cancelled", "canceled", "declined", "expired", "denied"):
            self.assertFalse(data.is_confirmed(res(1, "2026-10-01", "2026-10-05", 2000, st)))

    def test_new_and_modified_are_confirmed(self):
        for st in ("new", "modified", "NEW", " Modified "):
            self.assertTrue(data.is_confirmed(res(1, "2026-10-01", "2026-10-05", 2000, st)))

    def test_an_inquiry_is_not_confirmed(self):
        self.assertFalse(data.is_confirmed(res(1, "2026-10-01", "2026-10-05", 2000, "inquiry")))

    def test_cancelled_bookings_never_reach_the_observations(self):
        rows = data.unit_month_rows(
            [res(1, "2026-10-01", "2026-10-11", 6200),
             res(1, "2026-10-12", "2026-10-22", 9999, "cancelled")],
            10, "2026-08")
        self.assertEqual(rows[1][0]["nights"], 10)
        self.assertAlmostEqual(rows[1][0]["adr"], 620)


class ObservationTest(unittest.TestCase):
    def test_only_the_matching_calendar_month_is_collected(self):
        rows = data.unit_month_rows(
            [res(1, "2026-10-01", "2026-10-11", 6200),
             res(1, "2026-07-01", "2026-07-11", 3000)],
            10, "2026-08")
        self.assertEqual([o["month"] for o in rows[1]], ["2026-10"])

    def test_octobers_across_years_all_count(self):
        rows = data.unit_month_rows(
            [res(1, "2026-10-01", "2026-10-11", 6200),
             res(1, "2025-10-01", "2025-10-11", 5200),
             res(1, "2024-10-01", "2024-10-11", 4200)],
            10, "2026-08")
        self.assertEqual(len(rows[1]), 3)

    def test_age_in_months_drives_the_freshness_weight(self):
        rows = data.unit_month_rows([res(1, "2025-10-01", "2025-10-11", 5200)],
                                    10, "2026-08")
        self.assertEqual(rows[1][0]["months_old"], 10)

    def test_occupancy_is_nights_over_the_days_in_that_month(self):
        rows = data.unit_month_rows([res(1, "2026-10-01", "2026-10-16", 9300)],
                                    10, "2026-08")
        self.assertAlmostEqual(rows[1][0]["occ"], 15 / 31.0)

    def test_adr_is_revenue_over_nights_not_over_days(self):
        rows = data.unit_month_rows([res(1, "2026-10-01", "2026-10-11", 6200)],
                                    10, "2026-08")
        self.assertAlmostEqual(rows[1][0]["adr"], 620.0)

    def test_two_bookings_in_one_month_merge_into_one_observation(self):
        rows = data.unit_month_rows(
            [res(1, "2026-10-01", "2026-10-11", 6200),
             res(1, "2026-10-15", "2026-10-20", 3000)],
            10, "2026-08")
        self.assertEqual(len(rows[1]), 1)
        self.assertEqual(rows[1][0]["nights"], 15)

    def test_occupancy_can_never_exceed_one(self):
        rows = data.unit_month_rows(
            [res(1, "2026-10-01", "2026-11-01", 20000),
             res(1, "2026-10-05", "2026-10-25", 12000)],
            10, "2026-08")
        self.assertLessEqual(rows[1][0]["occ"], 1.0)


class PoolTest(unittest.TestCase):
    def test_pools_are_built_from_the_same_rows(self):
        unit_rows = {1: [{"adr": 600, "occ": .8, "nights": 25, "months_old": 1}],
                     2: [{"adr": 500, "occ": .7, "nights": 22, "months_old": 1}]}
        meta = {1: {"district": "الملقا", "bedrooms": 3},
                2: {"district": "الملقا", "bedrooms": 3}}
        d, b = data.pool_rows(unit_rows, meta,
                              lambda m: m.get("district"), lambda m: m.get("bedrooms"))
        self.assertEqual(len(d[("الملقا", 3)]), 2)
        self.assertEqual(len(b[3]), 2)

    def test_a_unit_with_no_district_still_joins_the_bedroom_pool(self):
        unit_rows = {1: [{"adr": 600, "occ": .8, "nights": 25, "months_old": 1}]}
        meta = {1: {"bedrooms": 2}}
        d, b = data.pool_rows(unit_rows, meta,
                              lambda m: m.get("district"), lambda m: m.get("bedrooms"))
        self.assertEqual(d, {})
        self.assertEqual(len(b[2]), 1)


class MonthArithmeticTest(unittest.TestCase):
    def test_months_between_counts_forward(self):
        self.assertEqual(data.months_between("2025-10", "2026-08"), 10)
        self.assertEqual(data.months_between("2026-08", "2026-08"), 0)

    def test_month_bounds_handles_february_in_a_leap_year(self):
        first, last = data.month_bounds("2028-02")
        self.assertEqual(last.day, 29)


class TurnoverCostTest(unittest.TestCase):
    def test_it_names_its_source_so_a_fallback_is_never_read_as_real(self):
        val, src = data.turnover_cost_sar(140.0)
        self.assertGreater(val, 0)
        self.assertIn("coverage_study", src)

    def test_the_fallback_is_labelled_as_a_fallback(self):
        val, src = data.turnover_cost_sar(140.0)
        if val == 140.0:
            self.assertIn("default", src)


class ReadOnlyTest(unittest.TestCase):
    def test_this_module_contains_no_write_verb(self):
        import inspect
        src = inspect.getsource(data)
        for verb in ("api_post", "api_put", "api_delete"):
            self.assertNotIn(verb + "(", src)

    def test_it_never_reaches_for_the_truncating_cache(self):
        """CLAUDE.md trap #4: the cache silently drops the newest months."""
        import ast, inspect
        names = set()
        for node in ast.walk(ast.parse(inspect.getsource(data))):
            if isinstance(node, ast.Attribute):
                names.add(node.attr)
            elif isinstance(node, ast.Name):
                names.add(node.id)
        self.assertNotIn("get_reservations_cached", names)


if __name__ == "__main__":
    unittest.main()


class PartialMonthTest(unittest.TestCase):
    """A month still running has unsold nights that may yet sell, so its
    occupancy reads low. Including it biases the forecast DOWN, which widens the
    price band and makes monthly look more viable than it is."""

    def test_the_current_month_is_flagged_partial(self):
        rows = data.unit_month_rows([res(1, "2026-08-01", "2026-08-11", 6200)],
                                    8, "2026-08")
        self.assertTrue(rows[1][0]["partial"])

    def test_a_completed_month_is_not_flagged(self):
        rows = data.unit_month_rows([res(1, "2025-08-01", "2025-08-11", 6200)],
                                    8, "2026-08")
        self.assertFalse(rows[1][0]["partial"])

    def test_the_flag_is_present_on_every_observation(self):
        rows = data.unit_month_rows(
            [res(1, "2026-08-01", "2026-08-11", 6200),
             res(1, "2025-08-01", "2025-08-11", 5200)], 8, "2026-08")
        for o in rows[1]:
            self.assertIn("partial", o)
