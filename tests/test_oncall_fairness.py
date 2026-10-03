# -*- coding: utf-8 -*-
"""
«المناوبة» — the unfair-warning paths the final review found, one test each.

Money is at stake: every path here used to end in a miss (and, twice, a formal warning with
a commission cut) for something the employee did not do. Plus the health of a system that
runs every night: issues that never close, a night that cannot be repaired.

Run: python3 -m unittest tests.test_oncall_fairness
"""

import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ops import db as odb                                        # noqa: E402
from schedule import db as sdb                                   # noqa: E402
from oncall import db, engine, notify, routes                    # noqa: E402
from tests.test_oncall_flow import Case, SUN, IDS, at            # noqa: E402


def mins(t, n):
    return t + datetime.timedelta(minutes=n)


class Fairness(Case):
    def setUp(self):
        super().setUp()
        self.slots = self.publish_sunday()
        self.first = self.slots[0]                                # 17:00-19:00

    def checks(self):
        return {c["due_at"][11:16]: c for c in db.checks_on(SUN.isoformat())}

    # --- Critical #1: the button must never judge -----------------------------------------
    def test_press_after_a_restart_before_the_first_tick_is_never_a_miss(self):
        self.walk(at(SUN, 17, 0), at(SUN, 17, 5))                # delivered, bot then goes down
        c = self.checks()["17:00"]
        code, _t = notify.answer_check(c["dm_message_id"], self.first["employee_did"], at(SUN, 17, 12))
        self.assertEqual(code, "late_noted")
        self.assertEqual(db.check(c["id"])["status"], "pending")  # the button decided nothing
        self.assertNotIn("miss", self.kinds())
        self.tick(at(SUN, 17, 13))                                # first tick after the restart
        self.assertEqual(db.check(c["id"])["status"], "voided")
        self.assertEqual(odb.counts()["ops_warnings"], 0)

    def test_a_genuine_late_press_is_recorded_as_late_by_the_tick(self):
        self.walk(at(SUN, 17, 0), at(SUN, 17, 10))
        c = self.checks()["17:00"]
        self.assertEqual(db.check(c["id"])["status"], "missed")
        code, _t = notify.answer_check(c["dm_message_id"], self.first["employee_did"], at(SUN, 17, 11))
        self.assertEqual(code, "late")
        self.assertEqual(db.check(c["id"])["status"], "late")

    def test_press_past_deadline_still_pending_becomes_late_when_judged(self):
        self.walk(at(SUN, 17, 0), at(SUN, 17, 9))
        c = self.checks()["17:00"]
        notify.answer_check(c["dm_message_id"], self.first["employee_did"], at(SUN, 17, 10, ) + datetime.timedelta(seconds=30))
        self.walk(at(SUN, 17, 10), at(SUN, 17, 11))
        self.assertEqual(db.check(c["id"])["status"], "late")

    # --- #2 switch OFF -> ON ---------------------------------------------------------------
    def test_switching_off_voids_what_was_pending(self):
        self.walk(at(SUN, 17, 0), at(SUN, 17, 3))
        notify.set_enabled(False, "اسيل", at(SUN, 17, 3))
        notify.set_enabled(True, "اسيل", at(SUN, 17, 40))
        self.walk(at(SUN, 17, 41), at(SUN, 17, 42))
        self.assertEqual(self.checks()["17:00"]["status"], "voided")
        self.assertEqual(self.checks()["17:00"]["void_reason"], "switched_off")
        self.assertNotIn("miss", self.kinds())

    # --- #3 leave recorded after publish ---------------------------------------------------
    def test_leave_approved_on_the_day_voids_checks_and_tells_the_supervisor(self):
        emp = {e["name"]: e["id"] for e in sdb.employees()}[self.first["employee"]]
        sdb.execute("INSERT INTO schedule_absences(employee_id,start_date,end_date,type,status,"
                    "shift,affects_coverage) VALUES(?,?,?,?,?,?,?)",
                    (emp, SUN.isoformat(), SUN.isoformat(), "sick", "approved", None, 1))
        self.walk(at(SUN, 17, 0), at(SUN, 17, 26))
        rows = self.checks()
        self.assertEqual({rows[k]["void_reason"] for k in ("17:00", "17:15")}, {"on_leave"})
        self.assertNotIn("miss", self.kinds())
        self.assertEqual(self.kinds().count("slot_on_leave"), 1)

    def test_leave_recorded_after_a_check_was_sent_voids_it_at_judging(self):
        self.walk(at(SUN, 17, 0), at(SUN, 17, 5))
        emp = {e["name"]: e["id"] for e in sdb.employees()}[self.first["employee"]]
        sdb.execute("INSERT INTO schedule_absences(employee_id,start_date,end_date,type,status,"
                    "shift,affects_coverage) VALUES(?,?,?,?,?,?,?)",
                    (emp, SUN.isoformat(), SUN.isoformat(), "sick", "approved", None, 1))
        self.walk(at(SUN, 17, 6), at(SUN, 17, 11))
        self.assertEqual(self.checks()["17:00"]["void_reason"], "on_leave")

    # --- #4 mid-shift reassignment ---------------------------------------------------------
    def test_reassigning_mid_shift_voids_the_outgoing_persons_pending_check(self):
        self.walk(at(SUN, 17, 15), at(SUN, 17, 20))
        c = self.checks()["17:15"]
        ok, err = notify.edit_slot(self.first["id"], "مآثر", "اسيل", "تغطية", at(SUN, 17, 20))
        self.assertTrue(ok, err)
        self.walk(at(SUN, 17, 21), at(SUN, 17, 26))
        self.assertEqual((db.check(c["id"])["status"], db.check(c["id"])["void_reason"]),
                         ("voided", "reassigned"))
        self.assertEqual(odb.counts()["ops_warnings"], 0)

    # --- #5 corrected Discord id -----------------------------------------------------------
    def test_corrected_discord_id_is_used_and_accepted(self):
        old = IDS[self.first["employee"] if self.first["employee"] != "مآثر" else "ماذر"]
        key = self.first["employee"] if self.first["employee"] in IDS else "ماذر"
        IDS[key] = "777"
        try:
            self.walk(at(SUN, 17, 0), at(SUN, 17, 1))
            c = self.checks()["17:00"]
            self.assertEqual(c["employee_did"], "777")
            code, _t = notify.answer_check(c["dm_message_id"], "777", at(SUN, 17, 2))
            self.assertEqual(code, "answered")
        finally:
            IDS[key] = old

    # --- #6 the press time is the press, not the worker thread -----------------------------
    def test_check_found_by_id_before_the_delivery_report(self):
        self.tick(at(SUN, 17, 0))                       # sent, delivery not reported yet
        c = self.checks()["17:00"]
        code, _t = notify.answer_check_id(c["id"], self.first["employee_did"], at(SUN, 17, 1))
        self.assertEqual(code, "answered")

    # --- #7 issues that never close, lists that never stop growing -------------------------
    def test_claimed_issue_auto_closes_after_two_days(self):
        notify.on_issue_opened("escalation", "m1", "ضيف", at(SUN, 17, 30))
        notify.on_escalation_claimed("m1", "نوره", at(SUN, 17, 31))
        later = SUN + datetime.timedelta(days=2)
        self.tick(at(later, 17, 31))
        self.assertIsNotNone(db.issue_by_ref("m1")["resolved_at"])

    def test_handover_lists_at_most_ten_issues(self):
        for i in range(25):
            notify.on_issue_opened("escalation", "m%d" % i, "ضيف %d" % i, at(SUN, 17, 30))
        self.tick(at(SUN, 19, 0))
        ho = [p for p in self.sent if p["kind"] == "handover"][0]["channel_text"]
        self.assertLessEqual(ho.count("• "), 10)
        self.assertIn("١٥", ho)                             # «و١٥ غيرها»
        self.assertLess(len(ho), 1900)


class Capacity(Case):
    # --- #8 more than 7 people -------------------------------------------------------------
    def test_more_than_seven_available_keeps_seven_whole_hours(self):
        names = ["a%d" % i for i in range(9)]
        s = engine.build_night(SUN, names, [])
        self.assertEqual(len(s), 7)
        self.assertEqual(s[-1]["end_min"], 420)
        self.assertEqual(sorted({x["start_min"] for x in s}), list(range(0, 420, 60)))

    # --- #9 roster read failure / repair ---------------------------------------------------
    def test_roster_read_failure_does_not_publish_an_empty_night(self):
        """The calendar read for the PEOPLE works, the one behind the Discord ids (ops reads
        the calendar again) fails transiently: that used to look like «everyone unlinked»
        and burn an empty night for good."""
        import schedule.owners as so
        real, calls = so.permanent_map, {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] >= 2:
                raise RuntimeError("database is locked")
            return real()
        so.permanent_map = flaky
        try:
            self.tick(at(SUN - datetime.timedelta(days=1), 12, 0))
        finally:
            so.permanent_map = real
        self.assertIsNone(db.night(SUN.isoformat()))       # not burned — retried next minute
        self.tick(at(SUN - datetime.timedelta(days=1), 12, 1))
        self.assertEqual(len(db.slots_for(SUN.isoformat())), 4)

    def test_editor_can_rebuild_a_night_before_any_check(self):
        self.publish_sunday()
        ok, err = notify.rebuild_night(SUN.isoformat(), "اسيل", at(SUN, 16, 0))
        self.assertTrue(ok, err)
        self.assertTrue(db.slots_for(SUN.isoformat()))
        self.walk(at(SUN, 17, 0), at(SUN, 17, 1))
        ok, err = notify.rebuild_night(SUN.isoformat(), "اسيل", at(SUN, 17, 2))
        self.assertFalse(ok)
        self.assertTrue(routes.state_payload(at(SUN, 12, 0))["tonight"]["slots"])

    # --- #10 the calendar's spelling wins --------------------------------------------------
    def test_roster_typed_with_another_spelling_stores_the_calendar_name(self):
        import json
        db.config_set("roster", json.dumps(["نوره", "ناصر", "محمد اليامي"], ensure_ascii=False))
        names = {s["employee"] for s in self.publish_sunday()}
        self.assertIn("نورة", names)
        self.assertNotIn("نوره", names)


if __name__ == "__main__":
    unittest.main()
