# -*- coding: utf-8 -*-
"""
«مركز الالتزام» is a showcase, not a window.

    it never reads the DB or calls a manager/inspector endpoint
    it carries no unit count, unit name, owner, price list or score of ours
    every screen says it is a demo
    the embedded JS parses and the file has zero backslashes

Run: python3 -m unittest tests.test_mot_center
"""
import os
import pathlib
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mot import center_page, routes  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = (ROOT / "mot" / "center_page.py").read_text(encoding="utf-8")
HTML = center_page.HTML


class TestNoPrivateData(unittest.TestCase):
    def test_no_api_calls_at_all(self):
        for needle in ("/api/mot", "/api/mot-t", "/api/mot-c", "fetch(", "XMLHttpRequest"):
            self.assertNotIn(needle, HTML, needle)

    def test_module_never_imports_db_or_host(self):
        self.assertNotIn("from . import db", SRC)
        self.assertNotIn("import db", SRC.replace("from . import catalogue", ""))
        self.assertNotIn("HOST", SRC)
        self.assertNotIn("_ls_get", SRC)

    def test_demo_label_everywhere(self):
        self.assertGreaterEqual(HTML.count("نموذج"), 6)
        self.assertIn("نموذج توضيحي", HTML)
        self.assertIn("noindex", HTML)

    def test_no_real_unit_shapes(self):
        # our real names look like "Ouja | 203 حطين"; the demo never uses that shape
        self.assertNotRegex(HTML, r"Ouja \| [0-9]")
        self.assertNotIn("Ouja |", HTML)


class TestIntegrity(unittest.TestCase):
    def test_zero_backslashes_outside_docstring(self):
        body = SRC.split('"""', 2)[2]
        self.assertNotIn(chr(92), body)

    def test_js_parses(self):
        try:
            import esprima
        except ImportError:
            self.skipTest("esprima not installed")
        for js in re.findall(r"<script>(.*?)</script>", HTML, re.S):
            esprima.parseScript(js)

    def test_route_is_public_and_registered(self):
        src = routes.register.__code__.co_consts
        self.assertIn("/compliance-center", src)
        import inspect
        reg = inspect.getsource(routes.register)
        self.assertIn('g("/compliance-center", handle_center_page)', reg)
        self.assertNotIn('_safe(handle_center_page)', reg)

    def test_report_embedded(self):
        self.assertIn("srcdoc=", HTML)
        self.assertIn("سجل مطابقة معايير وزارة السياحة", HTML)


if __name__ == "__main__":
    unittest.main()
