# -*- coding: utf-8 -*-
"""«إعادة إطلاق موقع الشقق» — the guest site relaunched at /apartments (2026-09-15).

Owner rules locked here:
  * The new address is LIVE BY DEFAULT — the old STAY_PAUSED=1 still set on Railway
    must not keep it dark (the owner never edits Railway vars).
  * The old /stay links forward (301) to /apartments, query string intact.
  * Every page carries the browsing-only notice: no booking, no payment here, booking
    inside Airbnb, units licensed by the Ministry of Tourism — and no license number.
  * /apartments/about is a full page saying the same, in Arabic and English.
  * Nothing on the site invites a guest to "book directly" outside the platform.
  * /elite and /monthly (which borrow /api/stay/*) are untouched.

Run: python3 -m unittest tests.test_apartments_site
"""
import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("STATE_DIR", "/tmp/ouja-test-state-apartments")
os.makedirs("/tmp/ouja-test-state-apartments", exist_ok=True)

import asyncio          # noqa: E402
from aiohttp import web  # noqa: E402
import bot              # noqa: E402


class _URL:
    def origin(self):
        return "http://localhost"

    def __str__(self):
        return "http://localhost"


class _Req:
    def __init__(self, match=None, qs=""):
        self.url = _URL()
        self.match_info = match or {}
        self.query_string = qs
        self.query = {}
        self.headers = {}
        self.cookies = {}


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


NOTICE_AR = "لا يتم أي حجز أو دفع"


class TestLiveByDefaultDespiteOldSwitch(unittest.TestCase):
    def test_old_stay_paused_flag_does_not_pause_apartments(self):
        prev_old, prev_new = os.environ.get("STAY_PAUSED"), os.environ.pop("APARTMENTS_PAUSED", None)
        os.environ["STAY_PAUSED"] = "1"           # exactly what Railway still has
        try:
            self.assertFalse(bot._stay_paused())
            self.assertEqual(_run(bot._handle_stay(_Req())).status, 200)
            self.assertEqual(_run(bot._handle_stay_about(_Req())).status, 200)
        finally:
            if prev_old is None:
                os.environ.pop("STAY_PAUSED", None)
            else:
                os.environ["STAY_PAUSED"] = prev_old
            if prev_new is not None:
                os.environ["APARTMENTS_PAUSED"] = prev_new


class TestOldAddressForwards(unittest.TestCase):
    def _go(self, rest="", qs=""):
        with self.assertRaises(web.HTTPMovedPermanently) as cm:
            _run(bot._handle_stay_legacy(_Req(match={"rest": rest}, qs=qs)))
        return cm.exception.location

    def test_root(self):
        self.assertEqual(self._go(), "/apartments")

    def test_search_keeps_query(self):
        self.assertEqual(self._go("search", "guests=2&check_in=2026-10-01"),
                         "/apartments/search?guests=2&check_in=2026-10-01")

    def test_unit_slug(self):
        self.assertEqual(self._go("ouja-hittin-101"), "/apartments/ouja-hittin-101")

    def test_hero_image_is_still_served_not_forwarded(self):
        """The dashboard previews /stay/hero-image — it must stay a file, not a redirect."""
        src = Path(bot.__file__).read_text(encoding="utf-8")
        i_hero = src.index('add_get("/stay/hero-image"')
        i_legacy = src.index('add_get("/stay/{rest:.*}"')
        self.assertLess(i_hero, i_legacy, "/stay/hero-image must be registered before the /stay catch-all")


class TestRouteOrder(unittest.TestCase):
    def test_about_and_match_precede_the_slug_catch_all(self):
        src = Path(bot.__file__).read_text(encoding="utf-8")
        i_slug = src.index('add_get("/apartments/{slug}"')
        for fixed in ('add_get("/apartments/about"', 'add_get("/apartments/match"',
                      'add_get("/apartments/search"', 'add_get("/apartments/id/{lid}"'):
            self.assertLess(src.index(fixed), i_slug, fixed)


class TestNoticeOnEveryPage(unittest.TestCase):
    def _page(self, route):
        return bot._stay_render(route, base="http://localhost")

    def test_landing_has_the_note_under_the_search_bar(self):
        html = self._page("landing")
        self.assertIn('class="note"', html)
        self.assertIn(NOTICE_AR, html)
        self.assertIn('href="/apartments/about"', html)

    def test_footer_on_every_route(self):
        for route in ("landing", "search", "listing", "match", "about"):
            with self.subTest(route=route):
                html = self._page(route)
                self.assertIn("موقع تصفح فقط", html)
                self.assertIn("عن هذا الموقع", html)

    def test_unit_page_says_no_payment_here(self):
        html = self._page("listing")
        self.assertIn("لا يتم أي حجز أو دفع في هذا الموقع", html)

    def test_no_direct_booking_invitation(self):
        html = self._page("listing")
        self.assertNotIn("احجز مباشرة", html)
        self.assertNotIn("أبغى أحجز مباشرة", html)

    def test_no_license_number_shown(self):
        html = self._page("about")
        self.assertNotRegex(html, r"رقم الترخيص|License No|license number", "owner asked for NO license number")

    def test_no_old_page_links_remain(self):
        html = self._page("landing")
        stray = [m for m in re.findall(r"(?<!/api)/stay[^\s'\"<]*", html) if not m.startswith("/stay/hero-image")]
        self.assertEqual(stray, [], stray)


class TestAboutPage(unittest.TestCase):
    def test_renders_with_its_own_title(self):
        html = bot._stay_render("about", base="http://localhost")
        self.assertIn("<title>عن هذا الموقع · عوجا</title>", html)
        self.assertIn('<link rel="canonical" href="http://localhost/apartments/about">', html)

    def test_says_the_four_things_in_both_languages(self):
        html = bot._stay_render("about", base="http://localhost")
        for needle in ("لا يتم أي حجز أو تأكيد حجز هنا", "لا يتم أي دفع أو تحصيل مالي",
                       "داخل منصة Airbnb", "مرخّصة من وزارة السياحة",
                       "No booking or booking confirmation is made here",
                       "No payment or collection of money",
                       "licensed by the Ministry of Tourism"):
            with self.subTest(needle=needle):
                self.assertIn(needle, html)

    def test_handler_serves_200(self):
        self.assertEqual(_run(bot._handle_stay_about(_Req())).status, 200)


class TestSearchEngineSignals(unittest.TestCase):
    def test_sitemap_lists_the_new_address_and_about(self):
        body = _run(bot._handle_sitemap(_Req())).text
        self.assertIn("http://localhost/apartments</loc>", body)
        self.assertIn("http://localhost/apartments/about</loc>", body)
        self.assertNotIn("/stay<", body)

    def test_robots_allows_the_new_address(self):
        txt = _run(bot._handle_robots(_Req())).text
        self.assertIn("Allow: /apartments", txt)


class TestBlastRadius(unittest.TestCase):
    def test_elite_monthly_and_shared_apis_untouched(self):
        for name, handler in (("/elite", bot._handle_elite), ("/monthly", bot._handle_monthly),
                              ("config", bot._api_stay_config), ("featured", bot._api_stay_featured)):
            with self.subTest(page=name):
                self.assertEqual(_run(handler(_Req())).status, 200)

    def test_business_page_book_button_points_at_the_new_address(self):
        self.assertEqual(bot._biz_links("https://oujares.com", "")["book"], "https://oujares.com/apartments")


if __name__ == "__main__":
    unittest.main()
