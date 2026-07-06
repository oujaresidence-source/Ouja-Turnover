# -*- coding: utf-8 -*-
"""Contract guard for the /studio page — the same class of outage as DASHBOARD_HTML:
one bad JS token = dead page. Locks (1) every <script> block esprima-parses,
(2) NO backslashes anywhere in the page string, (3) every /api/studio/* endpoint
the page calls is actually registered, (4) page string is balanced."""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from studio import routes  # noqa: E402


class TestStudioPageContract(unittest.TestCase):
    def test_scripts_parse(self):
        try:
            import esprima
        except ImportError:
            self.skipTest("esprima not installed")
        blocks = re.findall(r"<script>(.*?)</script>", routes.STUDIO_PAGE_HTML, re.S)
        self.assertTrue(blocks, "no <script> block found")
        for js in blocks:
            esprima.parseScript(js)   # raises on the offending line/col

    def test_no_backslashes_in_page(self):
        self.assertNotIn(chr(92), routes.STUDIO_PAGE_HTML,
                         "backslash found — the non-raw triple-quote trap")

    def test_balanced(self):
        h = routes.STUDIO_PAGE_HTML
        self.assertEqual(h.count("{"), h.count("}"))
        self.assertEqual(h.count("("), h.count(")"))
        self.assertEqual(h.count("`") % 2, 0)

    def test_api_endpoints_registered(self):
        import inspect
        used = set(re.findall(r"/api/studio/[a-z-]+", routes.STUDIO_PAGE_HTML))
        self.assertTrue(used, "page calls no studio APIs?")
        reg = inspect.getsource(routes.register)
        registered = set(re.findall(r"/api/studio/[a-z-]+", reg))
        missing = used - registered
        self.assertFalse(missing, "page calls unregistered endpoints: %s" % missing)


if __name__ == "__main__":
    unittest.main()
