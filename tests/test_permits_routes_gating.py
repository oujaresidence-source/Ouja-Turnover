# -*- coding: utf-8 -*-
"""
Who can reach which permits endpoint (tests/test_wifi_routes_gating.py pattern).

Locked here:
  * every /api/permits/* route is behind the `permits` page permission (read AND write),
  * the tab is in NAV_DEF (items + «التشغيل» right after wifi + both labels) and _USER_TABS,
  * a viewer is refused every write; only an admin may cancel, switch the mode or clear a
    review flag; going live needs the exact typed word,
  * a stored document path can never escape permits_docs/,
  * no request handler uses the default thread executor (CLAUDE.md trap 6).

Run: python3 -m unittest tests.test_permits_routes_gating
"""

import asyncio
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot                                         # noqa: E402
from brain import db as bdb                        # noqa: E402
from permits import db, engine, routes, service    # noqa: E402
from permits.host import HOST                      # noqa: E402


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

    class _App:
        class router:
            @staticmethod
            def add_get(path, h):
                seen.append(("GET", path, h))

            @staticmethod
            def add_post(path, h):
                seen.append(("POST", path, h))

    routes.register(_App)
    return seen


class TestRules(unittest.TestCase):

    def test_every_registered_api_route_has_a_rule(self):
        api = [(m, p) for m, p, _h in _registered() if p.startswith("/api/")]
        self.assertGreaterEqual(len(api), 18)
        for method, path in api:
            tab = _read_tab(path) if method == "GET" else _write_tab(path)
            self.assertEqual(tab, "permits", "%s %s has no permission rule" % (method, path))

    def test_the_only_non_api_route_is_the_static_script(self):
        others = [p for _m, p, _h in _registered() if not p.startswith("/api/")]
        self.assertEqual(others, ["/permits/static/permits_tab.js"])

    def test_nothing_is_exempt(self):
        for p in bot._ROLE_EXEMPT_WRITES:
            self.assertFalse(p.startswith("/api/permits"), p)


class TestNav(unittest.TestCase):

    def test_labels_in_both_languages(self):
        self.assertEqual(bot.NAV_DEF["labels"]["ar"]["permits"], "التصاريح")
        self.assertEqual(bot.NAV_DEF["labels"]["en"]["permits"], "Permits")

    def test_item_and_category_right_after_wifi(self):
        item = [i for i in bot.NAV_DEF["items"] if i["id"] == "permits"]
        self.assertEqual(item, [{"id": "permits", "ic": "tickets", "tk": "permits", "badge": "permits"}])
        ops = [c for c in bot.NAV_DEF["cats"] if c["tk"] == "cat_ops"][0]["ids"]
        self.assertEqual(ops[ops.index("wifi") + 1], "permits")

    def test_it_is_a_permission_key(self):
        self.assertIn("permits", bot._USER_TABS)

    def test_a_new_non_admin_user_does_not_get_it_for_free(self):
        self.assertFalse(bot._default_perms("viewer").get("permits", {}).get("write"))


class _Req(object):
    def __init__(self, role, body=None, query=None):
        self.role = role
        self._body = body or {}
        self.query = query or {}
        self.content_type = "application/json"

    async def json(self):
        return self._body


class TestHandlers(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="permits_routes_")
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        db.reset_init_cache()
        self.saved = {k: getattr(HOST, k) for k in ("dash_auth", "req_role", "actor", "json_response",
                                                     "web_thread", "state_dir", "listings")}

        async def wt(fn, *a, **kw):
            return fn(*a, **kw)

        HOST.dash_auth = lambda r: True
        HOST.req_role = lambda r: r.role
        HOST.actor = lambda r: "tester-" + r.role
        HOST.json_response = lambda body, status=200: (status, body)
        HOST.web_thread = wt
        HOST.state_dir = self.tmp
        HOST.listings = lambda: []
        self.pid = db.insert_permit({"permit_type": engine.SEED_TYPE, "permit_no": "1", "unit_text": "F2",
                                     "end_date": "2026-10-12"}, "t")

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(HOST, k, v)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def call(self, handler, role, body=None, query=None):
        return asyncio.run(routes._safe(handler)(_Req(role, body, query)))

    def test_viewer_is_refused_every_write(self):
        for h in (routes.api_create, routes.api_update, routes.api_renew, routes.api_cancel,
                  routes.api_link, routes.api_mode, routes.api_review_clear, routes.api_import_preview,
                  routes.api_import_commit):
            st, body = self.call(h, "viewer", {"id": self.pid, "mode": "live", "confirm": "تشغيل"})
            self.assertEqual(st, 403, h.__name__)
        self.assertEqual(service.effective_mode(), "dry")
        self.assertEqual(db.permit(self.pid)["status"], "active")

    def test_viewer_can_read(self):
        st, body = self.call(routes.api_list, "viewer")
        self.assertEqual(st, 200)
        self.assertFalse(body["can_edit"])
        self.assertEqual(len(body["rows"]), 1)

    def test_ops_cannot_cancel_or_switch_mode(self):
        self.assertEqual(self.call(routes.api_cancel, "ops", {"id": self.pid, "reason": "سبب كافي هنا"})[0], 403)
        self.assertEqual(self.call(routes.api_mode, "ops", {"mode": "live", "confirm": "تشغيل"})[0], 403)
        self.assertEqual(self.call(routes.api_review_clear, "ops", {"id": self.pid, "code": "x", "note": "abc"})[0], 403)

    def test_ops_can_edit(self):
        st, body = self.call(routes.api_update, "ops", {"id": self.pid, "notes": "اتصلنا"})
        self.assertEqual(st, 200, body)

    def test_going_live_needs_the_exact_word(self):
        st, body = self.call(routes.api_mode, "admin", {"mode": "live", "confirm": "yes"})
        self.assertEqual(st, 400)
        self.assertEqual(service.effective_mode(), "dry")
        st, body = self.call(routes.api_mode, "admin", {"mode": "live", "confirm": "تشغيل"})
        self.assertEqual(st, 200)
        self.assertEqual(service.effective_mode(), "live")

    def test_admin_can_cancel(self):
        st, body = self.call(routes.api_cancel, "admin", {"id": self.pid, "reason": "المالك طلع من عوجا"})
        self.assertEqual(st, 200, body)

    def test_unauthenticated_is_401(self):
        HOST.dash_auth = lambda r: False
        self.assertEqual(self.call(routes.api_list, "admin")[0], 401)

    def test_item_shows_last4_only_to_admin_and_ops(self):
        db.update_permit(self.pid, {"holder_id_last4": "4321"})
        for role, shown in (("admin", True), ("ops", True), ("viewer", False), ("accountant", False)):
            _st, body = routes.core_item(self.pid, role=role)
            self.assertEqual("holder_id_masked" in body["permit"], shown, role)
            self.assertNotIn("holder_id_last4", body["permit"])
        self.assertEqual(routes.core_item(self.pid, role="admin")[1]["permit"]["holder_id_masked"], "•••• 4321")


class TestDocuments(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="permits_docs_")
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        db.reset_init_cache()
        self.saved = HOST.state_dir
        HOST.state_dir = os.path.join(self.tmp, "state")
        os.makedirs(HOST.state_dir)
        with open(os.path.join(HOST.state_dir, "secret.txt"), "w") as f:
            f.write("x")
        self.pid = db.insert_permit({"permit_type": "t", "end_date": "2026-10-12"}, "t")

    def tearDown(self):
        HOST.state_dir = self.saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_the_name_never_becomes_a_path(self):
        rel = routes.save_doc(self.pid, "../../../etc/evil.pdf", b"%PDF-1.4")
        self.assertRegex(rel, r"^permits_docs/%d/[0-9a-f]{32}\.pdf$" % self.pid)
        db.update_permit(self.pid, {"doc_path": rel})
        path, ctype = routes.doc_file(self.pid)
        self.assertTrue(path and path.startswith(os.path.realpath(HOST.state_dir)))
        self.assertEqual(ctype, "application/pdf")

    def test_a_tampered_stored_path_cannot_escape(self):
        for bad in ("../secret.txt", "permits_docs/../secret.txt", "/etc/passwd",
                    "permits_docs/%d/../../secret.txt" % self.pid):
            db.update_permit(self.pid, {"doc_path": bad})
            self.assertEqual(routes.doc_file(self.pid), (None, None), bad)

    def test_only_allowed_types(self):
        for bad in ("x.exe", "x.html", "x.svg", "x", "x.pdf.js"):
            with self.assertRaises(ValueError):
                routes.save_doc(self.pid, bad, b"data")
        with self.assertRaises(ValueError):
            routes.save_doc(self.pid, "x.pdf", b"x" * (routes.DOC_MAX + 1))


class TestNoDefaultExecutorInHandlers(unittest.TestCase):

    def test_routes_source(self):
        src = open(routes.__file__, encoding="utf-8").read()
        self.assertNotIn("to_thread", src)
        self.assertNotIn("run_in_executor", src)


if __name__ == "__main__":
    unittest.main()
