# -*- coding: utf-8 -*-
"""
«رفع التقييم» — structure rules (G7), checked by reading the source, not by trusting it.

  * R2: no emoji in any button label (a Unicode-category scan, not a hand list)
  * never `import bot` (it would boot a second bot), never asyncio.to_thread (trap 6)
  * ZERO backslashes in reviewask/*.py (the house rule for every new package)
  * R8: no discount text in code — the owner's template is the only place it lives
  * R7: the only channel delete is _rv_delete_room, and only flow.sweep_closed calls it
  * the public /rv/<token> handler runs on the web pool (the web-lane rule)
  * no money words in the staff-facing texts

Run: python3 -m unittest tests.test_reviewask_structure
"""

import ast
import os
import re
import sys
import unicodedata
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
PKG = os.path.join(ROOT, "reviewask")

from reviewask import texts  # noqa: E402


def _py_files():
    return sorted(os.path.join(PKG, f) for f in os.listdir(PKG) if f.endswith(".py"))


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def _is_emoji_char(ch):
    cp = ord(ch)
    if unicodedata.category(ch) in ("So", "Sk", "Cs", "Co"):
        return True
    if cp in (0x200D, 0xFE0F, 0x20E3):                    # joiner, presentation selector, keycap
        return True
    return 0x1F000 <= cp <= 0x1FAFF or 0x2600 <= cp <= 0x27BF or 0x2B00 <= cp <= 0x2BFF


def _bot_rv_block():
    src = _read(os.path.join(ROOT, "bot.py"))
    start = src.index("# ==== «رفع التقييم» Review Push (reviewask/ package)")
    end = src.index("@tasks.loop(time=dt_time(hour=3, minute=0, tzinfo=TZ))", start)
    return src[start:end]


def _func_src(src, name):
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(src, node)
    raise AssertionError("%s not found" % name)


class TestButtons(unittest.TestCase):
    def test_the_scanner_catches_emoji(self):
        for bad in ("✅", "📱", "⭐", "🔴", "1️⃣", "↩"):
            self.assertTrue(any(_is_emoji_char(c) for c in bad), bad)
        for good in ("فتح واتساب", "أرسلت الرسالة", "قيّم", "رسالة Airbnb"):
            self.assertFalse(any(_is_emoji_char(c) for c in good), good)

    def test_no_emoji_in_any_button_label(self):
        self.assertTrue(texts.BUTTON_LABELS)
        for key, label in texts.BUTTON_LABELS.items():
            bad = [c for c in label if _is_emoji_char(c)]
            self.assertEqual(bad, [], "button %s carries %r" % (key, bad))

    def test_bot_buttons_take_their_labels_from_texts(self):
        block = _bot_rv_block()
        for m in re.finditer(r"discord\.ui\.Button\(label=([^,]+),", block):
            arg = m.group(1).strip()
            self.assertTrue("BUTTON_LABELS" in arg or arg.startswith("b[1]"), arg)
        for m in re.finditer(r"@discord\.ui\.button\(label=\"([^\"]*)\"", block):
            self.fail("decorated button with an inline label: %s" % m.group(1))


class TestPackageRules(unittest.TestCase):
    def test_never_imports_bot_and_never_to_thread(self):
        for p in _py_files():
            src = _read(p)
            self.assertIsNone(re.search(r"^\s*(import bot\b|from bot\b)", src, re.M), p)
            self.assertNotIn("to_thread(", src, p)

    def test_zero_backslashes(self):
        for p in _py_files():
            self.assertNotIn(chr(92), _read(p), p)

    def test_no_discount_in_code(self):
        for p in _py_files():
            src = _read(p)
            for bad in ("10%", "١٠٪", "10٪", "١٠%"):
                self.assertNotIn(bad, src, "%s hard-codes %s" % (p, bad))

    def test_no_money_words_in_staff_texts(self):
        src = _read(os.path.join(PKG, "texts.py"))
        doc = ast.get_docstring(ast.parse(src)) or ""
        src = src.replace(doc, "")                       # the docstring states the rule itself
        for bad in ("ر.س", "SAR", "ريال", "إيراد", "revenue"):
            self.assertNotIn(bad, src)

    def test_python39_syntax(self):
        for p in _py_files():
            src = _read(p)
            ast.parse(src, filename=p, feature_version=(3, 9))
            self.assertIsNone(re.search(r"^\s*match .+:$", src, re.M), p)


class TestDeletionIsFenced(unittest.TestCase):
    def test_delete_only_inside_sweep_closed(self):
        for p in _py_files():
            src = _read(p)
            self.assertNotIn(".delete(", src, p)
            if p.endswith("flow.py"):
                sweep = _func_src(src, "sweep_closed")
                self.assertIn('"delete_room"', sweep)
                self.assertEqual(src.count('"delete_room"'), 1, "delete_room used outside sweep_closed")
            elif not p.endswith("host.py"):
                self.assertNotIn("delete_room", src, p)

    def test_bot_side_has_one_channel_delete(self):
        block = _bot_rv_block()
        self.assertEqual(block.count(".delete("), 1)
        self.assertIn(".delete(", _func_src(_read(os.path.join(ROOT, "bot.py")), "_rv_delete_room"))
        self.assertEqual(block.count("_rv_delete_room"), 2)    # its def + the one wire entry

    def test_never_calls_archive_closed_channel(self):
        self.assertNotIn("archive_closed_channel", _bot_rv_block())
        for p in _py_files():
            self.assertNotIn("archive_closed_channel", _read(p), p)


class TestWebLane(unittest.TestCase):
    def test_public_link_runs_on_the_web_pool(self):
        src = _read(os.path.join(PKG, "routes.py"))
        body = _func_src(src, "handle_rv")
        self.assertIn("web_thread(", body)
        self.assertNotIn("to_thread(", body)

    def test_public_health_runs_on_the_web_pool(self):
        body = _func_src(_read(os.path.join(PKG, "routes.py")), "handle_health")
        self.assertIn("web_thread(", body)

    def test_every_api_handler_goes_through_web_thread(self):
        src = _read(os.path.join(PKG, "routes.py"))
        for name in re.findall(r"^async def (api_[a-z_]+)\(", src, re.M):
            body = _func_src(src, name)
            self.assertTrue("_run(" in body or "_need_admin" in body, name)


if __name__ == "__main__":
    unittest.main()
