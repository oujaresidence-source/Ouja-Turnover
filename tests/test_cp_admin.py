# -*- coding: utf-8 -*-
"""
cp.admin — the «الملف التعريفي» HTTP surface (v2 plan Tasks 3–6).

What these hold, in danger order:
  1. Auth: every admin route 401s without a dashboard session. None of them is
     in the public exemption list — that is asserted at the bot level too.
  2. The write discipline: validate → render → guard → save. A copy string
     carrying a withheld figure REFUSES to save and names the numbers.
  3. Publish requires create; rollback restores exactly; version routing on the
     public page follows published_version / preview token / CP_V2.

Run: python3 -m unittest tests.test_cp_admin
"""
import asyncio
import copy
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiohttp import web  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

from cp import host, routes  # noqa: E402


class _Disk:
    def __init__(self):
        self.data = {}

    def load(self, name, default=None):
        return copy.deepcopy(self.data.get(name, default))

    def save(self, name, obj):
        self.data[name] = copy.deepcopy(obj)
        return True


def _json_response(data, status=200):
    return web.json_response(data, status=status)


FAKE_CACHE = [
    {"id": 487708, "name": "Japandi #C3", "internal": "C3", "active": True,
     "bedrooms": 2, "area": "الغدير", "cover": "https://img/x1.jpg",
     "image_urls": ["https://img/x1.jpg", "https://img/x2.jpg"]},
    {"id": 999001, "name": "Stopped unit", "internal": "S1", "active": False,
     "bedrooms": 1, "area": "", "cover": "https://img/s.jpg", "image_urls": []},
]

FAKE_REVIEWS = [
    {"id": 86, "name": "Ghalia", "date": "Jun 2026", "listing": "2BR Pool",
     "lang": "ar", "text": "شكراً نورا وناصر"},
    {"id": 98, "name": "Nadeen", "date": "Apr 2026", "listing": "Japandi",
     "lang": "ar", "text": "بس العزل ضعيف"},
]


def make_client(loop, disk=None, authed=True, user="admin1", perms=None,
                sync_calls=None, snapshot_calls=None):
    disk = disk or _Disk()
    perms = perms if perms is not None else {"read": True, "write": True, "create": True}

    def dash_auth(request):
        return authed

    def dash_perms(request):
        return {"user": user, "cp": dict(perms)}

    host.wire({
        "web": web, "json_response": _json_response,
        "save_json": disk.save, "load_json": disk.load,
        "notify": None, "base_url": "https://oujares.com",
        "links": {"email": "Info@oujares.com", "wa": "966533779297"},
        "pdf_path": "", "default_lang": "ar",
        "english_ready": False, "redirect_business": False,
        "listing_photos": lambda lid, pinned=None: {"photo": "/elite/img?u=x&w=1024",
                                                    "srcset": "/elite/img?u=x&w=640 640w"},
        "dash_auth": dash_auth,
        "dash_perms": dash_perms,
        "listings_cache": lambda: {"listings": FAKE_CACHE, "synced_at": "2026-08-27T03:00:00"},
        "sync_listings": (sync_calls.append if sync_calls is not None else lambda: None)
        if isinstance(sync_calls, list) else (lambda: {"ok": True}),
        "reviews_store": lambda: FAKE_REVIEWS,
        "run_snapshot": (lambda: (snapshot_calls.append(1) or {"ok": True})
                         ) if isinstance(snapshot_calls, list) else (lambda: {"ok": True}),
        "upload_dir": "/tmp/cp-test-uploads",
    })
    routes._recent.clear()
    # mirror bot.py's client_max_size so upload-size tests exercise OUR
    # 4MB rule, not aiohttp's 1MB default 413
    app = web.Application(client_max_size=25 * 1024 * 1024)
    routes.register(app)
    client = TestClient(TestServer(app), loop=loop)
    loop.run_until_complete(client.start_server())
    return client, disk


class _Base(unittest.TestCase):
    kw = {}

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        self.disk = _Disk()
        self.client, _ = make_client(self.loop, disk=self.disk, **self.kw)

    def tearDown(self):
        self.loop.run_until_complete(self.client.close())
        self.loop.close()

    def get(self, path, **kw):
        return self.loop.run_until_complete(self.client.get(path, **kw))

    def post(self, path, **kw):
        return self.loop.run_until_complete(self.client.post(path, **kw))

    def jbody(self, resp):
        return self.loop.run_until_complete(resp.json())

    def tbody(self, resp):
        return self.loop.run_until_complete(resp.text())


class AuthWall(_Base):
    kw = {"authed": False}

    ROUTES_GET = ["/api/cp/admin/overview", "/api/cp/admin/contacts",
                  "/api/cp/admin/copy", "/api/cp/admin/figures",
                  "/api/cp/admin/showcase", "/api/cp/admin/reviews",
                  "/api/cp/admin/leads", "/api/cp/admin/leads.csv",
                  "/api/cp/admin/history"]
    ROUTES_POST = ["/api/cp/admin/contacts", "/api/cp/admin/copy",
                   "/api/cp/admin/figures", "/api/cp/admin/benchmarks",
                   "/api/cp/admin/showcase", "/api/cp/admin/reviews",
                   "/api/cp/admin/publish", "/api/cp/admin/rollback",
                   "/api/cp/admin/sync-listings", "/api/cp/admin/snapshot-now",
                   "/api/cp/admin/lead-status"]

    def test_every_admin_get_401s(self):
        for path in self.ROUTES_GET:
            with self.subTest(path=path):
                self.assertEqual(self.get(path).status, 401)

    def test_every_admin_post_401s(self):
        for path in self.ROUTES_POST:
            with self.subTest(path=path):
                self.assertEqual(self.post(path, json={}).status, 401)


class Reads(_Base):
    def test_overview_shape(self):
        d = self.jbody(self.get("/api/cp/admin/overview"))
        self.assertTrue(d["ok"])
        self.assertEqual(d["published_version"], "v1")
        self.assertIn("guard", d)
        self.assertTrue(d["guard"]["clean"])
        self.assertIn("leads_7d", d)
        self.assertIn("preview_url", d)

    def test_contacts_round_trip(self):
        d = self.jbody(self.get("/api/cp/admin/contacts"))
        self.assertEqual(d["contacts"]["whatsapp"], "966533779297")

    def test_showcase_lists_cache_with_inactive_warning(self):
        d = self.jbody(self.get("/api/cp/admin/showcase"))
        rows = {r["id"]: r for r in d["cache"]}
        self.assertFalse(rows[999001]["active"])
        self.assertEqual(d["synced_at"], "2026-08-27T03:00:00")

    def test_reviews_lists_store(self):
        d = self.jbody(self.get("/api/cp/admin/reviews"))
        self.assertEqual(len(d["store"]), 2)
        self.assertEqual(d["chosen"], [])


class WriteDiscipline(_Base):
    def test_contact_save_returns_guard_verdict(self):
        r = self.post("/api/cp/admin/contacts", json={"email": "x@oujares.com"})
        d = self.jbody(r)
        self.assertTrue(d["ok"])
        self.assertTrue(d["guard"]["clean"])

    def test_validation_error_is_a_400_with_arabic(self):
        r = self.post("/api/cp/admin/contacts", json={"booking_link": "javascript:x"})
        self.assertEqual(r.status, 400)
        self.assertIn("https", self.jbody(r)["error"])

    def test_a_poisoned_copy_string_refuses_to_save(self):
        r = self.post("/api/cp/admin/copy",
                      json={"hero_sub": "حققنا 7,669,457 ريال"})
        d = self.jbody(r)
        self.assertEqual(r.status, 400)
        self.assertIn("7,669,457", json.dumps(d, ensure_ascii=False))
        # and nothing was saved
        d2 = self.jbody(self.get("/api/cp/admin/copy"))
        self.assertNotIn("hero_sub", d2["overlay"])

    def test_clean_copy_saves(self):
        r = self.post("/api/cp/admin/copy", json={"hero_sub": "نص نظيف تماماً"})
        self.assertTrue(self.jbody(r)["ok"])
        d2 = self.jbody(self.get("/api/cp/admin/copy"))
        self.assertEqual(d2["overlay"]["hero_sub"], "نص نظيف تماماً")

    def test_manual_figure_missing_source_is_refused(self):
        r = self.post("/api/cp/admin/figures",
                      json={"messages_total": {"value": 160000, "as_of": "2026-09-01",
                                               "source": ""}})
        self.assertEqual(r.status, 400)

    def test_lead_status_updates_record(self):
        self.disk.data["cp_leads.json"] = {"leads": [
            {"at": 1, "audience": "owner", "fields": {"name": "خالد"}}]}
        r = self.post("/api/cp/admin/lead-status", json={"at": 1, "status": "contacted"})
        self.assertTrue(self.jbody(r)["ok"])
        self.assertEqual(self.disk.data["cp_leads.json"]["leads"][0]["status"], "contacted")

    def test_lead_status_whitelist(self):
        self.disk.data["cp_leads.json"] = {"leads": [{"at": 1, "fields": {}}]}
        r = self.post("/api/cp/admin/lead-status", json={"at": 1, "status": "hacked"})
        self.assertEqual(r.status, 400)


class RoleMatrix(unittest.TestCase):
    def _client(self, perms):
        self.loop = asyncio.new_event_loop()
        client, disk = make_client(self.loop, perms=perms)
        return client, disk

    def tearDown(self):
        self.loop.run_until_complete(self.client.close())
        self.loop.close()

    def test_viewer_reads_but_cannot_write(self):
        self.client, _ = self._client({"read": True, "write": False, "create": False})
        r = self.loop.run_until_complete(self.client.get("/api/cp/admin/overview"))
        self.assertEqual(r.status, 200)
        r = self.loop.run_until_complete(
            self.client.post("/api/cp/admin/copy", json={"k": "v"}))
        self.assertEqual(r.status, 403)

    def test_ops_writes_but_cannot_publish(self):
        self.client, _ = self._client({"read": True, "write": True, "create": False})
        r = self.loop.run_until_complete(
            self.client.post("/api/cp/admin/copy", json={"k": "نص"}))
        self.assertEqual(r.status, 200)
        r = self.loop.run_until_complete(
            self.client.post("/api/cp/admin/publish", json={"version": "v2"}))
        self.assertEqual(r.status, 403)

    def test_admin_publishes(self):
        self.client, _ = self._client({"read": True, "write": True, "create": True})
        r = self.loop.run_until_complete(
            self.client.post("/api/cp/admin/publish", json={"version": "v1"}))
        self.assertEqual(r.status, 200)


class PublishRollbackHistory(_Base):
    def test_publish_appends_history_and_flips_version(self):
        self.post("/api/cp/admin/copy", json={"hero_sub": "نص أول"})
        d = self.jbody(self.post("/api/cp/admin/publish", json={"version": "v1"}))
        self.assertTrue(d["ok"])
        h = self.jbody(self.get("/api/cp/admin/history"))
        self.assertEqual(len(h["history"]), 1)
        self.assertEqual(h["history"][0]["by"], "admin1")

    def test_rollback_restores(self):
        self.post("/api/cp/admin/copy", json={"hero_sub": "أول"})
        self.post("/api/cp/admin/publish", json={"version": "v1"})
        first_at = self.jbody(self.get("/api/cp/admin/history"))["history"][0]["at"]
        self.post("/api/cp/admin/copy", json={"hero_sub": "ثاني"})
        self.post("/api/cp/admin/publish", json={"version": "v1"})
        r = self.post("/api/cp/admin/rollback", json={"at": first_at})
        self.assertTrue(self.jbody(r)["ok"])

    def test_snapshot_now_runs_the_job(self):
        calls = []
        self.loop.run_until_complete(self.client.close())
        self.client, _ = make_client(self.loop, snapshot_calls=calls)
        self.post("/api/cp/admin/snapshot-now")
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()


class BotRegistration(unittest.TestCase):
    """The bot-side contract: tab, rule maps, sidebar labels — each one has a
    named trap in CLAUDE.md and each is pinned here."""

    @classmethod
    def setUpClass(cls):
        import bot
        cls.bot = bot

    def test_cp_is_a_user_tab(self):
        self.assertIn("cp", self.bot._USER_TABS)

    def test_rule_maps_cover_the_admin_prefix(self):
        self.assertIn(("/api/cp/admin/", "cp"), self.bot._ROLE_WRITE_RULES)
        self.assertIn(("/api/cp/admin/", "cp"), self.bot._ROLE_READ_RULES)

    def test_admin_routes_are_not_publicly_exempt(self):
        for path in self.bot._ROLE_EXEMPT_WRITES:
            self.assertFalse(path.startswith("/api/cp/admin"),
                             "%r must never be exempt" % path)
        self.assertIn("/api/cp/lead", self.bot._ROLE_EXEMPT_WRITES)

    def test_ops_gets_write_but_not_publish(self):
        perms = self.bot._default_perms("ops")["cp"]
        self.assertTrue(perms["read"])
        self.assertTrue(perms["write"])
        self.assertFalse(perms["create"])

    def test_viewer_reads_only(self):
        perms = self.bot._default_perms("viewer")["cp"]
        self.assertTrue(perms["read"])
        self.assertFalse(perms["write"])

    def test_sidebar_has_the_item_in_cat_guests(self):
        html = self.bot.DASHBOARD_HTML
        self.assertIn('{"id": "cp", "ic": "gw", "tk": "cp"}', html)
        self.assertIn('"ids": ["guests", "rec", "gw", "cp", "guide", "reviews"]', html)

    def test_label_keys_exist_in_both_languages(self):
        """The tab-label trap: a missing key renders the literal «undefined»."""
        html = self.bot.DASHBOARD_HTML
        self.assertIn('"cp": "الملف التعريفي"', html)
        self.assertIn('"cp": "Company Profile"', html)
