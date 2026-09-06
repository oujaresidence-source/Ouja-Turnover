# -*- coding: utf-8 -*-
"""
The inspector door can write results and photos and NOTHING else.

Reads the source of the two check_* cores, the shared photo core and the phone page, and
fails if they grow the words that would let a phone open, close, price, delete or mint.
Precedent: tests/test_wifi_lock.py::test_the_public_door_cannot_close_or_delete_anything.

Run: python3 -m unittest tests.test_mot_token_scope
"""
import inspect
import os
import pathlib
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mot import routes  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
FORBIDDEN_CALLS = ("open_round", "close_round", "abandon_round", "set_price", "mint_token",
                   "DELETE", "delete", "save_quote", "ticket_create", "onb_license_tasks",
                   "latest_closed_by_listing", "rounds_for(")


class TestInspectorDoorScope(unittest.TestCase):
    def test_check_cores_cannot_open_close_price_or_delete(self):
        for fn in (routes.core_check_get, routes.core_check_result, routes.core_photo,
                   routes._apply_result):
            src = inspect.getsource(fn)
            for word in FORBIDDEN_CALLS:
                self.assertNotIn(word, src, "%s can now %s" % (fn.__name__, word))

    def test_check_result_cannot_set_billed_to(self):
        src = inspect.getsource(routes.core_check_result)
        self.assertIn("allow_billed=False", src)

    def test_phone_page_never_calls_a_manager_endpoint(self):
        src = (ROOT / "mot" / "check_page.py").read_text(encoding="utf-8")
        for path in ("/api/mot/open", "/api/mot/close", "/api/mot/abandon", "/api/mot/price",
                     "/api/mot/prices", "/api/mot/token", "/api/mot/portfolio", "/api/mot/unit",
                     "/api/mot/result", "/api/mot/photo'", "/api/mot/report"):
            self.assertNotIn(path, src, "the phone page reaches %s" % path)
        self.assertIn("/api/mot-t/", src)
        self.assertIn("/api/mot/check-result", src)
        self.assertIn("/api/mot/check-photo", src)

    def test_token_reads_are_outside_the_gated_prefix(self):
        src = inspect.getsource(routes.register)
        self.assertIn('"/api/mot-t/{token}"', src)
        self.assertNotIn('"/api/mot/check-get', src)

    def test_pages_have_zero_backslashes_and_no_to_thread(self):
        for name in ("page.py", "check_page.py"):
            src = (ROOT / "mot" / name).read_text(encoding="utf-8")
            body = src.split('"""', 2)[2] if src.count('"""') >= 2 else src
            self.assertNotIn(chr(92), body, "%s contains a backslash" % name)
        for name in ("routes.py", "page.py", "check_page.py", "report.py", "photos.py"):
            src = (ROOT / "mot" / name).read_text(encoding="utf-8")
            self.assertNotIn("asyncio.to_thread", src, name)


if __name__ == "__main__":
    unittest.main()
