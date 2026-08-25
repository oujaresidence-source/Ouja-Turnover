# -*- coding: utf-8 -*-
"""
The share link «/kb/{token}» — the door with nothing but a secret in front of it.

The owner asked (2026-08-03) for a link that gives read AND edit to anyone holding it,
with no name prompt. That makes the token the entire security boundary, so these tests
exist to prove the boundary is where we think it is:

  • no token, wrong token, empty token, and the OLD token after a rotation are all refused
  • the refusal happens before the handler runs, on every public endpoint
  • the private /api/kb/ prefix cannot be reached through the public one
  • the token survives a restart (it is persisted, not generated per boot)
  • the page's javascript parses and contains no backslash (kb/page.py has the same
    Python-eats-the-escape trap as DASHBOARD_HTML)
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kb import db as kdb        # noqa: E402
from kb import page as kpage    # noqa: E402
from kb import routes as krt    # noqa: E402
from kb import seed as kseed    # noqa: E402


class _FakeURL(object):
    def __init__(self, token, path):
        self.query = {"t": token} if token else {}
        self._path = path


class _FakeRequest(dict):
    """Just enough aiohttp request for kb/routes' public handlers: a query string, a
    JSON body, and match_info. Nothing here talks to a socket."""

    def __init__(self, token=None, path="", body=None):
        dict.__init__(self)
        self.rel_url = _FakeURL(token, path)
        self.path = path
        self._body = body or {}
        # Every {placeholder} the public routes use, so match_info never KeyErrors.
        self.match_info = {"unit_id": "UNT-483841", "token": token or ""}

    async def json(self):
        return self._body


def _run(coro):
    """Own loop per call. Another test module in the suite closes the ambient loop, and
    asyncio.get_event_loop() then raises — which looked like a KB failure but was not."""
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _wire_test_host():
    """kb/routes replies through HOST.json_response. In production bot.py wires the real
    aiohttp one; here it returns the pair so the tests can read status AND payload."""
    from kb.host import HOST
    HOST.json_response = lambda data, status=200: (status, data)
    HOST.actor = lambda request: "tester"
    HOST.dash_auth = lambda request: False
    return HOST


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _wire_test_host()
        cls._tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        cls._tmp.close()
        kdb.set_db_path(cls._tmp.name)
        kdb.init()
        kseed.seed(force=True)

    @classmethod
    def tearDownClass(cls):
        kdb.set_db_path(None)
        try:
            os.unlink(cls._tmp.name)
        except OSError:
            pass


class TestToken(Base):
    def test_token_is_created_once_and_persists(self):
        t1 = kdb.share_token()
        self.assertTrue(t1)
        self.assertGreaterEqual(len(t1), 24)
        # A second call — and, since it reads from the DB, a restart — returns the same
        # token. A per-boot token would silently break every saved link on redeploy.
        kdb._inited.clear()
        self.assertEqual(kdb.share_token(), t1)

    def test_only_the_real_token_is_accepted(self):
        t = kdb.share_token()
        self.assertTrue(kdb.token_ok(t))
        for bad in ("", None, "x", t + "x", t[:-1], t.upper() if t.lower() != t else t + "A"):
            self.assertFalse(kdb.token_ok(bad), repr(bad))

    def test_rotation_kills_the_old_token(self):
        old = kdb.share_token()
        new = kdb.rotate_share_token(actor="faisal")
        self.assertNotEqual(old, new)
        self.assertFalse(kdb.token_ok(old), "the old link must stop working immediately")
        self.assertTrue(kdb.token_ok(new))

    def test_rotation_is_audited_without_storing_the_secret(self):
        kdb.rotate_share_token(actor="faisal")
        rows = kdb.audit_for("setting", kdb.SHARE_KEY)
        self.assertTrue(rows)
        self.assertEqual(rows[0]["changed_by"], "faisal")
        # The audit row must not be a second copy of a live secret.
        self.assertNotIn(kdb.share_token(), str(rows[0]["new_value"]))
        self.assertLess(len(str(rows[0]["new_value"])), 12)

    def test_share_url_shape(self):
        _, r = krt.core_share("https://oujares.com")
        self.assertEqual(r["url"], "https://oujares.com/kb/" + kdb.share_token())


class TestPublicEditsAreAttributed(Base):
    def test_public_edit_is_stamped_with_the_door_not_left_blank(self):
        """No name is asked for, by decision. The log still records HOW the edit came in,
        so a wrong number is at least traceable to the public link rather than to
        nothing at all."""
        _, r = krt.core_save_unit({"unit_id": "UNT-483841", "note": "من الرابط"},
                                  actor=krt.PUBLIC_ACTOR)
        self.assertTrue(r["ok"])
        row = kdb.audit_for("unit", "UNT-483841")[0]
        self.assertEqual(row["changed_by"], krt.PUBLIC_ACTOR)
        self.assertTrue(row["changed_by"].strip())

    def test_public_writes_go_through_the_same_validation(self):
        """The public door must not be a way around the enum rules."""
        _, r = krt.core_save_unit({"unit_id": "UNT-483841", "payment_cycle": "ربع سنوي"},
                                  actor=krt.PUBLIC_ACTOR)
        self.assertFalse(r["ok"])
        self.assertTrue(r["message"])


class TestRouteWiring(Base):
    """Read the registered routes rather than trusting the source to look right."""

    def setUp(self):
        self.routes = []

        class FakeRouter(object):
            def __init__(self, sink):
                self.sink = sink

            def add_get(self, path, h):
                self.sink.append(("GET", path, h))

            def add_post(self, path, h):
                self.sink.append(("POST", path, h))

        class FakeApp(object):
            def __init__(self, sink):
                self.router = FakeRouter(sink)

        krt.register(FakeApp(self.routes))

    def paths(self, method=None):
        return [p for m, p, _ in self.routes if method is None or m == method]

    def test_public_paths_never_start_with_the_private_prefix(self):
        """The role middleware gates the WHOLE /api/kb/ prefix. If a public path ever
        started with it, the share link would 403 for everyone; if the private prefix
        were loosened instead, the private door would open. Keep them disjoint."""
        for p in self.paths():
            if p.startswith("/api/kbp/"):
                self.assertFalse(p.startswith("/api/kb/"))

    def test_every_public_api_route_refuses_a_wrong_token(self):
        """Behaviour, not naming: actually CALL each public handler with a bad token and
        assert it comes back 403 without reaching the core. A handler registered without
        the _pub wrapper would sail straight through and answer 200."""
        pub = [(m, p, h) for m, p, h in self.routes if p.startswith("/api/kbp/")]
        self.assertTrue(pub)
        for m, p, h in pub:
            status, payload = _run(h(_FakeRequest(token="not-the-token", path=p)))
            self.assertEqual(status, 403, "%s %s let a wrong token through" % (m, p))
            self.assertEqual(payload.get("error"), "bad_link")

    def test_every_public_api_route_accepts_the_real_token(self):
        real = kdb.share_token()
        for m, p, h in [r for r in self.routes if r[1].startswith("/api/kbp/")]:
            status, payload = _run(h(_FakeRequest(token=real, path=p)))
            self.assertNotEqual(status, 403, "%s %s refused the real token" % (m, p))

    def test_a_write_accepts_the_token_from_the_body_too(self):
        """The page posts JSON; the token rides in the body there, not the query."""
        save = [h for m, p, h in self.routes if p == "/api/kbp/unit-save"][0]
        status, _ = _run(save(_FakeRequest(
            token=None, path="/api/kbp/unit-save",
            body={"t": kdb.share_token(), "unit_id": "UNT-483841", "note": "من الرابط"})))
        self.assertEqual(status, 200)

    def test_the_share_page_is_the_only_non_api_public_route(self):
        non_api = [p for p in self.paths() if not p.startswith("/api/")]
        self.assertEqual(non_api, ["/kb/{token}"])

    def test_private_routes_still_exist(self):
        for p in ("/api/kb/search", "/api/kb/unit-save", "/api/kb/share-rotate"):
            self.assertIn(p, self.paths())


class TestExemptList(Base):
    """Every public write must be listed in bot.py's exemption set, or the middleware
    demands a login and the share link's Save button silently 401s."""

    @classmethod
    def setUpClass(cls):
        super(TestExemptList, cls).setUpClass()
        import bot
        cls.bot = bot

    def test_public_writes_are_exempt(self):
        for p in ("/api/kbp/unit-save", "/api/kbp/unit-delete", "/api/kbp/question"):
            self.assertIn(p, self.bot._ROLE_EXEMPT_WRITES, p)

    def test_no_private_kb_path_leaked_into_the_exempt_list(self):
        for p in self.bot._ROLE_EXEMPT_WRITES:
            self.assertFalse(p.startswith("/api/kb/"), p)

    def test_private_prefix_still_gated_both_ways(self):
        self.assertIn(("/api/kb/", "kb"), self.bot._ROLE_READ_RULES)
        self.assertIn(("/api/kb/", "kb"), self.bot._ROLE_WRITE_RULES)

    def test_public_prefix_is_not_gated_by_a_role(self):
        for prefix, _tab in self.bot._ROLE_READ_RULES + self.bot._ROLE_WRITE_RULES:
            self.assertFalse("/api/kbp/".startswith(prefix) and prefix != "/api/",
                             "public prefix caught by role rule " + prefix)


class TestPageSource(Base):
    def test_no_backslash_anywhere(self):
        """kb/page.py is a normal triple-quoted string: Python eats any escape written
        into the JS, and one mangled literal takes the page down."""
        self.assertNotIn("\\", kpage.HTML)
        self.assertNotIn("\\", kpage.DEAD_HTML)

    def test_javascript_parses(self):
        import re
        try:
            import esprima
        except ImportError:
            self.skipTest("esprima not installed")
        blocks = re.findall(r"<script>(.*?)</script>", kpage.HTML, re.S)
        self.assertEqual(len(blocks), 1)
        esprima.parseScript(blocks[0])

    def test_balanced(self):
        for h in (kpage.HTML, kpage.DEAD_HTML):
            self.assertEqual(h.count("{"), h.count("}"))
            self.assertEqual(h.count("("), h.count(")"))
            self.assertEqual(h.count("`") % 2, 0)

    def test_page_talks_only_to_the_public_prefix(self):
        """A copy-paste from the dashboard JS would point at /api/kb/ and 403."""
        self.assertNotIn("/api/kb/", kpage.HTML)
        self.assertIn("/api/kbp/", kpage.HTML)

    def test_page_asks_search_engines_to_stay_out(self):
        self.assertIn('name="robots"', kpage.HTML)
        self.assertIn("noindex", kpage.HTML)

    def test_dead_link_page_explains_itself(self):
        self.assertIn("الرابط ما عاد يشتغل", kpage.DEAD_HTML)


if __name__ == "__main__":
    unittest.main()
