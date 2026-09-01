# -*- coding: utf-8 -*-
"""digest.render — html builds offline and obeys the design rules (tokens only, no
shadows, logical properties only, one eyebrow + one foot per page, layouts by count,
no placeholder card). The Chromium class renders the reference payload for real and
checks the geometry; it skips only when Chromium cannot launch."""
import json
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from digest.render import html as rhtml, tokens, build, audit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HEX = re.compile(r"#[0-9A-Fa-f]{6}\b")
_PHYSICAL = re.compile(r"(?<![-\w])(left|right)\s*:|(padding|margin|border)-(left|right)\s*:|text-align\s*:\s*(left|right)|float\s*:")


def ref():
    return build.reference_payload()


def section(p, key):
    return [s for s in p["sections"] if s["key"] == key][0]


class Offline(unittest.TestCase):
    def setUp(self):
        self.p = ref()
        self.html = rhtml.build_pages(self.p, {})

    def test_builds_a_document(self):
        self.assertTrue(self.html.startswith("<!doctype html>"))
        self.assertIn('<html lang="ar" dir="rtl">', self.html)
        self.assertEqual(self.html.count('class="page'), 6)      # cover + 4 sections + back

    def test_only_token_colours(self):
        hexes = {h.lower() for h in _HEX.findall(self.html)}
        self.assertTrue(hexes.issubset(tokens.hexes()), hexes - tokens.hexes())

    def test_no_shadows_no_physical_properties(self):
        css = "".join(re.findall(r"<style>(.*?)</style>", self.html, re.S))
        self.assertNotIn("box-shadow", css)
        self.assertNotIn("text-shadow", css)
        self.assertIsNone(_PHYSICAL.search(css), _PHYSICAL.search(css) and _PHYSICAL.search(css).group(0))

    def test_every_page_has_one_eyebrow_one_claim_one_foot(self):
        pages = re.findall(r'<section class="page.*?</section>', self.html, re.S)
        self.assertEqual(len(pages), 6)
        for pg in pages:
            self.assertEqual(pg.count('class="eyebrow"'), 1)
            self.assertEqual(pg.count('class="claim"'), 1)
            self.assertEqual(pg.count('class="foot"'), 1)

    def test_layout_follows_the_payload(self):
        self.assertIn('class="grid g3v"', self.html)
        p = ref(); s = section(p, "events"); s["items"] = s["items"][:2]; s["layout"] = "g2h"
        self.assertIn('class="grid g2h"', rhtml.build_pages(p, {}))

    def test_empty_section_is_not_a_page(self):
        p = ref(); section(p, "cinema")["items"] = []
        h = rhtml.build_pages(p, {})
        self.assertEqual(h.count('class="page'), 5)
        self.assertNotIn('class="page cinema"', h)
        self.assertNotIn('<div class="eyebrow">جديد في السينما</div>', h)

    def test_no_placeholder_and_every_card_has_a_title(self):
        self.assertNotIn("قريباً", self.html)
        self.assertNotIn("placeholder", self.html)
        cards = re.findall(r'<div class="card.*?</div></div>', self.html, re.S)
        self.assertTrue(cards)
        for c in cards:
            self.assertRegex(c, r'class="ttl">\S')

    def test_urls_only_from_the_verified_set(self):
        verified = set(self.p["verified_urls"])
        for u in re.findall(r'(?:href|data-url)="([^"]+)"', self.html):
            self.assertIn(u, verified)

    def test_qr_is_deterministic_and_local(self):
        a = rhtml.qr_svg("https://oujares.com")
        self.assertEqual(a, rhtml.qr_svg("https://oujares.com"))
        self.assertIn('data-url="https://oujares.com"', a)
        self.assertIn("viewBox=", a)
        self.assertIn(tokens.TOKENS["ink"].lower(), a.lower())

    def test_latin_runs_are_ltr_spans(self):
        p = ref(); section(p, "cinema")["items"][0]["ttl"] = "Fall 2: Deadpoint"
        h = rhtml.build_pages(p, {})
        self.assertIn('<span dir="ltr">Fall 2: Deadpoint</span>', h)

    def test_story_builds(self):
        s = rhtml.build_story(self.p, {})
        self.assertIn('class="story"', s)
        self.assertIn("نور الرياض يرجع", s)
        self.assertIn("الشباب × الهلال", s)

    def test_render_sources_have_zero_backslashes(self):
        for f in ("digest/render/html.py", "digest/render/audit.py", "digest/art_generated.py"):
            with open(os.path.join(ROOT, f), encoding="utf-8") as fh:
                self.assertNotIn(chr(92), fh.read(), f)

    def test_reference_payload_equals_the_test_fixture(self):
        with open(os.path.join(ROOT, "tests", "fixtures", "digest", "payload_good.json"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh), ref())


_CHROMIUM = build.chromium_available()


@unittest.skipUnless(_CHROMIUM, "Chromium (playwright) not available here")
class Chromium(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="digestrender_")
        cls.res = build.render(ref(), {}, cls.tmp, 0, run_audit=True)

    def test_pdf_geometry(self):
        import fitz
        d = fitz.open(self.res["pdf"])
        self.assertEqual(d.page_count, 6)
        for pg in d:
            self.assertEqual((round(pg.rect.width), round(pg.rect.height)), (810, 1440))
        self.assertIn("وش صاير بالرياض", d[0].get_text())

    def test_story_geometry(self):
        from PIL import Image
        self.assertEqual(Image.open(self.res["png"]).size, (1080, 1920))

    def test_audit_clean_and_layout_fingerprint(self):
        self.assertEqual(self.res["audit"], [])
        self.assertTrue(self.res["layout_md5"])
        self.assertTrue(self.res["layout"])

    def test_overflow_is_caught(self):
        p = ref()
        s = section(p, "events")
        s["items"] = [dict(s["items"][0], sub="كلمة " * 400) for _ in range(3)]
        with self.assertRaises(audit.LayoutError):
            build.render(p, {}, os.path.join(self.tmp, "bad"), 1, run_audit=True)


if __name__ == "__main__":
    unittest.main()
