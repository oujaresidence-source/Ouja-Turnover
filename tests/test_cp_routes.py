# -*- coding: utf-8 -*-
"""
cp.routes — the HTTP boundary, exercised with a real aiohttp app.

The properties held here are the ones a reader actually hits:
  * /cp redirects into the Arabic edition while English does not exist,
    and /cp/en comes back 302 (temporary), never 301 — a cache must not
    learn a permanent home for a page that is not built yet.
  * /cp.pdf without a file is an honest 404, not a broken download.
  * /business does NOT redirect until the flag is flipped (it serves English
    readers today; sending them to an Arabic-only page is a regression).
  * The lead endpoint validates, rate-limits, survives Discord being down,
    and never loses a lead that reached the disk.

Run: python3 -m unittest tests.test_cp_routes
"""
import asyncio
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiohttp import web  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

from cp import host, routes  # noqa: E402


def _json_response(data, status=200):
    return web.json_response(data, status=status)


class _Store:
    """In-memory stand-in for the bot's _save_json/_load_json pair."""
    def __init__(self):
        self.data = {}

    def load(self, name, default=None):
        return self.data.get(name, default)

    def save(self, name, obj):
        self.data[name] = obj
        return True


def make_client(loop, store=None, notify=None, **caps):
    store = store or _Store()
    wired = {
        "web": web, "json_response": _json_response,
        "save_json": store.save, "load_json": store.load,
        "notify": notify, "base_url": "https://oujares.com",
        "links": {"email": "partnerships@oujares.com", "wa": ""},
        "pdf_path": "", "default_lang": "ar",
        "english_ready": False, "redirect_business": False,
        "listing_photos": None,
    }
    wired.update(caps)
    host.wire(wired)
    routes._recent.clear()
    app = web.Application()
    routes.register(app)
    client = TestClient(TestServer(app), loop=loop)
    loop.run_until_complete(client.start_server())
    return client, store


class _Base(unittest.TestCase):
    caps = {}

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        self.notified = []
        self.client, self.store = make_client(
            self.loop, notify=self.notified.append, **self.caps)

    def tearDown(self):
        self.loop.run_until_complete(self.client.close())
        self.loop.close()

    def get(self, path, **kw):
        return self.loop.run_until_complete(self.client.get(path, **kw))

    def post(self, path, **kw):
        return self.loop.run_until_complete(self.client.post(path, **kw))

    def body(self, resp):
        return self.loop.run_until_complete(resp.text())


class Pages(_Base):
    def test_root_redirects_to_arabic(self):
        r = self.get("/cp", allow_redirects=False)
        self.assertEqual(r.status, 302)
        self.assertEqual(r.headers["Location"], "/cp/ar")

    def test_arabic_edition_serves(self):
        r = self.get("/cp/ar")
        self.assertEqual(r.status, 200)
        html = self.body(r)
        self.assertIn('lang="ar" dir="rtl"', html)
        self.assertIn("8,114", html)

    def test_english_redirects_temporarily_while_unbuilt(self):
        r = self.get("/cp/en", allow_redirects=False)
        self.assertEqual(r.status, 302)
        self.assertEqual(r.headers["Location"], "/cp/ar")

    def test_pdf_is_an_honest_404_without_a_file(self):
        r = self.get("/cp.pdf")
        self.assertEqual(r.status, 404)

    def test_business_is_untouched_by_default(self):
        r = self.get("/business")
        self.assertEqual(r.status, 404)  # not registered by this app at all


class BusinessRedirectFlag(_Base):
    caps = {"redirect_business": True}

    def test_business_301s_when_flagged(self):
        r = self.get("/business", allow_redirects=False)
        self.assertEqual(r.status, 301)
        self.assertEqual(r.headers["Location"], "/cp")


class StatsApi(_Base):
    def test_stats_carry_provenance_and_stamp(self):
        r = self.get("/api/cp/stats")
        data = self.loop.run_until_complete(r.json())
        self.assertTrue(data["ok"])
        self.assertFalse(data["stamp"]["live"])
        cell = data["figures"]["reservations_total"]
        self.assertEqual(cell["value"], 8114)
        self.assertEqual(cell["source"], "seeds")
        self.assertEqual(data["market"]["occupancy_pct"], 38)

    def test_reviews_api_serves_the_six_filled_slots(self):
        r = self.get("/api/cp/reviews")
        data = self.loop.run_until_complete(r.json())
        self.assertTrue(data["ok"])
        self.assertEqual(data["count"], 6)
        # the critical review is present and untouched (seeds §15)
        texts = [x["text_original"] for x in data["reviews"]]
        self.assertTrue(any("العزل ضعيف" in t for t in texts))
        # no internal fields leak through the public API
        for x in data["reviews"]:
            self.assertNotIn("review_id", x)
            self.assertNotIn("_why_chosen", x)


class Leads(_Base):
    def _lead(self, **over):
        payload = {"name": "خالد", "phone": "0551234567",
                   "audience": "owner", "message": "أملك شقة في الملقا"}
        payload.update(over)
        return self.post("/api/cp/lead", json=payload)

    def test_a_lead_lands_on_disk_and_notifies(self):
        r = self._lead()
        data = self.loop.run_until_complete(r.json())
        self.assertTrue(data["ok"])
        self.assertTrue(data["notified"])
        stored = self.store.data["cp_leads.json"]["leads"]
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["audience"], "owner")
        self.assertEqual(len(self.notified), 1)

    def test_no_contact_no_lead(self):
        r = self._lead(name="", phone="")
        self.assertEqual(r.status, 400)
        self.assertNotIn("cp_leads.json", self.store.data)

    def test_an_unknown_audience_is_coerced_not_stored_raw(self):
        self._lead(audience="<script>alert(1)</script>")
        stored = self.store.data["cp_leads.json"]["leads"]
        self.assertEqual(stored[0]["audience"], "owner")

    def test_unexpected_fields_are_dropped(self):
        self._lead(role="admin", amount="7,669,457")
        fields = self.store.data["cp_leads.json"]["leads"][0]["fields"]
        self.assertNotIn("role", fields)
        self.assertNotIn("amount", fields)

    def test_discord_down_still_saves_the_lead(self):
        def boom(record):
            raise RuntimeError("discord down")
        self.loop.run_until_complete(self.client.close())
        self.client, self.store = make_client(self.loop, notify=boom)
        r = self._lead()
        data = self.loop.run_until_complete(r.json())
        self.assertTrue(data["ok"])
        self.assertFalse(data["notified"])
        self.assertEqual(len(self.store.data["cp_leads.json"]["leads"]), 1)

    def test_rate_limit_kicks_in(self):
        for _ in range(routes._RATE_MAX):
            self._lead()
        r = self._lead()
        self.assertEqual(r.status, 429)
        stored = self.store.data["cp_leads.json"]["leads"]
        self.assertEqual(len(stored), routes._RATE_MAX)


if __name__ == "__main__":
    unittest.main()


class BrandAssets(_Base):
    def test_share_card_and_icons_serve(self):
        for name in ("icon.png", "icon-192.png", "icon-512.png", "share.png"):
            r = self.get("/cp/" + name)
            self.assertEqual(r.status, 200, name)
            self.assertIn("max-age", r.headers.get("Cache-Control", ""))

    def test_unknown_asset_404s(self):
        r = self.get("/cp/evil.png")
        self.assertEqual(r.status, 404)

    def test_page_head_carries_icon_and_share(self):
        html = self.body(self.get("/cp/ar"))
        self.assertIn('rel="icon" href="/cp/icon.png"', html)
        self.assertIn('og:image" content="https://oujares.com/cp/share.png', html)


class MiddlewareExemption(unittest.TestCase):
    """Found on the live deploy, not locally: bot.py's global role middleware
    401s any POST not in its exemption map, and these tests build a bare app
    that never runs it. The lead endpoint must stay exempt — it is the public
    door of the whole page."""

    def test_lead_endpoint_is_exempt_from_role_writes(self):
        import bot
        self.assertIn("/api/cp/lead", bot._ROLE_EXEMPT_WRITES)
