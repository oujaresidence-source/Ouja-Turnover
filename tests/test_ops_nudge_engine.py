# -*- coding: utf-8 -*-
"""
Phase 2 «القفل» — the turnover-nudge rules. PURE: no Discord, no database, no clock.

The invariants that matter:
    * every step is computed from the BOOKING's check-in time, never the wall clock
    * escalation is by CONTENT — only L3 and L5 may produce a new notification
    * «✅ جاهزة» is impossible without cleaning photos
    * two unanswered nudges at 3 AM mean asleep, which is never misconduct

Run: python3 -m unittest tests.test_ops_nudge_engine
"""

import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ops import engine  # noqa: E402

RIYADH = engine.tz()


def dt(d, hh, mm=0):
    return datetime.datetime(2026, 8, d, hh, mm, tzinfo=RIYADH)


class TestTheLadderFollowsTheGuest(unittest.TestCase):

    def test_steps_are_relative_to_check_in_not_the_clock(self):
        steps = engine.nudge_steps(dt(3, 15, 0))            # guest arrives 3 PM
        self.assertEqual([s["level"] for s in steps], ["L1", "L2", "L3", "L4", "L5"])
        self.assertEqual([(s["at"].hour, s["at"].minute) for s in steps],
                         [(12, 0), (14, 0), (15, 0), (15, 20), (15, 40)])

    def test_a_late_check_in_moves_the_whole_ladder(self):
        """The core of the spec: a 20:00 arrival must not be nudged on a 15:00 schedule."""
        early = engine.nudge_steps(dt(3, 15, 0))
        late = engine.nudge_steps(dt(3, 20, 0))
        for a, b in zip(early, late):
            self.assertEqual(b["at"] - a["at"], datetime.timedelta(hours=5))
        self.assertEqual(late[0]["at"].hour, 17)            # L1 at 5 PM, not noon

    def test_nothing_fires_before_three_hours_out(self):
        self.assertIsNone(engine.nudge_due_step(dt(3, 15, 0), dt(3, 11, 59)))
        self.assertEqual(engine.nudge_due_step(dt(3, 15, 0), dt(3, 12, 0))["level"], "L1")

    def test_a_sleeping_bot_sends_only_the_latest_level(self):
        s = engine.nudge_due_step(dt(3, 15, 0), dt(3, 15, 25))
        self.assertEqual(s["level"], "L4")

    def test_a_level_is_never_sent_twice(self):
        ci, now = dt(3, 15, 0), dt(3, 14, 5)
        self.assertEqual(engine.nudge_due_step(ci, now, [])["level"], "L2")
        self.assertIsNone(engine.nudge_due_step(ci, now, ["L1", "L2"]))

    def test_the_ladder_ends_at_l5(self):
        self.assertEqual(engine.nudge_due_step(dt(3, 15, 0), dt(3, 23, 0))["level"], "L5")
        self.assertIsNone(engine.nudge_due_step(dt(3, 15, 0), dt(3, 23, 0),
                                                engine.NUDGE_LEVELS))

    def test_countdown_minutes(self):
        self.assertEqual(engine.minutes_to(dt(3, 15, 0), dt(3, 14, 0)), 60)
        self.assertEqual(engine.minutes_to(dt(3, 15, 0), dt(3, 15, 30)), -30)


class TestOneMessageEditedInPlace(unittest.TestCase):
    """40 pings is how people learn to mute the bot — and then the whole suite dies quietly."""

    def test_only_l3_and_l5_may_buzz_a_phone(self):
        self.assertFalse(engine.nudge_is_push("L1"))
        self.assertFalse(engine.nudge_is_push("L2"))
        self.assertTrue(engine.nudge_is_push("L3"))
        self.assertFalse(engine.nudge_is_push("L4"))
        self.assertTrue(engine.nudge_is_push("L5"))

    def test_most_levels_are_silent_edits(self):
        pushes = [l for l in engine.NUDGE_LEVELS if engine.nudge_is_push(l)]
        self.assertEqual(len(pushes), 2)

    def test_l3_refreshes_every_ten_minutes_and_not_faster(self):
        self.assertTrue(engine.l3_refresh_due(None, dt(3, 15, 0)))
        last = dt(3, 15, 0)
        self.assertFalse(engine.l3_refresh_due(last, dt(3, 15, 9)))
        self.assertTrue(engine.l3_refresh_due(last, dt(3, 15, 10)))


class TestTheReadyButtonCannotLie(unittest.TestCase):

    def test_ack_is_refused_without_photos(self):
        self.assertFalse(engine.can_ack(False))
        self.assertFalse(engine.can_ack(0))
        self.assertFalse(engine.can_ack(None))
        self.assertFalse(engine.can_ack([]))

    def test_ack_is_allowed_once_photos_exist(self):
        self.assertTrue(engine.can_ack(True))
        self.assertTrue(engine.can_ack(3))
        self.assertTrue(engine.can_ack(["photo"]))


class TestSleepProtection(unittest.TestCase):
    """Being asleep at 3 AM is not misconduct."""

    def test_the_quiet_window_is_midnight_to_six(self):
        for h in (0, 1, 3, 5):
            self.assertTrue(engine.in_quiet_window(dt(3, h)), h)
        for h in (6, 9, 15, 23):
            self.assertFalse(engine.in_quiet_window(dt(3, h)), h)

    def test_a_window_that_wraps_past_midnight_works(self):
        self.assertTrue(engine.in_quiet_window(dt(3, 23), start=22, end=6))
        self.assertTrue(engine.in_quiet_window(dt(3, 2), start=22, end=6))
        self.assertFalse(engine.in_quiet_window(dt(3, 12), start=22, end=6))

    def test_an_empty_window_never_triggers(self):
        self.assertFalse(engine.in_quiet_window(dt(3, 3), start=0, end=0))

    def test_two_unanswered_nudges_at_night_mean_asleep(self):
        self.assertFalse(engine.sleep_reassign(1, in_quiet=True))
        self.assertTrue(engine.sleep_reassign(2, in_quiet=True))
        self.assertTrue(engine.sleep_reassign(5, in_quiet=True))

    def test_the_same_silence_in_daylight_is_not_sleep(self):
        self.assertFalse(engine.sleep_reassign(5, in_quiet=False))

    def test_this_module_cannot_produce_a_warning(self):
        """Structural: the sleep path must never reach the Phase 1 verdict function."""
        import inspect
        src = inspect.getsource(engine.sleep_reassign)
        self.assertNotIn("deadline_decision", src)
        self.assertNotIn("missed", src)


if __name__ == "__main__":
    unittest.main()
