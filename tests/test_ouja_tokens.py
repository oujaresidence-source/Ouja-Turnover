# -*- coding: utf-8 -*-
"""ONE look: the dashboard (DASHBOARD_HTML), the Finance Center (erp.css) and the team app
(staff/page.py) must carry the SAME «عوجا» colours and type. Change a colour in one place and
forget the others, and this fails before it reaches anyone's screen (owner, 2026-11-17: «in sync»).

Reads the files as text — no `import bot` (that boots the whole app)."""

import ast
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _dashboard_html():
    src = open(os.path.join(ROOT, "bot.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "DASHBOARD_HTML" for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError("DASHBOARD_HTML not found")


def _vars(text):
    text = re.sub(r"/[*].*?[*]/", "", text, flags=re.S)        # comments mention token names
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"--([a-z0-9-]+):([^;]+);", text)}


def _root_block(css):
    """The first :root{...} block as {name: value}."""
    i = css.index(":root{")
    return _vars(css[i:css.index("}", i)])


def _block(css, selector):
    i = css.index(selector + "{")
    return _vars(css[i:css.index("}", i)])


DASH = _dashboard_html()
ERP = open(os.path.join(ROOT, "finance", "static", "erp.css"), encoding="utf-8").read()
from staff import page as _staff_page  # noqa: E402
STAFF = _staff_page.HTML

D = _root_block(DASH)
E = _root_block(ERP)
S = _root_block(STAFF)

# the SAME colour under each surface's own name: (dashboard, finance, team app)
SHARED = [
    ("bg", "bg", "paper"),
    ("surface", "surface", "card"),
    ("text", "text", "ink"),
    ("text-2", "text-2", "ink2"),
    ("text-3", "text-3", "mut"),
    ("line", "line", "line2"),
    ("line-strong", "line-strong", "line"),
    ("gold-logo", "gold-logo", "gold"),
    ("green", "green", "ok"),
    ("green-soft", "green-soft", "ok-bg"),
    ("red", "red", "bad"),
    ("red-soft", "red-soft", "bad-bg"),
    ("yellow", "yellow", "warn"),
    ("yellow-soft", "yellow-soft", "warn-bg"),
]


class OneLook(unittest.TestCase):
    def test_colours_match_everywhere(self):
        for d, e, s in SHARED:
            with self.subTest(token=d):
                self.assertEqual(D[d].upper(), E[e].upper(), "dashboard vs finance: --%s" % d)
                self.assertEqual(D[d].upper(), S[s].upper(), "dashboard vs team app: --%s" % d)

    def test_dashboard_and_finance_share_every_common_colour(self):
        for k in ("surface-2", "surface-3", "tint", "mut", "blue", "blue-soft", "purple", "purple-soft",
                  "accent", "accent-soft", "ease"):
            with self.subTest(token=k):
                self.assertEqual(D[k].upper(), E[k].upper())

    def test_ink_acts_gold_only_marks(self):
        self.assertEqual(D["accent"].upper(), D["text"].upper())     # buttons/links are ink
        self.assertEqual(D["gold-logo"].upper(), "#A57A2C")

    def test_same_type_everywhere(self):
        for name, css in (("dashboard", DASH), ("finance", ERP), ("team app", STAFF)):
            with self.subTest(surface=name):
                self.assertIn("thmanyah-sans-regular.v20260827a.woff2", css)
                self.assertIn("Thmanyah Serif", css)
        self.assertTrue(D["font-ar"].startswith("'Thmanyah Sans'"))
        self.assertTrue(E["font-ar"].startswith("'Thmanyah Sans'"))

    def test_no_apple_blue_left_in_the_dashboard_or_finance(self):
        for name, css in (("dashboard", DASH), ("finance", ERP)):
            with self.subTest(surface=name):
                self.assertNotIn("#0A84FF", css.upper())
                self.assertNotIn("RGBA(10,132,255", css.upper().replace(" ", ""))

    def test_night_mode_is_the_same_paper_at_night(self):
        dark = _block(DASH, 'html[data-theme="dark"]')
        self.assertEqual(dark["bg"].upper(), "#15110D")
        self.assertEqual(dark["text"].upper(), "#F4EFE7")
        auto = DASH[DASH.index('html[data-theme="auto"]{'):]
        auto = _block(auto, 'html[data-theme="auto"]')
        for k in ("bg", "surface", "text", "accent", "red", "green"):
            with self.subTest(token=k):
                self.assertEqual(dark[k].upper(), auto[k].upper())

    def test_browser_bar_colour(self):
        self.assertIn('<meta name="theme-color" content="#F4EFE7">', DASH)
        self.assertIn('<meta name="theme-color" content="#F4EFE7">', STAFF)


class PhoneMenu(unittest.TestCase):
    def test_more_lists_every_allowed_page(self):
        i = DASH.index("function buildMoreNav(){")
        body = DASH[i:DASH.index("function buildInboxTabs(){", i)]
        self.assertIn("NAV_CATS.forEach", body)            # every category, like the sidebar
        self.assertIn("canRead(n.id)", body)               # only what this login may open
        self.assertIn("staffApp", body)

    def test_more_is_never_permission_gated(self):
        # go() bounces a non-admin off any page they can't read; «المزيد» is not a page in the
        # permission matrix, so without this every non-admin's «المزيد» tap landed on Home.
        self.assertIn("function canRead(id){ if(id==='more') return true;", DASH)

    def test_bottom_bar_is_per_role(self):
        self.assertIn("function mobileNav()", DASH)
        self.assertIn("mobileNav().filter", DASH)
        self.assertIn("repeat(5,1fr)", DASH)

    def test_team_app_lists_all_pages_from_the_shared_nav(self):
        self.assertIn("getJSON('/api/nav')", STAFF)
        self.assertIn("كل الصفحات", STAFF)


if __name__ == "__main__":
    unittest.main()
