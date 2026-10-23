# -*- coding: utf-8 -*-
"""
«طلبات سام» house rules, as code. Each assertion is a trap this repo has paid for.

Run: python3 -m unittest tests.test_rrdesk_structure
"""

import glob
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from rrdesk import study   # noqa: E402

PKG = os.path.join(ROOT, "rrdesk")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def pkg_files(exts=(".py", ".js")):
    out = []
    for dp, _dn, fns in os.walk(PKG):
        if "__pycache__" in dp:
            continue
        out += [os.path.join(dp, f) for f in fns if f.endswith(exts)]
    return sorted(out)


class Structure(unittest.TestCase):
    def test_zero_backslashes(self):
        bad = [os.path.relpath(f, ROOT) for f in pkg_files() if chr(92) in read(f)]
        self.assertEqual(bad, [])

    def test_never_imports_bot(self):
        for f in pkg_files((".py",)):
            src = read(f)
            self.assertIsNone(re.search(r"^[ ]*(import bot|from bot import)", src, re.M), f)

    def test_no_to_thread(self):
        for f in pkg_files((".py",)):
            self.assertNotIn("to_thread(", read(f), f)

    def test_study_tools_cannot_write_to_discord(self):
        for f in (os.path.join(ROOT, "tools", "rr_history_export.py"), os.path.join(PKG, "study.py")):
            src = read(f)
            for verb in ("POST", "PATCH", "PUT", "DELETE", '"post"', "urlopen(data", "data=",
                         ".send(", ".edit(", ".delete(", "create_text_channel", "add_reaction"):
                self.assertNotIn(verb, src, "%s contains %s" % (os.path.basename(f), verb))

    def test_no_route_button_or_command_can_accuse(self):
        """Misses are recorded only by the ladder; warnings only by the judge (flow._warn)."""
        for name in ("routes.py", "bridge.py", "texts.py", "translate.py", "study.py", "outbox.py"):
            src = read(os.path.join(PKG, name))
            for call in ("record_miss(", "issue_warning(", "_warn(", "ensure_obligation("):
                self.assertNotIn(call, src, "%s calls %s" % (name, call))
        flow = read(os.path.join(PKG, "flow.py"))
        self.assertEqual(flow.count("db.record_miss("), 1)
        i = flow.index("def _fire(")
        self.assertGreater(flow.index("db.record_miss("), i)
        bot = read(os.path.join(ROOT, "bot.py"))
        for call in ("_rrdesk.flow._warn", "_rrdesk.db.record_miss", "issue_warning"):
            if call == "issue_warning":
                continue
            self.assertNotIn(call, bot)

    def test_slash_names_are_ascii(self):
        names = re.findall(r'tree[.]command[(]name="([^"]+)"', read(os.path.join(ROOT, "bot.py")))
        self.assertTrue(names)
        bad = [n for n in names if not all(ord(c) < 128 for c in n) or not re.fullmatch(r"[-_a-z0-9]{1,32}", n)]
        self.assertEqual(bad, [])
        for want in ("rr-ask", "translate", "rrdesk-why", "rrdesk-off", "rrdesk-warnings-on", "rrdesk-study"):
            self.assertIn(want, names)

    def test_nav_labels_both_languages(self):
        bot = read(os.path.join(ROOT, "bot.py"))
        self.assertIn('{"id": "rrdesk", "ic": "tickets", "tk": "rrdesk"}', bot)
        self.assertIn('"rrdesk": "طلبات سام"', bot)
        self.assertIn('"rrdesk": "Sam\'s requests"', bot)

    def test_committed_fixtures_have_no_personal_data(self):
        files = glob.glob(os.path.join(ROOT, "tests", "fixtures", "rrdesk", "**", "*.*"), recursive=True)
        self.assertTrue(files)
        for f in files:
            if f.endswith(".py"):
                continue
            t = read(f)
            self.assertEqual(study.pii_hits(t), [], f)
            self.assertNotRegex(t, r"(?<![0-9])[12][0-9]{9}(?![0-9])", f)
            self.assertNotRegex(t, r"[0-9]{17,20}", f)          # Discord ids
            self.assertNotIn("@gmail", t)
        doc = os.path.join(ROOT, "docs", "rrdesk", "history_study.md")
        if os.path.exists(doc):
            self.assertEqual(study.pii_hits(read(doc)), [])

    def test_raw_exports_are_ignored(self):
        self.assertIn(".rrdesk_study/", read(os.path.join(ROOT, ".gitignore")))

    def test_staff_wording_has_no_money(self):
        src = read(os.path.join(PKG, "texts.py"))
        self.assertNotIn("ر.س", src)
        self.assertNotIn("SAR", src)
        self.assertNotIn("ريال", src)

    def test_switch_defaults(self):
        src = read(os.path.join(PKG, "flow.py"))
        self.assertIn('SWITCH_DEFAULTS = {"translate": "1", "requests": "1", "ladder": "1", "warn_live": "0",', src)

    def test_claude_md_section(self):
        md = read(os.path.join(ROOT, "CLAUDE.md"))
        self.assertIn("## RR Desk «طلبات سام» — `rrdesk/`", md)
        self.assertIn("rrdesk/DEBUG.md", md)
        i = md.index("TRAP — `_directpay_known_rooms` must scan the archive categories too.")
        self.assertIn("rrdesk", md[i:i + 900])          # added to the archive-scan trap list

    def test_js_parses_is_part_of_the_routine(self):
        self.assertTrue(os.path.exists(os.path.join(PKG, "static", "rrdesk_tab.js")))


if __name__ == "__main__":
    unittest.main()
