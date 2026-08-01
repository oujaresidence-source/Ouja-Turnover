# -*- coding: utf-8 -*-
"""Locks the cleaning-coverage maths with hand-checkable synthetic data.

Every number in here was worked out by hand first. If a test fails, the engine
changed its mind about something the owner is going to make a hiring decision on.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coverage_study import engine as E


# ---------------------------------------------------------------- geometry

class TestHaversine(unittest.TestCase):
    def test_zero_distance(self):
        self.assertEqual(E.haversine_m((24.75, 46.70), (24.75, 46.70)), 0)

    def test_known_short_hop(self):
        # 0.001 degrees of latitude is ~111.2 m anywhere on earth.
        d = E.haversine_m((24.750, 46.700), (24.751, 46.700))
        self.assertTrue(110 <= d <= 113, d)

    def test_symmetric(self):
        a, b = (24.7583, 46.7096), (24.8289, 46.7362)
        self.assertEqual(E.haversine_m(a, b), E.haversine_m(b, a))

    def test_missing_coords_returns_none(self):
        self.assertIsNone(E.haversine_m((None, 46.7), (24.7, 46.7)))
        self.assertIsNone(E.haversine_m(None, (24.7, 46.7)))


# ---------------------------------------------------------------- clustering

def _u(lid, lat=None, lng=None, **kw):
    d = {"lid": lid, "name": "Ouja | U%d" % lid, "lat": lat, "lng": lng,
         "team_id": kw.get("team_id", ""), "in_house": kw.get("in_house", False),
         "active": kw.get("active", True), "district": kw.get("district", "")}
    d.update(kw)
    return d


class TestClustering(unittest.TestCase):
    def test_same_building_is_one_cluster(self):
        # Eight units on one pin — the real Al-Nuzha case.
        units = [_u(i, 24.7583056, 46.7096111) for i in range(1, 9)]
        cl = E.cluster_units(units, radius_m=120)
        self.assertEqual(len(cl), 1)
        self.assertEqual(cl[0]["size"], 8)
        self.assertEqual(cl[0]["lids"], list(range(1, 9)))

    def test_far_apart_units_stay_separate(self):
        units = [_u(1, 24.7583, 46.7096), _u(2, 24.8289, 46.7362)]
        cl = E.cluster_units(units, radius_m=120)
        self.assertEqual(len(cl), 2)

    def test_radius_boundary(self):
        # ~111 m apart: inside a 120 m radius, outside a 100 m one.
        units = [_u(1, 24.750, 46.700), _u(2, 24.751, 46.700)]
        self.assertEqual(len(E.cluster_units(units, radius_m=120)), 1)
        self.assertEqual(len(E.cluster_units(units, radius_m=100)), 2)

    def test_units_without_coords_are_singletons_and_flagged(self):
        units = [_u(1, 24.75, 46.70), _u(2), _u(3)]
        cl = E.cluster_units(units, radius_m=120)
        self.assertEqual(len(cl), 3)
        located = [c for c in cl if c["has_location"]]
        self.assertEqual(len(located), 1)

    def test_deterministic_regardless_of_input_order(self):
        pts = [(1, 24.750, 46.700), (2, 24.7501, 46.7000), (3, 24.900, 46.900)]
        a = E.cluster_units([_u(*p) for p in pts], radius_m=120)
        b = E.cluster_units([_u(*p) for p in reversed(pts)], radius_m=120)
        self.assertEqual([c["lids"] for c in a], [c["lids"] for c in b])

    def test_cluster_carries_a_readable_label(self):
        units = [_u(1, 24.75, 46.70, district="الملقا"), _u(2, 24.75, 46.70, district="الملقا")]
        cl = E.cluster_units(units, radius_m=120)
        self.assertEqual(cl[0]["district"], "الملقا")


# ---------------------------------------------------------------- photo timing

class TestPhotoTiming(unittest.TestCase):
    """Must agree with bot.py's _cleanproof_timing — same rules, same fallbacks."""

    def test_first_photo_to_submit(self):
        rep = {"report_id": "r1", "created_at": "2026-07-20T10:00:00",
               "submitted_at": "2026-07-20T10:25:00", "updated_at": "2026-07-20T10:30:00"}
        photos = [{"report_id": "r1", "uploaded_at": "2026-07-20T10:05:00", "status": "uploaded"},
                  {"report_id": "r1", "uploaded_at": "2026-07-20T10:20:00", "status": "uploaded"}]
        started, ended, mins, n = E.photo_timing(rep, photos)
        self.assertEqual(mins, 20)          # 10:05 -> 10:25
        self.assertEqual(n, 2)

    def test_falls_back_to_last_photo_when_no_submit(self):
        rep = {"report_id": "r1", "created_at": "2026-07-20T10:00:00", "updated_at": "2026-07-20T11:00:00"}
        photos = [{"report_id": "r1", "uploaded_at": "2026-07-20T10:05:00", "status": "uploaded"},
                  {"report_id": "r1", "uploaded_at": "2026-07-20T10:35:00", "status": "uploaded"}]
        _, _, mins, _ = E.photo_timing(rep, photos)
        self.assertEqual(mins, 30)

    def test_removed_photos_ignored(self):
        rep = {"report_id": "r1", "created_at": "2026-07-20T10:00:00",
               "submitted_at": "2026-07-20T10:30:00"}
        photos = [{"report_id": "r1", "uploaded_at": "2026-07-20T09:00:00", "status": "removed"},
                  {"report_id": "r1", "uploaded_at": "2026-07-20T10:10:00", "status": "uploaded"}]
        _, _, mins, n = E.photo_timing(rep, photos)
        self.assertEqual(mins, 20)
        self.assertEqual(n, 1)

    def test_no_photos_gives_none_not_zero(self):
        rep = {"report_id": "r1", "created_at": "2026-07-20T10:00:00"}
        _, _, mins, n = E.photo_timing(rep, [])
        self.assertEqual(n, 0)
        self.assertIsNone(mins)

    def test_negative_duration_rejected(self):
        rep = {"report_id": "r1", "created_at": "2026-07-20T10:00:00",
               "submitted_at": "2026-07-20T09:00:00"}
        photos = [{"report_id": "r1", "uploaded_at": "2026-07-20T10:05:00", "status": "uploaded"}]
        _, _, mins, _ = E.photo_timing(rep, photos)
        self.assertIsNone(mins)

    def test_timezone_aware_and_naive_stamps_both_parse(self):
        rep = {"report_id": "r1", "created_at": "2026-07-20T10:00:00+03:00",
               "submitted_at": "2026-07-20T10:30:00+03:00"}
        photos = [{"report_id": "r1", "uploaded_at": "2026-07-20T10:00:00+03:00", "status": "uploaded"}]
        _, _, mins, _ = E.photo_timing(rep, photos)
        self.assertEqual(mins, 30)


# ---------------------------------------------------------------- done events

class TestDoneEvents(unittest.TestCase):
    def test_status_log_is_the_spine(self):
        log = [{"lid": 1, "date": "2026-07-20", "action": "done", "ts": "2026-07-20T11:00:00", "by": "noura"},
               {"lid": 2, "date": "2026-07-20", "action": "other", "ts": "2026-07-20T12:00:00", "by": "noura"}]
        ev = E.done_events(log, [])
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["lid"], 1)

    def test_reports_fill_gaps_the_trimmed_log_lost(self):
        # oujact_status.json keeps only the last 5000 events; cleaning_reports is never
        # pruned, so old days must still be recoverable from reports alone.
        reports = [{"report_id": "r9", "apartment_id": 7, "date": "2026-06-02",
                    "submitted_at": "2026-06-02T13:00:00", "cleaner_name": "nasser"}]
        ev = E.done_events([], reports)
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["lid"], 7)
        self.assertEqual(ev[0]["source"], "report")

    def test_no_double_count_when_both_sources_have_it(self):
        log = [{"lid": 7, "date": "2026-06-02", "action": "done",
                "ts": "2026-06-02T13:00:00", "by": "nasser"}]
        reports = [{"report_id": "r9", "apartment_id": 7, "date": "2026-06-02",
                    "submitted_at": "2026-06-02T13:00:05", "cleaner_name": "nasser"}]
        ev = E.done_events(log, reports)
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["source"], "status")   # the log wins

    def test_sorted_by_time(self):
        log = [{"lid": 2, "date": "2026-07-20", "action": "done", "ts": "2026-07-20T14:00:00", "by": "a"},
               {"lid": 1, "date": "2026-07-20", "action": "done", "ts": "2026-07-20T09:00:00", "by": "a"}]
        ev = E.done_events(log, [])
        self.assertEqual([e["lid"] for e in ev], [1, 2])

    def test_unparseable_timestamps_dropped_not_crashed(self):
        log = [{"lid": 1, "date": "2026-07-20", "action": "done", "ts": "not-a-date", "by": "a"},
               {"lid": 2, "date": "2026-07-20", "action": "done", "ts": "2026-07-20T09:00:00", "by": "a"}]
        ev = E.done_events(log, [])
        self.assertEqual([e["lid"] for e in ev], [2])


# ---------------------------------------------------------------- work days

class TestWorkDays(unittest.TestCase):
    def _day(self):
        # One person, four apartments: 09:00, 10:00, 11:30, 12:15
        # gaps = 60, 90, 45 minutes.  span = 09:00 -> 12:15 = 195 min.
        return [{"lid": 1, "date": "2026-07-20", "ts": "2026-07-20T09:00:00", "by": "noura", "source": "status"},
                {"lid": 2, "date": "2026-07-20", "ts": "2026-07-20T10:00:00", "by": "noura", "source": "status"},
                {"lid": 3, "date": "2026-07-20", "ts": "2026-07-20T11:30:00", "by": "noura", "source": "status"},
                {"lid": 4, "date": "2026-07-20", "ts": "2026-07-20T12:15:00", "by": "noura", "source": "status"}]

    def test_counts_and_span(self):
        wd = E.work_days(self._day())
        self.assertEqual(len(wd), 1)
        d = wd[0]
        self.assertEqual(d["count"], 4)
        self.assertEqual(d["span_min"], 195)
        self.assertEqual(d["person"], "noura")

    def test_gaps_are_between_consecutive_finishes(self):
        d = E.work_days(self._day())[0]
        self.assertEqual(d["gaps"], [60, 90, 45])

    def test_one_apartment_day_has_no_gaps(self):
        ev = [{"lid": 1, "date": "2026-07-20", "ts": "2026-07-20T09:00:00", "by": "n", "source": "status"}]
        d = E.work_days(ev)[0]
        self.assertEqual(d["gaps"], [])
        self.assertEqual(d["span_min"], 0)

    def test_two_people_same_day_are_two_rows(self):
        ev = self._day() + [{"lid": 9, "date": "2026-07-20", "ts": "2026-07-20T09:30:00",
                             "by": "nasser", "source": "status"}]
        wd = E.work_days(ev)
        self.assertEqual(len(wd), 2)
        self.assertEqual({r["person"] for r in wd}, {"noura", "nasser"})

    def test_same_person_across_days_are_separate_rows(self):
        ev = self._day() + [{"lid": 1, "date": "2026-07-21", "ts": "2026-07-21T09:00:00",
                             "by": "noura", "source": "status"}]
        self.assertEqual(len(E.work_days(ev)), 2)

    def test_unknown_person_bucketed_not_dropped(self):
        ev = [{"lid": 1, "date": "2026-07-20", "ts": "2026-07-20T09:00:00", "by": "", "source": "status"}]
        wd = E.work_days(ev)
        self.assertEqual(len(wd), 1)
        self.assertEqual(wd[0]["person"], E.UNKNOWN_PERSON)


# ---------------------------------------------------------------- cycle stats

class TestCycleStats(unittest.TestCase):
    def test_median_of_pooled_gaps(self):
        wd = [{"gaps": [30, 40, 50]}, {"gaps": [60, 70]}]
        s = E.cycle_stats(wd)
        self.assertEqual(s["median_min"], 50)        # 30,40,50,60,70
        self.assertEqual(s["n"], 5)

    def test_even_count_median_averages_the_middle_two(self):
        s = E.cycle_stats([{"gaps": [10, 20, 30, 40]}])
        self.assertEqual(s["median_min"], 25)

    def test_long_breaks_excluded_and_counted(self):
        # A 5-hour gap is lunch or a second shift, not one apartment's cycle.
        s = E.cycle_stats([{"gaps": [30, 40, 300]}], max_gap_min=180)
        self.assertEqual(s["n"], 2)
        self.assertEqual(s["excluded"], 1)
        self.assertEqual(s["median_min"], 35)

    def test_exclusion_is_reported_never_silent(self):
        s = E.cycle_stats([{"gaps": [30, 999]}], max_gap_min=180)
        self.assertIn("excluded", s)
        self.assertEqual(s["excluded"], 1)

    def test_no_gaps_gives_none_not_zero(self):
        s = E.cycle_stats([{"gaps": []}])
        self.assertIsNone(s["median_min"])
        self.assertEqual(s["n"], 0)

    def test_quartiles(self):
        s = E.cycle_stats([{"gaps": [10, 20, 30, 40, 50, 60, 70, 80]}])
        self.assertEqual(s["p25_min"], 25)
        self.assertEqual(s["p75_min"], 65)


# ---------------------------------------------------------------- capacity

class TestCapacityModel(unittest.TestCase):
    def test_straightforward_headcount(self):
        # 45 min/apartment, 8h day = 480 min -> 10.6 -> 10 apartments per person.
        # 40 apartments/day of demand -> 4 people.
        m = E.capacity_model(cycle_median_min=45, workday_min=480, demand_per_day=40,
                             current_people=2)
        self.assertEqual(m["units_per_person_day"], 10)
        self.assertEqual(m["people_needed"], 4)
        self.assertEqual(m["hire"], 2)

    def test_rounds_headcount_up_never_down(self):
        # 31 apartments / 10 per person = 3.1 -> you cannot hire 3.1 people.
        m = E.capacity_model(cycle_median_min=45, workday_min=480, demand_per_day=31,
                             current_people=0)
        self.assertEqual(m["people_needed"], 4)

    def test_already_enough_people_means_no_hiring(self):
        m = E.capacity_model(cycle_median_min=45, workday_min=480, demand_per_day=10,
                             current_people=3)
        self.assertEqual(m["people_needed"], 1)
        self.assertEqual(m["hire"], 0)

    def test_unknown_cycle_time_refuses_to_guess(self):
        m = E.capacity_model(cycle_median_min=None, workday_min=480, demand_per_day=40,
                             current_people=2)
        self.assertIsNone(m["people_needed"])
        self.assertTrue(m["reason"])

    def test_zero_demand_needs_nobody(self):
        m = E.capacity_model(cycle_median_min=45, workday_min=480, demand_per_day=0,
                             current_people=2)
        self.assertEqual(m["people_needed"], 0)
        self.assertEqual(m["hire"], 0)

    def test_cluster_saving_raises_throughput(self):
        # Stacked units skip the drive. A 25% saving on cycle time means more per day.
        base = E.capacity_model(cycle_median_min=60, workday_min=480, demand_per_day=40,
                                current_people=0)
        saved = E.capacity_model(cycle_median_min=60, workday_min=480, demand_per_day=40,
                                 current_people=0, cluster_saving_pct=25)
        self.assertEqual(base["units_per_person_day"], 8)
        self.assertEqual(saved["units_per_person_day"], 10)   # 480 / 45
        self.assertLess(saved["people_needed"], base["people_needed"])

    def test_saving_is_clamped_to_sane_range(self):
        m = E.capacity_model(cycle_median_min=60, workday_min=480, demand_per_day=40,
                             current_people=0, cluster_saving_pct=500)
        self.assertGreater(m["units_per_person_day"], 0)


# ---------------------------------------------------------------- unit build

class TestBuildUnits(unittest.TestCase):
    def setUp(self):
        self.listings = [
            {"id": 1, "internal_name": "Ouja | A", "active": True, "group": "الملقا",
             "oujact": True, "cleaning_team": "team-1", "lat": 24.75, "lng": 46.70,
             "maps_link": "", "address": "Malqa"},
            {"id": 2, "internal_name": "Ouja | B", "active": True, "group": "",
             "oujact": False, "cleaning_team": "team-2", "lat": None, "lng": None,
             "maps_link": "", "address": "Hittin"},
            {"id": 3, "internal_name": "Ouja | Old", "active": False, "group": "",
             "oujact": False, "cleaning_team": "", "lat": None, "lng": None},
        ]
        self.teams = [{"id": "team-1", "name": "أوجا الداخلي"},
                      {"id": "team-2", "name": "شركة خارجية"}]
        self.guide = [{"slug": "a", "listing_id": 1, "map_link": "https://maps.google.com/?q=24.9,46.9"},
                      {"slug": "b", "listing_id": 2, "map_link": "https://maps.google.com/?q=24.80,46.60"}]

    def test_inactive_units_excluded(self):
        u = E.build_units(self.listings, self.guide, self.teams, in_house_team_ids={"team-1"})
        self.assertEqual({x["lid"] for x in u}, {1, 2})

    def test_team_name_joined(self):
        u = {x["lid"]: x for x in E.build_units(self.listings, self.guide, self.teams,
                                                in_house_team_ids={"team-1"})}
        self.assertEqual(u[2]["team_name"], "شركة خارجية")

    def test_in_house_flag_from_team_id(self):
        u = {x["lid"]: x for x in E.build_units(self.listings, self.guide, self.teams,
                                                in_house_team_ids={"team-1"})}
        self.assertTrue(u[1]["in_house"])
        self.assertFalse(u[2]["in_house"])

    def test_listing_coords_beat_guide_coords(self):
        # The listings store is what the route/ETA code trusts, so it wins.
        u = {x["lid"]: x for x in E.build_units(self.listings, self.guide, self.teams)}
        self.assertEqual((u[1]["lat"], u[1]["lng"]), (24.75, 46.70))

    def test_guide_coords_fill_the_gap(self):
        u = {x["lid"]: x for x in E.build_units(self.listings, self.guide, self.teams)}
        self.assertEqual((u[2]["lat"], u[2]["lng"]), (24.80, 46.60))
        self.assertEqual(u[2]["coord_source"], "guide")

    def test_unit_with_no_location_anywhere_is_flagged(self):
        listings = [{"id": 5, "internal_name": "Ouja | Lost", "active": True}]
        u = E.build_units(listings, [], [])
        self.assertFalse(u[0]["has_location"])

    def test_unassigned_unit_kept_and_marked(self):
        listings = self.listings + [{"id": 4, "internal_name": "Ouja | New",
                                     "active": True, "cleaning_team": ""}]
        u = {x["lid"]: x for x in E.build_units(listings, [], self.teams)}
        self.assertEqual(u[4]["team_id"], "")
        self.assertEqual(u[4]["team_name"], "")


# ---------------------------------------------------------------- whole study

class TestStudy(unittest.TestCase):
    def test_start_date_is_the_earliest_evidence(self):
        log = [{"lid": 1, "date": "2026-07-01", "action": "done", "ts": "2026-07-01T10:00:00", "by": "a"}]
        reports = [{"report_id": "r", "apartment_id": 1, "date": "2026-06-05",
                    "submitted_at": "2026-06-05T10:00:00", "cleaner_name": "a"}]
        s = E.study(listings=[{"id": 1, "internal_name": "U", "active": True}],
                    guide_units=[], teams=[], status_log=log, reports=reports, photos=[])
        self.assertEqual(s["oujact"]["started_on"], "2026-06-05")

    def test_days_active_counts_days_with_work_not_calendar_days(self):
        log = [{"lid": 1, "date": "2026-07-01", "action": "done", "ts": "2026-07-01T10:00:00", "by": "a"},
               {"lid": 2, "date": "2026-07-05", "action": "done", "ts": "2026-07-05T10:00:00", "by": "a"}]
        s = E.study(listings=[{"id": 1, "internal_name": "U", "active": True}],
                    guide_units=[], teams=[], status_log=log, reports=[], photos=[])
        self.assertEqual(s["oujact"]["days_worked"], 2)

    def test_empty_everything_does_not_crash(self):
        s = E.study(listings=[], guide_units=[], teams=[], status_log=[], reports=[], photos=[])
        self.assertEqual(s["units"]["total"], 0)
        self.assertIsNone(s["oujact"]["started_on"])

    def test_since_filter_trims_the_window(self):
        log = [{"lid": 1, "date": "2026-06-01", "action": "done", "ts": "2026-06-01T10:00:00", "by": "a"},
               {"lid": 2, "date": "2026-07-20", "action": "done", "ts": "2026-07-20T10:00:00", "by": "a"}]
        s = E.study(listings=[], guide_units=[], teams=[], status_log=log, reports=[],
                    photos=[], since="2026-07-01")
        self.assertEqual(s["oujact"]["total_cleans"], 1)

    def test_counts_split_in_house_versus_third_party(self):
        listings = [{"id": 1, "internal_name": "A", "active": True, "cleaning_team": "team-1"},
                    {"id": 2, "internal_name": "B", "active": True, "cleaning_team": "team-2"},
                    {"id": 3, "internal_name": "C", "active": True, "cleaning_team": ""}]
        teams = [{"id": "team-1", "name": "Ouja"}, {"id": "team-2", "name": "Vendor"}]
        s = E.study(listings=listings, guide_units=[], teams=teams, status_log=[],
                    reports=[], photos=[], in_house_team_ids={"team-1"})
        self.assertEqual(s["units"]["in_house"], 1)
        self.assertEqual(s["units"]["third_party"], 1)
        self.assertEqual(s["units"]["unassigned"], 1)


if __name__ == "__main__":
    unittest.main()
