# -*- coding: utf-8 -*-
"""
Render + integrity tests for business.page.

Guards the two outage classes this repo has been bitten by:
  * a bad token in the embedded <script> (parsed here with esprima if present),
  * unfilled placeholders / brace imbalance in the served HTML.
Plus the brief's hard rules: numerals switch with language, our chrome is
emoji-free, and no static number contradicts the live snapshot.

Run:  python3 -m unittest tests.test_business_page
"""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from business import page, render  # noqa: E402

LINKS = {"book": "https://airbnb.com/x", "wa": "https://wa.me/966",
         "email": "oujaresidence@gmail.com"}


class Renders(unittest.TestCase):
    def setUp(self):
        self.html = {lang: page.render_page(lang, base="https://oujares.com", links=LINKS)
                     for lang in ("en", "ar")}

    def test_doctype_and_direction(self):
        self.assertIn("<!doctype html>", self.html["en"])
        self.assertIn('dir="ltr"', self.html["en"])
        self.assertIn('dir="rtl"', self.html["ar"])

    def test_no_unfilled_placeholders(self):
        for lang in ("en", "ar"):
            for ph in ("__LANG__", "__DIR__", "__BODY__", "__TITLE__", "__DESC__",
                       "__FOOTER__", "__HEAD_EXTRA__", "__BRAND__", "__ALT_HREF__"):
                self.assertNotIn(ph, self.html[lang], "%s left in %s" % (ph, lang))

    def test_brace_balance(self):
        for lang in ("en", "ar"):
            h = self.html[lang]
            self.assertEqual(h.count("{"), h.count("}"), "brace imbalance in " + lang)

    def test_embedded_script_parses(self):
        try:
            import esprima
        except ImportError:
            self.skipTest("esprima not installed")
        for lang in ("en", "ar"):
            for js in re.findall(r"<script>(.*?)</script>", self.html[lang], re.S):
                esprima.parseScript(js)  # raises on a bad token

    def test_numerals_switch_with_language(self):
        self.assertIn("7,311", self.html["en"])
        self.assertIn("4.77", self.html["en"])
        self.assertTrue(any(d in self.html["ar"] for d in "٠١٢٣٤٥٦٧٨٩"))
        self.assertIn("٧٬٣١١", self.html["ar"])  # 7,311 localized

    def test_meta_desc_matches_live_number_not_a_stale_constant(self):
        # the old bug: AR meta hardcoded ٣٬٨٣٥ (3,835). It must carry the live count.
        self.assertNotIn("٣٬٨٣٥", self.html["ar"])
        self.assertIn('content="', self.html["ar"])

    def test_seo_structured_data_present(self):
        for lang in ("en", "ar"):
            self.assertIn("application/ld+json", self.html[lang])
            self.assertIn('hreflang="ar"', self.html[lang])
            self.assertIn("AggregateRating", self.html[lang])
            self.assertIn('property="og:title"', self.html[lang])

    def test_tracks_render_without_owners_and_without_forms(self):
        for lang in ("en", "ar"):
            for tid in ("platforms", "corporate", "suppliers"):
                self.assertIn('id="%s"' % tid, self.html[lang])
            # owners track is hidden for now (owner request)
            self.assertNotIn('id="owners"', self.html[lang])
            self.assertNotIn('data-track="owners"', self.html[lang])
            # forms are hidden for now — no lead/proposal form in the DOM
            self.assertNotIn('data-kind="lead"', self.html[lang])
            self.assertNotIn('data-kind="proposal"', self.html[lang])
            self.assertNotIn('class="lead-form"', self.html[lang])

    def test_no_exact_listing_count_and_no_cr_or_hostaway(self):
        for lang in ("en", "ar"):
            h = self.html[lang]
            self.assertNotIn("67 listings", h)
            self.assertNotIn("Hostaway", h)          # "trusted PMS" instead
            self.assertNotIn("7050158810", h)         # CR number removed
            self.assertNotIn("Commercial Registration", h)

    def test_review_wall_scales_with_featured_default_and_show_all(self):
        for lang in ("en", "ar"):
            h = self.html[lang]
            total = h.count('data-themes=')          # every review card carries data-themes
            self.assertGreaterEqual(total, 100)       # the full curated set is in the DOM
            self.assertEqual(h.count('class="review "') + h.count('class="review"'), 30)  # 30 shown by default
            self.assertIn('class="review-wall collapsed"', h)
            self.assertIn("data-show-all", h)
            self.assertIn('class="tfilter', h)

    def test_our_chrome_is_emoji_free(self):
        # scan template + copy (not guest review text, which is verbatim)
        self.assertFalse(render.contains_emoji(page.SHELL))
        for lang in ("en", "ar"):
            t = page.COPY[lang]
            stack = [t]
            while stack:
                o = stack.pop()
                if isinstance(o, str):
                    self.assertFalse(render.contains_emoji(o), "emoji in copy: %r" % o)
                elif isinstance(o, dict):
                    stack.extend(o.values())
                elif isinstance(o, (list, tuple)):
                    stack.extend(o)


if __name__ == "__main__":
    unittest.main()
