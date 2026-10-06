# -*- coding: utf-8 -*-
"""The owner's public door and the send button (gate G31).

  * /m/{token} and /m/{token}.pdf live outside /api/meet/ and hand their work to web_thread,
  * a wrong or revoked token is the SAME 404 (status + body) as any unknown address,
  * 30 requests per IP per minute, then 429,
  * the WhatsApp redirect is login-gated, logs wa_opened, and only ever builds a wa.me link,
  * «إرسال» refuses while degraded, while a red line is open, or on a privacy hit.

Run: python3 -m unittest tests.test_owner_meet_links
"""
import asyncio
import copy
import datetime
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aiohttp import web  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

from brain import db as bdb  # noqa: E402
import owner_meet  # noqa: E402
from owner_meet import db, jobs, routes  # noqa: E402

FULL = json.loads((ROOT / "tests" / "fixtures" / "owner_meet" / "snapshot_full.json").read_text(encoding="utf-8"))
TZ = datetime.timezone(datetime.timedelta(hours=3))


class _Live(unittest.TestCase):
    auth = True

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        db._inited.clear()
        routes.IP_LIMIT.hits.clear()
        routes.TOKEN_LIMIT.hits.clear()
        self._submit = jobs._pool.submit
        jobs._pool.submit = lambda *a, **k: None

        async def wt(fn, *a, **k):
            return fn(*a, **k)

        owner_meet.wire({"dash_auth": lambda r: self.auth, "req_role": lambda r: "admin", "actor": lambda r: "Faisal",
                         "tab_allowed": lambda r, t: True, "json_response": lambda d, s=200: web.json_response(d, status=s),
                         "web": web, "web_thread": wt, "state_dir": self.tmp, "link_base": lambda: "https://x.test",
                         "owner_phone": lambda o: "0551112233", "owner_portal_token": lambda o: "portal-tok",
                         "staff_names": lambda: [], "now": lambda: datetime.datetime(2026, 10, 6, 12, tzinfo=TZ)})
        owner_meet.bootstrap()
        self.mid = db.create_meeting("مالك", [77], FULL["meta"]["period"], "2026-10-06", "t")
        db.save_snapshot(self.mid, FULL)
        db.set_build(self.mid, state="ready", progress=100)

    def tearDown(self):
        jobs._pool.submit = self._submit
        shutil.rmtree(self.tmp, ignore_errors=True)

    def call(self, method, path, n=1, **kw):
        async def go():
            app = web.Application()
            routes.register(app)
            out = None
            async with TestClient(TestServer(app)) as c:
                for _ in range(n):
                    r = await c.request(method, path, allow_redirects=False, **kw)
                    out = (r.status, r.headers, await r.read())
            return out
        return asyncio.run(go())

    def send(self):
        st, out = routes.core_send(self.mid, "Faisal", "admin")
        self.assertEqual(st, 200, out)
        return out["token"]


class OwnerDoor(_Live):
    def test_routes_sit_outside_api_meet_and_use_web_thread(self):
        src = (ROOT / "owner_meet" / "routes.py").read_text(encoding="utf-8")
        self.assertIn('r.add_get("/m/{token:[A-Za-z0-9_-]+}", handle_owner_page)', src)
        for name in ("handle_owner_page", "handle_owner_pdf"):
            body = src.split("async def %s(" % name, 1)[1].split("\nasync def ", 1)[0]
            self.assertIn("_run(", body)
            self.assertNotIn("to_thread", body)

    def test_the_owner_sees_his_page_and_the_open_is_counted(self):
        tok = self.send()
        st, h, body = self.call("GET", "/m/" + tok)
        self.assertEqual(st, 200)
        html = body.decode()
        self.assertIn("no-store", h["Cache-Control"])
        self.assertEqual(db.link(tok)["opens"], 1)
        self.assertNotIn("فحوص قبل العرض", html, "the presenter half never reaches the owner")

    def test_expense_lines_link_their_receipt_through_the_owner_proxy(self):
        snap = copy.deepcopy(FULL)
        snap["owner"]["units"][0]["expenses"] = [{"id": "exp_7", "date": "2026-08-02", "category": "صيانة",
                                                  "description": "تبديل حنفية", "amount": 180.0, "receipt": True}]
        db.save_snapshot(self.mid, snap)
        tok = self.send()
        html = self.call("GET", "/m/" + tok)[2].decode()
        self.assertIn('href="/fin/receipt/exp_7?t=portal-tok"', html)
        self.assertIn("تبديل حنفية", html)

    def test_wrong_and_revoked_tokens_are_the_same_404_as_nothing(self):
        tok = self.send()
        nothing = self.call("GET", "/no/such/page")
        wrong = self.call("GET", "/m/" + "A" * 43)
        routes.core_revoke(tok, "Faisal", "admin")
        revoked = self.call("GET", "/m/" + tok)
        self.assertEqual((wrong[0], wrong[2]), (nothing[0], nothing[2]))
        self.assertEqual((revoked[0], revoked[2]), (nothing[0], nothing[2]))
        self.assertEqual(self.call("GET", "/m/" + tok + ".pdf")[0], 404)

    def test_rate_limit(self):
        st, _h, _b = self.call("GET", "/m/" + "B" * 43, n=31)
        self.assertEqual(st, 429)

    def test_a_pdf_not_printed_yet_falls_back_to_the_page(self):
        tok = self.send()
        st, h, _b = self.call("GET", "/m/%s.pdf" % tok)
        self.assertEqual((st, h["Location"]), (302, "/m/" + tok))


class Send(_Live):
    def test_degraded_or_red_or_privacy_refuses(self):
        snap = copy.deepcopy(FULL)
        snap["meta"]["degraded"] = True
        db.save_snapshot(self.mid, snap)
        self.assertEqual(routes.core_send(self.mid, "Faisal", "admin")[0], 409)
        snap = copy.deepcopy(FULL)
        snap["presenter"]["readiness"].append({"level": "red", "key": "x", "text_ar": "أحمر"})
        db.save_snapshot(self.mid, snap)
        self.assertEqual(routes.core_send(self.mid, "Faisal", "admin")[0], 409)
        snap = copy.deepcopy(FULL)
        snap["owner"]["units"][0]["maint"]["rows"][0]["summary"] = "اتصل على 0559998877"
        db.save_snapshot(self.mid, snap)
        st, out = routes.core_send(self.mid, "Faisal", "admin")
        self.assertEqual(st, 409)
        self.assertIn("phone", out["privacy"])
        self.assertNotIn("0559998877", out["error_ar"])
        self.assertEqual(db.links_for(self.mid), [], "a refused send creates no link")

    def test_only_an_admin_sends(self):
        self.assertEqual(routes.core_send(self.mid, "x", "ops")[0], 403)

    def test_whatsapp_is_login_gated_and_only_a_wa_me_link(self):
        self.send()
        st, h, _b = self.call("GET", "/api/meet/meetings/%d/wa" % self.mid)
        self.assertEqual(st, 302)
        loc = h["Location"]
        self.assertTrue(loc.startswith("https://wa.me/966551112233?text="), loc)
        text = urllib.parse.unquote(loc.split("text=", 1)[1])
        self.assertIn("https://x.test/m/", text)
        self.assertIn("فيصل", text)
        self.assertEqual(db.q1("SELECT COUNT(*) n FROM meet_events WHERE kind='wa_opened'")["n"], 1)
        self.auth = False
        self.assertEqual(self.call("GET", "/api/meet/meetings/%d/wa" % self.mid)[0], 401)

    def test_nothing_sends_on_its_own(self):
        src = "".join(p.read_text(encoding="utf-8") for p in (ROOT / "owner_meet").glob("*.py"))
        self.assertIsNone(re.search("api[.]whatsapp|graph[.]facebook|smtp|send_message[(]", src))


if __name__ == "__main__":
    unittest.main()
