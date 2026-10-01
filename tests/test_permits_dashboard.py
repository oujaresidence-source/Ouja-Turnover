# -*- coding: utf-8 -*-
"""
The dashboard side of «التصاريح» cannot break the dashboard.

DASHBOARD_HTML is a normal Python string: one stray backslash in the embedded JS becomes
a real character and one bad token kills the WHOLE script — the dashboard won't even log
in (CLAUDE.md trap 1; it has bitten twice). So: every <script> is parsed, the stub that
loads the tab is backslash-free in the SOURCE, the tab's own file passes `node --check`,
and the cleanup jobs that delete channels are proven blind to permit rooms (F19).

Run: python3 -m unittest tests.test_permits_dashboard
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
TAB_JS = os.path.join(ROOT, "permits", "static", "permits_tab.js")

try:
    import esprima             # dev tool: pip install esprima
except Exception:              # pragma: no cover
    esprima = None


def _node():
    for cand in (shutil.which("node"), os.path.expanduser("~/.local/node/bin/node")):
        if cand and os.path.exists(cand):
            return cand
    return None


def _stub_source():
    src = open(os.path.join(ROOT, "bot.py"), encoding="utf-8").read()
    start = src.index("/* PERMITS «التصاريح» — the tab's code")
    end = src.index("async function loadWifi(force){", start)
    return src[start:end]


class TestEmbeddedScripts(unittest.TestCase):

    @unittest.skipIf(esprima is None, "esprima not installed")
    def test_every_script_parses(self):
        scripts = re.findall(r"<script>(.*?)</script>", bot.DASHBOARD_HTML, re.S)
        self.assertGreater(len(scripts), 0)
        for js in scripts:
            esprima.parseScript(js)

    def test_the_stub_has_zero_backslashes_and_is_short(self):
        stub = _stub_source()
        self.assertNotIn("\\", stub)
        self.assertLessEqual(len([ln for ln in stub.strip().splitlines() if ln.strip()]), 15)

    def test_the_version_placeholder_is_replaced(self):
        self.assertNotIn("__PERMITS_JS_V__", bot.DASHBOARD_HTML)
        self.assertRegex(bot.DASHBOARD_HTML, r"/permits/static/permits_tab\.js\?v=\d+")

    def test_go_loads_the_tab(self):
        self.assertIn("if(id==='permits') loadPermits();", bot.DASHBOARD_HTML)

    def test_the_badge_is_wired(self):
        self.assertIn("if(key==='permits') return ((D.permits && D.permits.counts) || {}).alert || 0;",
                      bot.DASHBOARD_HTML)
        self.assertIn("permitsBadgeRefresh();", bot.DASHBOARD_HTML)

    def test_one_section_with_the_ids_the_script_fills(self):
        self.assertEqual(bot.DASHBOARD_HTML.count('id="view_permits"'), 1)
        sec = bot.DASHBOARD_HTML[bot.DASHBOARD_HTML.index('id="view_permits"'):]
        sec = sec[:sec.index("</section>")]
        for i in ('id="pmTop"', 'id="pmKpis"', 'id="pmBody"'):
            self.assertIn(i, sec)
        self.assertNotIn('class="view on"', sec)                 # trap 3: never hardcode a panel on

    def test_the_tab_uses_only_globals_the_dashboard_defines(self):
        for fn in ("api", "post", "tok", "esc", "labelText", "toast", "putHtml", "emptyState",
                   "errorState", "openDrawer", "setDrawerBody", "setDrawerFoot", "closeDrawer",
                   "buildSideNav", "canRead"):
            self.assertRegex(bot.DASHBOARD_HTML, r"function %s\(" % fn, fn)
        self.assertIn("let L = ", bot.DASHBOARD_HTML)


class TestTabFile(unittest.TestCase):

    @unittest.skipIf(_node() is None, "node not installed")
    def test_node_check(self):
        r = subprocess.run([_node(), "--check", TAB_JS], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_no_inline_handler_string_building(self):
        js = open(TAB_JS, encoding="utf-8").read()
        self.assertNotIn("onclick=", js)

    def test_the_mode_switch_uses_the_typed_word(self):
        js = open(TAB_JS, encoding="utf-8").read()
        self.assertIn("confirm: val('pmGoWord')", js)
        self.assertNotIn("window.prompt", js)


class TestCleanupJobsIgnorePermitRooms(unittest.TestCase):
    """F19: nothing that deletes or parses ticket rooms may touch an `ouja-permit:` room."""

    class Ch(object):
        def __init__(self, name, topic):
            self.id = 424242
            self.name = name
            self.topic = topic

    def test_watchman_cleanup(self):
        ch = self.Ch("مغلقة-تصريح-007-f2", "ouja-permit: pid:12 tid:7 end:2026-10-12")
        self.assertFalse(bot._wm_is_watchman_ticket_channel(ch, closed_only=True))
        self.assertFalse(bot._wm_is_watchman_ticket_channel(ch, closed_only=False))

    def test_maint_ticket_parser(self):
        ch = self.Ch("تصريح-007-f2", "ouja-permit: pid:12 tid:7 end:2026-10-12")
        self.assertIsNone(bot._tk_rec_for(ch))

    def test_the_topic_never_carries_the_other_tags(self):
        from permits import engine
        t = engine.topic(12, 7, "2026-10-12")
        for tag in ("ouja-ticket:", "ouja-watchman:", "oujact:", "ouja-dp:"):
            self.assertNotIn(tag, t)


if __name__ == "__main__":
    unittest.main()
