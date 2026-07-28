# -*- coding: utf-8 -*-
"""
The response clock — «الاستجابة على وحداتك». PURE: no database, no Discord, no network.

Two rules, both about not punishing people for things that are not their fault:

    * worked_minutes counts ONLY time inside 11:00 → 01:30 Riyadh. A message that lands at
      02:00 does not start its clock until 11:00.
    * response_pairs makes ONE event per run of consecutive guest messages, not one per
      message — a chatty guest is one person waiting once, not three failures.

Run: python3 -m unittest tests.test_ops_response_clock
"""

import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ops import engine  # noqa: E402

RIYADH = engine.tz()
H = 60.0


def at(d, hh, mm=0):
    return datetime.datetime(2026, 8, d, hh, mm, tzinfo=RIYADH)


class TestWorkedMinutes(unittest.TestCase):

    def test_a_pair_fully_inside_the_window_equals_wall_clock(self):
        self.assertEqual(engine.worked_minutes(at(3, 13, 0), at(3, 15, 0)), 120.0)
        self.assertEqual(engine.worked_minutes(at(3, 11, 0), at(3, 11, 45)), 45.0)

    def test_a_two_am_arrival_starts_its_clock_at_eleven(self):
        """The spec's case. 02:00 is in the dead zone; nothing counts until 11:00."""
        self.assertEqual(engine.worked_minutes(at(3, 2, 0), at(3, 11, 30)), 30.0)
        self.assertEqual(engine.worked_minutes(at(3, 2, 0), at(3, 11, 0)), 0.0)
        self.assertEqual(engine.worked_minutes(at(3, 3, 30), at(3, 12, 0)), 60.0)

    def test_eleven_pm_to_noon_next_day_is_two_and_a_half_plus_one(self):
        """The spec's other case: 23:00 → 12:00 next day = 2.5h + 1h, not 13h."""
        self.assertEqual(engine.worked_minutes(at(3, 23, 0), at(4, 12, 0)), 2.5 * H + 1 * H)

    def test_the_dead_zone_costs_nobody_anything(self):
        self.assertEqual(engine.worked_minutes(at(3, 1, 30), at(3, 11, 0)), 0.0)
        self.assertEqual(engine.worked_minutes(at(3, 2, 0), at(3, 9, 0)), 0.0)

    def test_the_window_closes_at_one_thirty(self):
        self.assertEqual(engine.worked_minutes(at(3, 23, 0), at(4, 1, 30)), 150.0)
        self.assertEqual(engine.worked_minutes(at(3, 23, 0), at(4, 3, 0)), 150.0)  # 01:30 caps it

    def test_a_whole_working_day_is_fourteen_and_a_half_hours(self):
        self.assertEqual(engine.worked_minutes(at(3, 11, 0), at(4, 1, 30)), 14.5 * H)

    def test_several_days_add_up_without_counting_the_nights(self):
        # Fri 11:00 -> Sun 12:00 = 14.5h + 14.5h + 1h
        self.assertEqual(engine.worked_minutes(at(3, 11, 0), at(5, 12, 0)),
                         14.5 * H + 14.5 * H + 1 * H)

    def test_backwards_and_equal_pairs_are_zero_not_negative(self):
        self.assertEqual(engine.worked_minutes(at(3, 15, 0), at(3, 13, 0)), 0.0)
        self.assertEqual(engine.worked_minutes(at(3, 13, 0), at(3, 13, 0)), 0.0)

    def test_it_accepts_iso_strings(self):
        self.assertEqual(engine.worked_minutes("2026-08-03 13:00:00", "2026-08-03 15:00:00"),
                         120.0)
        self.assertEqual(engine.worked_minutes("2026-08-03T13:00:00", "2026-08-03T14:00:00"),
                         60.0)

    def test_garbage_never_raises_and_never_invents_time(self):
        for bad in (None, "", "not a date", "2026-13-99"):
            self.assertEqual(engine.worked_minutes(bad, at(3, 13, 0)), 0.0, bad)
            self.assertEqual(engine.worked_minutes(at(3, 13, 0), bad), 0.0, bad)

    def test_a_different_window_is_honoured(self):
        """The constants come from bot.py — this proves they are actually used and not
        quietly hard-coded here."""
        self.assertEqual(
            engine.worked_minutes(at(3, 9, 0), at(3, 12, 0), work_start=10,
                                  work_end_hour=18, work_end_min=0), 120.0)


class TestResponsePairs(unittest.TestCase):
    """One event per run of guest messages."""

    @staticmethod
    def msg(mid, inbound, when, body=""):
        return {"id": mid, "in": inbound, "t": when, "body": body}

    def pairs(self, msgs, auto=None):
        return engine.response_pairs(
            msgs,
            is_inbound=lambda m: m["in"],
            msg_time=lambda m: m["t"],
            is_automated=(auto or (lambda m: False)))

    def test_one_question_one_answer(self):
        p = self.pairs([self.msg("g1", True, "10:00"), self.msg("h1", False, "10:20")])
        self.assertEqual(len(p), 1)
        self.assertEqual(p[0]["incoming"]["id"], "g1")
        self.assertEqual(p[0]["outgoing"]["id"], "h1")
        self.assertEqual(p[0]["responded_at"], "10:20")

    def test_a_second_reply_in_the_same_exchange_is_not_a_new_event(self):
        p = self.pairs([self.msg("g1", True, "10:00"),
                        self.msg("h1", False, "10:20"),
                        self.msg("h2", False, "10:25"),
                        self.msg("h3", False, "10:31")])
        self.assertEqual(len(p), 1)
        self.assertEqual(p[0]["outgoing"]["id"], "h1")

    def test_three_guest_messages_in_a_row_are_ONE_wait(self):
        """A chatty guest is one person waiting once — not three failures for whoever owns
        that unit."""
        p = self.pairs([self.msg("g1", True, "10:00"),
                        self.msg("g2", True, "10:02"),
                        self.msg("g3", True, "10:05"),
                        self.msg("h1", False, "10:40")])
        self.assertEqual(len(p), 1)
        self.assertEqual(p[0]["incoming"]["id"], "g1")     # the clock starts at the FIRST
        self.assertEqual(p[0]["outgoing"]["id"], "h1")

    def test_two_separate_exchanges_are_two_events(self):
        p = self.pairs([self.msg("g1", True, "10:00"), self.msg("h1", False, "10:10"),
                        self.msg("g2", True, "14:00"), self.msg("h2", False, "14:30")])
        self.assertEqual([x["incoming"]["id"] for x in p], ["g1", "g2"])

    def test_an_unanswered_guest_still_counts(self):
        """Otherwise a team could score 100% by answering nothing at all."""
        p = self.pairs([self.msg("g1", True, "10:00")])
        self.assertEqual(len(p), 1)
        self.assertIsNone(p[0]["outgoing"])
        self.assertIsNone(p[0]["responded_at"])

    def test_an_automated_welcome_does_not_close_a_run(self):
        """It answers nobody, so the guest is still waiting and the clock keeps running."""
        p = self.pairs([self.msg("g1", True, "10:00"),
                        self.msg("auto", False, "10:00", "booking confirmed"),
                        self.msg("h1", False, "11:00")],
                       auto=lambda m: m["body"] == "booking confirmed")
        self.assertEqual(len(p), 1)
        self.assertEqual(p[0]["outgoing"]["id"], "h1")
        self.assertEqual(p[0]["responded_at"], "11:00")

    def test_a_host_message_with_nobody_waiting_creates_nothing(self):
        p = self.pairs([self.msg("h1", False, "09:00"), self.msg("h2", False, "09:05")])
        self.assertEqual(p, [])

    def test_an_empty_conversation_is_empty(self):
        self.assertEqual(self.pairs([]), [])
        self.assertEqual(engine.response_pairs(None, lambda m: True, lambda m: ""), [])


class TestAnsweredInTarget(unittest.TestCase):

    def test_inside_and_outside(self):
        self.assertTrue(engine.answered_in_target(29.9, 30))
        self.assertTrue(engine.answered_in_target(30, 30))
        self.assertFalse(engine.answered_in_target(30.1, 30))

    def test_unanswered_is_never_answered(self):
        self.assertFalse(engine.answered_in_target(None, 30))

    def test_an_instant_reply_counts(self):
        self.assertTrue(engine.answered_in_target(0.0, 30))


if __name__ == "__main__":
    unittest.main()
