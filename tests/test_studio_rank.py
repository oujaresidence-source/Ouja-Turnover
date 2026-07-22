# -*- coding: utf-8 -*-
"""TDD lock for studio.rank — «أقرب فكرة تشتغل».

The owner films the top card without reading the rest, so the order IS the product.
What must hold:
  * with zero history the ranking still discriminates (prior + signal + freshness)
  * real performance history outweighs the playbook prior, never the reverse
  * an ungrounded card can never outrank an equally-shaped grounded one
  * stale news loses to fresh news
  * the score is always 0..100 and the sort is stable
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from studio import learn, rank  # noqa: E402


def _card(trigger="curiosity", fmt="talking", family="internal", date="",
          signal="رقم حقيقي من بيانات عوجا", strength=50, title="عنوان"):
    return {"visual_title": title, "trigger_kind": trigger, "video_type": fmt,
            "signal_family": family, "signal_date": date, "signal_text": signal,
            "signal_strength": strength, "audience": "niche"}


def _hist(trigger, views, n=4):
    return [{"status": "posted", "views": views, "trigger_kind": trigger,
             "audience": "niche", "video_type": "talking",
             "signal_family": "internal"} for _ in range(n)]


class TestBounds(unittest.TestCase):
    def test_always_within_range(self):
        st = learn.stats(_hist("news", 5_000_000) + _hist("curiosity", 1))
        for c in (_card("news", "news_reaction", "external", "2026-07-23", strength=100),
                  _card("provocation", "story_voiceover", signal="", strength=0),
                  {}):
            s = rank.score(c, st, "2026-07-23")
            self.assertGreaterEqual(s, 0)
            self.assertLessEqual(s, 100)

    def test_junk_is_zero_not_a_crash(self):
        self.assertEqual(rank.score("not a card"), 0)
        self.assertEqual(rank.rank([None, "x", 3]), [])


class TestNoHistory(unittest.TestCase):
    def test_still_discriminates_on_day_one(self):
        st = learn.stats([])
        good = _card("identity", "before_after", strength=90)
        weak = _card("provocation", "story_voiceover", strength=20)
        self.assertGreater(rank.score(good, st), rank.score(weak, st))

    def test_history_contributes_nothing_when_absent(self):
        self.assertEqual(rank.history_points(_card("news"), learn.stats([])), 0.0)


class TestGrounding(unittest.TestCase):
    def test_ungrounded_card_loses_to_identical_grounded_one(self):
        st = learn.stats([])
        grounded = _card(signal="٤٧ من ٥٣ شقة محجوزة", strength=70)
        floating = _card(signal="", strength=70)
        self.assertGreater(rank.score(grounded, st), rank.score(floating, st))

    def test_missing_signal_is_named_in_the_reasons(self):
        why = rank.reasons_ar(_card(signal=""), learn.stats([]))
        self.assertTrue(any("بدون إشارة" in w for w in why), why)


class TestFreshness(unittest.TestCase):
    def test_fresh_news_beats_stale_news(self):
        st = learn.stats([])
        fresh = _card("news", "news_reaction", "external", "2026-07-23")
        stale = _card("news", "news_reaction", "external", "2026-01-01")
        self.assertGreater(rank.score(fresh, st, "2026-07-23"),
                           rank.score(stale, st, "2026-07-23"))

    def test_internal_signals_do_not_decay(self):
        old = _card("social_proof", "data_reveal", "internal", "2020-01-01")
        self.assertEqual(rank.freshness_points(old, "2026-07-23"), 0.0)

    def test_undated_external_gets_no_bonus(self):
        self.assertEqual(
            rank.freshness_points(_card("news", "talking", "external", ""), "2026-07-23"),
            0.0)


class TestHistoryWins(unittest.TestCase):
    def test_proven_trigger_overtakes_a_better_prior(self):
        # 'curiosity' has a weaker prior than 'identity', but it is what works for him
        st = learn.stats(_hist("curiosity", 800_000) + _hist("identity", 2_000))
        proven = _card("curiosity", "talking")
        prior_favourite = _card("identity", "talking")
        self.assertGreater(rank.score(proven, st), rank.score(prior_favourite, st))

    def test_reason_names_the_history_match(self):
        st = learn.stats(_hist("curiosity", 800_000) + _hist("identity", 2_000))
        why = rank.reasons_ar(_card("curiosity", "talking"), st)
        self.assertTrue(any("نجح لك" in w for w in why), why)


class TestRankSort(unittest.TestCase):
    def test_best_first_and_stamped(self):
        st = learn.stats([])
        out = rank.rank([_card("provocation", "story_voiceover", strength=10, title="ضعيفة"),
                         _card("identity", "before_after", strength=95, title="قوية")], st)
        self.assertEqual(out[0]["visual_title"], "قوية")
        self.assertIn("rank_score", out[0])
        self.assertIsInstance(out[0]["rank_why"], list)

    def test_ties_keep_incoming_order(self):
        st = learn.stats([])
        a, b = _card(title="أ"), _card(title="ب")
        out = rank.rank([a, b], st)
        self.assertEqual([c["visual_title"] for c in out], ["أ", "ب"])


if __name__ == "__main__":
    unittest.main()
