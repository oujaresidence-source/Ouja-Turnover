# -*- coding: utf-8 -*-
"""
cp.page — the rendered Arabic edition.

What these tests hold, in order of how expensive each would be to lose:

  1. The disclosure guard runs ON THE RENDER PATH, not just in CI — a page
     carrying a withheld figure raises, it does not serve.
  2. The copy is the approved document's copy. A handful of sentinel sentences
     (chosen from different sections, including ones with tricky diacritics)
     must appear byte-for-byte.
  3. Empty inputs degrade to the document's own visible placeholders — never
     invented reviews, never broken images, never a dead wa.me link.
  4. Every __TOKEN__ is filled on every render path.

Run: python3 -m unittest tests.test_cp_page
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cp import guard, page, stats  # noqa: E402


def render(**kw):
    kw.setdefault("base", "https://oujares.com")
    kw.setdefault("links", {"email": "partnerships@oujares.com", "wa": ""})
    return page.render_ar(**kw)


class EveryPlaceholderFills(unittest.TestCase):
    def test_default_render(self):
        self.assertEqual(page.remaining_placeholders(render()), [])

    def test_bare_render_no_base_no_links(self):
        self.assertEqual(page.remaining_placeholders(
            page.render_ar(base="", links=None)), [])

    def test_live_snapshot_render(self):
        html = render(snapshot={"reservations_total": 8290,
                                "computed_at": "2026-09-01T03:00:00Z"})
        self.assertEqual(page.remaining_placeholders(html), [])
        self.assertIn("8,290", html)


class CopyIsVerbatim(unittest.TestCase):
    """Sentences owned by the approved document, byte-for-byte."""

    SENTINELS = [
        # hero qualifier
        "وحداتنا لا.",
        # the door-code step — diacritics and all
        "آخر أربعة أرقام من جوالك، تُكتب على القفل لحظة الحجز وتنتهي بمغادرتك.",
        # the third decline
        "سلّمنا مُلّاكاً إلى صفقات أفضل من صفقتنا.",
        # governance: insurance stated honestly
        "نقولها صراحة لأنك ستسأل عنها.",
        # the withheld-items framing line
        "ننشر الأداء الإجمالي لأن بإمكانك التحقق منه.",
        # closing statement
        "أفضل الأرقام ليست في هذه الصفحة.",
    ]

    def test_sentinel_sentences_survive_the_port(self):
        html = render()
        for s in self.SENTINELS:
            with self.subTest(sentence=s[:32]):
                self.assertIn(s, html)

    def test_figures_render_as_the_seeds_state_them(self):
        html = render()
        for figure in ("8,114", "13,093", "76.9%", "4.77", "2,633", "87.6%",
                       "933", "78.6%", "152,177", "2.3", "66,000"):
            with self.subTest(figure=figure):
                self.assertIn(figure, html)

    def test_the_two_authored_routes_are_marked_in_data_not_prose(self):
        """Five doors render; exactly two carry authored=True in the data file."""
        html = render()
        self.assertEqual(html.count('<div class="route">'), 5)
        authored = [r for r in page.ROUTES_AR if r.get("authored")]
        self.assertEqual(len(authored), 2)
        self.assertEqual({r["key"] for r in authored}, {"platform", "supplier"})


class GuardRunsOnTheRenderPath(unittest.TestCase):
    def test_default_page_is_clean(self):
        render()  # assert_clean inside must not raise

    def test_a_poisoned_snapshot_cannot_serve(self):
        """A snapshot restating a retired figure kills the render, not the reader's
        trust. 7,311 is the retired stay count."""
        with self.assertRaises(guard.DisclosureError):
            render(snapshot={"reservations_total": 7311,
                             "computed_at": "2026-09-01T00:00:00Z"})

    def test_a_poisoned_review_cannot_serve(self):
        bad = [{"slot": 1, "guest_name": "X", "listing_name": "Y", "date": "Aug 2026",
                "language": "ar", "text_original": "إيرادهم 7,669,457 ريال"}]
        with self.assertRaises(guard.DisclosureError):
            render(reviews=bad)


class HonestDegradation(unittest.TestCase):
    def test_empty_review_slots_render_the_documents_blanks(self):
        html = render(reviews=[])
        self.assertEqual(html.count('class="fillin"') >= 6, True)
        self.assertIn("مراجعة ناقدة — وأبقِها كما هي.", html)

    def test_a_real_review_renders_verbatim_with_attribution(self):
        r = [{"slot": 1, "guest_name": "أحمد م.", "listing_name": "Ouja | Calma 90",
              "date": "أبريل 2026", "language": "ar",
              "text_original": "الشقة نظيفة والتواصل سريع، شكراً نورة."}]
        html = render(reviews=r)
        self.assertIn("الشقة نظيفة والتواصل سريع، شكراً نورة.", html)
        self.assertIn("أحمد م.", html)

    def test_an_english_review_keeps_ltr_and_gets_marked_translation(self):
        r = [{"slot": 1, "guest_name": "Sarah K.", "listing_name": "Ouja | Hue",
              "date": "May 2026", "language": "en",
              "text_original": "Spotless place, checked in at 2am with no fuss.",
              "translation_ar": "شقة نظيفة تماماً، سجلت دخولي الثانية فجراً بلا أي تعقيد."}]
        html = render(reviews=r)
        self.assertIn('lang="en" dir="ltr"', html)
        self.assertIn("Spotless place", html)
        self.assertIn("الترجمة", html)

    def test_empty_units_render_dashed_placeholders_not_broken_images(self):
        html = render(units=[])
        self.assertNotIn('<img src=""', html)
        self.assertGreaterEqual(html.count('<div class="ph">'), 6)

    def test_missing_whatsapp_renders_a_disabled_button_never_a_dead_link(self):
        html = render(links={"email": "x@oujares.com", "wa": ""})
        self.assertNotIn("wa.me/966500000000", html)
        self.assertNotIn('href="https://wa.me/"', html)
        self.assertIn("is-disabled", html)

    def test_placeholder_number_is_treated_as_unset(self):
        html = render(links={"email": "x@oujares.com", "wa": "966500000000"})
        self.assertNotIn("wa.me/966500000000", html)

    def test_real_whatsapp_number_renders_real_links(self):
        html = render(links={"email": "x@oujares.com", "wa": "966512345678"})
        self.assertIn("https://wa.me/966512345678", html)
        self.assertNotIn("is-disabled", html)

    def test_no_email_renders_no_gmail_fallback(self):
        """Defect §8.1: the Gmail address undoes the page. Without CP_EMAIL the
        buttons must NOT quietly fall back to oujaresidence@gmail.com."""
        html = render(links={"email": "", "wa": ""})
        self.assertNotIn("oujaresidence@gmail.com", html)
        self.assertNotIn("mailto:", html)


class SyncStampIsTruthful(unittest.TestCase):
    def test_without_a_snapshot_the_page_does_not_claim_nightly_refresh(self):
        html = render(snapshot=None)
        self.assertNotIn("تُحدَّث كل ليلة", html)
        self.assertIn("أغسطس 2026", html)

    def test_with_a_live_snapshot_it_does_and_dates_it(self):
        html = render(snapshot={"reservations_total": 8290,
                                "computed_at": "2026-09-03T03:00:00Z"})
        self.assertIn("تُحدَّث كل ليلة", html)
        self.assertIn("سبتمبر 2026", html)


class DerivedNumbersAreComputedNotTyped(unittest.TestCase):
    def test_occupancy_table_multiples(self):
        """1BR at 80.9 over a 38% market must print 2.1×, computed."""
        html = render()
        self.assertIn("80.9%", html)
        self.assertIn("2.1×", html)
        self.assertIn("1.9×", html)

    def test_bar_widths_move_with_the_figures(self):
        base = render()
        moved = render(snapshot={"adr_sar": 300, "reservations_total": 8114,
                                 "computed_at": "2026-09-01T00:00:00Z"})
        def width_of(html, needle="__"):
            import re
            m = re.search(r'style="width:([\d.]+)%">300', html)
            return m and m.group(1)
        self.assertIsNone(width_of(base))
        w = width_of(moved)
        self.assertIsNotNone(w)
        self.assertLess(float(w), 93.5)

    def test_capacity_bar_is_a_ratio(self):
        html = render()
        self.assertIn('style="width:37%"', html)  # 74 / 200


class OptionalNavigation(unittest.TestCase):
    def test_english_and_pdf_links_absent_until_real(self):
        html = render()
        self.assertNotIn('href="/cp/en"', html)
        self.assertNotIn('href="/cp.pdf"', html)
        self.assertNotIn('hreflang="en"', html)

    def test_present_when_enabled(self):
        html = render(english=True, pdf=True)
        self.assertIn('href="/cp/en"', html)
        self.assertIn('href="/cp.pdf"', html)
        self.assertIn('hreflang="en" href="https://oujares.com/cp/en"', html)


class TemplateHygiene(unittest.TestCase):
    def test_no_backslash_anywhere_in_the_rendered_page(self):
        self.assertNotIn("\\", render(units=[{
            "listing_id": "1", "name_ar": "عوجا | كالما", "bedrooms_label_ar": "غرفتان",
            "compound_ar": "كالما 90", "line_ar": "دخول ذاتي", "photo": "x.jpg"}]))

    def test_braces_balance(self):
        html = render()
        self.assertEqual(html.count("{"), html.count("}"))

    def test_script_parses(self):
        try:
            import esprima
        except ImportError:
            self.skipTest("esprima not installed here")
        import re
        for js in re.findall(r"<script>(.*?)</script>", render(), re.S):
            esprima.parseScript(js)


if __name__ == "__main__":
    unittest.main()


class TheSixChosenReviews(unittest.TestCase):
    """The filled slots (owner direction 2026-08-26: use the /business store).

    Every text must be byte-for-byte identical to business/data/reviews_curated.json
    — the store is the proof the words are the guests' own. If someone 'tidies' a
    review in cp_reviews.json, this is the test that catches it.
    """

    def setUp(self):
        import json
        with open(os.path.join(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))), "cp", "data", "cp_reviews.json"),
                encoding="utf-8") as fh:
            self.slots = json.load(fh)
        with open(os.path.join(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))), "business", "data",
                "reviews_curated.json"), encoding="utf-8") as fh:
            self.store = {r["id"]: r for r in json.load(fh)}

    def test_six_slots_all_filled(self):
        self.assertEqual(len(self.slots), 6)
        for rec in self.slots:
            with self.subTest(slot=rec["slot"]):
                self.assertTrue(rec["text_original"].strip())

    def test_every_text_is_verbatim_from_the_store(self):
        for rec in self.slots:
            with self.subTest(slot=rec["slot"]):
                self.assertEqual(rec["text_original"],
                                 self.store[rec["review_id"]]["text"])

    def test_the_critical_slot_is_genuinely_critical(self):
        critical = [r for r in self.slots if r["slot"] == 6][0]
        self.assertIn("العزل ضعيف", critical["text_original"])

    def test_the_english_review_carries_a_marked_translation(self):
        en = [r for r in self.slots if r["language"] == "en"]
        self.assertEqual(len(en), 1)
        self.assertTrue(en[0]["translation_ar"].strip())

    def test_dates_are_month_and_year_only(self):
        import re
        for rec in self.slots:
            with self.subTest(slot=rec["slot"]):
                self.assertTrue(re.match(r"^[؀-ۿ]+ 20\d\d$", rec["date"]),
                                "date %r is not «month year»" % rec["date"])

    def test_they_render_and_the_blanks_are_gone(self):
        html = render(reviews=self.slots)
        self.assertIn("العزل ضعيف", html)          # the critical one, kept in
        self.assertIn("ثاني مرة ازورهم", html)      # the returning guest
        self.assertIn("وحلها لي في دقائق", html)    # the fixed problem
        self.assertIn("I booked last minute", html)  # the English original
        self.assertIn("الترجمة", html)               # its marked translation
        self.assertNotIn("مراجعة منشورة حقيقية", html)  # no leftover blank briefs
        self.assertEqual(page.remaining_placeholders(html), [])
