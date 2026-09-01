# -*- coding: utf-8 -*-
"""digest.art_generated — deterministic seeded SVG: same input → same bytes, forever
(the frozen test depends on it). Cinema and fixtures use this kind only."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from digest import art_generated, art
from digest.render import tokens
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "digest"))
from _fake_http import FakeHttp


def _png(w, h):
    from PIL import Image
    import io
    im = Image.new("RGB", (w, h), (30, 40, 60)); b = io.BytesIO(); im.save(b, "PNG"); return b.getvalue()


class Fallback(unittest.TestCase):
    """A → B → C → D, offline through FakeHttp."""

    def _item(self, og="https://cdn.platinumlist.net/upload/e.jpg", url="https://riyadh.platinumlist.net/ar/event-tickets/1/x", slug=None):
        it = {"ttl": "نور الرياض", "url": url, "art_hint": {"og": og} if og else {}}
        if slug:
            it["slug"] = slug
        return it

    def test_cinema_and_fixtures_never_touch_the_network(self):
        http = FakeHttp()
        for section in ("cinema", "fixtures"):
            got = art.resolve(self._item(), section, 12, 0, http)
            self.assertEqual(got["kind"], "generated")
        self.assertEqual(http.calls, [])

    def test_og_same_site_big_enough_is_used_and_hashed(self):
        raw = _png(900, 600)
        http = FakeHttp(pages={"https://cdn.platinumlist.net/upload/e.jpg": (200, "image/png", raw)})
        got = art.resolve(self._item(), "events", 12, 0, http, owned={})
        self.assertEqual(got["kind"], "og")
        self.assertTrue(got["src"].startswith("data:image/jpeg;base64,"))
        self.assertEqual(len(got["sha256"]), 64)
        again = art.resolve(self._item(), "events", 12, 0, http, owned={})
        self.assertEqual(again["sha256"], got["sha256"])

    def test_og_rejected_cross_site_small_or_not_an_image(self):
        big = _png(900, 600)
        http = FakeHttp(pages={
            "https://images.example/e.jpg": (200, "image/png", big),
            "https://cdn.platinumlist.net/small.jpg": (200, "image/png", _png(300, 200)),
            "https://cdn.platinumlist.net/page.html": (200, "text/html", "<html>"),
        })
        self.assertEqual(art.resolve(self._item(og="https://images.example/e.jpg"), "events", 12, 0, http, owned={})["kind"], "generated")
        self.assertEqual(art.resolve(self._item(og="https://cdn.platinumlist.net/small.jpg"), "events", 12, 0, http, owned={})["kind"], "generated")
        self.assertEqual(art.resolve(self._item(og="https://cdn.platinumlist.net/page.html"), "events", 12, 0, http, owned={})["kind"], "generated")
        self.assertEqual(art.resolve(self._item(og="http://cdn.platinumlist.net/e.jpg"), "events", 12, 0, http, owned={})["kind"], "generated")

    def test_owned_wins_over_og(self):
        http = FakeHttp(pages={"https://oujares.com/img/wadi.jpg": (200, "image/jpeg", _png(1200, 800)),
                               "https://cdn.platinumlist.net/upload/e.jpg": (200, "image/png", _png(900, 600))})
        owned = {"wadi-hanifah": {"url": "https://oujares.com/img/wadi.jpg", "credit": "Ouja"}}
        got = art.resolve(self._item(slug="wadi-hanifah"), "worth", 12, 0, http, owned=owned)
        self.assertEqual(got["kind"], "owned")
        self.assertEqual([c[1] for c in http.calls], ["https://oujares.com/img/wadi.jpg"])

    def test_dead_og_falls_to_generated(self):
        got = art.resolve(self._item(), "events", 12, 0, FakeHttp(), owned={})
        self.assertEqual(got["kind"], "generated")
        self.assertTrue(got["sha256"])

    def test_same_site_rule(self):
        self.assertTrue(art.same_site("https://cdn.platinumlist.net/x.jpg", "https://riyadh.platinumlist.net/e"))
        self.assertFalse(art.same_site("https://cdn.example.com/x.jpg", "https://riyadh.platinumlist.net/e"))
        self.assertEqual(art.load_owned(), {})


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
