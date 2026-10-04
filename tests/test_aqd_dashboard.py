# -*- coding: utf-8 -*-
"""
The dashboard side of «العقود» cannot break the dashboard, and its doors are wired the way
the package assumes.

DASHBOARD_HTML is a normal Python string: one stray backslash in embedded JS becomes a real
character and one bad token kills the WHOLE script — the dashboard won't even log in
(CLAUDE.md trap 1). So every <script> is parsed, the stub is backslash-free in the SOURCE,
both real JS files pass `node --check`, and the permission maps are evaluated as data — the
client's phone link must never meet a role rule, and the private API must always meet one.

Run: python3 -m unittest tests.test_aqd_dashboard
"""

import os
import re
import shutil
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bot                     # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AQD = os.path.join(ROOT, "aqd")

try:
    import esprima
except Exception:              # pragma: no cover
    esprima = None


def _node():
    for cand in (shutil.which("node"), os.path.expanduser("~/.local/node/bin/node")):
        if cand and os.path.exists(cand):
            return cand
    return None


def _src():
    return open(os.path.join(ROOT, "bot.py"), encoding="utf-8").read()


def _stub():
    s = _src()
    return s[s.index("/* AQD-STUB-START */"):s.index("/* AQD-STUB-END */")]


class TestEmbeddedScripts(unittest.TestCase):

    @unittest.skipIf(esprima is None, "esprima not installed")
    def test_every_script_parses(self):
        scripts = re.findall(r"<script>(.*?)</script>", bot.DASHBOARD_HTML, re.S)
        self.assertGreater(len(scripts), 0)
        for js in scripts:
            esprima.parseScript(js)

    def test_the_stub_is_backslash_free_and_short(self):
        stub = _stub()
        self.assertNotIn("\\", stub)
        fn = stub[stub.index("function loadAqd(force){"):stub.index("var __aqdBadgeAt")]
        self.assertLessEqual(len([ln for ln in fn.strip().splitlines() if ln.strip()]), 15)

    def test_the_version_placeholder_is_baked(self):
        self.assertNotIn("__AQD_JS_V__", bot.DASHBOARD_HTML)
        self.assertRegex(bot.DASHBOARD_HTML, r"/aqd/static/aqd_tab\.js\?v=\d+")

    def test_the_view_and_its_hooks_exist(self):
        h = bot.DASHBOARD_HTML
        self.assertEqual(h.count('id="view_aqd"'), 1)
        self.assertIn("if(id==='aqd') loadAqd();", h)
        self.assertIn("aqdBadgeRefresh();", h)
        self.assertIn("if(key==='aqd')", h)
        self.assertNotIn('class="view on" id="view_aqd"', h)

    def test_sign_page_has_zero_backslashes(self):
        with open(os.path.join(AQD, "sign_page.py"), encoding="utf-8") as f:
            self.assertNotIn("\\", f.read())


class TestRealJsFiles(unittest.TestCase):

    def test_node_check_both_files(self):
        node = _node()
        if not node:
            self.skipTest("node not available")
        for name in ("aqd_tab.js", "sign.js"):
            r = subprocess.run([node, "--check", os.path.join(AQD, "static", name)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, name + ": " + r.stderr)

    def test_no_to_thread_anywhere_in_aqd(self):
        for dirpath, _d, names in os.walk(AQD):
            for nm in names:
                if nm.endswith((".py", ".js")):
                    with open(os.path.join(dirpath, nm), encoding="utf-8") as f:
                        self.assertNotIn("to_thread", f.read(), nm)


class TestNav(unittest.TestCase):

    def test_aqd_sits_in_owner_sales_after_quote(self):
        cat = [c for c in bot.NAV_DEF["cats"] if c["tk"] == "cat_owner_sales"][0]
        self.assertEqual(cat["ids"][:2], ["quote", "aqd"])
        item = [i for i in bot.NAV_DEF["items"] if i["id"] == "aqd"][0]
        self.assertEqual(item, {"id": "aqd", "ic": "quote", "tk": "aqd", "badge": "aqd"})

    def test_labels_in_both_languages(self):
        self.assertEqual(bot.NAV_DEF["labels"]["ar"]["aqd"], "العقود")
        self.assertEqual(bot.NAV_DEF["labels"]["en"]["aqd"], "Contracts")

    def test_aqd_is_a_permission_key(self):
        self.assertIn("aqd", bot._USER_TABS)


class TestPermissionMaps(unittest.TestCase):

    def _read_rule(self, path):
        for prefix, tab in bot._ROLE_READ_RULES:
            if path.startswith(prefix):
                return tab
        return None

    def _write_rule(self, path):
        if path in bot._ROLE_EXEMPT_WRITES:
            return "EXEMPT"
        for prefix, tab in bot._ROLE_WRITE_RULES:
            if path.startswith(prefix):
                return tab
        return None

    def test_public_writes_are_exact_path_exempt(self):
        for p in ("/api/aqd-t/open", "/api/aqd-t/verify", "/api/aqd-t/sign"):
            self.assertIn(p, bot._ROLE_EXEMPT_WRITES)

    def test_private_api_is_gated_for_read_and_write(self):
        self.assertIn(("/api/aqd/", "aqd"), bot._ROLE_READ_RULES)
        self.assertIn(("/api/aqd/", "aqd"), bot._ROLE_WRITE_RULES)
        for p in ("/api/aqd/list", "/api/aqd/get", "/api/aqd/file", "/api/aqd/settings"):
            self.assertEqual(self._read_rule(p), "aqd", p)
        for p in ("/api/aqd/save", "/api/aqd/send", "/api/aqd/countersign", "/api/aqd/settings"):
            self.assertEqual(self._write_rule(p), "aqd", p)

    def test_the_phone_link_never_meets_a_role_rule(self):
        tok = "A" * 43
        self.assertIsNone(self._read_rule("/api/aqd-t/" + tok))
        self.assertIsNone(self._read_rule("/api/aqd-t/%s/file" % tok))
        for p in ("/api/aqd-t/open", "/api/aqd-t/verify", "/api/aqd-t/sign"):
            self.assertEqual(self._write_rule(p), "EXEMPT")


if __name__ == "__main__":
    unittest.main()
