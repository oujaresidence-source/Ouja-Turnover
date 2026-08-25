# -*- coding: utf-8 -*-
"""«إيقاف موقع الضيوف» — the /stay pause switch, and the blast radius it must not have.

The owner asked (2026-08-24) for oujares.com/stay to go quiet: a real "page not
found", every page, switched from Railway with no code change.

The danger is not the pause — it is the over-reach. /elite and /monthly BORROW the
/api/stay/* endpoints (search, listing, event). A pause that grabs everything named
"stay" silently takes two other live sites down with it. So these tests lock BOTH
halves: the six guest pages go dark, and nothing else moves.

Run: python3 -m unittest tests.test_stay_pause
"""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("STATE_DIR", "/tmp/ouja-test-state-staypause")
os.makedirs("/tmp/ouja-test-state-staypause", exist_ok=True)

import asyncio          # noqa: E402
from aiohttp import web  # noqa: E402
import bot              # noqa: E402


class _URL:
    def origin(self):
        return "http://localhost"

    def __str__(self):
        return "http://localhost"


class _Req:
    """Just enough aiohttp request for these read-only page handlers."""
    def __init__(self, match=None, qs=""):
        self.url = _URL()
        self.match_info = match or {}
        self.query_string = qs
        self.query = {}
        self.headers = {}
        self.cookies = {}


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


class _Paused:
    """Context manager: flip the switch the way Railway does, then put it back."""
    def __init__(self, on):
        self.on = on
        self.prev = None

    def __enter__(self):
        self.prev = os.environ.get("STAY_PAUSED")
        os.environ["STAY_PAUSED"] = "1" if self.on else "0"
        return self

    def __exit__(self, *a):
        if self.prev is None:
            os.environ.pop("STAY_PAUSED", None)
        else:
            os.environ["STAY_PAUSED"] = self.prev
        return False


# The six visitor-facing pages, as (name, handler, request) — /stay, /stay/,
# /stay/search, /stay/match, /stay/id/{lid}, /stay/{slug}.
def _pages():
    return [
        ("/stay",         bot._handle_stay,        _Req()),
        ("/stay/search",  bot._handle_stay_search, _Req()),
        ("/stay/match",   bot._handle_stay_match,  _Req()),
        ("/stay/id/{lid}", bot._handle_stay_id,    _Req(match={"lid": "999999"})),
        ("/stay/{slug}",  bot._handle_stay_detail, _Req(match={"slug": "no-such-unit"})),
    ]


class TestSwitchDefaultsOff(unittest.TestCase):
    def test_default_is_live(self):
        """No env var set = the site is up. A pause must never be the default."""
        prev = os.environ.pop("STAY_PAUSED", None)
        try:
            self.assertFalse(bot._stay_paused())
        finally:
            if prev is not None:
                os.environ["STAY_PAUSED"] = prev

    def test_zero_is_live(self):
        with _Paused(False):
            self.assertFalse(bot._stay_paused())

    def test_one_is_paused(self):
        with _Paused(True):
            self.assertTrue(bot._stay_paused())


class TestPagesGoDark(unittest.TestCase):
    def test_every_page_404s_when_paused(self):
        with _Paused(True):
            for name, handler, req in _pages():
                with self.subTest(page=name):
                    with self.assertRaises(web.HTTPNotFound):
                        _run(handler(req))

    def test_every_page_serves_when_live(self):
        with _Paused(False):
            for name, handler, req in _pages():
                with self.subTest(page=name):
                    try:
                        resp = _run(handler(req))
                    except web.HTTPFound:
                        continue          # /stay/id redirects to the slug — still alive
                    self.assertEqual(resp.status, 200)


class TestBlastRadius(unittest.TestCase):
    """The pause must stop at /stay's own pages. Elite and Monthly share the pipes."""

    def test_shared_apis_stay_up(self):
        with _Paused(True):
            for name, handler in (("config", bot._api_stay_config),
                                  ("featured", bot._api_stay_featured)):
                with self.subTest(api=name):
                    resp = _run(handler(_Req()))
                    self.assertEqual(resp.status, 200)

    def test_elite_and_monthly_stay_up(self):
        with _Paused(True):
            for name, handler in (("/elite", bot._handle_elite),
                                  ("/monthly", bot._handle_monthly)):
                with self.subTest(site=name):
                    resp = _run(handler(_Req()))
                    self.assertEqual(resp.status, 200)

    def test_hero_image_is_not_a_page(self):
        """The dashboard previews the hero from /stay/hero-image. Pausing the guest
        site must not blind an internal tool."""
        with _Paused(True):
            try:
                resp = _run(bot._handle_stay_hero_image(_Req()))
            except web.HTTPNotFound:
                # No hero uploaded in a bare test state — that 404 is the handler's
                # own "nothing to serve", not the pause. Assert it is not the pause
                # by checking the live case gives the identical answer.
                with _Paused(False):
                    with self.assertRaises(web.HTTPNotFound):
                        _run(bot._handle_stay_hero_image(_Req()))
                return
            self.assertEqual(resp.status, 200)


class TestSearchEngineSignals(unittest.TestCase):
    def test_robots_stops_advertising_a_dead_site(self):
        with _Paused(True):
            txt = _run(bot._handle_robots(_Req())).text
            self.assertIn("Disallow: /stay", txt)
            self.assertNotIn("Allow: /stay", txt)

    def test_robots_allows_when_live(self):
        with _Paused(False):
            txt = _run(bot._handle_robots(_Req())).text
            self.assertIn("Allow: /stay", txt)

    def test_sitemap_lists_nothing_when_paused(self):
        with _Paused(True):
            body = _run(bot._handle_sitemap(_Req())).text
            self.assertNotIn("/stay", body)
            self.assertIn("<urlset", body)      # still valid XML, just empty

    def test_sitemap_lists_stay_when_live(self):
        with _Paused(False):
            body = _run(bot._handle_sitemap(_Req())).text
            self.assertIn("/stay", body)


class TestBusinessPageHasNoDeadButtons(unittest.TestCase):
    """/business is public and stays up while /stay is paused. None of its three
    buttons may point at a page that answers 404."""

    def test_live_book_goes_to_stay(self):
        with _Paused(False):
            l = bot._biz_links("https://oujares.com", "966500000000")
            self.assertEqual(l["book"], "https://oujares.com/stay")
            self.assertEqual(l["wa"], "https://wa.me/966500000000")

    def test_paused_book_goes_to_whatsapp(self):
        with _Paused(True):
            l = bot._biz_links("https://oujares.com", "966500000000")
            self.assertEqual(l["book"], "https://wa.me/966500000000")
            self.assertEqual(l["wa"], "https://wa.me/966500000000")

    def test_paused_without_a_number_falls_back_to_email_not_stay(self):
        """The pre-existing WhatsApp fallback was /stay. While paused that is a
        dead link, so both buttons must land on email instead."""
        with _Paused(True):
            l = bot._biz_links("https://oujares.com", "")
            for key in ("book", "wa"):
                with self.subTest(button=key):
                    self.assertNotIn("/stay", l[key])
                    self.assertTrue(l[key].startswith("mailto:"), l[key])

    def test_no_link_is_ever_empty(self):
        for paused in (True, False):
            for wa in ("966500000000", ""):
                for base in ("https://oujares.com", ""):
                    with _Paused(paused):
                        l = bot._biz_links(base, wa)
                    for key in ("book", "wa", "email"):
                        with self.subTest(paused=paused, wa=bool(wa),
                                          base=bool(base), button=key):
                            self.assertTrue(l[key], "empty href would reload the page")


if __name__ == "__main__":
    unittest.main()
