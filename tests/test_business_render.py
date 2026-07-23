# -*- coding: utf-8 -*-
"""
Tests for business.render — locale formatting + page-data assembly.

Numerals switch with language (superprompt §6): Western in EN, Arabic-Indic in AR,
with the Arabic thousands (٬) and decimal (٫) separators. One utility, never a
per-string decision.

Run:  python3 -m unittest tests.test_business_render
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from business import render  # noqa: E402


class NumberFormatting(unittest.TestCase):
    def test_integer_english_uses_western_digits_and_comma(self):
        self.assertEqual(render.fmt_int(7311, "en"), "7,311")
        self.assertEqual(render.fmt_int(11307, "en"), "11,307")

    def test_integer_arabic_uses_indic_digits_and_arabic_thousands(self):
        self.assertEqual(render.fmt_int(7311, "ar"), "٧٬٣١١")
        self.assertEqual(render.fmt_int(0, "ar"), "٠")

    def test_decimal_english(self):
        self.assertEqual(render.fmt_dec(4.77, "en"), "4.77")

    def test_decimal_arabic_uses_arabic_decimal_separator(self):
        self.assertEqual(render.fmt_dec(4.77, "ar"), "٤٫٧٧")

    def test_percent_english(self):
        self.assertEqual(render.fmt_pct(0.876, "en"), "87.6%")
        self.assertEqual(render.fmt_pct(0.368, "en"), "36.8%")

    def test_percent_arabic(self):
        self.assertEqual(render.fmt_pct(0.876, "ar"), "٨٧٫٦٪")

    def test_localize_digits_passthrough_for_english(self):
        self.assertEqual(render.localize_digits("Q2'26", "en"), "Q2'26")

    def test_localize_digits_arabic(self):
        self.assertEqual(render.localize_digits("2026", "ar"), "٢٠٢٦")


class PageDataAssembly(unittest.TestCase):
    def test_load_metrics_falls_back_to_verified_when_no_snapshot(self):
        # No STATE_DIR snapshot in the test env -> verified fallback (§4 numbers).
        m = render.load_metrics(state_dir="/nonexistent-dir-xyz")
        self.assertEqual(m["reservations_total"], 7311)
        self.assertEqual(m["rating_avg_5"], 4.77)

    def test_assemble_blob_has_all_sections(self):
        blob = render.assemble("en")
        for key in ("metrics", "manual", "reviews", "lang", "as_of"):
            self.assertIn(key, blob)
        self.assertEqual(blob["lang"], "en")
        self.assertEqual(len(blob["reviews"]), 30)

    def test_contains_emoji_detects_and_ignores_correctly(self):
        self.assertTrue(render.contains_emoji("great \U0001f44d"))
        self.assertTrue(render.contains_emoji("❤️"))
        self.assertFalse(render.contains_emoji("Two years. 7,311 stays."))
        self.assertFalse(render.contains_emoji("سنتان. ٧٬٣١١ إقامة."))
        self.assertFalse(render.contains_emoji("4.77★"))  # ★ is a typographic glyph, per §A1

    def test_our_chrome_is_emoji_free_but_guest_reviews_are_verbatim(self):
        # §6: our copy carries no emoji. §8: guest review text is verbatim (may have any).
        blob = render.assemble("en")
        for entry in blob["manual"].values():
            for k in ("label_en", "label_ar"):
                if entry.get(k):
                    self.assertFalse(render.contains_emoji(entry[k]),
                                     "manual label must be emoji-free: %r" % entry[k])
        # at least one seed review legitimately contains an emoji (proves we don't strip)
        self.assertTrue(any(render.contains_emoji(r["text"]) for r in blob["reviews"]))

    def test_reviews_carry_required_card_fields(self):
        blob = render.assemble("ar")
        r = blob["reviews"][0]
        for key in ("id", "name", "date", "listing", "lang", "themes", "text"):
            self.assertIn(key, r)


if __name__ == "__main__":
    unittest.main()
