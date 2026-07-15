# -*- coding: utf-8 -*-
"""Per-page permission enforcement (الصلاحيات لكل صفحة).

The dashboard sidebar, the ERP sidebar, and the server must all read the SAME stored
matrix. These tests lock:
  • _USER_TABS covers every NAV_DEF page id (single source of truth, no drift).
  • _default_perms honors the admin / ops / viewer templates.
  • _user_view / _norm_perms return a COMPLETE matrix (so the UI never has to guess).
  • _user_can reads the matrix with the role-default fallback.
  • _role_enforce_mw rejects unauthorized READ / WRITE / CREATE with 403, lets the
    right users + exempt/public endpoints through.
"""
import asyncio
import os
import shutil
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_STATE = "/tmp/ouja-test-state-perms"
shutil.rmtree(_STATE, ignore_errors=True)
os.makedirs(_STATE, exist_ok=True)
os.environ.setdefault("STATE_DIR", _STATE)

import bot  # noqa: E402


class _Req:
    def __init__(self, method="GET", path="/", token=None):
        self.method = method
        self.path = path
        self.query = {"token": token} if token else {}
        self.headers = {}
        self.cookies = {}


async def _ok_handler(request):
    return "HANDLER_RAN"


def _run_mw(req):
    return asyncio.run(bot._role_enforce_mw(req, _ok_handler))


class TestTabsSourceOfTruth(unittest.TestCase):
    def test_every_nav_page_is_a_permission_key(self):
        nav_ids = [it["id"] for it in bot.NAV_DEF["items"]]
        missing = [i for i in nav_ids if i not in bot._USER_TABS]
        self.assertEqual(missing, [], "nav pages missing from the permission matrix: %r" % missing)

    def test_default_perms_covers_all_tabs(self):
        for role in ("admin", "ops", "viewer", "accountant"):
            perms = bot._default_perms(role)
            for tab in bot._USER_TABS:
                self.assertIn(tab, perms, "%s missing tab %s" % (role, tab))

    def test_templates(self):
        adm = bot._default_perms("admin")
        self.assertTrue(all(p["read"] and p["write"] and p["create"] for p in adm.values()))
        viewer = bot._default_perms("viewer")
        self.assertTrue(all(not p["write"] and not p["create"] for p in viewer.values()))
        self.assertTrue(viewer["rev"]["read"])          # viewer reads
        self.assertFalse(viewer["users"]["read"])        # ...except the admin tab
        ops = bot._default_perms("ops")
        self.assertFalse(ops["finance"]["write"])        # ops: no finance write
        self.assertTrue(ops["tickets"]["create"])        # ops: creates tickets
        self.assertFalse(ops["pmo"]["create"])           # ...but not fit-out projects


class TestNormAndView(unittest.TestCase):
    def test_norm_is_whitelist_deny_by_default(self):
        # Only explicitly-granted tabs are readable; every other tab is DENIED (not filled
        # from the role default). This is what keeps ungranted pages out of the sidebar.
        u = {"role": "viewer", "perms": {"tickets": {"read": True, "write": False, "create": False}}}
        norm = bot._norm_perms(u)
        for tab in bot._USER_TABS:
            self.assertIn(tab, norm)                     # every tab present...
        self.assertTrue(norm["tickets"]["read"])         # explicit grant kept
        self.assertFalse(norm["inbox"]["read"])          # not granted → hidden
        self.assertFalse(norm["finance"]["read"])        # not granted → hidden
        self.assertFalse(norm["brain"]["read"])          # newly-added page → hidden

    def test_user_view_returns_complete_perms_no_hash(self):
        u = bot._user_create("نظرة", "secret123", role="viewer")
        v = bot._user_view(u)
        self.assertNotIn("password_hash", v)
        self.assertEqual(set(v["perms"].keys()), set(bot._USER_TABS))


class TestUserCan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin_tok = "perm-admin-tok"
        bot._users["u-adm"] = {"id": "u-adm", "name": "أدمن", "active": True,
                               "role": "admin", "perms": {}}
        bot._sessions[cls.admin_tok] = {"user_id": "u-adm", "expires_at": time.time() + 3600}

        # Nasser: custom user — can read+edit tickets, VIEW-only reviews, NOTHING finance.
        cls.nasser_tok = "perm-nasser-tok"
        nperms = bot._default_perms("viewer")
        nperms = {t: dict(nperms[t]) for t in nperms}
        nperms["tickets"] = {"read": True, "write": True, "create": False}
        nperms["reviews"] = {"read": True, "write": False, "create": False}
        nperms["finance"] = {"read": False, "write": False, "create": False}
        nperms["rev"] = {"read": False, "write": False, "create": False}
        bot._users["u-nasser"] = {"id": "u-nasser", "name": "ناصر", "active": True,
                                  "role": "viewer", "perms": nperms}
        bot._sessions[cls.nasser_tok] = {"user_id": "u-nasser", "expires_at": time.time() + 3600}

    def test_admin_can_everything(self):
        r = _Req(token=self.admin_tok)
        for tab in ("finance", "rev", "users", "tickets"):
            for act in ("read", "write", "create"):
                self.assertTrue(bot._user_can(r, tab, act))

    def test_nasser_matrix(self):
        r = _Req(token=self.nasser_tok)
        self.assertTrue(bot._user_can(r, "tickets", "read"))
        self.assertTrue(bot._user_can(r, "tickets", "write"))
        self.assertFalse(bot._user_can(r, "tickets", "create"))
        self.assertTrue(bot._user_can(r, "reviews", "read"))
        self.assertFalse(bot._user_can(r, "reviews", "write"))
        self.assertFalse(bot._user_can(r, "finance", "read"))
        self.assertFalse(bot._user_can(r, "rev", "read"))

    def test_no_session_denies(self):
        self.assertFalse(bot._user_can(_Req(token="garbage"), "tickets", "read"))

    def test_missing_tab_is_denied_not_role_default(self):
        # A user whose matrix only grants 'tickets' must NOT read anything else, even
        # though the viewer template would otherwise default those pages to readable.
        tok = "perm-whitelist-tok"
        bot._users["u-wl"] = {"id": "u-wl", "name": "وايت", "active": True, "role": "viewer",
                              "perms": {"tickets": {"read": True, "write": False, "create": False}}}
        bot._sessions[tok] = {"user_id": "u-wl", "expires_at": time.time() + 3600}
        r = _Req(token=tok)
        self.assertTrue(bot._user_can(r, "tickets", "read"))
        self.assertFalse(bot._user_can(r, "finance", "read"))   # never granted → denied
        self.assertFalse(bot._user_can(r, "brain", "read"))     # newly-added page → denied
        self.assertFalse(bot._user_can(r, "rev", "read"))


class TestMiddleware(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        TestUserCan.setUpClass()          # reuse the same fixtures
        cls.admin_tok = TestUserCan.admin_tok
        cls.nasser_tok = TestUserCan.nasser_tok

    # ---- READ enforcement ----
    def test_read_block_finance_for_nasser(self):
        resp = _run_mw(_Req("GET", "/api/finance/report", self.nasser_tok))
        self.assertEqual(resp.status, 403)

    def test_read_block_revenue_for_nasser(self):
        resp = _run_mw(_Req("GET", "/api/revenue", self.nasser_tok))
        self.assertEqual(resp.status, 403)

    def test_read_allow_finance_for_admin(self):
        self.assertEqual(_run_mw(_Req("GET", "/api/finance/report", self.admin_tok)), "HANDLER_RAN")

    def test_read_allow_tickets_for_nasser(self):
        self.assertEqual(_run_mw(_Req("GET", "/api/tickets/list", self.nasser_tok)), "HANDLER_RAN")

    def test_ambient_and_public_reads_pass_through(self):
        # exempt/ambient + unmapped public GETs must NOT be gated by the read rules
        for path in ("/api/overview", "/api/today", "/api/nav", "/api/stay/config",
                     "/api/schedule/day", "/api/units"):
            self.assertEqual(_run_mw(_Req("GET", path, self.nasser_tok)), "HANDLER_RAN",
                             "%s should pass through" % path)

    # ---- WRITE enforcement ----
    def test_write_block_finance_for_nasser(self):
        resp = _run_mw(_Req("POST", "/api/finance/adjust", self.nasser_tok))
        self.assertEqual(resp.status, 403)

    def test_write_allow_tickets_update_for_nasser(self):
        self.assertEqual(_run_mw(_Req("POST", "/api/tickets/update", self.nasser_tok)), "HANDLER_RAN")

    def test_write_block_reviews_for_nasser(self):
        # reviews read-only for Nasser → any reviews write is refused
        resp = _run_mw(_Req("POST", "/api/reviews/notes", self.nasser_tok))
        self.assertEqual(resp.status, 403)

    # ---- CREATE enforcement ----
    def test_create_block_ticket_for_nasser(self):
        # Nasser has tickets write but NOT create → /create is refused
        resp = _run_mw(_Req("POST", "/api/tickets/create", self.nasser_tok))
        self.assertEqual(resp.status, 403)
        self.assertEqual(resp.headers.get("Content-Type", "").split(";")[0], "application/json")

    def test_create_allow_ticket_for_admin(self):
        self.assertEqual(_run_mw(_Req("POST", "/api/tickets/create", self.admin_tok)), "HANDLER_RAN")

    def test_login_endpoint_exempt(self):
        self.assertEqual(_run_mw(_Req("POST", "/api/auth/login")), "HANDLER_RAN")


if __name__ == "__main__":
    unittest.main()
