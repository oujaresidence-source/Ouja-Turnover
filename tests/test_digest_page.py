# -*- coding: utf-8 -*-
"""digest.page + digest.routes contract: the owner page has ZERO backslashes, every
<script> parses (esprima), braces balance, every /api/digest/* the page calls is a
registered route, and the handlers answer 401 without a login and JSON with one."""
import asyncio
import inspect
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from digest import routes
from digest.host import HOST
from digest.page import DIGEST_PAGE_HTML

try:
    import esprima
except ImportError:                     # pragma: no cover
    esprima = None


class Page(unittest.TestCase):
    def test_zero_backslashes_in_the_module(self):
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "digest", "page.py")
        with open(p, encoding="utf-8") as fh:
            self.assertNotIn(chr(92), fh.read(), "backslash found — the non-raw triple-quote trap")

    @unittest.skipUnless(esprima, "esprima not installed")
    def test_every_script_parses(self):
        blocks = re.findall(r"<script>(.*?)</script>", DIGEST_PAGE_HTML, re.S)
        self.assertTrue(blocks)
        for js in blocks:
            esprima.parseScript(js)

    def test_balance(self):
        self.assertEqual(DIGEST_PAGE_HTML.count("{"), DIGEST_PAGE_HTML.count("}"))
        self.assertEqual(DIGEST_PAGE_HTML.count("("), DIGEST_PAGE_HTML.count(")"))
        self.assertEqual(DIGEST_PAGE_HTML.count("`") % 2, 0)

    def test_every_api_call_in_the_page_is_registered(self):
        src = inspect.getsource(routes.register)
        for path in set(re.findall(r"['\"](/api/digest/[a-z_/{}]+)['\"]", DIGEST_PAGE_HTML)):
            self.assertIn(path, src, path)
        self.assertIn("/digest/file/", src)

    def test_tokens_and_no_physical_props(self):
        css = re.search(r"<style>(.*?)</style>", DIGEST_PAGE_HTML, re.S).group(1)
        self.assertIn("--gold:#C6A15B", css)
        self.assertNotIn("box-shadow", css)
        self.assertIsNone(re.search(r"(?<![-\w])(left|right)\s*:", css))
        self.assertIn("prefers-reduced-motion", css)


class _Req(dict):
    def __init__(self, path="/", body=None, match=None):
        super().__init__()
        self.path = path
        self._body = body
        self.match_info = match or {}

    async def json(self):
        if self._body is None:
            raise ValueError("no body")
        return self._body


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _Resp(object):
    def __init__(self, data, status):
        self.data, self.status = data, status


class Routes(unittest.TestCase):
    def setUp(self):
        self._saved = {k: getattr(HOST, k, None) for k in ("dash_auth", "json_response", "web", "now", "http", "req_role")}
        HOST.json_response = lambda data, status=200: _Resp(data, status)
        HOST.req_role = lambda r: "admin"

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(HOST, k, v)

    def test_unauthorized_is_401_before_any_work(self):
        HOST.dash_auth = lambda r: False
        r = _run(routes._safe(routes.api_status)(_Req("/api/digest/status")))
        self.assertEqual(r.status, 401)
        r = _run(routes._safe(routes.api_act)(_Req("/api/digest/act", body={"action": "approve"})))
        self.assertEqual(r.status, 401)

    def test_unknown_action_is_refused(self):
        HOST.dash_auth = lambda r: True
        r = _run(routes._safe(routes.api_act)(_Req("/api/digest/act", body={"action": "explode", "issue": 1})))
        self.assertEqual(r.status, 200)
        self.assertFalse(r.data["ok"])

    def test_file_route_refuses_bad_kinds_and_ids(self):
        HOST.dash_auth = lambda r: True
        r = _run(routes._safe(routes.api_file)(_Req("/digest/file/1/exe", match={"n": "1", "kind": "exe"})))
        self.assertEqual(r.status, 404)
        r = _run(routes._safe(routes.api_file)(_Req("/digest/file/../x/pdf", match={"n": "../x", "kind": "pdf"})))
        self.assertEqual(r.status, 404)

    def test_register_adds_the_seven_routes(self):
        calls = []

        class R(object):
            def add_get(self, p, h):
                calls.append(("GET", p))

            def add_post(self, p, h):
                calls.append(("POST", p))

        class App(object):
            router = R()

        routes.register(App())
        self.assertEqual(sorted(calls), sorted([("GET", "/digest"), ("GET", "/digest/health"), ("GET", "/api/digest/status"), ("GET", "/api/digest/issue/{n}"),
                                                ("POST", "/api/digest/act"), ("POST", "/api/digest/build"), ("GET", "/digest/file/{n}/{kind}")]))

    def test_routes_survive_a_missing_library(self):
        """The container lesson (2026-09-02): with segno absent, register() must still add
        every route, /digest/health must say render_ready=false and name the error."""
        import importlib
        saved = sys.modules.get("segno")
        sys.modules["segno"] = None
        try:
            for m in [k for k in list(sys.modules) if k.startswith("digest.render") or k in ("digest.build", "digest.approval", "digest.notify", "digest.routes")]:
                del sys.modules[m]
            r2 = importlib.import_module("digest.routes")
            calls = []

            class R(object):
                def add_get(self, p, h):
                    calls.append(p)

                def add_post(self, p, h):
                    calls.append(p)

            class App(object):
                router = R()

            r2.register(App())
            self.assertIn("/digest", calls)
            self.assertIn("/digest/health", calls)
            HOST.json_response = lambda data, status=200: _Resp(data, status)
            r = _run(r2.health(_Req("/digest/health")))
            self.assertTrue(r.data["routes"])
            self.assertFalse(r.data["render_ready"])
            self.assertIn("segno", r.data["render_error"])
        finally:
            if saved is not None:
                sys.modules["segno"] = saved
            else:
                sys.modules.pop("segno", None)
            for m in [k for k in list(sys.modules) if k.startswith("digest.render") or k in ("digest.build", "digest.approval", "digest.notify", "digest.routes")]:
                del sys.modules[m]


if __name__ == "__main__":
    unittest.main()
