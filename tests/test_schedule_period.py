# -*- coding: utf-8 -*-
"""
Step 2 of «مخطط الإجازات والتغطية» — the PERIOD simulation.

"ناصر off 20–27 August" has to be answerable BEFORE it is saved: how much real work lands on
each remaining person each day, which days turn dangerous, which apartments nobody good can
take. This file locks that down before the code exists.

Owner rulings encoded here (2026-08-18), and each has a test:
  * minutes are the PRIMARY overload signal, units advisory — two caps that disagree is noise.
  * caps are NOT guessed (no hardcoded 16/8). They come from the observed 90th percentile of
    this team's own daily loads.
  * SAUDI_EVENTS is a LABEL, never a risk trigger — Riyadh Season is a five-month window and
    would otherwise paint half the year red. The risk signal is the turnover percentile.
  * a simulation writes NOTHING.
  * Hostaway down is a degraded answer, never a broken screen — and it must SAY «تقديري».

Run:  python3 -m unittest tests.test_schedule_period
"""
import datetime
import os
import sys
import tempfile
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb                    # noqa: E402
from schedule import db as sdb                 # noqa: E402
import schedule                                # noqa: E402
from schedule import routes, period, workload  # noqa: E402
from schedule.host import HOST                 # noqa: E402


def _emp(eid, name, load=10, turns=5, minutes=200, districts=None, deep=0):
    return {"id": eid, "name": name, "load": load, "real_turnovers": turns,
            "est_minutes": minutes, "districts": districts or ["الملقا"],
            "deep_cleans": deep, "checkins": 0}


def _day(date="2026-08-20", employees=None, off=None, **kw):
    d = {"date": date, "weekday_ar": "الخميس", "employees": employees or [],
         "off": off or [], "unassigned": [], "skipped_date_overrides": [],
         "total_turnovers": sum(e["real_turnovers"] for e in (employees or [])),
         "checkins": 0, "events": []}
    d.update(kw)
    return d


CAPS = {"minutes": 480, "units": 15, "source": "observed"}


def _codes(risks):
    return sorted(r["code"] for r in risks)


# =====================================================================
#  A. the pure risk/rollup layer
# =====================================================================
class PeriodRiskTest(unittest.TestCase):

    def test_nobody_working_is_the_hard_block(self):
        d = _day(employees=[], off=[{"id": 1, "name": "ناصر", "reason": "leave"},
                                    {"id": 2, "name": "مآثر", "reason": "off"}])
        r = period.day_risks(d, CAPS)
        self.assertIn("nobody_working", _codes(r))
        blocker = next(x for x in r if x["code"] == "nobody_working")
        self.assertEqual(blocker["severity"], "block")
        self.assertTrue(blocker["ar"] and blocker["en"], "every risk needs both languages")

    def test_minutes_are_primary_units_are_advisory(self):
        """14 units under the unit cap but way over the minute cap: the minute flag is the
        real one; the unit flag must not fire at all."""
        d = _day(employees=[_emp(1, "نورة", load=14, turns=14, minutes=620)])
        r = period.day_risks(d, CAPS)
        self.assertIn("overload", _codes(r))
        self.assertNotIn("overload_units", _codes(r))
        over = next(x for x in r if x["code"] == "overload")
        self.assertEqual(over["severity"], "warn")
        self.assertEqual(over["employee_id"], 1)

    def test_unit_flag_is_advisory_only_when_minutes_are_fine(self):
        d = _day(employees=[_emp(1, "نورة", load=20, turns=3, minutes=120)])
        r = period.day_risks(d, CAPS)
        self.assertIn("overload_units", _codes(r))
        self.assertEqual(next(x for x in r if x["code"] == "overload_units")["severity"], "info")
        self.assertNotIn("overload", _codes(r))

    def test_peak_demand_is_a_percentile_not_an_event(self):
        """A day is a peak because it is busy for THIS window, not because a season is on."""
        quiet = [_day("2026-08-%02d" % n, [_emp(1, "نورة", turns=4)]) for n in range(1, 10)]
        busy = _day("2026-08-10", [_emp(1, "نورة", turns=40)])
        days = quiet + [busy]
        period.mark_peaks(days)
        self.assertIn("peak_demand", _codes(period.day_risks(busy, CAPS)))
        self.assertNotIn("peak_demand", _codes(period.day_risks(quiet[0], CAPS)))

    def test_a_five_month_season_never_raises_a_risk(self):
        """Riyadh Season runs Oct->Mar. If an event could flag, half the year would be red."""
        d = _day(employees=[_emp(1, "نورة", turns=5)], events=["موسم الرياض", "عيد الفطر"])
        r = period.day_risks(d, CAPS)
        self.assertEqual([x for x in r if x["code"] == "peak_demand"], [])
        self.assertEqual(d["events"], ["موسم الرياض", "عيد الفطر"], "kept as a LABEL")

    def test_unassigned_apartments_are_flagged(self):
        d = _day(employees=[_emp(1, "نورة")], unassigned=[{"id": 9, "name": "حطين 6b"}])
        self.assertIn("unassigned", _codes(period.day_risks(d, CAPS)))

    def test_double_absence_fires_on_two_people_on_LEAVE(self):
        d = _day(employees=[_emp(1, "نورة")],
                 off=[{"id": 2, "name": "ناصر", "reason": "leave"},
                      {"id": 3, "name": "مآثر", "reason": "leave"}])
        self.assertIn("double_absence", _codes(period.day_risks(d, CAPS)))

    def test_double_absence_fires_on_three_out_however_caused(self):
        d = _day(employees=[_emp(1, "نورة")],
                 off=[{"id": 2, "name": "ناصر", "reason": "leave"},
                      {"id": 3, "name": "مآثر", "reason": "off"},
                      {"id": 4, "name": "عهود", "reason": "off"}])
        self.assertIn("double_absence", _codes(period.day_risks(d, CAPS)))

    def test_one_leave_landing_on_a_normal_off_day_is_NOT_a_warning(self):
        """Exactly one person is off by rota on five days of seven, so this shape is every
        ordinary leave day. Flagging it would fire almost daily and train the owner to ignore
        the whole risk list."""
        d = _day(employees=[_emp(1, "نورة")],
                 off=[{"id": 2, "name": "ناصر", "reason": "leave"},
                      {"id": 3, "name": "مآثر", "reason": "off"}])
        self.assertNotIn("double_absence", _codes(period.day_risks(d, CAPS)))

    def test_single_absence_is_not_a_double_absence(self):
        d = _day(employees=[_emp(1, "نورة")], off=[{"id": 2, "name": "ناصر", "reason": "off"}])
        self.assertNotIn("double_absence", _codes(period.day_risks(d, CAPS)))

    def test_deep_clean_clash_only_when_the_coverer_is_already_hot(self):
        hot = _day(employees=[_emp(1, "نورة", minutes=470, deep=1)])
        self.assertIn("deep_clean_clash", _codes(period.day_risks(hot, CAPS)))
        calm = _day(employees=[_emp(1, "نورة", minutes=100, deep=1)])
        self.assertNotIn("deep_clean_clash", _codes(period.day_risks(calm, CAPS)))

    def test_cross_district_at_three(self):
        two = _day(employees=[_emp(1, "نورة", districts=["الملقا", "قرطبة"])])
        self.assertNotIn("cross_district", _codes(period.day_risks(two, CAPS)))
        three = _day(employees=[_emp(1, "نورة", districts=["الملقا", "قرطبة", "العارض"])])
        self.assertIn("cross_district", _codes(period.day_risks(three, CAPS)))

    def test_stale_override_surfaces_from_the_engine(self):
        d = _day(employees=[_emp(1, "نورة")],
                 skipped_date_overrides=[{"apartment_id": 4, "covering_employee_id": 2,
                                          "reason": "target_off"}])
        self.assertIn("stale_override", _codes(period.day_risks(d, CAPS)))

    # ---- caps come from the team's own history, never from a guess ----
    def test_percentile_is_nearest_rank_and_deterministic(self):
        self.assertEqual(period.percentile(list(range(1, 11)), 90), 9)
        self.assertEqual(period.percentile([5], 90), 5)
        self.assertIsNone(period.percentile([], 90))

    def test_observed_caps_from_history_not_hardcoded(self):
        """13 ordinary days and one monster: p90 must sit near the real ceiling, and must not
        come back as 16/480."""
        hist = [{"units": u, "minutes": u * 35} for u in
                [10, 11, 12, 12, 13, 13, 13, 14, 14, 14, 15, 15, 16, 40]]
        caps = period.observed_caps(hist)
        self.assertEqual(caps["source"], "observed")
        self.assertEqual(caps["units"], 16)
        self.assertEqual(caps["minutes"], 16 * 35)
        self.assertNotEqual(caps["minutes"], 480, "must not fall back to the guessed default")

    def test_caps_unknown_when_there_is_no_history(self):
        caps = period.observed_caps([])
        self.assertIsNone(caps["units"])
        self.assertIsNone(caps["minutes"])
        self.assertEqual(caps["source"], "unknown")

    def test_no_overload_flag_at_all_when_caps_are_unknown(self):
        """Never invent a red bar on top of a number we could not compute."""
        d = _day(employees=[_emp(1, "نورة", load=99, minutes=9999)])
        r = period.day_risks(d, {"minutes": None, "units": None, "source": "unknown"})
        self.assertNotIn("overload", _codes(r))
        self.assertNotIn("overload_units", _codes(r))

    # ---- the rollup ----
    def test_rollup_deltas_and_worst_day(self):
        base = [_day("2026-08-20", [_emp(1, "نورة", load=9, minutes=300)]),
                _day("2026-08-21", [_emp(1, "نورة", load=9, minutes=300)])]
        plan = [_day("2026-08-20", [_emp(1, "نورة", load=13, minutes=520)]),
                _day("2026-08-21", [_emp(1, "نورة", load=11, minutes=380)])]
        for d in plan:
            d["risks"] = period.day_risks(d, CAPS)
        roll = period.summarize(plan, baseline=base, caps=CAPS)
        who = next(e for e in roll["by_employee"] if e["id"] == 1)
        self.assertEqual(who["baseline_load"], 18)      # 9 + 9
        self.assertEqual(who["plan_load"], 24)          # 13 + 11
        self.assertEqual(who["delta"], 6)
        self.assertEqual(who["delta_minutes"], 300)
        self.assertEqual(roll["worst_day"], "2026-08-20")
        self.assertIn("overload", [r["code"] for r in roll["risks"]])


# =====================================================================
#  B. the route — real seed, fake Hostaway
# =====================================================================
class PeriodRouteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="sched_period_")
        bdb.set_db_path_for_tests(os.path.join(cls.tmp, "brain.db"))
        sdb.reset_init_cache()
        schedule.wire({
            "dash_auth": lambda req: True,
            "req_role": lambda req: getattr(req, "_role", "admin"),
            "req_actor": lambda req: "فيصل",
            "json_response": lambda data, status=200: types.SimpleNamespace(data=data, status=status),
            "web": types.SimpleNamespace(Response=lambda **k: k),
            "notify": None,
            "now": lambda: datetime.datetime(2026, 8, 18, 9, 0),
            "load_json": lambda n, d=None: d, "save_json": lambda n, o: None,
            "listings": lambda: [],
            "ha_reservations_window": cls._fake_reservations,
            "ls_get": lambda: {"listings": {}},
            "deep_clean_state": lambda: {},
            "events_for_date": lambda d: [],
            "clean_defaults": lambda: {"clean_min": 20, "clean_max": 40, "park_buffer": 5},
            "confirmed_statuses": lambda: {"new", "modified"},
        })
        # link every schedule apartment to a fake Hostaway listing id so demand can land on it
        for i, a in enumerate(sdb.apartments(), start=1000):
            sdb.execute("UPDATE schedule_apartments SET listing_id=? WHERE id=?", (i, a["id"]))

    @staticmethod
    def _fake_reservations(p_start, p_end, start_iso, end_iso):
        """Two departures a day on the first two linked units, every day of the window."""
        out, d = [], datetime.date.fromisoformat(start_iso)
        end = datetime.date.fromisoformat(end_iso)
        n = 0
        while d <= end:
            for lid in (1000, 1001):
                n += 1
                out.append({"id": n, "status": "new", "listingMapId": lid,
                            "arrivalDate": d.isoformat(), "departureDate": d.isoformat()})
            d += datetime.timedelta(days=1)
        return out

    def setUp(self):
        sdb.execute("DELETE FROM schedule_date_overrides")
        sdb.execute("DELETE FROM schedule_absences")

    def _run(self, coro):
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def _req(self, query, role="admin"):
        r = types.SimpleNamespace(query=query, match_info={}, headers={})
        r._role = role
        return r

    def test_period_agrees_with_the_today_tab(self):
        """The one rule that stops two screens disagreeing: same date, same numbers."""
        res = self._run(routes.api_period(self._req({"start": "2026-08-20", "end": "2026-08-22"})))
        self.assertTrue(res.data["ok"])
        days = res.data["period"]["days"]
        self.assertEqual([d["date"] for d in days],
                         ["2026-08-20", "2026-08-21", "2026-08-22"])
        for d in days:
            same = routes.schedule_day(d["date"])
            self.assertEqual(sorted(e["load"] for e in d["employees"]),
                             sorted(w["load"] for w in same["working"]))

    def test_simulation_writes_nothing(self):
        before = (len(sdb.q("SELECT id FROM schedule_absences")),
                  len(sdb.q("SELECT id FROM schedule_date_overrides")))
        emp = sdb.q1("SELECT id FROM schedule_employees WHERE name='ناصر'")["id"]
        res = self._run(routes.api_period(self._req({
            "start": "2026-08-20", "end": "2026-08-27",
            "simulate_absence": "%d:2026-08-20:2026-08-27" % emp})))
        self.assertTrue(res.data["ok"])
        after = (len(sdb.q("SELECT id FROM schedule_absences")),
                 len(sdb.q("SELECT id FROM schedule_date_overrides")))
        self.assertEqual(before, after, "a dry run must never touch the database")
        # ...and ناصر really is shown as out on every day of it
        for d in res.data["period"]["days"]:
            self.assertIn("ناصر", [o["name"] for o in d["off"]])

    def test_multiple_simulated_absences_in_one_call(self):
        """Eid means several people at once."""
        a = sdb.q1("SELECT id FROM schedule_employees WHERE name='ناصر'")["id"]
        b = sdb.q1("SELECT id FROM schedule_employees WHERE name='نورة'")["id"]
        res = self._run(routes.api_period(self._req({
            "start": "2026-08-20", "end": "2026-08-21",
            "simulate_absence": "%d:2026-08-20:2026-08-21,%d:2026-08-20:2026-08-21" % (a, b)})))
        day = res.data["period"]["days"][0]
        names = [o["name"] for o in day["off"]]
        self.assertIn("ناصر", names)
        self.assertIn("نورة", names)
        self.assertEqual(len(res.data["period"]["simulated"]), 2)

    def test_baseline_delta_is_against_the_normal_week(self):
        emp = sdb.q1("SELECT id FROM schedule_employees WHERE name='ناصر'")["id"]
        res = self._run(routes.api_period(self._req({
            "start": "2026-08-20", "end": "2026-08-21",
            "simulate_absence": "%d:2026-08-20:2026-08-21" % emp})))
        roll = res.data["period"]["rollup"]
        naser = next(e for e in roll["by_employee"] if e["id"] == emp)
        self.assertLess(naser["delta"], 0, "the absent person carries less")
        others = [e for e in roll["by_employee"] if e["id"] != emp]
        self.assertTrue(any(e["delta"] > 0 for e in others), "somebody absorbs it")
        self.assertEqual(sum(e["delta"] for e in roll["by_employee"]), 0,
                         "work is moved, never created or lost")

    def test_window_is_capped(self):
        res = self._run(routes.api_period(self._req({"start": "2026-01-01", "end": "2026-12-31"})))
        self.assertFalse(res.data["ok"])
        self.assertIn("62", str(res.data.get("error", "")))

    def test_bad_dates_are_refused_cleanly(self):
        for q in ({"start": "nope", "end": "2026-08-21"},
                  {"start": "2026-08-22", "end": "2026-08-20"}):
            res = self._run(routes.api_period(self._req(q)))
            self.assertFalse(res.data["ok"])

    def test_real_turnovers_come_from_hostaway(self):
        res = self._run(routes.api_period(self._req({"start": "2026-08-20", "end": "2026-08-20"})))
        p = res.data["period"]
        self.assertEqual(p["demand_source"], "hostaway")
        self.assertEqual(p["days"][0]["total_turnovers"], 2)     # the fake feed gives 2/day
        worked = [e for e in p["days"][0]["employees"] if e["real_turnovers"]]
        self.assertTrue(worked, "the turnovers must land on whoever covers those units")
        self.assertTrue(all(e["est_minutes"] == e["real_turnovers"] * 35 for e in worked),
                        "midpoint(20,40) + 5 parking = 35 min per real turnover")

    def test_hostaway_down_degrades_and_says_so(self):
        def boom(*a, **k):
            raise RuntimeError("Hostaway down")
        orig = HOST.ha_reservations_window
        HOST.ha_reservations_window = boom
        try:
            res = self._run(routes.api_period(self._req({"start": "2026-08-20", "end": "2026-08-21"})))
            self.assertTrue(res.data["ok"], "a Hostaway hiccup must never break the planner")
            p = res.data["period"]
            self.assertEqual(p["demand_source"], "estimated")
            self.assertTrue(p["days"][0]["employees"], "still shows the coverage board")
        finally:
            HOST.ha_reservations_window = orig

    def test_simulate_mode_needs_an_editor(self):
        emp = sdb.q1("SELECT id FROM schedule_employees WHERE name='ناصر'")["id"]
        res = self._run(routes.api_period(self._req(
            {"start": "2026-08-20", "end": "2026-08-21",
             "simulate_absence": "%d:2026-08-20:2026-08-21" % emp}, role="viewer")))
        self.assertEqual(res.status, 403)

    def test_plain_read_is_public(self):
        """/team-calendar opens with no login, so the read-only period must too."""
        orig = HOST.dash_auth
        HOST.dash_auth = lambda req: False
        try:
            res = self._run(routes._safe_public(routes.api_period)(
                self._req({"start": "2026-08-20", "end": "2026-08-21"}, role="viewer")))
            self.assertTrue(res.data["ok"])
        finally:
            HOST.dash_auth = orig

    def test_workload_never_raises(self):
        """Every shape of broken Hostaway answer returns a usable, honest result."""
        for bad in (None, "nonsense", [{"no": "fields"}], [{"status": "cancelled"}]):
            got = workload.fetch_window("2026-08-20", "2026-08-21", _reservations=lambda *a: bad)
            self.assertIn(got["source"], ("hostaway", "estimated"))
            self.assertIsInstance(got["checkouts"], dict)


if __name__ == "__main__":
    unittest.main()
