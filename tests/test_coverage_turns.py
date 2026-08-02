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


if __name__ == "__main__":
    unittest.main()
