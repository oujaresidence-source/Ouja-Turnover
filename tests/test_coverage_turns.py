# -*- coding: utf-8 -*-
"""Turn deadlines, the shape of the week, and the corrected head count.

Every number here was worked out by hand before the assertion was written.

The point of this file: a day where all 19 turns are flexible and a day where 12 of them
must happen between one guest leaving and the next arriving are NOT the same day, and
until now they looked identical on the page. The deadline comes from the reservations,
not from cleaner behaviour — so it needs no new button and no change to how anyone works.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coverage_study import engine as E


def _res(lid, arrive, depart, checkin="15:00", checkout="11:00", status="new"):
    return {"listingMapId": lid, "arrivalDate": arrive, "departureDate": depart,
            "checkInTime": checkin, "checkOutTime": checkout, "status": status}


def _unit(lid, name=None, active=True):
    return {"lid": lid, "name": name or ("Ouja | U%d" % lid), "active": active,
            "team_id": "", "in_house": False, "has_location": True}


UNITS = [_unit(1), _unit(2), _unit(3)]
ALL_LIDS = {1, 2, 3, 9}          # 9 exists in Hostaway but is inactive


# ---------------------------------------------------------------- classification

class TestClassifyTurns(unittest.TestCase):
    def test_same_day_checkin_is_T0_with_the_checkin_time_as_deadline(self):
        rows = E.classify_turns([_res(1, "2026-07-01", "2026-07-10"),
                                 _res(1, "2026-07-10", "2026-07-14", checkin="16:00")],
                                UNITS, ALL_LIDS)["rows"]
        t = [r for r in rows if r["date"] == "2026-07-10"][0]
        self.assertEqual(t["kind"], "T0")
        self.assertTrue(t["deadline"].startswith("2026-07-10T16:00"), t["deadline"])

    def test_next_day_checkin_is_T1_due_end_of_that_day(self):
        rows = E.classify_turns([_res(2, "2026-07-01", "2026-07-10"),
                                 _res(2, "2026-07-11", "2026-07-15")],
                                UNITS, ALL_LIDS)["rows"]
        t = [r for r in rows if r["date"] == "2026-07-10"][0]
        self.assertEqual(t["kind"], "T1")
        self.assertTrue(t["deadline"].startswith("2026-07-11T23:59"), t["deadline"])

    def test_a_gap_is_T2_with_no_deadline(self):
        rows = E.classify_turns([_res(3, "2026-07-01", "2026-07-10"),
                                 _res(3, "2026-07-20", "2026-07-25")],
                                UNITS, ALL_LIDS)["rows"]
        t = [r for r in rows if r["date"] == "2026-07-10"][0]
        self.assertEqual(t["kind"], "T2")
        self.assertIsNone(t["deadline"])

    def test_no_following_booking_at_all_is_T2(self):
        rows = E.classify_turns([_res(1, "2026-07-01", "2026-07-10")], UNITS, ALL_LIDS)["rows"]
        self.assertEqual(rows[0]["kind"], "T2")

    def test_apartment_not_linked_to_hostaway_is_skipped_with_an_arabic_reason(self):
        out = E.classify_turns([_res(77, "2026-07-01", "2026-07-10")], UNITS, ALL_LIDS)
        self.assertEqual(out["rows"], [])
        self.assertEqual(len(out["skipped"]), 1)
        reason = out["skipped"][0]["reason"]
        self.assertTrue(reason.strip())
        self.assertIn("غير مرتبطة", reason)

    def test_inactive_apartment_is_skipped_with_its_own_distinct_reason(self):
        out = E.classify_turns([_res(9, "2026-07-01", "2026-07-10")], UNITS, ALL_LIDS)
        self.assertEqual(out["rows"], [])
        reason = out["skipped"][0]["reason"]
        self.assertIn("غير مفعّلة", reason)

    def test_the_two_skip_reasons_are_different(self):
        a = E.classify_turns([_res(77, "2026-07-01", "2026-07-10")], UNITS, ALL_LIDS)["skipped"][0]
        b = E.classify_turns([_res(9, "2026-07-01", "2026-07-10")], UNITS, ALL_LIDS)["skipped"][0]
        self.assertNotEqual(a["reason"], b["reason"])

    def test_cancelled_reservations_are_ignored(self):
        out = E.classify_turns([_res(1, "2026-07-01", "2026-07-10", status="cancelled")],
                               UNITS, ALL_LIDS)
        self.assertEqual(out["rows"], [])

    def test_a_cancelled_next_booking_does_not_create_a_false_T0(self):
        # The dangerous case: a same-day arrival that was cancelled must NOT make the
        # turn look like a hard deadline.
        rows = E.classify_turns([_res(1, "2026-07-01", "2026-07-10"),
                                 _res(1, "2026-07-10", "2026-07-12", status="cancelled")],
                                UNITS, ALL_LIDS)["rows"]
        self.assertEqual(rows[0]["kind"], "T2")

    def test_by_date_counts_each_kind(self):
        out = E.classify_turns([
            _res(1, "2026-06-28", "2026-07-10"), _res(1, "2026-07-10", "2026-07-12"),
            _res(2, "2026-06-28", "2026-07-10"), _res(2, "2026-07-11", "2026-07-13"),
            _res(3, "2026-06-28", "2026-07-10"),
        ], UNITS, ALL_LIDS)
        day = out["by_date"]["2026-07-10"]
        self.assertEqual((day["T0"], day["T1"], day["T2"]), (1, 1, 1))
        self.assertEqual(day["total"], 3)

    def test_window_filter_trims_by_checkout_date(self):
        out = E.classify_turns([_res(1, "2026-05-01", "2026-05-10"),
                                _res(1, "2026-07-01", "2026-07-10")],
                               UNITS, ALL_LIDS, since="2026-06-01")
        self.assertEqual([r["date"] for r in out["rows"]], ["2026-07-10"])

    def test_missing_checkin_time_falls_back_to_the_default_hour(self):
        rows = E.classify_turns([_res(1, "2026-07-01", "2026-07-10"),
                                 _res(1, "2026-07-10", "2026-07-12", checkin="")],
                                UNITS, ALL_LIDS)["rows"]
        self.assertTrue(rows[0]["deadline"].startswith("2026-07-10T15:00"))


# ---------------------------------------------------------------- week shape

class TestWeekShape(unittest.TestCase):
    def _turns(self):
        # 2026-07-05 is a Sunday. Two turns Sunday, one Monday, three Thursday.
        out = []
        for d, n in (("2026-07-05", 2), ("2026-07-06", 1), ("2026-07-09", 3)):
            for i in range(n):
                out.append({"lid": i + 1, "date": d, "kind": "T0" if i == 0 else "T2",
                            "deadline": None})
        return out

    def test_always_seven_days_even_when_a_weekday_is_empty(self):
        w = E.week_shape(self._turns())
        self.assertEqual(len(w["days"]), 7)
        totals = {d["weekday"]: d["total"] for d in w["days"]}
        self.assertEqual(sum(1 for v in totals.values() if v == 0), 4)

    def test_t0_is_broken_out_per_day(self):
        w = E.week_shape(self._turns())
        thu = [d for d in w["days"] if d["total"] == 3][0]
        self.assertEqual(thu["T0"], 1)

    def test_busiest_day_is_identified(self):
        w = E.week_shape(self._turns())
        self.assertEqual(w["busiest"]["total"], 3)

    def test_p70_sits_between_the_mean_and_the_busiest(self):
        # Guards an off-by-one that would silently invert the whole recommendation.
        turns = []
        for i, d in enumerate(("2026-07-05", "2026-07-06", "2026-07-07",
                               "2026-07-08", "2026-07-09")):
            for k in range(i + 1):
                turns.append({"lid": k + 1, "date": d, "kind": "T2", "deadline": None})
        w = E.week_shape(turns)
        self.assertLessEqual(w["mean_per_day"], w["p70_per_day"])
        self.assertLessEqual(w["p70_per_day"], w["busiest"]["total"])

    def test_empty_input_does_not_crash(self):
        w = E.week_shape([])
        self.assertEqual(len(w["days"]), 7)
        self.assertEqual(w["mean_per_day"], 0)


# ---------------------------------------------------------------- head count

class TestHeadcount(unittest.TestCase):
    def test_payroll_is_never_below_on_shift(self):
        for demand in (5, 18.7, 40):
            h = E.headcount(demand_per_day=demand, rate=4, current_people=4)
            self.assertGreaterEqual(h["payroll"], h["on_shift_avg"])

    def test_roster_and_absence_are_applied(self):
        # 18.7 / 4 = 4.675 -> 5 on shift. 5 * (30/26) * 1.08 = 6.23 -> 7 on payroll.
        h = E.headcount(demand_per_day=18.7, rate=4, current_people=4,
                        roster_factor=30 / 26.0, absence_factor=0.08)
        self.assertEqual(h["on_shift_avg"], 5)
        self.assertEqual(h["payroll"], 7)
        self.assertEqual(h["gap"], 3)

    def test_raising_absence_raises_payroll_and_leaves_on_shift_alone(self):
        a = E.headcount(demand_per_day=18.7, rate=4, current_people=4, absence_factor=0.08)
        b = E.headcount(demand_per_day=18.7, rate=4, current_people=4, absence_factor=0.30)
        self.assertEqual(a["on_shift_avg"], b["on_shift_avg"])
        self.assertGreater(b["payroll"], a["payroll"])

    def test_peak_day_needs_more_people_than_the_average_day(self):
        h = E.headcount(demand_per_day=18.7, rate=4, current_people=4, peak_per_day=30)
        self.assertGreater(h["on_shift_peak"], h["on_shift_avg"])
        self.assertEqual(h["on_shift_peak"], 8)          # ceil(30/4)

    def test_gap_never_goes_negative(self):
        h = E.headcount(demand_per_day=4, rate=4, current_people=20)
        self.assertEqual(h["gap"], 0)

    def test_no_rate_refuses_to_guess(self):
        h = E.headcount(demand_per_day=18.7, rate=None, current_people=4)
        self.assertIsNone(h["payroll"])
        self.assertTrue(h["reason"])


# ---------------------------------------------------------------- reconciliation

class TestReconcile(unittest.TestCase):
    def test_reports_the_gap_when_checkouts_exceed_logged_cleans(self):
        r = E.reconcile(logged_per_day=18.7, checkouts_per_day=22.1, units=[], events=[])
        self.assertAlmostEqual(r["unlogged_per_day"], 3.4, places=1)
        self.assertTrue(r["has_gap"])

    def test_reports_no_gap_when_they_match(self):
        r = E.reconcile(logged_per_day=20.0, checkouts_per_day=20.0, units=[], events=[])
        self.assertEqual(r["unlogged_per_day"], 0)
        self.assertFalse(r["has_gap"])

    def test_more_logged_than_checkouts_is_not_a_negative_gap(self):
        r = E.reconcile(logged_per_day=25.0, checkouts_per_day=20.0, units=[], events=[])
        self.assertEqual(r["unlogged_per_day"], 0)

    def test_crew_rows_compare_tagged_units_against_cleans_on_those_units(self):
        # OujaCT tagged to 2 units but 100 cleans logged on them -> implausible, flagged.
        units = [{"lid": 1, "team_id": "t1", "team_name": "OujaCT", "in_house": True},
                 {"lid": 2, "team_id": "t1", "team_name": "OujaCT", "in_house": True},
                 {"lid": 3, "team_id": "", "team_name": "", "in_house": False}]
        events = ([{"lid": 1, "date": "2026-07-0%d" % (i % 9 + 1)} for i in range(100)]
                  + [{"lid": 3, "date": "2026-07-01"}] * 40)
        r = E.reconcile(logged_per_day=0, checkouts_per_day=0, units=units, events=events)
        crew = {c["name"]: c for c in r["crews"]}
        self.assertEqual(crew["OujaCT"]["units"], 2)
        self.assertEqual(crew["OujaCT"]["cleans"], 100)
        self.assertTrue(crew["OujaCT"]["implausible"])

    def test_cleans_on_untagged_apartments_are_surfaced(self):
        units = [{"lid": 3, "team_id": "", "team_name": "", "in_house": False}]
        events = [{"lid": 3, "date": "2026-07-01"}] * 40
        r = E.reconcile(logged_per_day=0, checkouts_per_day=0, units=units, events=events)
        self.assertEqual(r["untagged_cleans"], 40)


# ---------------------------------------------------------------- cleaner capacity

def _u2(lid, in_house, team="t1", name=None):
    return {"lid": lid, "in_house": in_house, "team_id": team if in_house else "v1",
            "team_name": "OujaCT" if in_house else "StayClean",
            "name": name or ("U%d" % lid)}


class TestCleanerCapacity(unittest.TestCase):
    """The rate that matters for hiring is per CLEANER, and the log never records a
    cleaner — only the supervisor who pressed done (owner, 2026-08-02). So it is derived:
    checkouts on OUR OWN apartments, divided by the cleaners we actually employ."""

    def _rows(self):
        # 3 own apartments (1,2,3) + 2 outsourced (8,9). 10-day window.
        rows = []
        for d in range(1, 11):
            day = "2026-07-%02d" % d
            for lid in (1, 2, 3):
                rows.append({"lid": lid, "date": day, "kind": "T1"})
            for lid in (8, 9):
                rows.append({"lid": lid, "date": day, "kind": "T1"})
        return rows

    def _units(self):
        return [_u2(1, True), _u2(2, True), _u2(3, True), _u2(8, False), _u2(9, False)]

    def test_only_our_own_apartments_count(self):
        c = E.cleaner_capacity(self._rows(), self._units(), cleaners=3, window_days=10)
        self.assertEqual(c["own_units"], 3)
        self.assertEqual(c["own_checkouts"], 30)          # 3 apartments x 10 days
        self.assertEqual(c["own_per_day"], 3.0)

    def test_rate_is_per_cleaner_not_per_supervisor(self):
        c = E.cleaner_capacity(self._rows(), self._units(), cleaners=3, window_days=10)
        self.assertEqual(c["per_cleaner_typical"], 1.0)   # 3 a day across 3 cleaners

    def test_busiest_day_is_reported_as_the_capacity_floor(self):
        # A typical day understates capacity when the team is not busy. Their best
        # observed day is the honest lower bound on what they CAN do.
        rows = self._rows() + [{"lid": 1, "date": "2026-07-05", "kind": "T1"},
                               {"lid": 2, "date": "2026-07-05", "kind": "T1"},
                               {"lid": 3, "date": "2026-07-05", "kind": "T1"}]
        c = E.cleaner_capacity(rows, self._units(), cleaners=3, window_days=10)
        self.assertEqual(c["busiest_day"], 6)
        self.assertEqual(c["per_cleaner_best"], 2.0)

    def test_idle_team_is_flagged_rather_than_read_as_capacity(self):
        c = E.cleaner_capacity(self._rows(), self._units(), cleaners=3, window_days=10)
        self.assertTrue(c["likely_underused"])            # 1.0/day/cleaner is not busy

    def test_a_busy_team_is_not_flagged(self):
        rows = []
        for d in range(1, 11):
            for lid in (1, 2, 3):
                for k in range(4):
                    rows.append({"lid": lid, "date": "2026-07-%02d" % d, "kind": "T1"})
        c = E.cleaner_capacity(rows, self._units(), cleaners=3, window_days=10)
        self.assertFalse(c["likely_underused"])

    def test_no_cleaners_refuses_rather_than_dividing_by_zero(self):
        c = E.cleaner_capacity(self._rows(), self._units(), cleaners=0, window_days=10)
        self.assertIsNone(c["per_cleaner_typical"])
        self.assertTrue(c["reason"])

    def test_no_own_apartments_refuses(self):
        units = [_u2(8, False), _u2(9, False)]
        c = E.cleaner_capacity(self._rows(), units, cleaners=3, window_days=10)
        self.assertEqual(c["own_units"], 0)
        self.assertTrue(c["reason"])


# ---------------------------------------------------------------- cost

class TestCostCompare(unittest.TestCase):
    def test_saving_when_in_house_is_cheaper(self):
        # 20 cleans/day, 2 per cleaner per day -> 10 on shift.
        # 10 x (7/6) x 1.067 = 12.45 -> 13 on payroll.
        # 13 x 1300 + 1 x 6000 = 22,900/month.
        # Now: 3 x 1300 + 6000 + 36,000 to companies = 45,900. Saving = 23,000.
        c = E.cost_compare(demand_per_day=20, per_cleaner_day=2,
                           cleaner_cost=1300, supervisor_cost=6000, supervisors=1,
                           current_cleaners=3, vendor_monthly=36000,
                           roster_factor=7 / 6.0, absence_factor=0.067)
        self.assertEqual(c["cleaners_needed"], 13)
        self.assertEqual(c["inhouse_monthly"], 22900)
        self.assertEqual(c["current_monthly"], 45900)
        self.assertEqual(c["saving_monthly"], 23000)

    def test_loss_when_in_house_is_dearer(self):
        c = E.cost_compare(demand_per_day=20, per_cleaner_day=1,
                           cleaner_cost=1300, supervisor_cost=6000, supervisors=1,
                           current_cleaners=3, vendor_monthly=5000,
                           roster_factor=7 / 6.0, absence_factor=0.067)
        self.assertLess(c["saving_monthly"], 0)

    def test_cost_per_clean_is_reported(self):
        c = E.cost_compare(demand_per_day=20, per_cleaner_day=2,
                           cleaner_cost=1300, supervisor_cost=6000, supervisors=1,
                           current_cleaners=3, vendor_monthly=36000)
        self.assertGreater(c["inhouse_per_clean"], 0)
        self.assertEqual(c["vendor_per_clean"], 60.0)     # 36000 / (20*30)

    def test_no_rate_refuses_to_guess(self):
        c = E.cost_compare(demand_per_day=20, per_cleaner_day=None,
                           cleaner_cost=1300, supervisor_cost=6000)
        self.assertIsNone(c["saving_monthly"])
        self.assertTrue(c["reason"])

    def test_no_vendor_prices_still_reports_the_in_house_cost(self):
        c = E.cost_compare(demand_per_day=20, per_cleaner_day=2,
                           cleaner_cost=1300, supervisor_cost=6000, vendor_monthly=None)
        self.assertGreater(c["inhouse_monthly"], 0)
        self.assertIsNone(c["saving_monthly"])


class TestVendorMonthly(unittest.TestCase):
    """Priced PER APARTMENT PER MONTH — how the owner is actually billed, and it varies
    with the bedroom count."""

    def _units(self):
        return [{"lid": 1, "name": "A11", "team_id": "v1", "team_name": "StayClean",
                 "in_house": False, "bedrooms": 2},
                {"lid": 2, "name": "B10", "team_id": "v2", "team_name": "Servicu",
                 "in_house": False, "bedrooms": 3},
                {"lid": 3, "name": "OURS", "team_id": "t1", "team_name": "OujaCT",
                 "in_house": True, "bedrooms": 1},
                {"lid": 4, "name": "NOTEAM", "team_id": "", "team_name": "",
                 "in_house": False, "bedrooms": 1}]

    def test_sums_the_monthly_price_of_each_outsourced_apartment(self):
        out = E.vendor_monthly([], self._units(), {"1": 1200, "2": 1800}, window_days=30)
        self.assertEqual(out["total_monthly"], 3000)
        self.assertEqual(out["apartments"], 2)          # ours and the untagged one excluded
        self.assertEqual(out["missing_prices"], [])

    def test_our_own_and_untagged_apartments_are_not_billed(self):
        out = E.vendor_monthly([], self._units(), {"1": 1200, "2": 1800, "3": 999, "4": 999})
        self.assertEqual(out["total_monthly"], 3000)

    def test_an_apartment_with_no_price_is_counted_missing_not_zeroed(self):
        out = E.vendor_monthly([], self._units(), {"1": 1200}, window_days=30)
        self.assertEqual(out["total_monthly"], 1200)
        self.assertIn("B10", out["missing_prices"])
        self.assertEqual(out["missing_count"], 1)
        self.assertEqual(out["priced_count"], 1)

    def test_cost_per_clean_is_derived_from_that_apartment_turnover(self):
        # 1,200 a month over 6 checkouts a month = 200 per clean.
        rows = [{"lid": 1, "date": "2026-07-%02d" % (d + 1)} for d in range(6)]
        out = E.vendor_monthly(rows, self._units(), {"1": 1200}, window_days=30)
        row = [r for r in out["rows"] if r["lid"] == 1][0]
        self.assertEqual(row["cleans_per_month"], 6.0)
        self.assertEqual(row["per_clean"], 200.0)

    def test_bedrooms_are_carried_through_for_the_price_list(self):
        out = E.vendor_monthly([], self._units(), {})
        self.assertEqual({r["name"]: r["bedrooms"] for r in out["rows"]},
                         {"A11": 2, "B10": 3})

    def test_integer_and_string_apartment_keys_both_work(self):
        a = E.vendor_monthly([], self._units(), {"1": 1200})["total_monthly"]
        b = E.vendor_monthly([], self._units(), {1: 1200})["total_monthly"]
        self.assertEqual(a, b)

    def test_grouped_by_company_for_scanning(self):
        out = E.vendor_monthly([], self._units(), {"1": 1200, "2": 1800})
        self.assertEqual({t["name"]: t["monthly"] for t in out["by_team"]},
                         {"StayClean": 1200, "Servicu": 1800})


if __name__ == "__main__":
    unittest.main()
