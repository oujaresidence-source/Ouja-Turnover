# -*- coding: utf-8 -*-
"""
Phase 2 «القفل» lifecycle, on a real (temporary) brain.db. No Discord, no network.

The rules being locked here:
    * ladder times come from the BOOKING's check-in, not the wall clock
    * escalation EDITS the stored message id instead of sending a new message
    * «✅ جاهزة» is refused when no cleaning photo exists for that unit+date
    * two missed nudges in the quiet window reassign the unit and generate NO warning
    * dry-run sends nothing

Run: python3 -m unittest tests.test_ops_turnover
"""

import datetime
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb                          # noqa: E402
from ops import db, engine, turnover                 # noqa: E402
from ops.host import HOST                            # noqa: E402

RIYADH = engine.tz()
WID = "12345:2026-08-03"


def at(d, hh, mm=0):
    return datetime.datetime(2026, 8, d, hh, mm, tzinfo=RIYADH)


class TurnoverCase(unittest.TestCase):

    ENV = {"NUDGE_ENABLED": "1", "NUDGE_DRYRUN": "0",
           "NUDGE_QUIET_START": "0", "NUDGE_QUIET_END": "6"}

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="opsnudge_")
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        db.reset_init_cache()

        self.sent = []
        self.photos = False
        self.done = False
        self.item = {
            "work_item_id": WID, "unit": "Ouja | الملقا 1", "date": "2026-08-03",
            "employee": "ناصر", "employee_did": "111", "checkin_at": at(3, 15, 0),
            "backup": {"name": "نورة", "did": "333"},
        }
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

    def kinds(self):
        return [p.get("kind") for p in self.sent]

    def ops_of(self, kind="nudge"):
        return [p.get("op") for p in self.sent if p.get("kind") == kind]

    def give_message_id(self, mid="msg-1", when=None):
        """Stand in for bot.py reporting back the id of the message it posted."""
        db.set_nudge_message(WID, "dm", "chan-1", mid, at=when)


class TestTheLadderFollowsTheBooking(TurnoverCase):

    def test_nothing_happens_more_than_three_hours_out(self):
        r = turnover.tick(now=at(3, 11, 0))
        self.assertEqual(r["nudged"], [])
        self.assertEqual(self.sent, [])

    def test_l1_fires_three_hours_before_the_guest(self):
        r = turnover.tick(now=at(3, 12, 1))
        self.assertEqual([n["level"] for n in r["nudged"]], ["L1"])
        self.assertIn("15:00", self.sent[0]["text"])

    def test_a_later_check_in_shifts_everything(self):
        """Wall-clock 12:00 nudges a 15:00 arrival but must NOT nudge a 20:00 one."""
        self.item["checkin_at"] = at(3, 20, 0)
        self.assertEqual(turnover.tick(now=at(3, 12, 1))["nudged"], [])
        self.assertEqual([n["level"] for n in turnover.tick(now=at(3, 17, 1))["nudged"]], ["L1"])

    def test_no_check_in_means_total_silence(self):
        self.item["checkin_at"] = None
        r = turnover.tick(now=at(3, 15, 0))
        self.assertEqual(r["nudged"], [])
        self.assertEqual(self.sent, [])
        self.assertEqual(r["skipped"][0]["why"], "no check-in today")

    def test_each_level_fires_once(self):
        turnover.tick(now=at(3, 12, 1))
        self.assertEqual(turnover.tick(now=at(3, 12, 30))["nudged"], [])
        self.assertEqual(db.nudge_levels_sent(WID), ["L1"])

    def test_the_full_ladder_in_order(self):
        seen = []
        for now in (at(3, 12, 1), at(3, 14, 1), at(3, 15, 1), at(3, 15, 21), at(3, 15, 41)):
            seen += [n["level"] for n in turnover.tick(now=now)["nudged"]]
        self.assertEqual(seen, ["L1", "L2", "L3", "L4", "L5"])


class TestOneMessageEditedInPlace(TurnoverCase):
    """The non-negotiable: escalate by CONTENT, not by volume."""

    def test_the_first_nudge_is_a_new_message_and_the_second_is_an_edit(self):
        turnover.tick(now=at(3, 12, 1))                 # L1 -> nothing to edit yet
        self.assertEqual(self.ops_of(), ["send"])
        self.give_message_id()
        turnover.tick(now=at(3, 14, 1))                 # L2 -> edit
        self.assertEqual(self.ops_of(), ["send", "edit"])

    def test_escalation_carries_the_stored_message_id(self):
        turnover.tick(now=at(3, 12, 1))
        self.give_message_id("msg-42")
        turnover.tick(now=at(3, 14, 1))
        edit = [p for p in self.sent if p.get("op") == "edit"][0]
        self.assertEqual(edit["message_id"], "msg-42")
        self.assertEqual(edit["channel_id"], "chan-1")

    def test_only_l3_and_l5_are_allowed_to_buzz_a_phone(self):
        ops = {}
        for lvl, now in (("L1", at(3, 12, 1)), ("L2", at(3, 14, 1)), ("L3", at(3, 15, 1)),
                         ("L4", at(3, 15, 21))):
            before = len(self.sent)
            turnover.tick(now=now)
            new = [p for p in self.sent[before:] if p.get("kind") == "nudge"]
            ops[lvl] = new[0]["op"] if new else None
            if lvl == "L1":
                self.give_message_id()       # bot.py reports back the id it just posted
        self.assertEqual(ops["L1"], "send")  # nothing existed yet — the only allowed exception
        self.assertEqual(ops["L2"], "edit")  # silent
        self.assertEqual(ops["L3"], "send")  # phone buzz, by design
        self.assertEqual(ops["L4"], "edit")  # silent again; the LEAD is the one pinged here

    def test_l3_refreshes_the_countdown_by_editing_not_re_sending(self):
        turnover.tick(now=at(3, 15, 1))                  # L3 opens the message
        self.give_message_id(when=at(3, 15, 1))
        before = len(self.sent)
        self.assertEqual(turnover.tick(now=at(3, 15, 5))["edited"], [])   # too soon
        self.assertEqual(len(self.sent), before)
        turnover.tick(now=at(3, 15, 12))                 # 10+ minutes later
        refreshed = [p for p in self.sent[before:] if p.get("kind") == "nudge"]
        self.assertTrue(refreshed)
        self.assertTrue(all(p["op"] == "edit" for p in refreshed))

    def test_the_ladder_never_steps_backwards(self):
        """After an L3 has gone out, a skipped L2 must never fire and tell somebody things
        got calmer while a guest is at the door."""
        turnover.tick(now=at(3, 15, 1))                  # jumps straight to L3
        self.assertEqual(db.nudge_levels_sent(WID), ["L3"])
        r = turnover.tick(now=at(3, 15, 3))
        self.assertEqual(r["nudged"], [])
        self.assertNotIn("L2", db.nudge_levels_sent(WID))

    def test_the_message_id_survives_a_restart(self):
        """It lives in the database, not in memory — the Musaed duplicate-spam lesson."""
        turnover.tick(now=at(3, 12, 1))
        self.give_message_id("msg-persist")
        db.reset_init_cache()                            # as if the process restarted
        self.assertEqual(db.nudge_item(WID)["message_id"], "msg-persist")
        turnover.tick(now=at(3, 14, 1))
        self.assertEqual([p for p in self.sent if p.get("op") == "edit"][0]["message_id"],
                         "msg-persist")


class TestTheReadyButton(TurnoverCase):

    def test_ready_is_refused_with_no_photos(self):
        turnover.tick(now=at(3, 12, 1))
        r = turnover.press_ready(WID, "ناصر")
        self.assertFalse(r["ok"])
        self.assertTrue(r["need_photos"])
        self.assertIn("صور", r["error"])
        self.assertIsNone(db.nudge_item(WID)["acked_at"])

    def test_ready_works_once_photos_exist(self):
        turnover.tick(now=at(3, 12, 1))
        self.photos = True
        r = turnover.press_ready(WID, "ناصر")
        self.assertTrue(r["ok"])
        self.assertIsNotNone(db.nudge_item(WID)["acked_at"])

    def test_the_message_offers_the_upload_link_while_photos_are_missing(self):
        turnover.tick(now=at(3, 12, 1))
        self.assertIn("الصور ما وصلت", self.sent[0]["text"])
        self.assertFalse(self.sent[0]["can_ack"])

    def test_acking_stops_the_ladder_completely(self):
        turnover.tick(now=at(3, 12, 1))
        self.photos = True
        turnover.press_ready(WID, "ناصر")
        before = len(self.sent)
        for now in (at(3, 14, 1), at(3, 15, 1), at(3, 15, 41)):
            turnover.tick(now=now)
        self.assertEqual(len(self.sent), before)
        self.assertTrue(db.nudge_item(WID)["closed_at"])

    def test_a_button_press_is_found_by_message_id_after_a_restart(self):
        turnover.tick(now=at(3, 12, 1))
        self.give_message_id("msg-77")
        self.photos = True
        r = turnover.press_ready("msg-77", "ناصر")       # only the message id is known
        self.assertTrue(r["ok"])
        self.assertEqual(r["work_item_id"], WID)

    def test_problem_stops_the_nudging_and_pulls_the_lead(self):
        turnover.tick(now=at(3, 12, 1))
        r = turnover.press_problem(WID, "ناصر", "الباب مقفل")
        self.assertTrue(r["ok"])
        self.assertIn("nudge_problem", self.kinds())
        before = len(self.sent)
        turnover.tick(now=at(3, 15, 1))
        self.assertEqual(len(self.sent), before)         # silence, a human is on it


class TestSleepProtection(TurnoverCase):
    """Being asleep at 3 AM is not misconduct."""

    def setUp(self):
        super().setUp()
        self.item["checkin_at"] = at(4, 4, 0)            # a 4 AM arrival

    def test_two_unanswered_night_nudges_reassign_to_the_backup(self):
        turnover.tick(now=at(4, 1, 1))                   # L1  (01:00, quiet)
        turnover.tick(now=at(4, 3, 1))                   # L2  (03:00, quiet)
        r = turnover.tick(now=at(4, 4, 1))               # third pass -> asleep
        self.assertEqual([a["employee"] for a in r["asleep"]], ["ناصر"])
        row = db.nudge_item(WID)
        self.assertEqual(row["reassigned_to"], "نورة")
        self.assertEqual(row["reassigned_reason"], "reassigned_asleep")

    def test_the_backup_and_the_lead_are_told_with_full_context(self):
        for now in (at(4, 1, 1), at(4, 3, 1), at(4, 4, 1)):
            turnover.tick(now=now)
        msg = [p for p in self.sent if p.get("kind") == "nudge_asleep"][0]
        self.assertEqual(msg["employee"], "نورة")
        self.assertIn("الملقا", msg["text"])
        self.assertIn("ما انسجل عليه أي إنذار", msg["lead_text"])

    def test_it_generates_no_warning_at_all(self):
        for now in (at(4, 1, 1), at(4, 3, 1), at(4, 4, 1)):
            turnover.tick(now=now)
        c = db.counts()
        self.assertEqual(c["ops_warnings"], 0)
        self.assertEqual(c["ops_obligations"], 0)

    def test_nudging_stops_for_the_sleeping_person(self):
        for now in (at(4, 1, 1), at(4, 3, 1), at(4, 4, 1)):
            turnover.tick(now=now)
        before = len(self.sent)
        turnover.tick(now=at(4, 4, 30))
        self.assertEqual([p for p in self.sent[before:] if p.get("kind") == "nudge"], [])

    def test_the_same_silence_in_daylight_never_reassigns(self):
        self.item["checkin_at"] = at(3, 15, 0)
        for now in (at(3, 12, 1), at(3, 14, 1), at(3, 15, 1)):
            turnover.tick(now=now)
        self.assertIsNone(db.nudge_item(WID)["reassigned_to"])

    def test_repeat_offences_surface_as_a_staffing_signal_not_a_discipline_one(self):
        for now in (at(4, 1, 1), at(4, 3, 1), at(4, 4, 1)):
            turnover.tick(now=now)
        sig = turnover.state("2026-08-03")["staffing_signal"]
        self.assertEqual(sig[0]["employee"], "ناصر")
        self.assertEqual(sig[0]["n"], 1)


class TestDryRun(TurnoverCase):

    ENV = dict(TurnoverCase.ENV, NUDGE_DRYRUN="1")

    def test_it_sends_nothing_and_logs_everything(self):
        for now in (at(3, 12, 1), at(3, 14, 1), at(3, 15, 1), at(3, 15, 21), at(3, 15, 41)):
            turnover.tick(now=now)
        self.assertEqual(self.sent, [])
        self.assertGreater(db.counts()["ops_dryrun_log"], 0)
        self.assertEqual(db.nudge_levels_sent(WID), ["L1", "L2", "L3", "L4", "L5"])
        self.assertTrue(all(r["path"] == "dryrun" for r in db.nudge_rows(WID)))

    def test_a_dry_run_night_reassignment_touches_nothing(self):
        self.item["checkin_at"] = at(4, 4, 0)
        for now in (at(4, 1, 1), at(4, 3, 1), at(4, 4, 1)):
            turnover.tick(now=now)
        self.assertEqual(self.sent, [])
        rows = [r for r in db.dry_rows(50) if r["kind"] == "nudge_asleep"]
        self.assertTrue(rows)
        self.assertIn("بدون أي إنذار", rows[0]["detail"])


class TestPhase2CannotWarnAnybody(unittest.TestCase):
    """Structural. Phase 2 is a reminder system; it must never reach Phase 1's punishment."""

    def test_the_turnover_module_never_touches_warnings(self):
        import inspect
        src = inspect.getsource(turnover)
        for forbidden in ("issue_warning", "deadline_decision", "compute_multiplier",
                          "ops_warnings"):
            self.assertNotIn(forbidden, src, forbidden)


if __name__ == "__main__":
    unittest.main()
