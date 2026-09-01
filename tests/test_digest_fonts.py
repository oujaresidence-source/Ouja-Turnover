# -*- coding: utf-8 -*-
"""digest.render.fonts — every declared face resolves to a real woff2 in fonts/ that is
byte-identical to the monthly_public original (the good Thmanyah cut, not the older
ThmanyahDisplay-* files), and the @font-face block uses file:// urls so Chromium
subsets and embeds. In the style of tests/test_monthly_fonts.py."""
import hashlib
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from digest.render import fonts, tokens

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MONTHLY = os.path.join(ROOT, "monthly_public", "static", "fonts")


def md5(path):
    with open(path, "rb") as fh:
        return hashlib.md5(fh.read()).hexdigest()


class Faces(unittest.TestCase):
    def test_every_declared_face_exists_and_is_woff2(self):
        self.assertEqual(len(fonts.FACES), 5)
        for fam, w, f in fonts.FACES:
            with self.subTest(face=f):
                p = fonts.path_for(f)
                self.assertTrue(os.path.isfile(p), p)
                with open(p, "rb") as fh:
                    self.assertEqual(fh.read(4), b"wOF2")
                self.assertIn(fam, (fonts.SERIF, fonts.SANS))
                self.assertIn(w, (400, 500, 700, 900))

    def test_files_are_byte_identical_to_the_monthly_public_originals(self):
        for f, origin in fonts.ORIGINS.items():
            with self.subTest(face=f):
                self.assertEqual(md5(fonts.path_for(f)), md5(os.path.join(MONTHLY, origin)))

    def test_not_the_older_display_cut(self):
        # fonts/ThmanyahDisplay-*.woff2 is a different, smaller cut used by cp/; the
        # digest must never reference it.
        for fam, w, f in fonts.FACES:
            self.assertFalse(f.startswith("ThmanyahDisplay-"))

    def test_font_faces_css_uses_file_urls(self):
        css = fonts.font_faces()
        self.assertEqual(css.count("@font-face"), 5)
        self.assertEqual(css.count('src:url("file://'), 5)
        self.assertIn('font-family:"Thmanyah Serif Display";font-weight:900', css)
        self.assertIn('font-family:"Thmanyah Sans";font-weight:400', css)
        self.assertNotIn(chr(92), css)

    def test_stacks_fall_back_to_almarai_then_system(self):
        st = fonts.stacks()
        self.assertTrue(st["serif"].startswith('"Thmanyah Serif Display"'))
        self.assertIn("Almarai", st["sans"])
        self.assertIn("system-ui", st["sans"])
        self.assertTrue(os.path.isfile(fonts.path_for("Almarai-400.woff2")))


class Tokens(unittest.TestCase):
    def test_root_block_and_geometry(self):
        css = tokens.css_root()
        self.assertTrue(css.startswith(":root{--ink:#0B1A2E"))
        self.assertIn("--gold:#C6A15B", css)
        self.assertEqual((tokens.PAGE_W_PT, tokens.PAGE_H_PT), (810, 1440))
        self.assertEqual((tokens.STORY_W, tokens.STORY_H), (1080, 1920))
        self.assertEqual(tokens.STORY_CSS_W * 2, tokens.STORY_W)


if __name__ == "__main__":
    unittest.main()
