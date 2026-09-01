# -*- coding: utf-8 -*-
"""digest.links — a dead link never ships. Offline via FakeHttp."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "digest"))

from digest import links
from _fake_http import FakeHttp


class Verify(unittest.TestCase):
    def setUp(self):
        self.http = FakeHttp(pages={
            "https://ok.example/a": (200, "text/html", "<html>a</html>"),
            "https://ok.example/pdf": (200, "application/pdf", b"%PDF"),
            "https://ok.example/gone": (404, "text/html", ""),
            "https://ok.example/new": (200, "text/html", "<html>new</html>"),
            "https://ok.example/nohead": (200, "text/html", "<html>x</html>"),
        }, redirects={"https://ok.example/old": "https://ok.example/new"},
           head_status={"https://ok.example/nohead": 405})

    def test_keeps_200_html_only(self):
        got = links.verify(["https://ok.example/a", "https://ok.example/pdf", "https://ok.example/gone"], self.http)
        self.assertEqual(got, {"https://ok.example/a": "https://ok.example/a"})

    def test_stores_the_final_url_after_redirect(self):
        got = links.verify(["https://ok.example/old"], self.http)
        self.assertEqual(got, {"https://ok.example/old": "https://ok.example/new"})

    def test_http_scheme_is_refused_before_any_call(self):
        got = links.verify(["http://ok.example/a"], self.http)
        self.assertEqual(got, {})
        self.assertEqual(self.http.calls, [])

    def test_head_405_is_reported_as_dead_by_the_fake_but_live_falls_back(self):
        # FakeHttp models a CDN that refuses HEAD; net_live's real head() falls back to
        # a ranged GET (covered by its own code path), the verifier just trusts head().
        self.assertEqual(links.verify(["https://ok.example/nohead"], self.http), {})

    def test_exception_from_http_is_a_dead_link_not_a_crash(self):
        class Boom(FakeHttp):
            def head(self, url, timeout=12):
                raise RuntimeError("dns")
        self.assertEqual(links.verify(["https://ok.example/a"], Boom()), {})

    def test_duplicates_checked_once(self):
        links.verify(["https://ok.example/a", "https://ok.example/a"], self.http)
        self.assertEqual(len([c for c in self.http.calls if c[0] == "head"]), 1)


class Provenance(unittest.TestCase):
    def test_constructed_url_is_refused(self):
        seen = {"https://riyadh.platinumlist.net/event/x"}
        self.assertTrue(links.provenance_ok("https://riyadh.platinumlist.net/event/x", seen))
        self.assertFalse(links.provenance_ok("https://riyadh.platinumlist.net/event/y", seen))
        self.assertFalse(links.provenance_ok("", seen))

    def test_same_origin(self):
        self.assertTrue(links.same_origin("https://a.example/x", "https://A.example/y?z"))
        self.assertFalse(links.same_origin("https://a.example/x", "https://cdn.a.example/y"))
        self.assertFalse(links.same_origin("https://a.example/x", "http://a.example/x"))


if __name__ == "__main__":
    unittest.main()
