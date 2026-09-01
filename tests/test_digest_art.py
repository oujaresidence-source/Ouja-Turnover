# -*- coding: utf-8 -*-
"""digest.art_generated — deterministic seeded SVG: same input → same bytes, forever
(the frozen test depends on it). Cinema and fixtures use this kind only."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from digest import art_generated
from digest.render import tokens


class Generated(unittest.TestCase):
    def test_same_seed_same_svg(self):
        a = art_generated.svg("12|cinema|0", "الليلة الطويلة", "portrait")
        b = art_generated.svg("12|cinema|0", "الليلة الطويلة", "portrait")
        self.assertEqual(a, b)
        self.assertEqual(art_generated.sha256_of(a), art_generated.sha256_of(b))

    def test_different_slot_different_texture(self):
        a = art_generated.svg("12|cinema|0", "x", "portrait")
        b = art_generated.svg("12|cinema|1", "x", "portrait")
        self.assertNotEqual(a, b)

    def test_kinds_and_geometry(self):
        for kind, (w, h) in art_generated.KINDS.items():
            s = art_generated.svg("s", ("الشباب", "الهلال") if kind == "band" else "ن", kind)
            self.assertIn('viewBox="0 0 %d %d"' % (w, h), s)
            self.assertTrue(s.startswith("<svg") and s.endswith("</svg>"))

    def test_band_sets_both_club_names_in_type_no_crests(self):
        s = art_generated.svg("12|fixtures|band", ("الشباب", "الهلال"), "band")
        self.assertIn(">الشباب<", s)
        self.assertIn(">الهلال<", s)
        self.assertNotIn("<image", s)

    def test_glyph_is_the_first_letter_and_escaped(self):
        s = art_generated.svg("s", "<b>&x", "square")
        self.assertIn(">b<", s)
        self.assertNotIn("<b>", s)
        self.assertIn("Thmanyah Serif Display", s)

    def test_only_token_colours_and_low_amplitude(self):
        import re
        s = art_generated.svg("s", "ن", "square")
        hexes = {h.lower() for h in re.findall(r"#[0-9A-Fa-f]{6}", s)}
        self.assertTrue(hexes.issubset(tokens.hexes()), hexes - tokens.hexes())
        self.assertEqual(s.count("<polyline"), art_generated.LINES)
        self.assertLessEqual(art_generated.AMPLITUDE, 3.0)

    def test_no_backslashes_in_module(self):
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "digest", "art_generated.py")
        with open(p, encoding="utf-8") as fh:
            self.assertNotIn(chr(92), fh.read())


if __name__ == "__main__":
    unittest.main()
