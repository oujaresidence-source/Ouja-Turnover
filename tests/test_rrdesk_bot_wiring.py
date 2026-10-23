# -*- coding: utf-8 -*-
"""
«طلبات سام» wiring inside bot.py — read as TEXT (importing bot.py boots a Discord bot).

Each assertion is a past outage class: bot.py calling `_rrdesk.<name>` that does not exist
(the digest outage), a tab id without a label («undefined»), an /api/ prefix missing from the
role rules, a listener never registered (a button that "does nothing"), and a ticket close
blocked by an add-on.

Run: python3 -m unittest tests.test_rrdesk_bot_wiring
"""

import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import rrdesk   # noqa: E402


def src():
    with open(os.path.join(ROOT, "bot.py"), encoding="utf-8") as f:
        return f.read()


class Wiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = src()

    def test_every_rrdesk_attribute_bot_touches_exists(self):
        refs = set(re.findall(r"_rrdesk[.]([A-Za-z_]+)(?:[.]([A-Za-z_]+))?", self.s))
        self.assertTrue(refs)
        for top, sub in refs:
            self.assertTrue(hasattr(rrdesk, top), "_rrdesk.%s" % top)
            if sub:
                self.assertTrue(hasattr(getattr(rrdesk, top), sub), "_rrdesk.%s.%s" % (top, sub))

    def test_import_is_optional(self):
        self.assertIn("import rrdesk as _rrdesk", self.s)
        self.assertIn("_HAS_RRDESK = False", self.s)

    def test_listeners_loop_routes(self):
        for ev in ("on_message", "on_raw_message_edit", "on_raw_message_delete", "on_raw_reaction_add",
                   "on_interaction"):
            self.assertIn('bot.add_listener(_rrdesk.bridge.%s, "%s")' % (ev, ev), self.s)
        self.assertIn("_pending.append(rrdesk_loop)", self.s)
        self.assertIn('_loop_guard(rrdesk_loop, "rrdesk_loop")', self.s)
        self.assertIn("@tasks.loop(minutes=1)" + chr(10) + "async def rrdesk_loop():", self.s)
        self.assertIn("_rrdesk.register_routes(app)", self.s)

    def test_role_rules_read_and_write(self):
        self.assertEqual(self.s.count('("/api/rrdesk/", "rrdesk")'), 2)

    def test_dashboard_view_loader_and_version(self):
        self.assertIn('id="view_rrdesk"', self.s)
        self.assertIn("if(id==='rrdesk') loadRrdesk();", self.s)
        self.assertIn("function loadRrdesk(force){", self.s)
        self.assertIn('"__RRDESK_JS_V__", (_rrdesk.routes.js_version()', self.s)
        self.assertIn('"tickets", "rrdesk", "clean"', self.s)

    def test_stub_is_short_and_backslash_free(self):
        i = self.s.index('<section class="view" id="view_rrdesk">')
        self.assertNotIn(chr(92), self.s[i:self.s.index("</section>", i)])
        k = self.s.index("function loadRrdesk(force){")
        m = self.s.index("document.head.appendChild(s);", k)
        stub = self.s[k:m]
        self.assertNotIn(chr(92), stub)
        self.assertLessEqual(stub.count(chr(10)), 15)

    def test_close_hook_cannot_block_a_close(self):
        i = self.s.index("async def _tk_close(interaction):")
        body = self.s[i:self.s.index("_MAINT_CLOSE_REFUSAL = (", i)]
        j = body.index("_rrdesk.flow.ticket_closed")
        block = body[body.rfind("try:", 0, j):body.index("except Exception as _rdk:", j)]
        self.assertIn("asyncio.wait_for(", block)
        self.assertIn("timeout=5", block)
        # the close's own steps (lock, rename, archive) all come AFTER and outside the hook
        self.assertGreater(body.index("_tk_lock_channel(ch)"), j)
        self.assertGreater(body.index('ch.edit(name=("مغلقة-"'), j)

    def test_wire_hands_over_everything_the_package_uses(self):
        i = self.s.index("def _rd_wire():")
        body = self.s[i:i + 2500]
        for cap in ("rr_record", "rr_records", "enrich", "off_today", "once_claim", "watchdog_channel",
                    "api_key", "model", "responsible_for", "lead_id", "on_leave", "employees",
                    "is_admin", "web_thread", "dash_auth", "req_role"):
            self.assertIn('"%s"' % cap, body, cap)
            self.assertTrue(hasattr(rrdesk.HOST, cap), cap)

    def test_commands_registered(self):
        for name in ("rr-ask", "translate", "rrdesk-why", "rrdesk-sam", "rrdesk-switch", "rrdesk-off",
                     "rrdesk-on", "rrdesk-warnings-on", "rrdesk-warnings-off", "rrdesk-study", "rrdesk-setup"):
            self.assertIn('@bot.tree.command(name="%s"' % name, self.s)
        for alias in ('aliases=["ترجمة"]', 'aliases=["طلب-سام"]', 'aliases=["ليش"]', 'aliases=["دراسة-rr"]'):
            self.assertIn(alias, self.s)

    def test_members_intent_untouched(self):
        self.assertIn('intents.members = os.environ.get("MEMBERS_INTENT", "0").strip() == "1"', self.s)

    def test_existing_rr_flow_untouched(self):
        """The RR opening / English / close-out / nudge code is byte-for-byte what main has."""
        try:
            base = subprocess.run(["git", "-C", ROOT, "show", "origin/main:bot.py"], capture_output=True,
                                  text=True, timeout=30).stdout
        except Exception:
            self.skipTest("git unavailable")
        if not base:
            self.skipTest("origin/main not available")
        for start, end in (("async def _rr_open_ticket(", "def _rr_enrich(code):"),
                           ("async def _rr_generate_english(", "RR_WA_CAP "),
                           ("class RRCloseoutModal(", "async def _rr_closeout_submit("),
                           ("async def _rr_run_nudges():", "class _RRStatusSelect(")):
            a = base[base.index(start):base.index(end, base.index(start))]
            b = self.s[self.s.index(start):self.s.index(end, self.s.index(start))]
            self.assertEqual(a, b, start)
        diff = subprocess.run(["git", "-C", ROOT, "diff", "--stat", "origin/main", "--",
                               "tests/test_rr_closeout.py"], capture_output=True, text=True).stdout
        self.assertEqual(diff.strip(), "")


if __name__ == "__main__":
    unittest.main()
