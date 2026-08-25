# -*- coding: utf-8 -*-
"""TDD lock for studio.plan.choose — the daily-set selector (pure).

Spec H2/H4/H5. What must hold no matter how the pool looks:
  * an angle already served recently never comes back
  * the set spreads across audience / source family / trigger before it chases
    raw strength (three variations of the same strong card is a wasted day)
  * a fresh external signal outranks an equally strong evergreen one
  * two near-duplicate candidates never both land in the same day
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from studio import engine, plan  # noqa: E402


def _card(title, angle="", audience="niche", family="internal", trigger="curiosity",
          strength=50, date=""):
    c = {"id": abs(hash(title)) % 100000, "visual_title": title, "angle": angle or title,
         "audience": audience, "signal_family": family, "trigger_kind": trigger,
         "strength": strength, "signal_date": date}
    c["nkey"] = engine.novelty_key(title + " " + (angle or title))
    return c


class TestChoose(unittest.TestCase):
    def test_empty_pool(self):
        self.assertEqual(plan.choose([], [], n=3), [])

    def test_respects_n(self):
        # deliberately unrelated angles — near-duplicates are collapsed on purpose
        pool = [_card(t) for t in (
            "الإشغال وصل ذروته نهاية الأسبوع",
            "كيف نحوّل شقة عادية لتجربة فندقية",
            "نظام سياحي جديد يخص كل مالك عقار",
            "أسرع تنظيف بين ضيفين بالرياض",
            "أعلى سعر ليلة عندنا هالشهر")]
        self.assertEqual(len(plan.choose(pool, [], n=3)), 3)

    def test_already_served_angle_is_excluded(self):
        served = _card("تسعير الشقق يتغير كل ساعة بالرياض")
        other = _card("كيف ننظف الشقة خلال ساعتين بين ضيفين")
        got = plan.choose([served, other], recent_keys=[served["nkey"]], n=3)
        self.assertEqual([c["visual_title"] for c in got], [other["visual_title"]])

    def test_near_duplicates_do_not_both_get_picked(self):
        a = _card("تسعير الشقق يتغير كل ساعة بالرياض")
        b = _card("الشقق بالرياض تسعيرها يتغير كل ساعة", strength=99)
        c = _card("كيف نحوّل شقة عادية لتجربة فندق")
        got = plan.choose([a, b, c], [], n=3)
        self.assertEqual(len(got), 2, [x["visual_title"] for x in got])

    def test_spread_beats_raw_strength(self):
        # three strong but identical-shaped cards vs one weaker card that adds variety
        strong = [_card("موضوع قوي واحد اليوم", audience="niche", family="internal",
                        trigger="curiosity", strength=95),
                  _card("موضوع قوي ثاني مختلف", audience="niche", family="internal",
                        trigger="curiosity", strength=94),
                  _card("موضوع قوي ثالث بعيد", audience="niche", family="internal",
                        trigger="curiosity", strength=93)]
        varied = _card("زاوية مختلفة للجمهور العام", audience="escape",
                       family="external", trigger="news", strength=40,
                       date="2026-07-23")
        got = plan.choose(strong + [varied], [], n=2, today="2026-07-23")
        self.assertIn(varied["visual_title"], [c["visual_title"] for c in got])

    def test_fresh_news_outranks_stale_news_of_equal_strength(self):
        fresh = _card("خبر نزل اليوم عن الأنظمة", family="external", trigger="news",
                      strength=50, date="2026-07-23")
        stale = _card("خبر قديم عن السوق العالمي", family="external", trigger="news",
                      strength=50, date="2026-01-01")
        got = plan.choose([stale, fresh], [], n=1, today="2026-07-23")
        self.assertEqual(got[0]["visual_title"], fresh["visual_title"])

    def test_missing_signal_date_does_not_crash_or_win(self):
        undated = _card("بدون تاريخ", family="external", trigger="news", strength=50)
        dated = _card("بتاريخ اليوم وموضوع مختلف", family="external", trigger="news",
                      strength=50, date="2026-07-23")
        got = plan.choose([undated, dated], [], n=1, today="2026-07-23")
        self.assertEqual(got[0]["visual_title"], dated["visual_title"])

    def test_junk_entries_are_ignored(self):
        good = _card("فكرة سليمة عن الإشغال")
        self.assertEqual(len(plan.choose([None, "x", 5, good], [], n=3)), 1)


if __name__ == "__main__":
    unittest.main()
