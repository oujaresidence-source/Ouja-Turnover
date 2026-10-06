# -*- coding: utf-8 -*-
"""The «اجتماع المالك» tab inside DASHBOARD_HTML (gate G15) — the trap that kills a login.

Run: python3 -m unittest tests.test_owner_meet_dashboard
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("STATE_DIR", tempfile.mkdtemp(prefix="ouja-meet-dash-"))

import bot  # noqa: E402

TAB_JS = ROOT / "owner_meet" / "static" / "owner_meet_tab.js"
STUB_START = "/* OWNER MEETING «اجتماع المالك» — the tab's code"
STUB_END = "/* «رفع التقييم» — the tab's code"


def _node():
    for c in (shutil.which("node"), os.path.expanduser("~/.local/node/bin/node")):
        if c and os.path.exists(c):
            return c
    return None


class DashboardTab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = bot.DASHBOARD_HTML

    def test_view_exists_once_and_is_not_forced_on(self):
        self.assertEqual(self.html.count('id="view_meet"'), 1)
        self.assertNotIn('class="view on" id="view_meet"', self.html)
        sec = self.html.split('id="view_meet"', 1)[1].split("</section>", 1)[0]
        self.assertIn('id="omBody"', sec)

    def test_stub_is_short_and_backslash_free(self):
        stub = self.html.split(STUB_START, 1)[1].split(STUB_END, 1)[0]
        self.assertNotIn(chr(92), stub)
        self.assertLessEqual(len([l for l in stub.splitlines() if l.strip()]), 15)
        self.assertIn("window.MeetTab.load(force)", stub)

    def test_cache_buster_is_baked(self):
        self.assertNotIn("__OWNER_MEET_JS_V__", self.html)
        self.assertRegex(self.html, r"/meet/static/owner_meet_tab\.js\?v=[0-9]+")

    def test_go_routes_the_tab(self):
        self.assertIn("if(id==='meet') loadMeet();", self.html)

    def test_tab_js_parses_and_never_builds_inline_handlers(self):
        src = TAB_JS.read_text(encoding="utf-8")
        self.assertNotIn("onclick=", src)
        self.assertNotIn(chr(92), src)
        node = _node()
        if node is None:
            self.skipTest("node not installed")
        for f in sorted((ROOT / "owner_meet" / "static").glob("*.js")):
            r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, "%s: %s" % (f.name, r.stderr))

    def test_the_globals_the_tab_uses_exist(self):
        for g in ("async function api(", "async function post(", "function esc(", "function putHtml(",
                  "function errorState(", "function tok("):
            self.assertIn(g, self.html, g)

    def test_dashboard_scripts_still_parse(self):
        try:
            import esprima
        except ImportError:
            self.skipTest("esprima not installed")
        for js in re.findall(r"<script>(.*?)</script>", self.html, re.S):
            esprima.parseScript(js)


if __name__ == "__main__":
    unittest.main()
