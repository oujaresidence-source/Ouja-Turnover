# -*- coding: utf-8 -*-
"""
«المناوبة» end-to-end on a real (temporary) brain.db with the real Employee Calendar seed.
No Discord, no network — HOST.send is a list and delivery is reported back by hand.

Locked here (the rules that cost somebody money or a guest if they break):
    * tomorrow is published at 12:00, once; weekly days off and leave are respected
    * a night that was never published produces no check and no miss
    * the check button only counts from the person on duty, within 10 minutes
    * 1st miss = alert, 2nd = ONE formal warning in ops_warnings (kind 'oc'), 3rd = alert only
    * an undelivered check, or one spanned by bot downtime, is void — never a miss
    * swaps: only the target answers; accepted = slots rewritten; 15:00 lock expires requests
    * an issue opened 17-24 belongs to whoever is on duty; a claimer from outside is a helper
    * stale / claim-overdue alerts fire once
    * switch OFF = the tick sends nothing
(The ops retirement rule lives in tests/test_oncall_retirement.py.)

Run: python3 -m unittest tests.test_oncall_flow
"""

import datetime
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb                      # noqa: E402
from schedule import db as sdb, seed as sseed    # noqa: E402
from ops import db as odb, engine as oeng         # noqa: E402
from ops.host import HOST as OPS_HOST            # noqa: E402
from oncall import db, notify                    # noqa: E402
from oncall.host import HOST                     # noqa: E402

RIYADH = oeng.tz()
IDS = {"ناصر": "101", "ماذر": "102", "نورة": "103", "محمد اليامي": "104", "عهود": "105"}
SUP = "900"
SAT = datetime.date(2026, 10, 3)     # publish day
SUN = datetime.date(2026, 10, 4)     # the night under test — مآثر's weekly day off (0)


def at(d, hh, mm=0):
    return datetime.datetime(d.year, d.month, d.day, hh, mm, tzinfo=RIYADH)


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="oncalltest_")
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        sdb.reset_init_cache()
        odb.reset_init_cache()
        db.reset_init_cache()
        sseed.seed_if_empty()
        self._env = {k: os.environ.get(k) for k in ("OPS_DISCORD_IDS", "OPS_NAME_ALIASES",
                                                     "OPS_LEAD_ID")}
        os.environ.update({"OPS_DISCORD_IDS": "", "OPS_NAME_ALIASES": "", "OPS_LEAD_ID": ""})
        OPS_HOST.discord_ids = lambda: dict(IDS)
        OPS_HOST.public_base = lambda: "https://ouja.test"
        self.sent = []
        self.clock = at(SAT, 11, 0)
        HOST.send = self.sent.append
        HOST.now = lambda: self.clock
        db.config_set("supervisor_did", SUP)

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    # helpers ---------------------------------------------------------------
    def tick(self, when):
        self.clock = when
        return notify.tick(when)

    def walk(self, start, end):
        """Tick every minute from start to end inclusive, like the real loop (a jump longer
        than 2 minutes between ticks IS bot downtime and voids checks)."""
        t = start
        while t <= end:
            self.tick(t)
            self.deliver_all()
            t += datetime.timedelta(minutes=1)

    def kinds(self):
        return [p["kind"] for p in self.sent]

    def deliver_all(self):
        """Pretend Discord delivered every reported payload, in order, with fake ids."""
        for i, p in enumerate(self.sent):
            r = p.get("report")
            if r and not p.get("_done"):
                notify.delivered(r, True, "dm%d" % i, True, "ch%d" % i)
                p["_done"] = True

    def publish_sunday(self):
        self.tick(at(SAT, 12, 0))
        self.deliver_all()
        return db.slots_for(SUN.isoformat())


class Publish(Case):
    def test_nothing_before_noon(self):
        self.tick(at(SAT, 11, 59))
        self.assertIsNone(db.night(SUN.isoformat()))

    def test_noon_publishes_tomorrow_once_without_the_day_off(self):
        slots = self.publish_sunday()
        names = [s["employee"] for s in slots]
        self.assertEqual(len(slots), 4)
        self.assertNotIn("مآثر", names)                   # Sunday is her weekly day off
        self.assertEqual(sorted((s["end_min"] - s["start_min"]) // 60 for s in slots), [1, 2, 2, 2])
        self.tick(at(SAT, 12, 1))
        self.assertEqual(self.kinds().count("schedule"), 1)
        self.assertEqual(db.night(SUN.isoformat())["message_id"], "ch0")

    def test_ohoud_takes_the_first_slot_every_working_day(self):
        import datetime as _dt
        firsts = {}
        for i in range(7):
            pub = SAT + _dt.timedelta(days=i)
            self.tick(at(pub, 12, 0))
            night = (pub + _dt.timedelta(days=1)).isoformat()
            firsts[night] = db.slots_for(night)[0]["employee"]
        worked = {k: v for k, v in firsts.items()
                  if _dt.date.fromisoformat(k).weekday() != 5}          # her day off: Saturday
        self.assertEqual(set(worked.values()), {"عهود"}, firsts)
        self.assertEqual(len(worked), 6)

    def test_first_slot_can_be_switched_off(self):
        db.config_set("first_slot", "")
        from oncall import engine as E
        names = ["نورة", "ناصر", "محمد اليامي", "عهود"]
        self.assertEqual([x["employee"] for x in self.publish_sunday()],
                         [x["employee"] for x in E.build_night(SUN, names, [])])

    def test_unlinked_person_is_left_out_and_supervisor_told(self):
        del IDS["عهود"]
        try:
            slots = self.publish_sunday()
        finally:
            IDS["عهود"] = "105"
        self.assertNotIn("عهود", [s["employee"] for s in slots])
        sup = [p for p in self.sent if p["kind"] == "supervisor"]
        self.assertEqual(sup[0]["dm"][0]["did"], SUP)
        self.assertIn("عهود", sup[0]["dm"][0]["text"])

    def test_leave_respected_but_morning_half_day_still_on_tonight(self):
        emps = {e["name"]: e["id"] for e in sdb.employees()}
        sdb.execute("INSERT INTO schedule_absences(employee_id,start_date,end_date,type,status,"
                    "shift,affects_coverage) VALUES(?,?,?,?,?,?,?)",
                    (emps["ناصر"], SUN.isoformat(), SUN.isoformat(), "annual", "approved", None, 1))
        sdb.execute("INSERT INTO schedule_absences(employee_id,start_date,end_date,type,status,"
                    "shift,affects_coverage) VALUES(?,?,?,?,?,?,?)",
                    (emps["نورة"], SUN.isoformat(), SUN.isoformat(), "half_day", "approved",
                     "morning", 1))
        sdb.execute("INSERT INTO schedule_absences(employee_id,start_date,end_date,type,status,"
                    "shift,affects_coverage) VALUES(?,?,?,?,?,?,?)",
                    (emps["عهود"], SUN.isoformat(), SUN.isoformat(), "half_day", "approved",
                     "evening", 0))
        names = [s["employee"] for s in self.publish_sunday()]
        self.assertNotIn("ناصر", names)
        self.assertNotIn("عهود", names)
        self.assertIn("نورة", names)


class Checks(Case):
    def first_slot(self):
        return self.publish_sunday()[0]

    def test_no_night_no_checks(self):
        self.tick(at(SUN, 17, 0))
        self.assertEqual(db.checks_on(SUN.isoformat()), [])

    def test_check_at_slot_start_and_answer(self):
        s = self.first_slot()
        self.tick(at(SUN, 17, 0))
        self.assertEqual(self.kinds().count("check"), 1)
        self.deliver_all()
        c = db.checks_on(SUN.isoformat())[0]
        code, _t = notify.answer_check(c["dm_message_id"], "999", at(SUN, 17, 2))
        self.assertEqual(code, "not_yours")
        code, _t = notify.answer_check(c["ch_message_id"], s["employee_did"], at(SUN, 17, 3))
        self.assertEqual(code, "answered")
        self.tick(at(SUN, 17, 11))
        self.assertEqual(db.check(c["id"])["status"], "answered")
        self.assertNotIn("miss", self.kinds())

    def test_reminder_fifteen_minutes_before(self):
        self.first_slot()
        self.tick(at(SUN, 16, 45))
        self.tick(at(SUN, 16, 46))
        self.assertEqual(self.kinds().count("reminder"), 1)

    def _miss_one(self, hh, mm):
        self.walk(at(SUN, hh, mm), at(SUN, hh, mm + 10))

    def test_two_misses_one_warning_three_misses_still_one(self):
        s = self.first_slot()
        self.assertEqual(s["end_min"] - s["start_min"], 120)        # 17:00-19:00
        self._miss_one(17, 0)
        self.assertEqual(odb.counts()["ops_warnings"], 0)
        self.assertEqual(self.kinds().count("miss"), 1)
        self._miss_one(17, 15)
        ws = odb.warnings_for(s["employee"], "active")
        self.assertEqual(len(ws), 1)
        self.assertEqual(odb.obligation(ws[0]["obligation_id"])["kind"], "oc")
        self.assertIn("warning", self.kinds())
        led = odb.q1("SELECT * FROM ops_commission_ledger WHERE employee=?", (s["employee"],))
        self.assertEqual(led["multiplier"], 0.9)
        self._miss_one(17, 30)
        self.assertEqual(len(odb.warnings_for(s["employee"])), 1)
        self.assertEqual(self.kinds().count("miss"), 3)

    def test_late_press_is_still_a_miss(self):
        s = self.first_slot()
        self._miss_one(17, 0)
        c = db.checks_on(SUN.isoformat())[0]
        code, _t = notify.answer_check(c["dm_message_id"], s["employee_did"], at(SUN, 17, 12))
        self.assertEqual(code, "late")
        self.assertEqual(db.check(c["id"])["status"], "late")

    def test_undelivered_check_is_void(self):
        self.first_slot()
        self.tick(at(SUN, 17, 0))                  # never delivered
        self.tick(at(SUN, 17, 1))
        self.tick(at(SUN, 17, 11))
        c = db.checks_on(SUN.isoformat())[0]
        self.assertEqual((c["status"], c["void_reason"]), ("voided", "not_delivered"))
        self.assertNotIn("miss", self.kinds())

    def test_bot_downtime_voids_and_never_warns(self):
        self.first_slot()
        self.tick(at(SUN, 17, 0))
        self.deliver_all()
        self.tick(at(SUN, 17, 1))
        self.tick(at(SUN, 17, 20))                # 19 minutes of silence = a redeploy
        rows = {c["due_at"][11:16]: c for c in db.checks_on(SUN.isoformat())}
        self.assertEqual(rows["17:00"]["status"], "voided")
        self.assertEqual(rows["17:00"]["void_reason"], "bot_down")
        self.assertEqual(rows["17:15"]["status"], "voided")        # never sent at all
        self.assertNotIn("miss", self.kinds())

    def test_switch_off_sends_nothing(self):
        self.first_slot()
        notify.set_enabled(False, "tester", at(SUN, 16, 0))
        n = len(self.sent)
        self.tick(at(SUN, 17, 0))
        self.assertEqual(len(self.sent), n)


class Swaps(Case):
    def setUp(self):
        super().setUp()
        self.slots = self.publish_sunday()
        self.a, self.b = self.slots[0], self.slots[1]

    def test_exchange_accept(self):
        ok, _t = notify.request_swap(self.a["id"], self.b["employee_did"], at(SAT, 13, 0))
        self.assertTrue(ok)
        self.deliver_all()
        sw = db.q1("SELECT * FROM oncall_swaps")
        ok, _t = notify.answer_swap(sw["message_id"], "999", True, at(SAT, 13, 5))
        self.assertFalse(ok)                                   # only the target answers
        ok, _t = notify.answer_swap(sw["message_id"], self.a["employee_did"], True, at(SAT, 13, 6))
        self.assertTrue(ok)
        self.assertEqual(db.slot(self.a["id"])["employee"], self.b["employee"])
        self.assertEqual(db.slot(self.b["id"])["employee"], self.a["employee"])
        self.assertIn("schedule_edit", self.kinds())

    def test_own_slot_refused(self):
        ok, _t = notify.request_swap(self.a["id"], self.a["employee_did"], at(SAT, 13, 0))
        self.assertFalse(ok)

    def test_lock_expires_pending_and_refuses_new(self):
        notify.request_swap(self.a["id"], self.b["employee_did"], at(SAT, 13, 0))
        self.tick(at(SUN, 15, 0))
        self.assertEqual(db.night(SUN.isoformat())["status"], "locked")
        self.assertEqual(db.q1("SELECT status FROM oncall_swaps")["status"], "expired")
        ok, _t = notify.request_swap(self.a["id"], self.b["employee_did"], at(SUN, 15, 1))
        self.assertFalse(ok)

    def test_editor_reassign_needs_reason(self):
        ok, err = notify.edit_slot(self.a["id"], "مآثر", "اسيل", "", at(SUN, 16, 0))
        self.assertFalse(ok)
        ok, err = notify.edit_slot(self.a["id"], "مآثر", "اسيل", "تغطية", at(SUN, 16, 0))
        self.assertTrue(ok, err)
        self.assertEqual(db.slot(self.a["id"])["employee"], "مآثر")


class Issues(Case):
    def setUp(self):
        super().setUp()
        self.slots = self.publish_sunday()
        self.first = self.slots[0]                             # 17:00-19:00

    def test_outside_window_nobody_owns(self):
        self.assertIsNone(notify.on_issue_opened("escalation", "m1", "ضيف", at(SUN, 16, 30)))

    def test_owner_is_whoever_is_on_duty(self):
        r = notify.on_issue_opened("escalation", "m1", "ضيف", at(SUN, 17, 30))
        self.assertEqual(r["owner"], self.first["employee"])
        self.assertIsNone(notify.on_issue_opened("escalation", "m1", "ضيف", at(SUN, 17, 31)))

    def test_outside_claimer_is_helper_owner_stays(self):
        notify.on_issue_opened("escalation", "m1", "ضيف", at(SUN, 17, 30))
        notify.on_escalation_claimed("m1", "اسيل", at(SUN, 17, 35))
        i = db.issue_by_ref("m1")
        self.assertEqual((i["owner"], i["helper"]), (self.first["employee"], "اسيل"))

    def test_claim_overdue_alert_once(self):
        notify.on_issue_opened("escalation", "m1", "ضيف", at(SUN, 17, 30))
        self.tick(at(SUN, 17, 40))
        self.tick(at(SUN, 17, 41))
        self.assertEqual(self.kinds().count("claim_overdue"), 1)

    def test_stale_after_slot_end_once(self):
        notify.on_issue_opened("maint", "ch9", "تسريب", at(SUN, 18, 0))
        self.tick(at(SUN, 18, 50))
        self.assertNotIn("stale", self.kinds())
        self.tick(at(SUN, 19, 0))
        self.tick(at(SUN, 19, 40))
        self.assertEqual(self.kinds().count("stale"), 1)

    def test_resolve_permissions(self):
        notify.on_issue_opened("escalation", "m1", "ضيف", at(SUN, 17, 30))
        notify.delivered({"what": "issue_note", "id": "m1"}, False, "", True, "note1")
        ok, _t = notify.resolve_press("note1", "999", False, at(SUN, 17, 50))
        self.assertFalse(ok)
        ok, _t = notify.resolve_press("note1", self.first["employee_did"], False, at(SUN, 17, 51))
        self.assertTrue(ok)
        self.assertIsNotNone(db.issue_by_ref("m1")["resolved_at"])

    def test_handover_and_summary(self):
        notify.on_issue_opened("escalation", "m1", "ضيف", at(SUN, 17, 30))
        self.tick(at(SUN, 19, 0))
        ho = [p for p in self.sent if p["kind"] == "handover"]
        self.assertEqual(len(ho), 1)
        self.assertIn("ضيف", ho[0]["channel_text"])
        self.tick(at(SUN + datetime.timedelta(days=1), 0, 5))
        self.tick(at(SUN + datetime.timedelta(days=1), 0, 6))
        self.assertEqual(self.kinds().count("summary"), 1)


if __name__ == "__main__":
    unittest.main()
