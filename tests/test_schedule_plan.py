# -*- coding: utf-8 -*-
"""
Step 3 of «مخطط الإجازات والتغطية» — saving a plan, undoing a plan, and suggesting a coverer.

A plan is ONE thing: the leave plus every apartment the owner moved because of it. It has to
save as one thing and come back as one thing, or the owner is left hand-unpicking rows.

Rules locked here:
  * one transaction — a plan is never half-saved.
  * the simulation is re-run SERVER-SIDE at save time. `nobody_working` is refused outright;
    everything else is a warning the owner must accept EXPLICITLY, never silently.
  * undo removes exactly its own rows and nothing else — not a hand-made leave, not another
    plan's pins.
  * created_by is the logged-in person, not the hardcoded "editor" the old code wrote.
  * the suggested coverer is ranked in the ENGINE (pure, testable), not in JavaScript.

Run:  python3 -m unittest tests.test_schedule_plan
"""
import datetime
import os
import sys
import tempfile
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb                  # noqa: E402
from schedule import db as sdb               # noqa: E402
import schedule                              # noqa: E402
from schedule import routes, engine, seed    # noqa: E402


# =====================================================================
#  A. the pure suggestion ranking
# =====================================================================
class SuggestionRankingTest(unittest.TestCase):
    CANDS = [{"id": 1, "name": "ناصر", "sort_order": 0},
             {"id": 2, "name": "نورة", "sort_order": 2},
             {"id": 3, "name": "عهود", "sort_order": 4}]

    def _ctx(self, **kw):
        base = {"apartment_district": "الملقا", "districts": {}, "history": {}, "minutes": {}}
        base.update(kw)
        return base

    def test_same_district_wins_over_everything(self):
        """The biggest real saving is not driving from Malqa to Qurtubah."""
        ranked = engine.rank_candidates(
            {"id": 9, "name": "الملقا 1"}, self.CANDS,
            self._ctx(districts={1: ["قرطبة"], 2: ["الملقا"], 3: ["قرطبة"]},
                      history={1: 5}, minutes={2: 400, 1: 10, 3: 10}))
        self.assertEqual(ranked[0]["id"], 2)
        self.assertEqual(ranked[0]["reason"], "same_district")
        self.assertIn("المجمع", ranked[0]["reason_ar"])

    def test_history_breaks_a_district_tie(self):
        ranked = engine.rank_candidates(
            {"id": 9, "name": "الملقا 1"}, self.CANDS,
            self._ctx(districts={1: ["الملقا"], 2: ["الملقا"], 3: ["الملقا"]},
                      history={2: 3}, minutes={1: 10, 2: 300, 3: 10}))
        self.assertEqual(ranked[0]["id"], 2)
        self.assertEqual(ranked[0]["reason"], "covers_it_usually")

    def test_lowest_load_breaks_the_remaining_tie(self):
        ranked = engine.rank_candidates(
            {"id": 9, "name": "الملقا 1"}, self.CANDS,
            self._ctx(districts={}, history={}, minutes={1: 500, 2: 120, 3: 300}))
        self.assertEqual(ranked[0]["id"], 2)
        self.assertEqual(ranked[0]["reason"], "lightest_day")

    def test_stable_and_deterministic_when_everything_ties(self):
        a = engine.rank_candidates({"id": 9, "name": "x"}, self.CANDS, self._ctx())
        b = engine.rank_candidates({"id": 9, "name": "x"}, self.CANDS, self._ctx())
        self.assertEqual([c["id"] for c in a], [c["id"] for c in b])
        self.assertEqual([c["id"] for c in a], [1, 2, 3])       # sort_order, then id

    def test_every_candidate_is_returned_not_just_the_winner(self):
        ranked = engine.rank_candidates({"id": 9, "name": "x"}, self.CANDS, self._ctx())
        self.assertEqual(len(ranked), 3)
        self.assertTrue(all(c.get("reason_ar") and c.get("reason_en") for c in ranked))

    def test_no_candidates_is_not_a_crash(self):
        self.assertEqual(engine.rank_candidates({"id": 9, "name": "x"}, [], self._ctx()), [])


# =====================================================================
#  B. saving / undoing a plan
# =====================================================================
class PlanRouteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="sched_plan_")
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
            "ha_reservations_window": lambda *a, **k: [],
            "ls_get": lambda: {"listings": {}},
            "deep_clean_state": lambda: {},
            "events_for_date": lambda d: [],
        })

    def setUp(self):
        sdb.execute("DELETE FROM schedule_date_overrides")
        sdb.execute("DELETE FROM schedule_absences")
        sdb.execute("DELETE FROM schedule_plans")

    def _run(self, coro):
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def _req(self, body=None, match=None, query=None, role="admin"):
        r = types.SimpleNamespace(query=query or {}, match_info=match or {}, headers={})
        r._role = role
        r._body = body or {}

        async def _json():
            return r._body
        r.json = _json
        return r

    def _ids(self):
        return {e["name"]: e["id"] for e in sdb.employees()}

    def _apt_of(self, name):
        return sdb.q1("SELECT a.id id, a.name name FROM schedule_apartments a "
                      "JOIN schedule_employees e ON a.owner_id=e.id WHERE e.name=? LIMIT 1",
                      (name,))

    # ---- the happy path ----
    def test_plan_saves_leave_and_pins_as_one_thing(self):
        E, apt = self._ids(), self._apt_of("ناصر")
        res = self._run(routes.api_plan_save(self._req({
            "employees": [{"employee_id": E["ناصر"], "start": "2026-08-20",
                           "end": "2026-08-22", "type": "vacation", "note": "سفر"}],
            "overrides": [{"date": "2026-08-20", "apartment_id": apt["id"],
                           "covering_employee_id": E["نورة"]}],
            "note": "خطة أغسطس"})))
        self.assertTrue(res.data["ok"], res.data)
        pid = res.data["plan_id"]
        self.assertEqual(len(sdb.q("SELECT id FROM schedule_absences WHERE plan_id=?", (pid,))), 1)
        pins = sdb.q("SELECT * FROM schedule_date_overrides WHERE plan_id=?", (pid,))
        self.assertEqual(len(pins), 1)
        self.assertEqual(pins[0]["covering_employee_id"], E["نورة"])
        # and the board actually reflects it
        day = routes.schedule_day("2026-08-20")
        self.assertIn("ناصر", [o["name"] for o in day["off"]])
        nora = next(w for w in day["working"] if w["id"] == E["نورة"])
        self.assertIn(apt["id"], [c["apartment"]["id"] for c in nora["coverage"]])

    def test_created_by_is_the_logged_in_person_not_editor(self):
        E = self._ids()
        res = self._run(routes.api_plan_save(self._req({
            "employees": [{"employee_id": E["مآثر"], "start": "2026-08-20",
                           "end": "2026-08-20", "type": "sick"}]})))
        row = sdb.q1("SELECT created_by FROM schedule_absences WHERE plan_id=?",
                     (res.data["plan_id"],))
        self.assertEqual(row["created_by"], "فيصل")
        self.assertNotEqual(row["created_by"], "editor")

    # ---- the guard rails ----
    def test_nobody_working_is_refused_and_writes_nothing(self):
        E = self._ids()
        everyone = [{"employee_id": i, "start": "2026-08-20", "end": "2026-08-20",
                     "type": "vacation"} for i in E.values()]
        res = self._run(routes.api_plan_save(self._req({"employees": everyone})))
        self.assertFalse(res.data["ok"])
        self.assertEqual(res.data.get("code"), "nobody_working")
        self.assertEqual(sdb.q("SELECT id FROM schedule_absences"), [])
        self.assertEqual(sdb.q("SELECT id FROM schedule_plans"), [])

    def test_warnings_must_be_accepted_explicitly(self):
        """An apartment with no permanent owner raises a warning. It must not save silently,
        and it must not be an outright block either — the owner decides."""
        E = self._ids()
        orphan = sdb.apartments()[0]
        sdb.execute("UPDATE schedule_apartments SET owner_id=NULL WHERE id=?", (orphan["id"],))
        try:
            body = {"employees": [{"employee_id": E["ناصر"], "start": "2026-08-20",
                                   "end": "2026-08-20", "type": "vacation"}]}
            first = self._run(routes.api_plan_save(self._req(dict(body))))
            self.assertFalse(first.data["ok"])
            self.assertEqual(first.data.get("code"), "needs_confirm")
            self.assertTrue(first.data["warnings"], "the owner must be told WHAT to accept")
            self.assertEqual(sdb.q("SELECT id FROM schedule_absences"), [])
            body["accept_warnings"] = True
            second = self._run(routes.api_plan_save(self._req(body)))
            self.assertTrue(second.data["ok"])
        finally:
            sdb.execute("UPDATE schedule_apartments SET owner_id=? WHERE id=?",
                        (E["ناصر"], orphan["id"]))

    def test_editor_gating_on_save_and_undo(self):
        E = self._ids()
        res = self._run(routes.api_plan_save(self._req(
            {"employees": [{"employee_id": E["ناصر"], "start": "2026-08-20",
                            "end": "2026-08-20", "type": "sick"}]}, role="viewer")))
        self.assertEqual(res.status, 403)
        undo = self._run(routes.api_plan_delete(self._req(match={"id": "1"}, role="viewer")))
        self.assertEqual(undo.status, 403)

    def test_a_plan_with_nothing_in_it_is_refused(self):
        res = self._run(routes.api_plan_save(self._req({"employees": []})))
        self.assertFalse(res.data["ok"])

    # ---- undo ----
    def test_undo_removes_exactly_its_own_rows(self):
        E = self._ids()
        a1, a2 = self._apt_of("ناصر"), self._apt_of("مآثر")
        p1 = self._run(routes.api_plan_save(self._req({
            "employees": [{"employee_id": E["ناصر"], "start": "2026-08-20",
                           "end": "2026-08-20", "type": "vacation"}],
            "overrides": [{"date": "2026-08-20", "apartment_id": a1["id"],
                           "covering_employee_id": E["نورة"]}]}))).data["plan_id"]
        p2 = self._run(routes.api_plan_save(self._req({
            "employees": [{"employee_id": E["عهود"], "start": "2026-08-25",
                           "end": "2026-08-25", "type": "vacation"}],
            "overrides": [{"date": "2026-08-25", "apartment_id": a2["id"],
                           "covering_employee_id": E["نورة"]}]}))).data["plan_id"]
        # plus a leave and a pin made BY HAND, outside any plan
        sdb.execute("INSERT INTO schedule_absences(employee_id,start_date,end_date,type,status,"
                    "created_at) VALUES(?,?,?,?,?,?)",
                    (E["مآثر"], "2026-09-01", "2026-09-01", "sick", "approved", sdb.now_iso()))
        sdb.execute("INSERT INTO schedule_date_overrides(date,apartment_id,"
                    "covering_employee_id,created_at) VALUES(?,?,?,?)",
                    ("2026-09-01", a1["id"], E["نورة"], sdb.now_iso()))

        res = self._run(routes.api_plan_delete(self._req(match={"id": str(p1)})))
        self.assertTrue(res.data["ok"])
        self.assertEqual(sdb.q("SELECT id FROM schedule_absences WHERE plan_id=?", (p1,)), [])
        self.assertEqual(sdb.q("SELECT id FROM schedule_date_overrides WHERE plan_id=?", (p1,)), [])
        self.assertEqual(len(sdb.q("SELECT id FROM schedule_absences WHERE plan_id=?", (p2,))), 1)
        self.assertEqual(len(sdb.q("SELECT id FROM schedule_date_overrides WHERE plan_id=?", (p2,))), 1)
        self.assertEqual(len(sdb.q("SELECT id FROM schedule_absences WHERE plan_id IS NULL")), 1)
        self.assertEqual(len(sdb.q("SELECT id FROM schedule_date_overrides WHERE plan_id IS NULL")), 1)

    def test_undo_of_an_unknown_plan_is_a_clean_no(self):
        res = self._run(routes.api_plan_delete(self._req(match={"id": "9999"})))
        self.assertFalse(res.data["ok"])

    # ---- the leave list ----
    def test_absences_list_is_readable_with_counts(self):
        E, apt = self._ids(), self._apt_of("ناصر")
        self._run(routes.api_plan_save(self._req({
            "employees": [{"employee_id": E["ناصر"], "start": "2026-08-20",
                           "end": "2026-08-22", "type": "vacation", "note": "سفر"}],
            "overrides": [{"date": "2026-08-20", "apartment_id": apt["id"],
                           "covering_employee_id": E["نورة"]}]})))
        res = self._run(routes.api_absences(self._req(query={"from": "2026-08-01",
                                                             "to": "2026-09-01"})))
        self.assertTrue(res.data["ok"])
        rows = res.data["absences"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["employee_name"], "ناصر")
        self.assertEqual(rows[0]["type"], "vacation")
        self.assertEqual(rows[0]["days"], 3)
        self.assertEqual(rows[0]["override_count"], 1)
        self.assertEqual(rows[0]["created_by"], "فيصل")

    def test_absences_list_window_filters(self):
        E = self._ids()
        self._run(routes.api_plan_save(self._req({
            "employees": [{"employee_id": E["ناصر"], "start": "2026-08-20",
                           "end": "2026-08-22", "type": "vacation"}]})))
        far = self._run(routes.api_absences(self._req(query={"from": "2027-01-01",
                                                             "to": "2027-02-01"})))
        self.assertEqual(far.data["absences"], [])

    # ---- the types the planner offers ----
    def test_disabled_types_stay_out_of_the_planner(self):
        """SUPERSEDED IN PART on 2026-08-18: «نصف يوم» came back once the owner replaced the
        capacity idea with a morning/evening flag (see tests/test_schedule_leave_types.py), and
        «no_show» left because you record one on the day, not in advance. What still holds:
        تأخير and تدريب are never offered, and both remain valid on the legacy endpoint."""
        for bad in ("late", "training", "no_show"):
            self.assertNotIn(bad, routes.PLANNER_ABSENCE_TYPES)
        for legacy in ("half_day", "late", "training", "no_show"):
            self.assertIn(legacy, routes.ABSENCE_TYPES, "still valid for the legacy endpoint")

    def test_planner_refuses_a_disabled_type(self):
        E = self._ids()
        res = self._run(routes.api_plan_save(self._req({
            "employees": [{"employee_id": E["ناصر"], "start": "2026-08-20",
                           "end": "2026-08-20", "type": "late"}]})))
        self.assertFalse(res.data["ok"])
        self.assertEqual(sdb.q("SELECT id FROM schedule_absences"), [])


if __name__ == "__main__":
    unittest.main()


class SuggestRouteTest(PlanRouteTest):
    """The popup's «مقترح» — real day, real candidates, reason shown."""

    def test_suggest_ranks_the_working_team_and_names_the_current_holder(self):
        E, apt = self._ids(), self._apt_of("ناصر")
        res = self._run(routes.api_suggest(self._req(
            query={"date": "2026-08-20", "apartment_id": str(apt["id"])})))
        self.assertTrue(res.data["ok"])
        self.assertEqual(res.data["current"]["name"], "ناصر")
        self.assertEqual(res.data["current"]["kind"], "own")
        ids = [c["id"] for c in res.data["candidates"]]
        self.assertIn(E["نورة"], ids)
        self.assertTrue(all(c.get("reason_ar") for c in res.data["candidates"]))

    def test_suggest_excludes_whoever_is_out_that_day(self):
        E, apt = self._ids(), self._apt_of("ناصر")
        res = self._run(routes.api_suggest(self._req(
            query={"date": "2026-08-20", "apartment_id": str(apt["id"]),
                   "simulate_absence": "%d:2026-08-20:2026-08-20" % E["نورة"]})))
        self.assertNotIn(E["نورة"], [c["id"] for c in res.data["candidates"]])

    def test_suggest_refuses_an_unknown_apartment(self):
        res = self._run(routes.api_suggest(self._req(
            query={"date": "2026-08-20", "apartment_id": "999999"})))
        self.assertFalse(res.data["ok"])


class SuggestDayRouteTest(PlanRouteTest):
    """The reassignment sheet's data: every apartment needing cover on one date, ranked."""

    def test_lists_the_absent_persons_apartments_with_candidates(self):
        E = self._ids()
        res = self._run(routes.api_suggest_day(self._req(query={
            "date": "2026-08-20",
            "simulate_absence": "%d:2026-08-20:2026-08-20" % E["ناصر"]})))
        self.assertTrue(res.data["ok"], res.data)
        rows = res.data["units"]
        self.assertEqual(len(rows), 11, "ناصر owns 11 apartments in the seed")
        self.assertTrue(all(r["owner_name"] == "ناصر" for r in rows))
        self.assertTrue(all(r["candidates"] for r in rows))
        self.assertNotIn(E["ناصر"], [c["id"] for c in rows[0]["candidates"]],
                         "the person who is out cannot be a candidate")
        self.assertTrue(all(c.get("reason_ar") for c in rows[0]["candidates"]))

    def test_a_dry_run_pin_shows_as_pinned_and_writes_nothing(self):
        E = self._ids()
        apt = self._apt_of("ناصر")
        before = len(sdb.q("SELECT id FROM schedule_date_overrides"))
        res = self._run(routes.api_suggest_day(self._req(query={
            "date": "2026-08-20",
            "simulate_absence": "%d:2026-08-20:2026-08-20" % E["ناصر"],
            "pins": "2026-08-20:%d:%d" % (apt["id"], E["نورة"])})))
        row = next(r for r in res.data["units"] if r["apartment_id"] == apt["id"])
        self.assertTrue(row["pinned"])
        self.assertEqual(row["current_name"], "نورة")
        self.assertEqual(len(sdb.q("SELECT id FROM schedule_date_overrides")), before)

    def test_pins_flow_through_the_period_preview_too(self):
        E, apt = self._ids(), self._apt_of("ناصر")
        res = self._run(routes.api_period(self._req(query={
            "start": "2026-08-20", "end": "2026-08-20",
            "simulate_absence": "%d:2026-08-20:2026-08-20" % E["ناصر"],
            "pins": "2026-08-20:%d:%d" % (apt["id"], E["عهود"])})))
        day = res.data["period"]["days"][0]
        ahoud = next(e for e in day["employees"] if e["id"] == E["عهود"])
        others = [e for e in day["employees"] if e["id"] != E["عهود"]]
        self.assertTrue(ahoud["load"] >= max(e["load"] for e in others) - 1)
        self.assertEqual(sum(e["load"] for e in day["employees"]), 53)

    def test_a_bad_pin_string_is_refused_cleanly(self):
        res = self._run(routes.api_suggest_day(self._req(query={
            "date": "2026-08-20", "pins": "garbage"})))
        self.assertFalse(res.data["ok"])

    def test_sheet_is_editor_only_when_simulating(self):
        E = self._ids()
        res = self._run(routes.api_suggest_day(self._req(query={
            "date": "2026-08-20",
            "simulate_absence": "%d:2026-08-20:2026-08-20" % E["ناصر"]}, role="viewer")))
        self.assertEqual(res.status, 403)
