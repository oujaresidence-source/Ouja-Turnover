# -*- coding: utf-8 -*-
"""
ops.engine invariants — «نظام الالتزام». PURE: no Discord, no database, no network, no clock.

These lock the rules that decide whether a person loses money, so they must be green before
any of the delivery, storage or UI code is trusted.

Run:  python3 -m unittest tests.test_ops_engine
"""

import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ops import engine  # noqa: E402

RIYADH = engine.tz()


def dt(y, m, d, hh=0, mm=0):
    return datetime.datetime(y, m, d, hh, mm, tzinfo=RIYADH)


class TestMultiplier(unittest.TestCase):
    """Warnings SUBTRACT commission. This table is the money."""

    def test_the_table(self):
        self.assertEqual(engine.compute_multiplier(0), 1.0)
        self.assertEqual(engine.compute_multiplier(1), 0.9)
        self.assertEqual(engine.compute_multiplier(2), 0.75)
        self.assertEqual(engine.compute_multiplier(3), 0.0)
        self.assertEqual(engine.compute_multiplier(4), 0.0)
        self.assertEqual(engine.compute_multiplier(17), 0.0)

    def test_garbage_input_never_costs_money(self):
        for bad in (None, -1, "", "0"):
            self.assertEqual(engine.compute_multiplier(bad), 1.0)

    def test_voided_and_retired_are_not_counted(self):
        ws = [{"status": "active"}, {"status": "voided"}, {"status": "retired"},
              {"status": "active"}]
        self.assertEqual(engine.active_count(ws), 2)
        self.assertEqual(engine.compute_multiplier(engine.active_count(ws)), 0.75)

    def test_all_voided_restores_full_commission(self):
        ws = [{"status": "voided"}, {"status": "voided"}, {"status": "retired"}]
        self.assertEqual(engine.active_count(ws), 0)
        self.assertEqual(engine.compute_multiplier(engine.active_count(ws)), 1.0)


class TestDeadlineAndLadder(unittest.TestCase):

    def test_due_lands_monday_2359_riyadh(self):
        due = engine.due_at_for_week("2026-W31")
        self.assertEqual(due.weekday(), 0)                      # Monday
        self.assertEqual((due.hour, due.minute), (23, 59))
        self.assertEqual(due.utcoffset(), datetime.timedelta(hours=3))
        self.assertEqual(due.date().isoformat(), "2026-07-27")

    def test_week_key_round_trips(self):
        self.assertEqual(engine.iso_week_key("2026-07-27"), "2026-W31")
        self.assertEqual(engine.week_monday("2026-W31").isoformat(), "2026-07-27")
        self.assertEqual(engine.parse_week_key("2026-W05"), (2026, 5))

    def test_malformed_week_key_raises_instead_of_guessing(self):
        for bad in ("", "2026W31", "2026-31", None, "garbage"):
            with self.assertRaises(ValueError):
                engine.parse_week_key(bad)

    def test_ladder_lands_sun18_mon10_mon16_mon20(self):
        """The spec's clock times. The offsets put each step at :59; the 5-minute tick
        delivers it on the round hour, which is what the team actually sees."""
        due = engine.due_at_for_week("2026-W31")               # Mon 2026-07-27 23:59
        steps = engine.ladder_steps(due)
        self.assertEqual([s["level"] for s in steps], ["L1", "L2", "L3", "L4", "issue"])
        self.assertEqual([s["hours_before"] for s in steps], [30, 14, 8, 4, 0])

        want = [("2026-07-26", 17, 59, 18),      # Sunday  -> fires 18:00
                ("2026-07-27", 9, 59, 10),       # Monday  -> fires 10:00
                ("2026-07-27", 15, 59, 16),
                ("2026-07-27", 19, 59, 20)]
        for step, (day, hh, mm, fires) in zip(steps, want):
            self.assertEqual(step["at"].date().isoformat(), day)
            self.assertEqual((step["at"].hour, step["at"].minute), (hh, mm))
            # the first 5-minute tick at-or-after the step is the round hour named in the spec
            tick = step["at"] + datetime.timedelta(minutes=1)
            self.assertEqual(tick.hour, fires)
        self.assertEqual(steps[-1]["at"], due)

    def test_due_step_picks_only_the_latest_pending_level(self):
        """A bot asleep through L1+L2 must send L3 only — never three DMs at once."""
        due = engine.due_at_for_week("2026-W31")
        self.assertIsNone(engine.due_step(due, dt(2026, 7, 26, 12, 0)))
        self.assertEqual(engine.due_step(due, dt(2026, 7, 26, 18, 0))["level"], "L1")
        self.assertEqual(engine.due_step(due, dt(2026, 7, 27, 16, 0))["level"], "L3")
        self.assertEqual(engine.due_step(due, dt(2026, 7, 27, 23, 59))["level"], "issue")

    def test_already_sent_levels_are_never_resent(self):
        due = engine.due_at_for_week("2026-W31")
        now = dt(2026, 7, 27, 16, 0)
        self.assertEqual(engine.due_step(due, now, ["L1", "L2"])["level"], "L3")
        # L1-L3 all sent and L4 is not due until 19:59 -> nothing to send. Silence is correct.
        self.assertIsNone(engine.due_step(due, now, ["L1", "L2", "L3"]))
        # a skipped earlier level is still sendable if it is the only one left pending
        self.assertEqual(engine.due_step(due, now, ["L1", "L3"])["level"], "L2")
        self.assertIsNone(engine.due_step(due, now, ["L1", "L2", "L3", "L4", "issue"]))

    def test_a_moved_deadline_moves_the_whole_ladder(self):
        due = engine.due_at_for_week("2026-W31", hour=20, minute=0)
        self.assertEqual((due.hour, due.minute), (20, 0))
        self.assertEqual(engine.ladder_steps(due)[0]["at"], due - datetime.timedelta(hours=30))


class TestQuarterAndMonth(unittest.TestCase):

    def test_quarter_key(self):
        self.assertEqual(engine.quarter_key("2026-07-28"), "2026-Q3")
        self.assertEqual(engine.quarter_key("2026-01-01"), "2026-Q1")
        self.assertEqual(engine.quarter_key("2026-03-31"), "2026-Q1")
        self.assertEqual(engine.quarter_key("2026-04-01"), "2026-Q2")
        self.assertEqual(engine.quarter_key(datetime.date(2026, 12, 31)), "2026-Q4")

    def test_month_key(self):
        self.assertEqual(engine.month_key("2026-07-28"), "2026-07")


class TestForgiveness(unittest.TestCase):

    def test_free_pass_applies_once_and_only_on_a_first_miss(self):
        self.assertTrue(engine.free_pass_decision(used_this_quarter=False,
                                                  prior_misses_this_quarter=0))
        # already spent this quarter
        self.assertFalse(engine.free_pass_decision(True, 0))
        # not the first miss
        self.assertFalse(engine.free_pass_decision(False, 1))
        self.assertFalse(engine.free_pass_decision(False, 5))

    def test_four_clean_weeks_retire_one_warning(self):
        weeks = [{"period_key": "2026-W%02d" % w, "clean": True} for w in (28, 29, 30, 31)]
        r = engine.retirement_check("ناصر", weeks)
        self.assertTrue(r["retire"])
        self.assertEqual(r["streak"], 4)
        self.assertEqual(r["through"], "2026-W31")
        self.assertEqual(r["employee"], "ناصر")

    def test_three_clean_weeks_are_not_enough(self):
        weeks = [{"period_key": "2026-W%02d" % w, "clean": True} for w in (29, 30, 31)]
        self.assertFalse(engine.retirement_check("ناصر", weeks)["retire"])

    def test_a_miss_resets_the_streak(self):
        weeks = [{"period_key": "2026-W28", "clean": True},
                 {"period_key": "2026-W29", "clean": True},
                 {"period_key": "2026-W30", "clean": False},   # broke it
                 {"period_key": "2026-W31", "clean": True}]
        r = engine.retirement_check("ناصر", weeks)
        self.assertFalse(r["retire"])
        self.assertEqual(r["streak"], 1)

    def test_streak_counts_only_the_most_recent_run(self):
        weeks = ([{"period_key": "a%d" % i, "clean": True} for i in range(6)]
                 + [{"period_key": "bad", "clean": False}]
                 + [{"period_key": "c%d" % i, "clean": True} for i in range(4)])
        self.assertTrue(engine.retirement_check("ناصر", weeks)["retire"])
        self.assertEqual(engine.retirement_check("ناصر", weeks)["streak"], 4)

    def test_leave_and_excuse_keep_a_streak_alive(self):
        """A week covered by approved leave is clean — being off must never cost a streak."""
        weeks = [{"period_key": "w1", "clean": True},    # done
                 {"period_key": "w2", "clean": True},    # waived (leave)
                 {"period_key": "w3", "clean": True},    # excused
                 {"period_key": "w4", "clean": True}]
        self.assertTrue(engine.retirement_check("عهود", weeks)["retire"])


class TestTheVerdict(unittest.TestCase):
    """deadline_decision is the ONLY function that can produce a miss."""

    def test_done_wins_over_everything(self):
        v, _ = engine.deadline_decision(done=True, on_leave=True, excused=True,
                                        free_pass_available=True, reachable=False)
        self.assertEqual(v, "done")

    def test_approved_leave_waives_silently(self):
        v, why = engine.deadline_decision(done=False, on_leave=True)
        self.assertEqual(v, "waived")
        self.assertIn("إجازة", why)

    def test_leave_is_checked_before_the_free_pass(self):
        """Leave must not burn somebody's one quarterly pass."""
        v, _ = engine.deadline_decision(done=False, on_leave=True, free_pass_available=True)
        self.assertEqual(v, "waived")

    def test_leader_excuse_before_the_deadline_blocks_the_warning(self):
        v, _ = engine.deadline_decision(done=False, excused=True)
        self.assertEqual(v, "excused")

    def test_excuse_is_checked_before_the_free_pass(self):
        v, _ = engine.deadline_decision(done=False, excused=True, free_pass_available=True)
        self.assertEqual(v, "excused")

    def test_first_miss_of_the_quarter_is_forgiven(self):
        v, why = engine.deadline_decision(done=False, free_pass_available=True, prior_misses=0)
        self.assertEqual(v, "free_pass")
        self.assertIn("السماح الفصلي", why)

    def test_second_miss_of_the_quarter_is_a_warning(self):
        v, _ = engine.deadline_decision(done=False, free_pass_available=True, prior_misses=1)
        self.assertEqual(v, "missed")

    def test_pass_already_spent_means_a_warning(self):
        v, _ = engine.deadline_decision(done=False, free_pass_available=False, prior_misses=0)
        self.assertEqual(v, "missed")

    def test_an_unreachable_person_is_never_warned(self):
        """We could not get a single message to them. Accusing them anyway would make the
        whole system illegitimate on day one."""
        v, why = engine.deadline_decision(done=False, free_pass_available=False, reachable=False)
        self.assertEqual(v, "unreachable")
        self.assertIn("ما ينسجل إنذار", why)

    def test_the_plain_miss(self):
        v, why = engine.deadline_decision(done=False, on_leave=False, excused=False,
                                          free_pass_available=False, prior_misses=2,
                                          reachable=True)
        self.assertEqual(v, "missed")
        self.assertTrue(why.strip())

    def test_every_verdict_is_declared(self):
        for kwargs in ({"done": True}, {"on_leave": True}, {"excused": True},
                       {"free_pass_available": True}, {"reachable": False}, {}):
            v, _ = engine.deadline_decision(**kwargs)
            self.assertIn(v, engine.VERDICTS)


class TestAppealLadder(unittest.TestCase):

    def test_stages_go_aseel_reem_faisal_then_close(self):
        self.assertEqual(engine.APPEAL_STAGES, ("s1", "s2", "s3"))
        self.assertEqual(engine.next_stage("s1"), "s2")
        self.assertEqual(engine.next_stage("s2"), "s3")
        self.assertEqual(engine.next_stage("s3"), "closed")
        self.assertEqual(engine.next_stage("closed"), "closed")
        self.assertEqual(engine.next_stage("nonsense"), "closed")

    def test_sla_is_24h_and_overdue_is_inclusive(self):
        opened = dt(2026, 7, 28, 9, 0)
        due = engine.appeal_due_at(opened, 24)
        self.assertEqual(due, dt(2026, 7, 29, 9, 0))
        self.assertFalse(engine.appeal_overdue(due, dt(2026, 7, 29, 8, 59)))
        self.assertTrue(engine.appeal_overdue(due, due))
        self.assertTrue(engine.appeal_overdue(due, dt(2026, 7, 30, 0, 0)))
        self.assertFalse(engine.appeal_overdue(None, dt(2030, 1, 1)))

    def test_reject_without_a_written_reason_is_refused(self):
        self.assertFalse(engine.can_reject(""))
        self.assertFalse(engine.can_reject("   "))
        self.assertFalse(engine.can_reject(None))
        self.assertTrue(engine.can_reject("التقرير ما وصل فعلاً"))


class TestPublicSummaryHasNoNames(unittest.TestCase):

    def test_counts_only(self):
        s = engine.public_summary_counts(23, 24, 3, 2, [1.0, 0.9, 1.0, 1.0, 0.9])
        self.assertEqual(s["done"], 23)
        self.assertEqual(s["total"], 24)
        self.assertEqual(s["warnings"], 3)
        self.assertEqual(s["voided"], 2)
        self.assertEqual(s["avg_commission_pct"], 96)

    def test_the_return_value_cannot_carry_a_name(self):
        s = engine.public_summary_counts(23, 24, 3, 2, [1.0])
        blob = repr(s)
        for name in ("ناصر", "مآثر", "نورة", "محمد اليامي", "عهود"):
            self.assertNotIn(name, blob)
        for key in s:
            self.assertNotIn("employee", key)
            self.assertNotIn("name", key)

    def test_no_multipliers_means_no_division_by_zero(self):
        self.assertEqual(engine.public_summary_counts(0, 0, 0, 0, [])["avg_commission_pct"], 100)


if __name__ == "__main__":
    unittest.main()
