# -*- coding: utf-8 -*-
"""Who can reach which «اجتماع المالك» door (gates G13 / G15, S2 part).

Locked here:
  * every /api/meet/* route is behind the «meet» permission for reads AND writes, nothing is exempt,
  * the only non-/api/ routes are the two pages and the two static allow-lists,
  * the pages refuse without login (302 to the dashboard) and without the permission (403),
  * static and font doors serve only their allow-list (no path tricks),
  * OWNER_MEET_ENABLED=0 registers nothing,
  * the cursor round-trips with a rising sequence,
  * every handler hands its work to HOST.web_thread (never to_thread),
  * NAV item + both labels + cat_finance + the permission key exist.

Run: python3 -m unittest tests.test_owner_meet_routes
"""
import asyncio
import datetime
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_STATE = tempfile.mkdtemp(prefix="ouja-meet-routes-")
os.environ["STATE_DIR"] = _STATE

from aiohttp import web  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

import bot  # noqa: E402
from brain import db as bdb  # noqa: E402
import owner_meet  # noqa: E402
from owner_meet import db, jobs, routes  # noqa: E402

FULL = json.loads((ROOT / "tests" / "fixtures" / "owner_meet" / "snapshot_full.json").read_text(encoding="utf-8"))
TZ = datetime.timezone(datetime.timedelta(hours=3))


def _read_tab(path):
    for prefix, tab in bot._ROLE_READ_RULES:
        if path.startswith(prefix):
            return tab
    return None


def _write_tab(path):
    if path in bot._ROLE_EXEMPT_WRITES:
        return "EXEMPT"
    for prefix, tab in bot._ROLE_WRITE_RULES:
        if path.startswith(prefix):
            return tab
    return None


def _registered():
    seen = []

    class _R:
        @staticmethod
        def add_get(path, h):
            seen.append(("GET", path, h))

        @staticmethod
        def add_post(path, h):
            seen.append(("POST", path, h))

    class _App:
        router = _R

    routes.register(_App)
    return seen


class RulesAndNav(unittest.TestCase):
    def test_every_api_route_is_behind_meet_for_read_and_write(self):
        for method, path, _h in _registered():
            if path.startswith("/api/"):
                self.assertEqual(_read_tab(path), "meet", path)
                self.assertEqual(_write_tab(path), "meet", path)

    def test_the_only_non_api_routes_are_pages_and_static(self):
        non_api = sorted(p for _m, p, _h in _registered() if not p.startswith("/api/"))
        self.assertEqual(non_api, ["/m/{token:[A-Za-z0-9_-]+}", "/m/{token:[A-Za-z0-9_-]+}.pdf",
                                   "/meet/font/{name}", "/meet/static/{name}", "/meet/{id:[0-9]+}",
                                   "/meet/{id:[0-9]+}/notes"])

    def test_nothing_is_exempt(self):
        self.assertFalse([p for p in bot._ROLE_EXEMPT_WRITES if p.startswith("/api/meet")])

    def test_nav_item_labels_and_category(self):
        items = [i["id"] for i in bot.NAV_DEF["items"]]
        self.assertIn("meet", items)
        self.assertEqual(items.index("meet"), items.index("ownrep") + 1)
        fin = [c for c in bot.NAV_DEF["cats"] if c["tk"] == "cat_finance"][0]
        self.assertEqual(fin["ids"][fin["ids"].index("ownrep") + 1], "meet")
        self.assertEqual(bot.NAV_DEF["labels"]["ar"]["meet"], "اجتماع المالك")
        self.assertEqual(bot.NAV_DEF["labels"]["en"]["meet"], "Owner meeting")
        self.assertIn("meet", bot._USER_TABS)

    def test_a_new_non_admin_user_does_not_get_it_for_free(self):
        for role in ("ops", "viewer", "accountant"):
            perms = bot._default_perms(role)
            self.assertFalse((perms.get("meet") or {}).get("read"), role)

    def test_disabled_registers_nothing(self):
        os.environ["OWNER_MEET_ENABLED"] = "0"
        try:
            self.assertEqual(_registered(), [])
        finally:
            os.environ.pop("OWNER_MEET_ENABLED", None)

    def test_disabled_also_hides_the_menu_item(self):
        import subprocess
        code = "import bot; print('meet' in [i['id'] for i in bot.NAV_DEF['items']])"
        env = dict(os.environ, OWNER_MEET_ENABLED="0", STATE_DIR=tempfile.mkdtemp())
        out = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), env=env, capture_output=True, text=True)
        self.assertIn("False", out.stdout.strip().splitlines()[-1:] and out.stdout.strip().splitlines()[-1])

    def test_every_handler_uses_web_thread(self):
        src = (ROOT / "owner_meet" / "routes.py").read_text(encoding="utf-8")
        self.assertNotIn("to_thread", src)
        self.assertNotIn("run_in_executor", src)
        for name in re.findall(r"^async def ((?:api|page|handle)_[a-z_]+)\(", src, re.M):
            body = src.split("async def %s(" % name, 1)[1].split("\nasync def ", 1)[0].split("\ndef ", 1)[0]
            uses = ("_run(" in body) or ("_page(request" in body) or ("cursor_" in body)
            self.assertTrue(uses, "%s does blocking work off the web lane?" % name)
        self.assertIn("return await HOST.web_thread(fn", src)


class _Live(unittest.TestCase):
    """A real aiohttp app with the package's routes and fake caps."""

    auth = True
    role = "admin"
    allowed = True

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        db._inited.clear()
        routes._cursor.clear()
        self.started = []
        self._orig_start = jobs.start
        jobs.start = lambda mid, params: self.started.append((mid, params)) or True

        async def wt(fn, *a, **k):
            return fn(*a, **k)

        owner_meet.wire({
            "dash_auth": lambda r: self.auth, "req_role": lambda r: self.role, "actor": lambda r: "tester",
            "tab_allowed": lambda r, t: self.allowed and t == "meet",
            "json_response": lambda d, s=200: web.json_response(d, status=s), "web": web, "web_thread": wt,
            "now": lambda: datetime.datetime(2026, 10, 6, 12, 0, tzinfo=TZ), "state_dir": self.tmp,
            "owners": lambda: [{"owner": "مالك", "units": [{"apartment": "A1", "lid": 77}]}],
            "owner_lids": lambda o: [77] if o == "مالك" else [],
            "listings_meta": lambda: {77: {"name": "Ouja | A1", "bedrooms": 2}},
        })
        owner_meet.bootstrap()
        p = FULL["meta"]["period"]
        self.mid = db.create_meeting("مالك", [77], p, "2026-10-06", "t")
        db.save_snapshot(self.mid, FULL)
        db.set_build(self.mid, state="ready", progress=100)

    def tearDown(self):
        jobs.start = self._orig_start
        shutil.rmtree(self.tmp, ignore_errors=True)

    def call(self, method, path, **kw):
        async def go():
            app = web.Application()
            routes.register(app)
            async with TestClient(TestServer(app)) as c:
                r = await c.request(method, path, allow_redirects=False, **kw)
                body = await r.read()
                return r.status, r.headers, body
        return asyncio.run(go())


class Pages(_Live):
    def test_admin_gets_the_presentation_and_the_notes(self):
        st, h, body = self.call("GET", "/meet/%d" % self.mid)
        self.assertEqual(st, 200)
        self.assertIn("text/html", h["Content-Type"])
        self.assertIn('class="slide on"', body.decode())
        self.assertEqual(h.get("Cache-Control"), "no-store")
        st, _h, body = self.call("GET", "/meet/%d/notes" % self.mid)
        self.assertEqual(st, 200)
        self.assertIn("فحوص قبل العرض", body.decode())

    def test_unknown_meeting_is_404(self):
        self.assertEqual(self.call("GET", "/meet/999999")[0], 404)

    def test_not_logged_in_is_sent_to_the_dashboard(self):
        self.auth = False
        st, h, _b = self.call("GET", "/meet/%d" % self.mid)
        self.assertEqual(st, 302)
        self.assertEqual(h["Location"], "/dashboard#meet")

    def test_logged_in_without_the_permission_is_403(self):
        self.role, self.allowed = "ops", False
        self.assertEqual(self.call("GET", "/meet/%d" % self.mid)[0], 403)
        self.assertEqual(self.call("GET", "/meet/%d/notes" % self.mid)[0], 403)
        self.assertEqual(self.call("GET", "/api/meet/owners")[0], 403)

    def test_api_without_login_is_401(self):
        self.auth = False
        self.assertEqual(self.call("GET", "/api/meet/owners")[0], 401)


class Api(_Live):
    def test_owners_lists_units_with_names(self):
        st, _h, b = self.call("GET", "/api/meet/owners")
        d = json.loads(b)
        self.assertEqual(st, 200)
        self.assertEqual(d["owners"][0]["units"], [{"lid": 77, "name": "Ouja | A1"}])

    def test_create_validates_in_arabic_and_starts_a_build(self):
        st, _h, b = self.call("POST", "/api/meet/meetings", json={"owner": "مالك", "lids": [99], "kind": "quarter"})
        self.assertEqual(st, 400)
        self.assertIn("ليست لهذا المالك", json.loads(b)["error_ar"])
        st, _h, b = self.call("POST", "/api/meet/meetings", json={"owner": "مالك", "lids": [77], "kind": "quarter"})
        d = json.loads(b)
        self.assertEqual(st, 200, d)
        mid, params = self.started[-1]
        self.assertEqual(mid, d["id"])
        self.assertEqual(params["period"]["months"], ["2026-07", "2026-08", "2026-09"])
        self.assertEqual(params["lids"], [], "all of the owner's units = the owner-level money")

    def test_status_carries_readiness_and_send_state(self):
        st, _h, b = self.call("GET", "/api/meet/meetings/%d" % self.mid)
        d = json.loads(b)
        self.assertEqual(st, 200)
        self.assertEqual(d["version"], 1)
        self.assertTrue(d["can_send"])

    def test_cursor_round_trip(self):
        _s, _h, b = self.call("POST", "/api/meet/meetings/%d/cursor" % self.mid, json={"i": 3, "by": "notes"})
        first = json.loads(b)
        self.assertEqual((first["i"], first["by"]), (3, "notes"))
        _s, _h, b = self.call("POST", "/api/meet/meetings/%d/cursor" % self.mid, json={"i": 4, "by": "stage"})
        self.assertGreater(json.loads(b)["seq"], first["seq"])
        _s, _h, b = self.call("GET", "/api/meet/meetings/%d/cursor" % self.mid)
        self.assertEqual(json.loads(b)["i"], 4)


class Static(_Live):
    def test_allow_listed_js_and_fonts_only(self):
        st, h, b = self.call("GET", "/meet/static/stage.js")
        self.assertEqual(st, 200)
        self.assertIn("javascript", h["Content-Type"])
        for bad in ("/meet/static/routes.py", "/meet/static/..%2Froutes.py", "/meet/font/LICENSE-Thmanyah.pdf",
                    "/meet/font/..%2F..%2Fbot.py"):
            self.assertEqual(self.call("GET", bad)[0], 404, bad)
        st, h, _b = self.call("GET", "/meet/font/ThmanyahSans-Regular.woff2")
        self.assertEqual(st, 200)
        self.assertIn("immutable", h["Cache-Control"])


if __name__ == "__main__":
    unittest.main()
