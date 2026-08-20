# -*- coding: utf-8 -*-
"""
Step 4-A of «مخطط الإجازات» — what a leave TYPE actually means, and who has to approve it.

Owner rulings (2026-08-18), each one a test below:

  * «نصف يوم» is NOT 50% of anything. Checkout is 12:00 and check-in is 15:00, so every
    cleaning starts at midday: a MORNING half-day misses all of it (absent), an EVENING
    half-day catches all of it (present). Two flags, and NO fractional maths in the engine.
  * «تدريب» needs no type of its own — record it as leave and put the reason in the note.
  * «تأخير» is gone from the planner entirely.
  * «no_show» is not something you plan in advance, so it leaves the planning dialog — but it
    still affects coverage, and recording it TODAY must redistribute immediately.
  * Approval is per TYPE, not global: nobody requests being ill. Sick/emergency take effect
    at once (ops records, owner is told, owner can reverse). Annual/unpaid wait for the owner.

Run:  python3 -m unittest tests.test_schedule_leave_types
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
from schedule import routes                  # noqa: E402


class LeaveTypeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="sched_types_")
        bdb.set_db_path_for_tests(os.path.join(cls.tmp, "brain.db"))
        sdb.reset_init_cache()
        cls.notified = []
        schedule.wire({
            "dash_auth": lambda req: True,
            "req_role": lambda req: getattr(req, "_role", "admin"),
            "req_actor": lambda req: "فيصل",
            "json_response": lambda data, status=200: types.SimpleNamespace(data=data, status=status),
            "web": types.SimpleNamespace(Response=lambda **k: k),
            "notify": lambda payload: cls.notified.append(payload),
            "now": lambda: datetime.datetime(2026, 8, 18, 9, 0),
            "load_json": lambda n, d=None: d, "save_json": lambda n, o: None,
            "listings": lambda: [],
            "ha_reservations_window": lambda *a, **k: [],
            "ls_get": lambda: {"listings": {}},
            "deep_clean_state": lambda: {},
            "events_for_date": lambda d: [],
        })

    def setUp(self):
        sdb.execute("DELETE FROM schedule_absences")
        sdb.execute("DELETE FROM schedule_date_overrides")
        sdb.execute("DELETE FROM schedule_plans")
        type(self).notified = []

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

    def _off_names(self, date_iso):
        return [o["name"] for o in routes.schedule_day(date_iso)["off"]]

    # ---------------- the half-day rule ----------------
    def test_morning_half_day_is_a_full_absence(self):
        """Cleaning starts at midday, so someone who only works the morning does none of it."""
        E = self._ids()
        r = self._run(routes.api_plan_save(self._req({"employees": [
            {"employee_id": E["ناصر"], "start": "2026-08-20", "end": "2026-08-20",
             "type": "half_day", "shift": "morning"}]})))
        self.assertTrue(r.data["ok"], r.data)
        self.assertIn("ناصر", self._off_names("2026-08-20"))
        row = sdb.q1("SELECT * FROM schedule_absences WHERE employee_id=?", (E["ناصر"],))
        self.assertEqual(row["affects_coverage"], 1)
        self.assertEqual(row["shift"], "morning")

    def test_evening_half_day_leaves_coverage_untouched(self):
        """An evening half-day catches every cleaning, so the board must not move at all."""
        E = self._ids()
        before = {w["name"]: w["load"] for w in routes.schedule_day("2026-08-20")["working"]}
        r = self._run(routes.api_plan_save(self._req({"employees": [
            {"employee_id": E["ناصر"], "start": "2026-08-20", "end": "2026-08-20",
             "type": "half_day", "shift": "evening"}]})))
        self.assertTrue(r.data["ok"], r.data)
        self.assertNotIn("ناصر", self._off_names("2026-08-20"))
        after = {w["name"]: w["load"] for w in routes.schedule_day("2026-08-20")["working"]}
        self.assertEqual(before, after, "an evening half-day must move nothing")
        row = sdb.q1("SELECT * FROM schedule_absences WHERE employee_id=?", (E["ناصر"],))
        self.assertEqual(row["affects_coverage"], 0, "recorded, but not a coverage event")

    def test_no_fractional_capacity_anywhere(self):
        """The whole point of the morning/evening split: the engine stays integer. Nobody is
        ever 0.5 of a person."""
        E = self._ids()
        self._run(routes.api_plan_save(self._req({"employees": [
            {"employee_id": E["ناصر"], "start": "2026-08-20", "end": "2026-08-20",
             "type": "half_day", "shift": "morning"}]})))
        day = routes.schedule_day("2026-08-20")
        for w in day["working"]:
            self.assertIsInstance(w["load"], int)
        self.assertEqual(sum(w["load"] for w in day["working"]), 53)

    def test_half_day_needs_a_shift(self):
        E = self._ids()
        r = self._run(routes.api_plan_save(self._req({"employees": [
            {"employee_id": E["ناصر"], "start": "2026-08-20", "end": "2026-08-20",
             "type": "half_day"}]})))
        self.assertFalse(r.data["ok"])
        self.assertEqual(sdb.q("SELECT id FROM schedule_absences"), [])

    # ---------------- which types the planner offers ----------------
    def test_planner_types_after_the_owners_ruling(self):
        self.assertEqual(routes.PLANNER_ABSENCE_TYPES,
                         ("vacation", "sick", "emergency", "unpaid", "half_day"))
        for gone in ("late", "training"):
            self.assertNotIn(gone, routes.PLANNER_ABSENCE_TYPES)
        self.assertNotIn("no_show", routes.PLANNER_ABSENCE_TYPES,
                         "a no-show is recorded on the day, never planned in advance")

    def test_training_has_no_type_of_its_own(self):
        """Owner: record it as leave with the reason in the note."""
        self.assertNotIn("training", routes.PLANNER_ABSENCE_TYPES)
        E = self._ids()
        r = self._run(routes.api_plan_save(self._req({"employees": [
            {"employee_id": E["ناصر"], "start": "2026-08-20", "end": "2026-08-20",
             "type": "vacation", "note": "تدريب في الرياض"}]})))
        self.assertTrue(r.data["ok"])
        row = sdb.q1("SELECT note FROM schedule_absences WHERE employee_id=?", (E["ناصر"],))
        self.assertEqual(row["note"], "تدريب في الرياض")

    # ---------------- no_show: same day, immediate ----------------
    def test_no_show_recorded_today_redistributes_at_once(self):
        E = self._ids()
        today = "2026-08-18"                      # a Tuesday — ناصر is already off by rota,
        who = "مآثر"                              # so use somebody who is actually working
        self.assertNotIn(who, self._off_names(today))
        r = self._run(routes.api_absence_add(self._req({
            "employee_id": E[who], "start_date": today, "end_date": today,
            "type": "no_show"})))
        self.assertTrue(r.data["ok"], r.data)
        self.assertIn(who, self._off_names(today), "a no-show must take effect immediately")
        day = routes.schedule_day(today)
        self.assertEqual(sum(w["load"] for w in day["working"]), 53)

    def test_no_show_clears_the_attribution_cache(self):
        """ops caches who is responsible per date. Without invalidation a no-show recorded at
        10am would still be blamed on the person who did not turn up."""
        E = self._ids()
        cleared = []
        from schedule.host import HOST
        HOST.on_change = lambda dates=None: cleared.append(dates)
        try:
            self._run(routes.api_absence_add(self._req({
                "employee_id": E["ناصر"], "start_date": "2026-08-18",
                "end_date": "2026-08-18", "type": "no_show"})))
            self.assertTrue(cleared, "every absence write must announce the change")
        finally:
            HOST.on_change = None

    # ---------------- approval, per type ----------------
    def test_sick_and_emergency_apply_at_once_from_ops(self):
        """Nobody requests being ill in advance."""
        E = self._ids()
        for typ, name in (("sick", "مآثر"), ("emergency", "نورة")):
            sdb.execute("DELETE FROM schedule_absences")     # one at a time: two people out
            r = self._run(routes.api_plan_save(self._req({"employees": [   # would (rightly)
                {"employee_id": E[name], "start": "2026-08-20", "end": "2026-08-20",  # warn
                 "type": typ}]}, role="ops")))
            self.assertTrue(r.data["ok"], r.data)
            row = sdb.q1("SELECT status FROM schedule_absences WHERE employee_id=?", (E[name],))
            self.assertEqual(row["status"], "approved", "%s must take effect at once" % typ)
            self.assertIn(name, self._off_names("2026-08-20"))

    def test_annual_and_unpaid_from_ops_wait_for_the_owner(self):
        E = self._ids()
        for typ, name in (("vacation", "مآثر"), ("unpaid", "نورة")):
            sdb.execute("DELETE FROM schedule_absences")
            r = self._run(routes.api_plan_save(self._req({"employees": [
                {"employee_id": E[name], "start": "2026-08-20", "end": "2026-08-20",
                 "type": typ}]}, role="ops")))
            self.assertTrue(r.data["ok"], r.data)
            row = sdb.q1("SELECT status FROM schedule_absences WHERE employee_id=?", (E[name],))
            self.assertEqual(row["status"], "pending", "%s needs the owner" % typ)
            self.assertNotIn(name, self._off_names("2026-08-20"),
                             "a pending leave must not move the board yet")

    def test_the_owner_never_waits_for_themselves(self):
        E = self._ids()
        r = self._run(routes.api_plan_save(self._req({"employees": [
            {"employee_id": E["ناصر"], "start": "2026-08-20", "end": "2026-08-20",
             "type": "vacation"}]}, role="admin")))
        row = sdb.q1("SELECT status FROM schedule_absences WHERE employee_id=?", (E["ناصر"],))
        self.assertEqual(row["status"], "approved")

    def test_owner_is_told_about_an_immediate_leave(self):
        E = self._ids()
        self._run(routes.api_plan_save(self._req({"employees": [
            {"employee_id": E["مآثر"], "start": "2026-08-20", "end": "2026-08-20",
             "type": "sick"}]}, role="ops")))
        self.assertTrue(type(self).notified, "the owner has to hear about it")

    def test_owner_can_reverse_an_immediate_leave(self):
        E = self._ids()
        r = self._run(routes.api_plan_save(self._req({"employees": [
            {"employee_id": E["مآثر"], "start": "2026-08-20", "end": "2026-08-20",
             "type": "sick"}]}, role="ops")))
        aid = sdb.q1("SELECT id FROM schedule_absences WHERE employee_id=?", (E["مآثر"],))["id"]
        rev = self._run(routes.api_absence_decide(self._req(
            {"id": aid, "decision": "rejected", "reason": "غلط في التسجيل"})))
        self.assertTrue(rev.data["ok"], rev.data)
        self.assertNotIn("مآثر", self._off_names("2026-08-20"))
        row = sdb.q1("SELECT * FROM schedule_absences WHERE id=?", (aid,))
        self.assertEqual(row["status"], "rejected")
        self.assertEqual(row["decided_by"], "فيصل")

    def test_approving_a_pending_leave_moves_the_board(self):
        E = self._ids()
        self._run(routes.api_plan_save(self._req({"employees": [
            {"employee_id": E["مآثر"], "start": "2026-08-20", "end": "2026-08-20",
             "type": "vacation"}]}, role="ops")))
        aid = sdb.q1("SELECT id FROM schedule_absences WHERE employee_id=?", (E["مآثر"],))["id"]
        self.assertNotIn("مآثر", self._off_names("2026-08-20"))
        ok = self._run(routes.api_absence_decide(self._req({"id": aid, "decision": "approved"})))
        self.assertTrue(ok.data["ok"])
        self.assertIn("مآثر", self._off_names("2026-08-20"))

    def test_only_the_owner_decides(self):
        E = self._ids()
        self._run(routes.api_plan_save(self._req({"employees": [
            {"employee_id": E["مآثر"], "start": "2026-08-20", "end": "2026-08-20",
             "type": "vacation"}]}, role="ops")))
        aid = sdb.q1("SELECT id FROM schedule_absences WHERE employee_id=?", (E["مآثر"],))["id"]
        r = self._run(routes.api_absence_decide(
            self._req({"id": aid, "decision": "approved"}, role="ops")))
        self.assertEqual(r.status, 403)

    def test_pending_shows_in_the_list_flagged(self):
        E = self._ids()
        self._run(routes.api_plan_save(self._req({"employees": [
            {"employee_id": E["مآثر"], "start": "2026-08-20", "end": "2026-08-20",
             "type": "vacation"}]}, role="ops")))
        res = self._run(routes.api_absences(self._req(query={"from": "2026-08-01",
                                                             "to": "2026-09-01"})))
        row = res.data["absences"][0]
        self.assertEqual(row["status"], "pending")
        self.assertTrue(row["needs_decision"])

    # ---------------- the simulation must respect pending too ----------------
    def test_a_pending_leave_is_not_simulated_into_the_board(self):
        E = self._ids()
        self._run(routes.api_plan_save(self._req({"employees": [
            {"employee_id": E["مآثر"], "start": "2026-08-20", "end": "2026-08-21",
             "type": "vacation"}]}, role="ops")))
        res = self._run(routes.api_period(self._req(query={"start": "2026-08-20",
                                                           "end": "2026-08-21"})))
        for d in res.data["period"]["days"]:
            self.assertNotIn("مآثر", [o["name"] for o in d["off"]])


if __name__ == "__main__":
    unittest.main()


class RecoveryOwnerTest(LeaveTypeTest):
    """Recovery excludes «the person who owns the problem» from calling the guest. While the
    permanent owner is on leave that person is whoever actually cleaned — otherwise the
    coverer gets handed the apology call for her own mistake, and the person excluded is
    sitting at home."""

    def test_owner_of_the_problem_is_the_days_coverer(self):
        import bot
        E = self._ids()
        for i, a in enumerate(sdb.apartments()):
            sdb.execute("UPDATE schedule_apartments SET listing_id=? WHERE id=?",
                        (2000 + i, a["id"]))
        apt = sdb.q1("SELECT a.id id, a.listing_id lid, a.name name FROM schedule_apartments a "
                     "JOIN schedule_employees e ON a.owner_id=e.id WHERE e.name='مآثر' LIMIT 1")
        # _recovery_unit_owner reads the REAL clock, so the absence and the pin have to
        # land on the day it will actually look at. A hard-coded date silently stops
        # testing anything the moment it passes.
        today = bot.datetime.now(bot.TZ).date().isoformat()
        self.assertEqual(bot._recovery_unit_owner(lid=apt["lid"]), "مآثر")
        sdb.execute("INSERT INTO schedule_absences(employee_id,start_date,end_date,type,"
                    "status,affects_coverage,created_at) VALUES(?,?,?,?,?,?,?)",
                    (E["مآثر"], today, today, "sick", "approved", 1, sdb.now_iso()))
        sdb.execute("INSERT INTO schedule_date_overrides(date,apartment_id,"
                    "covering_employee_id,created_at) VALUES(?,?,?,?)",
                    (today, apt["id"], E["نورة"], sdb.now_iso()))
        self.assertEqual(bot._recovery_unit_owner(lid=apt["lid"]), "نورة",
                         "the coverer owns the problem that day")

    def test_falls_back_to_the_permanent_owner_when_the_calendar_says_nothing(self):
        import bot
        self.assertIsNone(bot._recovery_unit_owner(lid=999999, name="لا توجد"))


class PublicLeaveStripTest(LeaveTypeTest):
    """«إجازات هذا الأسبوع» on /team-calendar. That link opens with NO login and gets
    forwarded around, so it may carry names and dates and nothing else — the type says
    «مرضية» about a real person and the note is where the actual reason is written."""

    def _strip(self):
        return routes.schedule_week().get("leave") or []

    def test_shows_who_is_out_this_week(self):
        E = self._ids()
        sdb.execute("INSERT INTO schedule_absences(employee_id,start_date,end_date,type,status,"
                    "affects_coverage,note,created_at) VALUES(?,?,?,?,?,?,?,?)",
                    (E["مآثر"], "2026-08-19", "2026-08-20", "sick", "approved", 1,
                     "عملية في المستشفى", sdb.now_iso()))
        rows = self._strip()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "مآثر")
        self.assertEqual(rows[0]["start"], "2026-08-19")

    def test_never_leaks_the_type_or_the_note(self):
        E = self._ids()
        sdb.execute("INSERT INTO schedule_absences(employee_id,start_date,end_date,type,status,"
                    "affects_coverage,note,created_at) VALUES(?,?,?,?,?,?,?,?)",
                    (E["مآثر"], "2026-08-19", "2026-08-20", "sick", "approved", 1,
                     "عملية في المستشفى", sdb.now_iso()))
        blob = str(self._strip())
        for leak in ("sick", "مرضية", "عملية", "المستشفى", "note", "type"):
            self.assertNotIn(leak, blob, "«%s» must never reach the public link" % leak)

    def test_past_leave_is_not_shown(self):
        E = self._ids()
        sdb.execute("INSERT INTO schedule_absences(employee_id,start_date,end_date,type,status,"
                    "affects_coverage,created_at) VALUES(?,?,?,?,?,?,?)",
                    (E["مآثر"], "2026-08-10", "2026-08-12", "vacation", "approved", 1,
                     sdb.now_iso()))
        self.assertEqual(self._strip(), [], "today and forward only")

    def test_pending_and_evening_half_days_are_not_shown(self):
        E = self._ids()
        sdb.execute("INSERT INTO schedule_absences(employee_id,start_date,end_date,type,status,"
                    "affects_coverage,created_at) VALUES(?,?,?,?,?,?,?)",
                    (E["مآثر"], "2026-08-19", "2026-08-19", "vacation", "pending", 1,
                     sdb.now_iso()))
        sdb.execute("INSERT INTO schedule_absences(employee_id,start_date,end_date,type,status,"
                    "affects_coverage,shift,created_at) VALUES(?,?,?,?,?,?,?,?)",
                    (E["نورة"], "2026-08-19", "2026-08-19", "half_day", "approved", 0,
                     "evening", sdb.now_iso()))
        self.assertEqual(self._strip(), [],
                         "an unapproved request is not news, and an evening half-day is not an absence")
