# -*- coding: utf-8 -*-
"""
«المناوبة» wiring inside bot.py — read as TEXT (importing bot.py boots a Discord bot).

Each assertion is a past outage class in this repo: a tab id without a label renders
«undefined»; an /api/ prefix missing from the role rules is either open to everyone or a
401 for everyone; a listener never registered is a button that "does nothing".

Run: python3 -m unittest tests.test_oncall_wiring
"""

import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def src():
    with open(os.path.join(ROOT, "bot.py"), encoding="utf-8") as f:
        return f.read()


class Wiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = src()

    def test_import_is_optional(self):
        self.assertIn("import oncall as _oncall", self.s)
        self.assertIn("_HAS_ONCALL = False", self.s)

    def test_role_rules_read_and_write(self):
        self.assertEqual(self.s.count('("/api/oncall/", "oncall")'), 2)

    def test_nav_item_and_both_labels(self):
        self.assertIn('{"id": "oncall", "ic": "calendar", "tk": "oncall"}', self.s)
        self.assertIn('"rvpush", "oncall", "listings"', self.s)
        self.assertIn('"oncall": "المناوبة"', self.s)
        self.assertIn('"oncall": "On-call"', self.s)

    def test_dashboard_view_loader_and_version(self):
        self.assertIn('id="view_oncall"', self.s)
        self.assertIn("if(id==='oncall') loadOncall();", self.s)
        self.assertIn("function loadOncall(force){", self.s)
        self.assertIn('"__ONCALL_JS_V__", (_oncall.routes.js_version()', self.s)

    def test_no_backslash_in_the_dashboard_additions(self):
        i = self.s.index('<section class="view" id="view_oncall">')
        j = self.s.index("</section>", i)
        self.assertNotIn(chr(92), self.s[i:j])
        k = self.s.index("function loadOncall(force){")
        m = self.s.index("document.head.appendChild(s);", k)
        self.assertNotIn(chr(92), self.s[k:m])

    def test_listeners_loop_and_routes(self):
        self.assertIn('bot.add_listener(_oc_interaction, "on_interaction")', self.s)
        self.assertIn('bot.add_listener(_oc_on_message, "on_message")', self.s)
        self.assertIn("_pending.append(oncall_loop)", self.s)
        self.assertIn('_loop_guard(oncall_loop, "oncall_loop")', self.s)
        self.assertIn("_oncall.register_routes(app)", self.s)

    def test_all_four_issue_hooks(self):
        self.assertIn('_oncall.notify.on_issue_opened, "escalation"', self.s)
        self.assertIn('_oncall.notify.on_issue_opened, "maint"', self.s)
        self.assertIn("_oncall.notify.on_escalation_claimed", self.s)
        self.assertEqual(len(re.findall(r"_oncall\.notify\.on_issue_resolved", self.s)), 2)

    def test_thread_safe_delivery(self):
        i = self.s.index("def _oc_send(payload):")
        self.assertIn("run_coroutine_threadsafe", self.s[i:i + 900])


if __name__ == "__main__":
    unittest.main()
