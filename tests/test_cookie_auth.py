# -*- coding: utf-8 -*-
"""Session cookie transport — direct oujares.com/erp#... links must work after one
login/dashboard entry. _req_token: ?token= → X-Token header → ouja_token cookie
(HttpOnly server-side fallback; the SPA keeps its query/header flow untouched)."""
import asyncio
import os
import shutil
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_STATE = "/tmp/ouja-test-state-cookie"
shutil.rmtree(_STATE, ignore_errors=True)
os.makedirs(_STATE, exist_ok=True)
os.environ.setdefault("STATE_DIR", _STATE)

import bot  # noqa: E402
from finance import api as fapi  # noqa: E402
import finance  # noqa: E402

fapi.attach(bot)


class _Req:
    def __init__(self, query=None, headers=None, cookies=None):
        self.query = query or {}
        self.headers = headers or {}
        self.cookies = cookies or {}


class TestCookieAuth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tok = "sess-cookie-test-token"
        bot._users["u-ck"] = {"id": "u-ck", "name": "كوكي", "active": True,
                              "role": "admin", "perms": {}}
        bot._sessions[cls.tok] = {"user_id": "u-ck",
                                  "expires_at": time.time() + 3600}

    def test_dash_auth_accepts_cookie(self):
        self.assertTrue(bot._dash_auth(_Req(cookies={"ouja_token": self.tok})))

    def test_dash_auth_rejects_bad_cookie(self):
        self.assertFalse(bot._dash_auth(_Req(cookies={"ouja_token": "nope"})))
        self.assertFalse(bot._dash_auth(_Req()))

    def test_query_wins_over_cookie(self):
        # a stale cookie must not shadow an explicit (valid) query token
        r = _Req(query={"token": self.tok}, cookies={"ouja_token": "stale-dead"})
        self.assertTrue(bot._dash_auth(r))

    def test_role_and_actor_via_cookie(self):
        r = _Req(cookies={"ouja_token": self.tok})
        self.assertEqual(bot._req_role(r), "admin")
        self.assertEqual(bot._req_actor(r), "كوكي")
        self.assertEqual(bot._exp4_actor(r), "كوكي")

    def test_user_can_via_cookie(self):
        self.assertTrue(bot._user_can(_Req(cookies={"ouja_token": self.tok}), "users", "read"))

    def test_expired_session_cookie_rejected(self):
        bot._sessions["dead-tok"] = {"user_id": "u-ck", "expires_at": time.time() - 10}
        self.assertFalse(bot._dash_auth(_Req(cookies={"ouja_token": "dead-tok"})))

    def test_erp_entry_plants_cookie_on_query_token(self):
        resp = asyncio.run(finance._h_erp(_Req(query={"token": self.tok})))
        self.assertEqual(resp.status, 200)
        ck = resp.cookies.get("ouja_token")
        self.assertIsNotNone(ck)
        self.assertEqual(ck.value, self.tok)
        self.assertTrue(ck["httponly"])
        self.assertEqual(ck["samesite"], "Lax")
        self.assertTrue(ck["secure"])

    def test_erp_entry_no_cookie_when_cookie_authed(self):
        # already cookie-authed bare visit: serve the app, don't re-set the cookie
        resp = asyncio.run(finance._h_erp(_Req(cookies={"ouja_token": self.tok})))
        self.assertEqual(resp.status, 200)
        self.assertIsNone(resp.cookies.get("ouja_token"))

    def test_erp_entry_still_gated_without_anything(self):
        resp = asyncio.run(finance._h_erp(_Req()))
        self.assertEqual(resp.status, 401)

    def test_gate_page_is_a_login_form(self):
        """Direct /erp link with no session: a LOGIN form (posts to /api/auth/login,
        which plants the cookie), not a dead 'go back to the dashboard' card."""
        resp = asyncio.run(finance._h_erp(_Req()))
        self.assertEqual(resp.status, 401)
        body = resp.text
        self.assertIn("/api/auth/login", body)
        self.assertIn('type="password"', body)
        self.assertIn("location.reload", body)   # hash survives the reload → deep link lands
        self.assertNotIn("\\n", body.split("<script>")[1].split("</script>")[0])

    def test_logout_deletes_cookie_and_session(self):
        bot._sessions["logout-tok"] = {"user_id": "u-ck",
                                       "expires_at": time.time() + 3600}
        resp = asyncio.run(bot._api_auth_logout(_Req(cookies={"ouja_token": "logout-tok"})))
        self.assertNotIn("logout-tok", bot._sessions)
        ck = resp.cookies.get("ouja_token")
        self.assertIsNotNone(ck)          # deletion cookie (Max-Age=0)
        self.assertEqual(ck.value, "")


if __name__ == "__main__":
    unittest.main()
