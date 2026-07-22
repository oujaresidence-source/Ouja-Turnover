# -*- coding: utf-8 -*-
"""TDD lock for studio.virality — the research-backed structural audit.

The danger with a "virality score" is that it becomes astrology: a confident number
with nothing behind it. These tests pin it to the researched mechanics and, just as
importantly, pin what it must NEVER reward.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from studio import virality as V  # noqa: E402


def _good():
    return {
        "hook_spoken": "٩٠٪ من ضيوفنا يحجزون قبل يوم واحد",
        "visual_title": "السوق كله صار لحظي",
        "visual_sub": "لو عندك شقة في الرياض هذا يغيّر تسعيرك",
        "angle": "نشرح كيف تقدر تستفيد من الحجز اللحظي",
        "why_it_works": "رقم حقيقي أول ٣ث",
        "script": ["(٠-٣ث) ٩٠٪ من ضيوفنا يحجزون قبل يوم",
                   "(٣-٩ث) لكن أغلب الملاك يسعّرون بشهر",
                   "(٩-١٨ث) الطريقة اللي نسويها احنا",
                   "(١٨-٢٦ث) درس عملي تقدر تجربه بكرة",
                   "(٢٦-٣٠ث) عشان كذا ٩٠٪ من ضيوفنا يحجزون قبل يوم"],
        "cta": "احفظ الفيديو",
        "signal_text": "وسيط مهلة الحجز = يوم واحد",
        "trigger_kind": "social_proof", "video_type": "data_reveal",
    }


class TestBounds(unittest.TestCase):
    def test_score_in_range(self):
        for c in (_good(), {}, {"hook_spoken": ""}, "junk"):
            s = V.score(c) if isinstance(c, dict) else V.audit(c)["score"]
            self.assertGreaterEqual(s, 0)
            self.assertLessEqual(s, 100)

    def test_junk_is_zero_not_a_crash(self):
        a = V.audit("nope")
        self.assertEqual(a["score"], 0)
        self.assertEqual(a["fixes"], [])


class TestHook(unittest.TestCase):
    def test_greeting_opener_is_punished(self):
        c = _good()
        c["hook_spoken"] = "السلام عليكم حياكم الله معكم فيصل من عوجا"
        self.assertLess(V.f_hook_speed(c), 0.5)

    def test_banned_cliche_zeroes_the_hook_factor(self):
        c = _good()
        c["hook_spoken"] = "لن تصدق وش صار في شقتنا"
        self.assertEqual(V.f_hook_speed(c), 0.0)

    def test_short_cold_open_scores_full(self):
        self.assertEqual(V.f_hook_speed(_good()), 1.0)

    def test_long_rambling_hook_drops(self):
        c = _good()
        c["hook_spoken"] = " ".join(["كلمة"] * 20)
        self.assertLess(V.f_hook_speed(c), 0.5)


class TestNumbers(unittest.TestCase):
    def test_arabic_indic_digits_count(self):
        self.assertTrue(V.has_number("٩٠٪ من الضيوف"))

    def test_spoken_arabic_quantities_count(self):
        # he talks, he doesn't read digits aloud — «قبل يوم واحد» is just as specific
        self.assertTrue(V.has_number("يحجزون قبل يوم واحد"))
        self.assertTrue(V.has_number("تسعين بالمية من الضيوف"))
        self.assertFalse(V.has_number("شوف وش صار عندنا"))

    def test_a_bare_year_is_not_a_statistic(self):
        self.assertFalse(V.has_number("في سنة 2026 صار شي"))

    def test_beat_timestamps_do_not_fake_specificity(self):
        c = _good()
        c["hook_spoken"] = "شوف وش صار"
        c["visual_title"] = "قصة من الشقة"
        c["signal_text"] = ""
        self.assertLess(V.f_specificity(c), 0.5)

    def test_number_only_in_the_signal_scores_partial(self):
        c = _good()
        c["hook_spoken"] = "خلني أوريك شي"
        c["visual_title"] = "من داخل العملية"
        v = V.f_specificity(c)
        self.assertGreater(v, 0.3)
        self.assertLess(v, 1.0)


class TestLengthAndRhythm(unittest.TestCase):
    def test_reads_arabic_indic_timings(self):
        secs, n = V.beat_timing(_good()["script"])
        self.assertEqual(secs, 30)
        self.assertEqual(n, 5)

    def test_sweet_spot_scores_full(self):
        self.assertEqual(V.f_length(_good()), 1.0)

    def test_way_too_long_is_penalised(self):
        c = _good()
        c["script"] = ["(٠-٣ث) هوك", "(٣-١٢٠ث) شرح طويل"]
        self.assertLess(V.f_length(c), 0.5)

    def test_unknown_length_is_neutral_not_a_failure(self):
        c = _good()
        c["script"] = ["هوك بدون توقيت", "شرح بدون توقيت"]
        self.assertEqual(V.f_length(c), 0.6)


class TestLoop(unittest.TestCase):
    def test_ending_that_returns_to_the_hook_scores_full(self):
        self.assertEqual(V.f_loop_close(_good()), 1.0)

    def test_unrelated_ending_scores_low(self):
        c = _good()
        c["script"] = c["script"][:-1] + ["(٢٦-٣٠ث) تابعونا للمزيد من المحتوى"]
        self.assertLess(V.f_loop_close(c), 0.6)


class TestSuppression(unittest.TestCase):
    def test_rage_wording_is_penalised_not_rewarded(self):
        clean = _good()
        rage = _good()
        rage["visual_title"] = "فضيحة وكارثة في السوق"
        self.assertLess(V.audit(rage)["score"], V.audit(clean)["score"])
        self.assertLess(V.f_no_suppression(rage), 0.5)

    def test_clean_card_is_not_penalised(self):
        self.assertEqual(V.f_no_suppression(_good()), 1.0)


class TestOnscreen(unittest.TestCase):
    def test_title_that_just_echoes_the_hook_is_marked_down(self):
        c = _good()
        c["visual_title"] = c["hook_spoken"]
        self.assertLessEqual(V.f_onscreen(c), 0.5)

    def test_missing_title_is_zero(self):
        c = _good()
        c["visual_title"] = ""
        self.assertEqual(V.f_onscreen(c), 0.0)


class TestAudit(unittest.TestCase):
    def test_well_built_card_outscores_a_sloppy_one(self):
        sloppy = {"hook_spoken": "السلام عليكم اليوم بنتكلم عن موضوع مهم جداً للجميع",
                  "visual_title": "", "script": [], "angle": ""}
        self.assertGreater(V.audit(_good())["score"], V.audit(sloppy)["score"] + 30)

    def test_weak_factors_come_back_as_actionable_arabic_fixes(self):
        sloppy = {"hook_spoken": "السلام عليكم معكم فيصل", "visual_title": "",
                  "script": [], "angle": "", "signal_text": ""}
        fixes = V.audit(sloppy)["fixes"]
        self.assertTrue(fixes)
        for f in fixes:
            self.assertTrue(f.strip())

    def test_verified_tier_fixes_are_listed_before_directional_ones(self):
        sloppy = {"hook_spoken": "السلام عليكم معكم فيصل", "visual_title": "",
                  "script": ["مشهد واحد بدون توقيت"], "angle": "", "signal_text": ""}
        a = V.audit(sloppy)
        first = a["fixes"][0]
        directional = {V.FIXES["length"], V.FIXES["interrupts"]}
        self.assertNotIn(first, directional)

    def test_strong_factors_are_reported_as_wins(self):
        self.assertTrue(V.audit(_good())["wins"])

    def test_every_factor_has_a_fix_string(self):
        for name, _fn, _w, _label in V.FACTORS:
            self.assertIn(name, V.FIXES)


if __name__ == "__main__":
    unittest.main()
