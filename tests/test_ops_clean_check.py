# -*- coding: utf-8 -*-
"""
«القفل» — ONE question per turnover, asked once, after its moment has passed.

The rules being locked:
    * nothing is sent BEFORE check-in time — being nudged early is nagging, not help
    * a turnover with NO check-in today triggers at DAILY_CHECK_HOUR instead. This one is a
      regression guard: those apartments were getting no reminder at all after the old
      shared-room loop was superseded.
    * «نعم» without photos is refused; «لا» without a reason is refused
    * answering «لا» tells the lead which unit and why
    * one message only — no repeats
    * quiet-hours reassignment still applies and creates NO warning

Run: python3 -m unittest tests.test_ops_clean_check
"""

import datetime
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb                        # noqa: E402
from ops import db, engine, turnover, switch       # noqa: E402
from ops.host import HOST                          # noqa: E402

RIYADH = engine.tz()
WID = "12345:2026-08-03"


def at(d, hh, mm=0):
    return datetime.datetime(2026, 8, d, hh, mm, tzinfo=RIYADH)


class CleanCase(unittest.TestCase):
    ENV = {"CLEAN_CHECK_ENABLED": "1", "CLEAN_CHECK_DRYRUN": "0",
           "DAILY_CHECK_HOUR": "16", "NUDGE_QUIET_START": "0", "NUDGE_QUIET_END": "6"}

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="opsclean_")
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        db.reset_init_cache()
        switch.invalidate()
        self.sent = []
        self.photos = False
        self.done = False
        self.item = {"work_item_id": WID, "unit": "Ouja | الملقا 1", "date": "2026-08-03",
                     "employee": "ناصر", "employee_did": "111",
                     "checkin_at": at(3, 15, 0), "backup": {"name": "نورة", "did": "333"}}
        HOST.notify = self.sent.append
        HOST.turnover_items = lambda: [dict(self.item, photos=self.photos, done=self.done)]
        HOST.has_photos = lambda wid: self.photos
        HOST.public_base = lambda: "https://ouja.test"
        self._saved = {k: os.environ.get(k) for k in self.ENV}
        os.environ.update(self.ENV)

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        switch.invalidate()

    def kinds(self):
        return [p.get("kind") for p in self.sent]


class TestWhenTheQuestionIsAsked(CleanCase):

    def test_nothing_before_check_in(self):
        for now in (at(3, 9, 0), at(3, 12, 0), at(3, 14, 59)):
            r = turnover.tick(now=now)
            self.assertEqual(r["asked"], [], now)
        self.assertEqual(self.sent, [])

    def test_it_asks_the_moment_check_in_passes(self):
        r = turnover.tick(now=at(3, 15, 1))
        self.assertEqual([a["employee"] for a in r["asked"]], ["ناصر"])
        self.assertIn("هل تم تنظيف الشقة؟", self.sent[0]["text"])
        self.assertIn("15:00", self.sent[0]["text"])

    def test_no_check_in_today_triggers_at_the_daily_hour(self):
        """The regression guard: these apartments were getting nothing at all."""
        self.item["checkin_at"] = None
        self.assertEqual(turnover.tick(now=at(3, 15, 30))["asked"], [])   # before 16:00
        r = turnover.tick(now=at(3, 16, 1))
        self.assertEqual([a["employee"] for a in r["asked"]], ["ناصر"])
        self.assertIn("المراجعة اليومية", self.sent[0]["text"])

    def test_the_daily_hour_is_configurable(self):
        self.item["checkin_at"] = None
        os.environ["DAILY_CHECK_HOUR"] = "18"
        self.assertEqual(turnover.tick(now=at(3, 16, 30))["asked"], [])
        self.assertEqual(len(turnover.tick(now=at(3, 18, 1))["asked"]), 1)

    def test_a_late_check_in_shifts_the_question(self):
        self.item["checkin_at"] = at(3, 21, 0)
        self.assertEqual(turnover.tick(now=at(3, 16, 30))["asked"], [])
        self.assertEqual(len(turnover.tick(now=at(3, 21, 1))["asked"]), 1)

    def test_a_finished_turnover_is_never_asked_about(self):
        self.done = True
        r = turnover.tick(now=at(3, 15, 1))
        self.assertEqual(r["asked"], [])
        self.assertEqual(self.sent, [])


class TestOneMessageOnly(CleanCase):

    def test_ten_ticks_produce_one_question(self):
        for m in range(1, 40, 2):
            turnover.tick(now=at(3, 16, m))
        self.assertEqual(len([p for p in self.sent if p.get("kind") == "clean_check"]), 1)
        self.assertEqual(db.counts()["ops_clean_checks"], 1)

    def test_no_repeats_after_an_answer(self):
        turnover.tick(now=at(3, 15, 1))
        self.photos = True
        turnover.answer_yes(WID, "ناصر")
        before = len(self.sent)
        for h in (16, 17, 18, 20):
            turnover.tick(now=at(3, h, 0))
        self.assertEqual(len(self.sent), before)

    def test_the_question_survives_a_restart_without_repeating(self):
        turnover.tick(now=at(3, 15, 1))
        db.reset_init_cache()
        turnover.tick(now=at(3, 15, 30))
        self.assertEqual(db.counts()["ops_clean_checks"], 1)


class TestYes(CleanCase):

    def test_yes_without_photos_is_refused(self):
        turnover.tick(now=at(3, 15, 1))
        r = turnover.answer_yes(WID, "ناصر")
        self.assertFalse(r["ok"])
        self.assertTrue(r["need_photos"])
        self.assertIsNone(db.clean_check(WID)["answered_at"])

    def test_yes_works_once_photos_exist(self):
        turnover.tick(now=at(3, 15, 1))
        self.photos = True
        r = turnover.answer_yes(WID, "ناصر")
        self.assertTrue(r["ok"])
        row = db.clean_check(WID)
        self.assertEqual(row["answer"], "yes")
        self.assertTrue(row["answered_at"])

    def test_the_question_offers_the_upload_while_photos_are_missing(self):
        turnover.tick(now=at(3, 15, 1))
        self.assertIn("الصور ما وصلت", self.sent[0]["text"])
        self.assertFalse(self.sent[0]["can_ack"])

    def test_the_first_answer_wins(self):
        turnover.tick(now=at(3, 15, 1))
        self.photos = True
        turnover.answer_yes(WID, "ناصر")
        r = turnover.answer_no(WID, "ناصر", "team_missing")
        self.assertFalse(r["ok"])
        self.assertEqual(db.clean_check(WID)["answer"], "yes")


class TestNo(CleanCase):

    def test_no_without_a_reason_is_refused(self):
        turnover.tick(now=at(3, 15, 1))
        for bad in (None, "", "   ", "not_a_code"):
            r = turnover.answer_no(WID, "ناصر", bad)
            self.assertFalse(r["ok"], bad)
            self.assertTrue(r["need_reason"])
        self.assertIsNone(db.clean_check(WID)["answered_at"])

    def test_other_needs_the_free_text(self):
        turnover.tick(now=at(3, 15, 1))
        self.assertFalse(turnover.answer_no(WID, "ناصر", "other", "")["ok"])
        self.assertTrue(turnover.answer_no(WID, "ناصر", "other", "الكهرب مقطوع")["ok"])
        self.assertEqual(db.clean_check(WID)["reason_text"], "الكهرب مقطوع")

    def test_a_quick_reason_is_stored(self):
        turnover.tick(now=at(3, 15, 1))
        r = turnover.answer_no(WID, "ناصر", "team_missing")
        self.assertTrue(r["ok"])
        row = db.clean_check(WID)
        self.assertEqual(row["answer"], "no")
        self.assertEqual(row["reason_code"], "team_missing")

    def test_answering_no_tells_the_lead_the_unit_and_the_reason(self):
        turnover.tick(now=at(3, 15, 1))
        turnover.answer_no(WID, "ناصر", "no_supplies")
        lead = [p for p in self.sent if p.get("kind") == "clean_problem"]
        self.assertEqual(len(lead), 1)
        self.assertIn("الملقا", lead[0]["lead_text"])
        self.assertIn("نقص أدوات", lead[0]["lead_text"])
        self.assertIn("ناصر", lead[0]["lead_text"])

    def test_all_five_reasons_are_offered(self):
        codes = [c for c, _ in engine.REASONS]
        self.assertEqual(codes, ["team_missing", "not_vacant", "unit_problem",
                                 "no_supplies", "other"])


class TestTheReasonsView(CleanCase):

    def test_reasons_are_grouped_by_count(self):
        for i, code in enumerate(["team_missing", "team_missing", "no_supplies"]):
            wid = "u%d:2026-08-03" % i
            db.open_clean_check({"work_item_id": wid, "unit": "u%d" % i,
                                 "responsible": "ناصر", "responsible_did": "1",
                                 "day_key": "2026-08-03", "month_key": "2026-08"})
            db.answer_clean_check(wid, "no", code, "")
        st = turnover.state("2026-08-03")
        self.assertEqual(st["reasons"][0]["code"], "team_missing")
        self.assertEqual(st["reasons"][0]["n"], 2)
        self.assertEqual(st["reasons"][0]["label"], "الفريق ما وصل")

    def test_the_totals_line_counts_silence_too(self):
        turnover.tick(now=at(3, 15, 1))
        st = turnover.state("2026-08-03")
        self.assertEqual(st["totals"]["asked"], 1)
        self.assertEqual(st["totals"]["silent"], 1)


class TestSleepProtection(CleanCase):
    """Being asleep at 3 AM is not misconduct."""

    def setUp(self):
        super().setUp()
        self.item["checkin_at"] = at(4, 1, 0)
        self.item["date"] = "2026-08-04"
        global WID

    def test_two_unanswered_night_asks_reassign_and_never_warn(self):
        wid = self.item["work_item_id"]
        turnover.tick(now=at(4, 1, 1))                      # the one question, at 01:00
        db.open_clean_check({"work_item_id": "other:2026-08-04", "unit": "x",
                             "responsible": "ناصر", "responsible_did": "111",
                             "asked_at": at(4, 2, 0).isoformat(timespec="seconds"),
                             "day_key": "2026-08-04", "month_key": "2026-08"})
        r = turnover.tick(now=at(4, 3, 0))                  # still quiet, two unanswered
        self.assertEqual([a["employee"] for a in r["asleep"]], ["ناصر"])
        row = db.clean_check(wid)
        self.assertEqual(row["reassigned_to"], "نورة")
        self.assertEqual(row["reassigned_reason"], "reassigned_asleep")
        c = db.counts()
        self.assertEqual(c["ops_warnings"], 0)
        self.assertEqual(c["ops_obligations"], 0)

    def test_the_backup_and_the_lead_are_told(self):
        turnover.tick(now=at(4, 1, 1))
        db.open_clean_check({"work_item_id": "other:2026-08-04", "unit": "x",
                             "responsible": "ناصر", "responsible_did": "111",
                             "asked_at": at(4, 2, 0).isoformat(timespec="seconds"),
                             "day_key": "2026-08-04", "month_key": "2026-08"})
        turnover.tick(now=at(4, 3, 0))
        msg = [p for p in self.sent if p.get("kind") == "clean_asleep"][0]
        self.assertEqual(msg["employee"], "نورة")
        self.assertIn("ما انسجل عليه أي إنذار", msg["lead_text"])

    def test_daylight_silence_never_reassigns(self):
        self.item["checkin_at"] = at(3, 15, 0)
        self.item["date"] = "2026-08-03"
        turnover.tick(now=at(3, 15, 1))
        turnover.tick(now=at(3, 18, 0))
        self.assertIsNone(db.clean_check(WID)["reassigned_to"])


class TestDryRun(CleanCase):
    ENV = dict(CleanCase.ENV, CLEAN_CHECK_DRYRUN="1")

    def test_it_asks_nobody_and_logs_everything(self):
        turnover.tick(now=at(3, 15, 1))
        self.assertEqual(self.sent, [])
        self.assertGreater(db.counts()["ops_dryrun_log"], 0)
        self.assertEqual(db.counts()["ops_clean_checks"], 1)


class TestItCannotWarnAnybody(unittest.TestCase):
    def test_the_module_never_touches_warnings(self):
        import inspect
        src = inspect.getsource(turnover)
        for forbidden in ("issue_warning", "deadline_decision", "compute_multiplier",
                          "ops_warnings"):
            self.assertNotIn(forbidden, src, forbidden)


if __name__ == "__main__":
    unittest.main()
