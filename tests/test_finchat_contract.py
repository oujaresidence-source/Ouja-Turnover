# -*- coding: utf-8 -*-
"""Guards the finchat API↔erp.js contract: the SPA must call the real endpoints and read
keys the API actually returns (the [object Object] trap class — see CLAUDE.md)."""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


class TestFinchatContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = _read("finance", "static", "erp.js")
        cls.routes_py = _read("finchat", "routes.py")
        cls.answer_py = _read("finchat", "answer.py")

    def test_js_uses_every_finchat_endpoint(self):
        for ep in ("/erp/api/finchat/ask", "/erp/api/finchat/history",
                   "/erp/api/finchat/escalate", "/erp/api/finchat/inbox",
                   "/erp/api/finchat/inbox/answer", "/erp/api/finchat/kb",
                   "/erp/api/finchat/kb/save", "/erp/api/finchat/kb/toggle",
                   "/erp/api/finchat/kb/delete"):
            self.assertIn(ep, self.js, ep)

    def test_endpoints_js_calls_are_registered(self):
        """Every /erp/api/finchat/* path referenced by the SPA exists in routes.register."""
        called = set(re.findall(r"['\"](/erp/api/finchat/[a-z/\-]+)['\"]", self.js))
        registered = set(re.findall(r"['\"](/erp/api/finchat/[a-z/\-]+)['\"]", self.routes_py))
        self.assertTrue(called)
        self.assertEqual(called - registered, set(),
                         "SPA calls endpoints the API never registered")

    def test_ask_reply_keys(self):
        # API returns these (answer.py builds the dict; routes passes it through)
        for key in ('"ok"', '"answer"', '"links"', '"model"', '"confidence"',
                    '"esc_offer"', '"msg_id"'):
            self.assertIn(key, self.answer_py, key)
        # SPA reads them
        for expr in ("r.answer", "r.links", "r.esc_offer"):
            self.assertIn(expr, self.js, expr)

    def test_history_and_admin_reply_keys(self):
        for key in ('"msgs"', '"items"', '"open_count"', '"count"', '"esc_id"'):
            self.assertIn(key, self.routes_py, key)
        self.assertIn("r.msgs", self.js)

    def test_error_bodies_carry_arabic_message(self):
        """daily_cap / api_error / already_answered must ship message_ar for the UI."""
        self.assertGreaterEqual(self.answer_py.count("message_ar"), 2)
        self.assertIn("message_ar", self.routes_py)
        self.assertIn("message_ar", self.js)

    def test_i18n_keys_exist_in_both_langs(self):
        """Every t('fc_*')/t('as_*') the JS reads must exist in BOTH T.ar and T.en
        (a miss renders the literal 'undefined' — Trap 2 class)."""
        used = set(re.findall(r"t\('((?:fc|as|ws_assist)[a-z_]*)'\)", self.js))
        self.assertTrue(used)
        m = re.search(r"ar:\s*\{(.*?)\n\s*\},\s*\n\s*en:\s*\{(.*?)\n\s*\}\s*\n\s*\};",
                      self.js, re.S)
        self.assertIsNotNone(m, "could not locate T.ar/T.en blocks")
        ar, en = m.group(1), m.group(2)
        for k in sorted(used):
            self.assertIsNotNone(re.search(r"\b%s\s*:" % re.escape(k), ar), "T.ar missing " + k)
            self.assertIsNotNone(re.search(r"\b%s\s*:" % re.escape(k), en), "T.en missing " + k)


if __name__ == "__main__":
    unittest.main()
