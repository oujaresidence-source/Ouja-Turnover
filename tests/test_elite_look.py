"""/elite on «لوك عوجا» (2026-11-25).

/elite is the VIP twin of /apartments: same look (limestone paper, night ink, gold for marks
only, the two Thmanyah faces, 52px pills, hairlines), same date sheet and photo viewer, but
booking stays WhatsApp-only. These tests lock the parts that broke or drifted before:
  * the look itself (tokens + self-hosted fonts, no Google Fonts, no old Bonvoy faces);
  * no Airbnb anywhere in the page;
  * no apartment counts, neither on screen nor in the page data;
  * ZERO backslashes in the embedded JS, and the JS parses (one bad token = blank page);
  * guest reviews reach the unit page, with a source line that does not name a platform.
"""
import asyncio
import inspect
import json
import re
import unittest

import bot

try:
    import esprima
except ImportError:          # pragma: no cover
    esprima = None


def _scripts(html):
    return re.findall(r"<script>(.*?)</script>", html, re.S)


def _data(html):
    m = re.search(r"var ELITE=(.*?);\n", html)
    return json.loads(m.group(1))


class _Req:
    query_string = ""
    query = {}
    match_info = {}

    class url:
        @staticmethod
        def origin():
            return "https://example.test"


class TestEliteLook(unittest.TestCase):
    def setUp(self):
        self.t = bot.ELITE_HTML

    def test_ouja_tokens_and_fonts(self):
        for tok in ("--paper:#F4EFE7", "--ink:#1D1813", "--gold:#A57A2C", "--night:#15110D"):
            self.assertIn(tok, self.t)
        self.assertIn('font-family:"Thmanyah Serif"', self.t)
        self.assertIn('font-family:"Thmanyah Sans"', self.t)
        self.assertIn("/monthly/static/fonts/thmanyah-", self.t)
        for banned in ("fonts.googleapis", "Cormorant", "Reem Kufi", "IBM Plex"):
            self.assertNotIn(banned, self.t)

    def test_pill_buttons_are_ink_52px(self):
        m = re.search(r"\.btn\{[^}]*\}", self.t)
        self.assertIsNotNone(m)
        self.assertIn("min-height:52px", m.group(0))
        self.assertIn("border-radius:999px", m.group(0))
        self.assertIn("background:var(--ink)", m.group(0))

    def test_no_airbnb_anywhere(self):
        self.assertNotIn("airbnb", self.t.lower())

    def test_no_airbnb_in_unit_page_data(self):
        html = bot._elite_render("listing", {"id": 1, "slug": "x", "name_ar": "عوجا", "airbnb_url": "",
                                             "airbnb_source": "hostaway", "has_airbnb": True})
        self.assertNotIn("airbnb", html.lower())

    def test_no_apartment_counts_on_screen(self):
        js = "".join(_scripts(self.t))
        self.assertIsNone(re.search(r"res\.length\s*\+|\+\s*res\.length", js))
        # o.count was the per-neighbourhood count; ro.count (how many guest reviews) is fine
        self.assertIsNone(re.search(r"(?<![A-Za-z_])o\.count", js))
        self.assertNotIn("cfg.count", js)

    def test_no_counts_in_page_data(self):
        cfg = _data(bot._elite_render("home"))["config"]
        self.assertNotIn("count", cfg)
        for nb in cfg.get("neighborhoods") or []:
            self.assertNotIn("count", nb)

    def test_js_has_zero_backslashes(self):
        for js in _scripts(self.t):
            self.assertNotIn("\\", js)

    @unittest.skipIf(esprima is None, "esprima missing")
    def test_js_parses(self):
        for route in ("home", "search", "listing"):
            for js in _scripts(bot._elite_render(route)):
                esprima.parseScript(js)

    def test_whatsapp_only_booking(self):
        js = "".join(_scripts(self.t))
        self.assertIn("wa.me/", js)
        self.assertIn("function waBook(", js)
        self.assertIn("خصم عضوية عوجا إيليت: 20%", js)

    def test_date_sheet_and_viewer_present(self):
        js = "".join(_scripts(self.t))
        self.assertIn("function openSheet(", js)
        self.assertIn("function openGallery(", js)
        self.assertIn(".lb-strip img{display:block;width:100%;height:auto", self.t)

    def test_photos_go_through_webp_proxy(self):
        self.assertIn("'/elite/img?u='", self.t)

    def test_reviews_reach_the_unit_page(self):
        self.assertIn("guest_reviews", inspect.getsource(bot._handle_elite_detail))
        self.assertIn("من تقييمات ضيوف عوجا", self.t)

    def test_routes_still_serve(self):
        r = asyncio.run(bot._handle_elite(_Req()))
        self.assertEqual(r.status, 200)
        r = asyncio.run(bot._handle_elite_search(_Req()))
        self.assertEqual(r.status, 200)


if __name__ == "__main__":
    unittest.main()
