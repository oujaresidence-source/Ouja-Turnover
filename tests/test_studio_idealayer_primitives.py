# -*- coding: utf-8 -*-
"""TDD lock for the idea-layer fix primitives (2026-07-24). All PURE.

These are the pieces the generation rewrite stands on: kill the timed-beat grid,
enforce number-first, give every card a distinct shape, and reduce virality to ONE
actionable fix. Locked here so the ideas.py rewrite can rely on them.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from studio import engine, shapes, virality  # noqa: E402


class TestStripTimestamps(unittest.TestCase):
    def test_strips_arabic_beat_grid(self):
        self.assertEqual(engine.strip_timestamps("(٠-٣ث) ٩٠٪ يحجزون قبل يوم"),
                         "90٪ يحجزون قبل يوم")

    def test_strips_english_beat_grid(self):
        self.assertEqual(engine.strip_timestamps("(3-8s) here is the turn"),
                         "here is the turn")

    def test_strips_leading_time_label(self):
        self.assertEqual(engine.strip_timestamps("0-3: the hook lands"), "the hook lands")

    def test_leaves_a_real_number_alone(self):
        # a fact number in the sentence must survive — only the beat marker goes
        self.assertIn("47", engine.strip_timestamps("(٣-٨ث) 47 شقة محجوزة"))

    def test_no_timestamp_left_after_parse(self):
        raw = {"ideas": [{"hook_spoken": "٤٧ شقة محجوزة الخميس الجاي",
                          "visual_title": "الخميس مو الثلاثاء", "why_it_works": "رقم",
                          "script": ["(٠-٣ث) ٤٧ محجوزة", "(٣-٨ث) طيب ليش الخميس",
                                     "(٨-١٦ث) عشان الويكند"]}]}
        card = engine.parse_ideas(raw)[0]
        joined = " ".join(card["script"])
        self.assertNotRegex(joined, r"[（(]\s*\d+\s*[-–—]\s*\d+")
        self.assertNotIn("ث)", joined)
        self.assertIn("47", joined)


class TestNumberFirst(unittest.TestCase):
    def test_hook_leading_with_number_passes(self):
        self.assertTrue(engine.leads_with_number("٩٠٪ من ضيوفنا يحجزون قبل يوم",
                                                 "وسيط مهلة الحجز يوم واحد ٩٠٪"))

    def test_hook_burying_the_number_fails(self):
        self.assertFalse(engine.leads_with_number(
            "تعرف كم ضيف يحجز بسرعة؟ عندنا ٩٠٪", "٩٠٪ يحجزون قبل يوم"))

    def test_fact_without_a_number_is_vacuously_ok(self):
        self.assertTrue(engine.leads_with_number("قصة غريبة صارت لنا",
                                                 "موقف طريف بدون أرقام"))

    def test_spoken_word_number_in_fact_still_needs_a_number_up_front(self):
        # fact has a digit; hook must lead with a digit/percent
        self.assertFalse(engine.leads_with_number("خلني أحكي لك قصة",
                                                  "٤٧ شقة محجوزة"))


class TestShapes(unittest.TestCase):
    def test_source_gets_a_natural_shape(self):
        self.assertEqual(shapes.pick_shape("reviews"), "quote_reaction")
        self.assertEqual(shapes.pick_shape("regulation"), "news_react")

    def test_candidates_are_distinct(self):
        c = shapes.candidate_shapes("occupancy", "social_proof", "niche", n=3)
        self.assertEqual(len(c), len(set(c)))
        self.assertEqual(len(c), 3)

    def test_exclude_rotates_away(self):
        first = shapes.pick_shape("pricing")
        second = shapes.pick_shape("pricing", exclude={first})
        self.assertNotEqual(first, second)

    def test_every_source_resolves_to_a_real_shape(self):
        for src in engine.SIGNAL_SOURCES:
            k = shapes.pick_shape(src)
            self.assertIn(k, shapes.SHAPE_KEYS, src)

    def test_guide_block_names_each_shape(self):
        block = shapes.guide_block(["cold_number", "myth_bust"])
        self.assertIn("cold_number", block)
        self.assertIn("myth_bust", block)


class TestSingleFix(unittest.TestCase):
    def _card(self, **kw):
        c = {"hook_spoken": "٩٠٪ من ضيوفنا يحجزون قبل يوم",
             "visual_title": "السوق صار لحظي", "visual_sub": "لو عندك شقة بالرياض",
             "angle": "شرح", "script": ["٩٠٪ يحجزون قبل يوم", "لكن الملاك يسعّرون بشهر",
                                        "الطريقة اللي نسويها", "عشان كذا ٩٠٪ يحجزون قبل يوم"],
             "cta": "احفظه", "signal_text": "وسيط مهلة الحجز يوم واحد"}
        c.update(kw)
        return c

    def test_returns_at_most_one_fix(self):
        a = virality.audit(self._card(hook_spoken="السلام عليكم معكم فيصل",
                                      visual_title="", script=[], signal_text=""))
        self.assertLessEqual(len(a["fixes"]), 1)

    def test_a_clean_card_shows_no_fix(self):
        self.assertEqual(virality.audit(self._card())["fixes"], [])

    def test_the_fix_is_the_weakest_factor(self):
        # this card is fine except it has no on-screen sub that differs — force a weak spot
        card = self._card(visual_title=self._card()["hook_spoken"])  # title echoes hook
        a = virality.audit(card)
        if a["fixes"]:
            self.assertEqual(a["weakest"], "onscreen")

    def test_satisfied_number_first_is_never_a_fix(self):
        a = virality.audit(self._card())   # number leads the hook
        self.assertNotIn(virality.FIXES["specificity"], a["fixes"])


if __name__ == "__main__":
    unittest.main()
