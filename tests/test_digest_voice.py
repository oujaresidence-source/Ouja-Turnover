# -*- coding: utf-8 -*-
"""digest.voice — the slop denylist (brief §3.4) and the numeral rule
(Arabic-Indic in prose). Pure half only; the model half is exercised in
test_digest_build with a fake model."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from digest import voice


class Denylist(unittest.TestCase):
    BANNED = [
        "اكتشف الرياض من جديد",
        "اكتشفوا الفعاليات",
        "لا تفوّت الفرصة",
        "لا تفوت العرض",
        "تجربة استثنائية للعائلة",
        "أجواء لا مثيل لها",
        "وجهتك المثالية للعطلة",
        "أجواء ساحرة في الدرعية",
        "على بُعد خطوات من الشقة",
        "على بعد خطوات",
        "انغمس في الثقافة",
        "استمتع بالأجواء",
        "استمتع بـ عرض الليلة",
        "نقلة نوعية في الترفيه",
        "حدث لا يُفوَّت",
        "سحر الرياض",
    ]
    CLEAN = [
        "نور الرياض يرجع",
        "أعمال ضوئية في سبع مناطق، الدخول مجاني",
        "الجمعة ٩ المساء: الشباب والهلال",
        "مشي على الماء قبل المغرب، وموقف قريب",
        "ما لقينا معلومة موثوقة عن الحفلة، فحذفناها",
        "استكشاف الوادي يبدأ من الموقف الشمالي",   # «استكشاف» ≠ «اكتشف»
    ]

    def test_every_banned_phrase_is_caught(self):
        for s in self.BANNED:
            with self.subTest(s=s):
                self.assertTrue(voice.slop_hits(s), s)

    def test_clean_najdi_lines_pass(self):
        for s in self.CLEAN:
            with self.subTest(s=s):
                self.assertEqual(voice.slop_hits(s), [], s)

    def test_hits_report_the_phrase(self):
        hits = voice.slop_hits("اكتشف الرياض، تجربة استثنائية")
        self.assertEqual(len(hits), 2)
        self.assertTrue(any("اكتشف" in h for h in hits))

    def test_is_clean_helper(self):
        self.assertTrue(voice.is_clean("نور الرياض يرجع"))
        self.assertFalse(voice.is_clean("لا تفوّت نور الرياض"))


class Numerals(unittest.TestCase):
    def test_prose_conversion(self):
        self.assertEqual(voice.to_arabic_indic("الجمعة 9:00م"), "الجمعة ٩:٠٠م")
        self.assertEqual(voice.to_arabic_indic("3 سبتمبر · أكشن"), "٣ سبتمبر · أكشن")
        self.assertEqual(voice.to_arabic_indic("بدون أرقام"), "بدون أرقام")

    def test_prose_digits_leaves_latin_runs_alone(self):
        self.assertEqual(voice.prose_digits("Fall 2: Deadpoint"), "Fall 2: Deadpoint")
        self.assertEqual(voice.prose_digits("الجمعة 9:00م"), "الجمعة ٩:٠٠م")
        self.assertEqual(voice.prose_digits(""), "")

    def test_western_digits_in_prose_detector(self):
        self.assertEqual(voice.western_digits_in_prose("٣ سبتمبر"), [])
        self.assertEqual(voice.western_digits_in_prose("3 سبتمبر و 2026"), ["3", "2026"])

    def test_title_and_sub_limits(self):
        self.assertTrue(voice.title_ok("نور الرياض يرجع"))
        self.assertFalse(voice.title_ok("نور الرياض يرجع مرة ثانية"))
        self.assertTrue(voice.sub_ok(" ".join(["كلمة"] * 10)))
        self.assertFalse(voice.sub_ok(" ".join(["كلمة"] * 11)))
        self.assertFalse(voice.title_ok(""))


class Prompt(unittest.TestCase):
    def test_system_prompt_carries_the_bans_and_the_facts_rule(self):
        p = voice.PROMPT_SYSTEM
        self.assertIn("اكتشف", p)
        self.assertIn("لا تفوّت", p)
        self.assertIn("ممنوع", p)
        self.assertNotIn(chr(92), p, "backslash in a prompt string — the non-raw triple-quote trap")


if __name__ == "__main__":
    unittest.main()
