# -*- coding: utf-8 -*-
"""TDD lock for studio.learn — the performance learning loop (pure math).

Spec Section I: learn which TRIGGERS / AUDIENCES / FORMATS / SOURCE FAMILIES earn
views for THIS account, bias generation toward them, and make the learning VISIBLE.

Locks:
  * a dimension value under MIN_SAMPLE posts is never reported as a finding
    (two lucky videos must not rewrite the strategy)
  * lift is measured against the overall mean, not against zero
  * strength_of degrades to a neutral score when there's no history yet
  * insights are Arabic strings the owner can actually read
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from studio import learn  # noqa: E402


def _post(trigger, views, audience="niche", video_type="talking",
          signal_family="internal"):
    return {"trigger_kind": trigger, "views": views, "audience": audience,
            "video_type": video_type, "signal_family": signal_family,
            "status": "posted"}


class TestStats(unittest.TestCase):
    def test_no_history_is_empty_not_crash(self):
        st = learn.stats([])
        self.assertEqual(st["n"], 0)
        self.assertEqual(learn.insights_ar(st), [])

    def test_ignores_unposted_and_zero_view_rows(self):
        rows = [_post("curiosity", 0), dict(_post("curiosity", 500), status="new")]
        self.assertEqual(learn.stats(rows)["n"], 0)

    def test_under_min_sample_is_not_a_finding(self):
        rows = [_post("news", 100000), _post("news", 90000), _post("tour_x", 10)]
        st = learn.stats(rows)
        self.assertEqual(learn.insights_ar(st), [])   # 2 posts < MIN_SAMPLE

    def test_lift_is_relative_to_overall_mean(self):
        rows = ([_post("curiosity", 200)] * 3) + ([_post("identity", 1000)] * 3)
        st = learn.stats(rows)
        trig = st["dims"]["trigger"]
        self.assertGreater(trig["identity"]["lift"], 1.0)
        self.assertLess(trig["curiosity"]["lift"], 1.0)
        self.assertEqual(trig["identity"]["n"], 3)

    def test_insights_mention_the_winner_in_arabic(self):
        rows = ([_post("curiosity", 200)] * 3) + ([_post("news", 2000)] * 3)
        lines = learn.insights_ar(learn.stats(rows))
        self.assertTrue(lines)
        self.assertTrue(any("خبر" in ln or "news" in ln for ln in lines),
                        "insight should name the winning trigger: %r" % lines)


class TestStrength(unittest.TestCase):
    def test_neutral_when_no_history(self):
        st = learn.stats([])
        s = learn.strength_of({"trigger": "news", "audience": "niche",
                               "video_type": "talking"}, st)
        self.assertEqual(s, learn.NEUTRAL_STRENGTH)

    def test_winning_trigger_scores_above_losing_one(self):
        rows = ([_post("curiosity", 200)] * 4) + ([_post("news", 4000)] * 4)
        st = learn.stats(rows)
        hi = learn.strength_of({"trigger": "news"}, st)
        lo = learn.strength_of({"trigger": "curiosity"}, st)
        self.assertGreater(hi, lo)

    def test_always_within_bounds(self):
        rows = ([_post("news", 10_000_000)] * 5) + ([_post("curiosity", 1)] * 5)
        st = learn.stats(rows)
        for t in ("news", "curiosity", "unknown_trigger"):
            s = learn.strength_of({"trigger": t}, st)
            self.assertGreaterEqual(s, 0)
            self.assertLessEqual(s, 100)


class TestBiasHint(unittest.TestCase):
    def test_empty_without_history(self):
        self.assertEqual(learn.bias_hint_ar(learn.stats([])), "")

    def test_mentions_winners_when_history_exists(self):
        rows = ([_post("news", 5000, audience="escape")] * 4) + \
               ([_post("curiosity", 100)] * 4)
        hint = learn.bias_hint_ar(learn.stats(rows))
        self.assertIn("news", hint)


if __name__ == "__main__":
    unittest.main()
