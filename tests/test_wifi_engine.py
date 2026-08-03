# -*- coding: utf-8 -*-
"""
wifi.engine — the date maths, locked.

THE RULE THIS FILE EXISTS TO PROTECT:
    A package sold as 90 days counts down from 90 days. The system NEVER invents a
    shorter number out of thin air. It shortens only after Ouja's OWN data has proven,
    three separate times, that this seller short-changes us.

test_label_stands_when_we_have_learned_nothing is that rule. Do not weaken it.

Run: python3 -m unittest tests.test_wifi_engine
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wifi import engine  # noqa: E402


class TestLearnedDays(unittest.TestCase):
    """learned_days = the median real duration, and only once we have enough of them."""

    def test_median_of_three(self):
        self.assertEqual(engine.learned_days([70, 72, 75]), 72)

    def test_two_observations_is_not_enough_to_guess(self):
        self.assertIsNone(engine.learned_days([70, 72]))

    def test_zero_and_one_observations(self):
        self.assertIsNone(engine.learned_days([]))
        self.assertIsNone(engine.learned_days([70]))

    def test_median_resists_the_outlier(self):
        """A mean would say 104 — one weird row must not move the number."""
        self.assertEqual(engine.learned_days([70, 72, 75, 200]), 73)
        self.assertNotEqual(engine.learned_days([70, 72, 75, 200]), 104)

    def test_none_entries_are_ignored_not_counted(self):
        """still_working checks yield None; they must not pad the count to the minimum."""
        self.assertIsNone(engine.learned_days([70, None, 72, None]))
        self.assertEqual(engine.learned_days([70, None, 72, 75]), 72)

    def test_minimum_is_a_named_constant(self):
        self.assertEqual(engine.MIN_OBSERVATIONS, 3)


class TestExpectedDays(unittest.TestCase):

    def test_label_stands_when_we_have_learned_nothing(self):
        """THE OWNER RULE. 90 days means 90 days until our own data says otherwise."""
        self.assertEqual(engine.expected_days(90, None), (90, "label"))
        self.assertEqual(engine.expected_days(30, None), (30, "label"))
        self.assertEqual(engine.expected_days(60, None), (60, "label"))

    def test_learned_wins_once_it_exists(self):
        self.assertEqual(engine.expected_days(90, 72), (72, "learned"))

    def test_learned_longer_than_label_is_still_learned(self):
        """Our data is our data — it may also prove a package runs LONGER."""
        self.assertEqual(engine.expected_days(30, 34), (34, "learned"))


class TestExpectedEnd(unittest.TestCase):

    def test_plain_addition(self):
        self.assertEqual(engine.expected_end("2026-08-03", 30), "2026-09-02")

    def test_month_end_rollover_does_not_crash(self):
        """Bought 31 Jan, 30-day package -> 2 March. Riyadh dates, plain calendar days."""
        self.assertEqual(engine.expected_end("2026-01-31", 30), "2026-03-02")

    def test_across_a_leap_year_february(self):
        self.assertEqual(engine.expected_end("2028-01-31", 30), "2028-03-01")

    def test_missing_activation_date_is_not_a_guess(self):
        self.assertIsNone(engine.expected_end(None, 30))
        self.assertIsNone(engine.expected_end("", 30))


class TestDaysLeft(unittest.TestCase):

    def test_sign_across_the_boundary(self):
        self.assertEqual(engine.days_left("2026-08-10", "2026-08-03"), 7)
        self.assertEqual(engine.days_left("2026-08-03", "2026-08-03"), 0)
        self.assertEqual(engine.days_left("2026-08-01", "2026-08-03"), -2)

    def test_unknown_end_is_unknown_not_zero(self):
        self.assertIsNone(engine.days_left(None, "2026-08-03"))


class TestStatusBand(unittest.TestCase):

    def test_the_exact_boundaries(self):
        self.assertEqual(engine.status_band(-1), "dead")
        self.assertEqual(engine.status_band(0), "urgent")
        self.assertEqual(engine.status_band(3), "urgent")
        self.assertEqual(engine.status_band(4), "soon")
        self.assertEqual(engine.status_band(14), "soon")
        self.assertEqual(engine.status_band(15), "ok")

    def test_unknown_when_we_have_no_number(self):
        """A blank date is «ما نعرف» — never quietly folded into 'ok' or 'dead'."""
        self.assertEqual(engine.status_band(None), "unknown")


class TestRealDays(unittest.TestCase):
    """One observation -> the duration it proves, or None when it proves nothing."""

    SUB = {"activation_date": "2026-06-01"}

    def test_exact_expiry(self):
        got = engine.real_days(self.SUB, {"kind": "exact_expiry", "end_date": "2026-08-10"})
        self.assertEqual(got, 70)

    def test_died(self):
        got = engine.real_days(self.SUB, {"kind": "died", "end_date": "2026-08-12"})
        self.assertEqual(got, 72)

    def test_days_left(self):
        """Reported on 1 Aug with 10 days left -> ends 11 Aug -> 71 real days."""
        got = engine.real_days(self.SUB, {"kind": "days_left",
                                          "observed_on": "2026-08-01", "days_left": 10})
        self.assertEqual(got, 71)

    def test_still_working_proves_nothing_about_the_end(self):
        got = engine.real_days(self.SUB, {"kind": "still_working", "observed_on": "2026-08-01"})
        self.assertIsNone(got)

    def test_underivable_rows_return_none_instead_of_a_number(self):
        self.assertIsNone(engine.real_days(self.SUB, {"kind": "died", "end_date": None}))
        self.assertIsNone(engine.real_days(self.SUB, {"kind": "days_left",
                                                      "observed_on": "2026-08-01"}))
        self.assertIsNone(engine.real_days({"activation_date": None},
                                           {"kind": "died", "end_date": "2026-08-12"}))
        self.assertIsNone(engine.real_days(self.SUB, {"kind": "nonsense"}))

    def test_a_negative_duration_is_rejected_not_stored(self):
        """An end BEFORE activation is a typo, not a 'very short package'."""
        self.assertIsNone(engine.real_days(self.SUB, {"kind": "died", "end_date": "2026-05-01"}))


class TestEffectiveEnd(unittest.TestCase):
    """Precedence is the heart of it: a typed fact always beats a calculation."""

    BASE = {"activation_date": "2026-06-01", "label_days": 90}

    def test_real_beats_everything(self):
        sub = dict(self.BASE, real_end="2026-07-20", stated_end="2026-08-25")
        self.assertEqual(engine.effective_end(sub, 72), ("2026-07-20", "real"))

    def test_stated_beats_the_estimate(self):
        sub = dict(self.BASE, real_end=None, stated_end="2026-08-25")
        self.assertEqual(engine.effective_end(sub, 72), ("2026-08-25", "stated"))

    def test_estimate_is_the_last_resort(self):
        sub = dict(self.BASE, real_end=None, stated_end=None)
        self.assertEqual(engine.effective_end(sub, None), ("2026-08-30", "estimate"))

    def test_the_estimate_uses_learned_days_when_we_have_them(self):
        sub = dict(self.BASE, real_end=None, stated_end=None)
        self.assertEqual(engine.effective_end(sub, 72), ("2026-08-12", "estimate"))

    def test_no_activation_date_yields_no_end_at_all(self):
        sub = {"activation_date": None, "label_days": 90, "real_end": None, "stated_end": None}
        self.assertEqual(engine.effective_end(sub, None), (None, "unknown"))

    def test_a_blank_string_is_not_a_date(self):
        sub = dict(self.BASE, real_end="", stated_end="")
        self.assertEqual(engine.effective_end(sub, None), ("2026-08-30", "estimate"))


class TestDescribe(unittest.TestCase):
    """describe() is the ONE producer of the numbers every surface renders, so the
    dashboard, the fill page and any future reminder cannot drift apart."""

    def test_a_label_trusted_subscription_is_flagged_as_such(self):
        sub = {"activation_date": "2026-07-20", "label_days": 30, "status": "active"}
        d = engine.describe(sub, learned=None, today="2026-08-03")
        self.assertEqual(d["expected_days"], 30)
        self.assertEqual(d["confidence"], "label")
        self.assertEqual(d["end_date"], "2026-08-19")
        self.assertEqual(d["end_source"], "estimate")
        self.assertEqual(d["days_left"], 16)
        self.assertEqual(d["band"], "ok")

    def test_a_learned_subscription_counts_down_from_our_own_data(self):
        sub = {"activation_date": "2026-07-20", "label_days": 30, "status": "active"}
        d = engine.describe(sub, learned=24, today="2026-08-03")
        self.assertEqual(d["expected_days"], 24)
        self.assertEqual(d["confidence"], "learned")
        self.assertEqual(d["end_date"], "2026-08-13")
        self.assertEqual(d["days_left"], 10)
        self.assertEqual(d["band"], "soon")

    def test_a_dateless_backfill_row_stays_honestly_unknown(self):
        sub = {"activation_date": None, "label_days": 30, "status": "active", "is_backfill": 1}
        d = engine.describe(sub, learned=None, today="2026-08-03")
        self.assertIsNone(d["end_date"])
        self.assertIsNone(d["days_left"])
        self.assertEqual(d["band"], "unknown")

    def test_a_dead_subscription_reads_dead_whatever_the_maths_says(self):
        sub = {"activation_date": "2026-07-20", "label_days": 90,
               "status": "dead", "real_end": "2026-08-01"}
        d = engine.describe(sub, learned=None, today="2026-08-03")
        self.assertEqual(d["end_source"], "real")
        self.assertEqual(d["band"], "dead")


class TestLearningKey(unittest.TestCase):
    """Learning is per (provider, source, label_days) — Mobily-from-a-shop is not
    Mobily-from-Mobily, and a 30-day pack teaches nothing about a 90-day one."""

    def test_the_key_separates_what_must_stay_separate(self):
        a = engine.learning_key({"provider": "mobily", "source_kind": "vendor",
                                 "source_name": "محل النور", "label_days": 90})
        b = engine.learning_key({"provider": "mobily", "source_kind": "first_party",
                                 "source_name": "", "label_days": 90})
        c = engine.learning_key({"provider": "mobily", "source_kind": "vendor",
                                 "source_name": "محل النور", "label_days": 30})
        self.assertNotEqual(a, b)
        self.assertNotEqual(a, c)

    def test_the_same_shop_is_the_same_key_whatever_the_spacing_or_case(self):
        a = engine.learning_key({"provider": "Mobily", "source_kind": "vendor",
                                 "source_name": " محل النور ", "label_days": 90})
        b = engine.learning_key({"provider": "mobily", "source_kind": "vendor",
                                 "source_name": "محل النور", "label_days": 90})
        self.assertEqual(a, b)


class TestSyntheticEndToEnd(unittest.TestCase):
    """The synthetic-data logic check CLAUDE.md asks for: fake subs + fake observations
    through the engine, numbers asserted by hand."""

    def test_a_shop_earns_its_shorter_countdown_over_three_orders(self):
        sub = {"activation_date": "2026-05-01", "label_days": 90,
               "provider": "mobily", "source_kind": "vendor", "source_name": "محل النور"}
        # Three finished orders from the same shop, each dying early.
        history = [
            ({"activation_date": "2026-01-01"}, {"kind": "died", "end_date": "2026-03-12"}),   # 70
            ({"activation_date": "2026-02-01"}, {"kind": "died", "end_date": "2026-04-14"}),   # 72
            ({"activation_date": "2026-03-01"}, {"kind": "exact_expiry", "end_date": "2026-05-15"}),  # 75
        ]
        obs = [engine.real_days(s, c) for s, c in history]
        self.assertEqual(obs, [70, 72, 75])

        # Before the third order landed we still trusted the label.
        self.assertEqual(engine.expected_days(90, engine.learned_days(obs[:2])), (90, "label"))

        # With three, the median (72) takes over.
        learned = engine.learned_days(obs)
        self.assertEqual(learned, 72)
        d = engine.describe(sub, learned=learned, today="2026-07-01")
        self.assertEqual(d["expected_days"], 72)
        self.assertEqual(d["confidence"], "learned")
        self.assertEqual(d["end_date"], "2026-07-12")     # 1 May + 72 days
        self.assertEqual(d["days_left"], 11)              # 1 July -> 12 July
        self.assertEqual(d["band"], "soon")

        # And the label figure would have been 30 July — 18 days of false comfort.
        label = engine.describe(sub, learned=None, today="2026-07-01")
        self.assertEqual(label["end_date"], "2026-07-30")
        self.assertEqual(label["days_left"] - d["days_left"], 18)


if __name__ == "__main__":
    unittest.main()
