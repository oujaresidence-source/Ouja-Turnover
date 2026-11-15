# -*- coding: utf-8 -*-
"""
«الأهداف ودفتر العملاء» wiring inside bot.py — read as TEXT (importing bot.py boots a Discord bot).

Each assertion is a past outage class in this repo: a tab id without a label renders
«undefined»; an /api/ prefix missing from the role rules is open to everyone or a 401 for
everyone; one bad token in the dashboard script and the page will not even log in.

THE SWITCH-OFF GUARANTEE: nothing for this feature was typed into the DASHBOARD_HTML literal.
The two views and their loader are spliced in at import, only under `if _HAS_TARGETS:`, so
with TG_ENABLED=0 the served dashboard is the same string it was before this feature existed.

Run: python3 -m unittest tests.test_targets_wiring
"""

import ast
import copy
import os
import re
import shutil
import subprocess
import sys
import unittest
import warnings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from targets import page, routes        # noqa: E402

try:
    import esprima
except Exception:                        # pragma: no cover
    esprima = None


def src():
    with open(os.path.join(ROOT, "bot.py"), encoding="utf-8") as f:
        return f.read()


def dashboard_literal(text):
    """The dashboard string as PYTHON evaluates it (escapes consumed) — what is really served."""
    start = text.index('DASHBOARD_HTML = """') + len("DASHBOARD_HTML = ")
    end = text.index('"""', start + 3) + 3
    return ast.literal_eval(text[start:end])


class Wiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = src()
        cls.html = dashboard_literal(cls.s)

    def test_bot_py_still_compiles_with_no_syntax_warning(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error", SyntaxWarning)
            compile(self.s, "bot.py", "exec")

    def test_import_is_optional_and_follows_the_switch(self):
        self.assertIn("import targets as _targets", self.s)
        self.assertIn("_HAS_TARGETS = bool(_targets.enabled())", self.s)
        self.assertIn("_HAS_TARGETS = False", self.s)

    def test_role_rules_read_and_write_and_the_public_box(self):
        self.assertEqual(self.s.count('("/api/targets/", "targets")'), 2)
        self.assertEqual(self.s.count('("/api/book/", "book")'), 2)
        self.assertEqual(self.s.count('"/api/tg-consent",'), 1)
        self.assertNotIn('"/api/book/wa",', self.s)              # the press is never exempt from login

    def test_every_splice_is_behind_the_switch(self):
        for call in ("_targets.routes.patch_nav(NAV_DEF)",
                     "DASHBOARD_HTML = _targets.routes.patch_dashboard(DASHBOARD_HTML)"):
            i = self.s.index(call)
            self.assertEqual(self.s[:i].rstrip().splitlines()[-1].strip(), "if _HAS_TARGETS:")
        i = self.s.index("_targets.register_routes(app)")
        self.assertIn("if _HAS_TARGETS:", self.s[i - 400:i])

    def test_nav_is_patched_before_the_permission_reconcile(self):
        self.assertLess(self.s.index("_targets.routes.patch_nav(NAV_DEF)"),
                        self.s.index("for _nav_it in NAV_DEF.get(\"items\", []):"))
        self.assertLess(self.s.index("_targets.routes.patch_nav(NAV_DEF)"),
                        self.s.index("_NAV_DEF_JSON = json.dumps(NAV_DEF"))

    def test_history_comes_from_the_window_fetch_only(self):
        self.assertIn('"fetch_window": fetch_reservations_window,', self.s)
        pkg = os.path.join(ROOT, "targets")
        for name in os.listdir(pkg):
            if name.endswith(".py"):
                with open(os.path.join(pkg, name), encoding="utf-8") as f:
                    self.assertNotIn("get_reservations_cached", f.read(), name)

    def test_handlers_run_on_web_thread(self):
        self.assertIn('"web_thread": web_thread,', self.s[self.s.index("def _tg_wire():"):])
        with open(os.path.join(ROOT, "targets", "routes.py"), encoding="utf-8") as f:
            r = f.read()
        self.assertNotIn("to_thread", r)

    def test_nightly_is_a_plain_task_not_a_tasks_loop(self):
        i = self.s.index("async def _tg_nightly_loop():")
        self.assertNotIn("@tasks.loop", self.s[i - 200:i])
        self.assertIn("asyncio.create_task(_tg_nightly_loop())", self.s)


class SwitchedOffIsUnchanged(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = src()
        cls.html = dashboard_literal(cls.s)

    def test_nothing_was_typed_into_the_dashboard_literal(self):
        for word in ("view_targets", "view_book", "loadTargets", "loadBook", "tgBody", "bkBody",
                     "targets_tab.js", "أهدافي", "دفتر العملاء"):
            self.assertNotIn(word, self.html, word)

    def test_nothing_was_typed_into_nav_def(self):
        i = self.s.index("NAV_DEF = {")
        j = self.s.index('"erp_targets":', i)
        self.assertNotIn('"targets"', self.s[i:j])
        self.assertNotIn('"book"', self.s[i:j])

    def test_guide_page_is_served_as_is_without_the_extra(self):
        from guide import routes as gr
        with open(os.path.join(ROOT, "guide", "templates", "guide.html"), encoding="utf-8") as f:
            raw = f.read()
        self.assertNotIn("tgConsent", raw)
        old = gr.HOST.page_extra
        try:
            gr.HOST.page_extra = ""
            self.assertEqual(gr._with_extra(raw), raw)
            gr.HOST.page_extra = routes.GUIDE_CONSENT_HTML
            out = gr._with_extra(raw)
            self.assertEqual(out.count('id="tgConsent"'), 1)
            self.assertLess(out.index('id="tgConsent"'), out.index('<footer class="footer">'))
            self.assertEqual(out.replace(routes.GUIDE_CONSENT_HTML, "", 1), raw)
        finally:
            gr.HOST.page_extra = old


class SwitchedOn(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = src()
        cls.html = dashboard_literal(cls.s)
        cls.patched = routes.patch_dashboard(cls.html)

    def test_anchors_exist_exactly_once(self):
        for a in (routes.ANCHOR_VIEW, routes.ANCHOR_HOOK, routes.ANCHOR_STUB):
            self.assertEqual(self.html.count(a), 1, a)

    def test_views_loader_and_hook_are_added_once(self):
        self.assertNotEqual(self.patched, self.html)
        for needle in ('id="view_targets"', 'id="view_book"', 'id="tgBody"', 'id="bkBody"',
                       "function loadTargets(force)", "function loadBook(force)",
                       "if(id==='targets') loadTargets();", "if(id==='book') loadBook();"):
            self.assertEqual(self.patched.count(needle), 1, needle)
        self.assertNotIn("__TG_JS_V__", self.patched)
        self.assertEqual(self.patched.count('<section class="view"'), self.html.count('<section class="view"') + 2)
        self.assertEqual(self.patched.count("</section>"), self.html.count("</section>") + 2)

    def test_default_panel_rule_is_respected(self):
        self.assertNotIn('class="view on"', routes.DASH_VIEWS)     # CLAUDE.md trap 3
        self.assertNotIn('class="panel on"', routes.DASH_VIEWS)

    def test_no_backslash_and_balanced_additions(self):
        for name in ("DASH_VIEWS", "DASH_STUBS", "DASH_HOOK", "GUIDE_CONSENT_HTML"):
            text = getattr(routes, name)
            self.assertNotIn(chr(92), text, name)
            self.assertEqual(text.count("{"), text.count("}"), name)
            self.assertEqual(text.count("("), text.count(")"), name)
            self.assertEqual(text.count("`") % 2, 0, name)
        with open(os.path.join(ROOT, "targets", "page.py"), encoding="utf-8") as f:
            self.assertNotIn(chr(92), f.read())

    def test_a_missing_anchor_changes_nothing(self):
        broken = self.html.replace(routes.ANCHOR_HOOK, "", 1)
        self.assertEqual(routes.patch_dashboard(broken), broken)

    def test_nav_gets_both_ids_with_labels_in_both_languages(self):
        nav = {"cats": [{"tk": "cat_overview", "ids": ["home"]}, {"tk": "cat_ops", "ids": ["inbox"]}],
               "items": [{"id": "home", "ic": "home", "tk": "home"}],
               "labels": {"ar": {"home": "الرئيسية"}, "en": {"home": "Home"}}}
        before = copy.deepcopy(nav)
        out = routes.patch_nav(nav)
        for tab in ("targets", "book"):
            self.assertIn(tab, [i["id"] for i in out["items"]])
            self.assertIn(tab, out["cats"][1]["ids"])
            self.assertTrue(out["labels"]["ar"][tab])
            self.assertTrue(out["labels"]["en"][tab])
        self.assertEqual(out["labels"]["ar"]["home"], before["labels"]["ar"]["home"])
        routes.patch_nav(out)                                      # idempotent
        self.assertEqual([i["id"] for i in out["items"]].count("targets"), 1)
        self.assertEqual(out["cats"][1]["ids"].count("book"), 1)
        ics = {m for m in re.findall(r'"ic": "([a-z_]+)"', self.s)}
        for it in routes.NAV_ITEMS:
            self.assertIn(it["ic"], ics)                           # an icon the front-ends already draw

    @unittest.skipIf(esprima is None, "esprima not installed")
    def test_every_script_still_parses(self):
        for js in re.findall(r"<script>(.*?)</script>", self.patched, re.S):
            if "__NAV_DEF_JSON__" in js:
                js = js.replace("__NAV_DEF_JSON__", "{}")
            esprima.parseScript(js)
        for which in ("targets", "book"):
            html = page.render(which, "1")
            self.assertIn('data-which="%s"' % which, html)
            for js in re.findall(r"<script>(.*?)</script>", html, re.S):
                esprima.parseScript(js)
        for js in re.findall(r"<script>(.*?)</script>", routes.GUIDE_CONSENT_HTML, re.S):
            esprima.parseScript(js)

    def test_tab_script_passes_node_check(self):
        node = shutil.which("node") or os.path.expanduser("~/.local/node/bin/node")
        if not os.path.exists(node):
            self.skipTest("node not installed")
        r = subprocess.run([node, "--check", routes.STATIC_JS], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_tab_script_uses_only_the_host_pages_helpers(self):
        with open(routes.STATIC_JS, encoding="utf-8") as f:
            js = f.read()
        self.assertIn("window.TargetsTab", js)
        self.assertNotIn("innerHTML", js)                          # everything goes through putHtml + esc
        self.assertNotIn("onclick=", js)                           # event delegation only
        shim = page._SHIM
        for helper in ("function api(", "function post(", "function esc(", "function labelText(",
                       "function toast(", "function putHtml(", "function emptyState(",
                       "function errorState(", "function tok("):
            self.assertIn(helper, shim, helper)


if __name__ == "__main__":
    unittest.main()
