# -*- coding: utf-8 -*-
"""
«أهدافي» must open in a second, not forty.

2026-11-15: the first employee to open the page got «…» and nothing else. Building his call
list read the server's secret from the database once PER GUEST; once the callable pool was
opened to every guest that was 8,000 connections per page load — instant on a laptop, over
40 seconds on the live volume. The page's cost must not grow with the number of guests.

Run: python3 -m unittest tests.test_targets_speed
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb                                 # noqa: E402
from targets import book, db, pay, routes, score            # noqa: E402
from tests.test_targets_flow import NORA, Case              # noqa: E402


class Connections(Case):
    def count(self, fn):
        real, n = bdb.connect, [0]

        def counting(*a, **kw):
            n[0] += 1
            return real(*a, **kw)
        bdb.connect = counting
        try:
            fn()
        finally:
            bdb.connect = real
        return n[0]

    def setUp(self):
        super().setUp()
        os.environ["TG_POOL_CHANNELS"] = "all"
        score.propose("2026-Q4", self.today())
        db.approve_targets("2026-Q4", "owner", "now")

    def test_the_call_list_does_not_open_the_database_per_guest(self):
        few = self.count(lambda: book.call_list(NORA, self.today(), limit=0))
        for i in range(60, 400):                              # 340 more past guests
            self.res("101", self.phone(i), "ضيف%d" % i, "2026-03-%02d" % (1 + i % 27), "2026-03-%02d" % (2 + i % 27))
        many = self.count(lambda: book.call_list(NORA, self.today(), limit=0))
        self.assertLess(many, 30)
        self.assertLessEqual(many, few + 5)                   # the same handful, however many guests

    def test_the_whole_page_is_a_handful_of_reads(self):
        for i in range(60, 400):
            self.res("101", self.phone(i), "ضيف%d" % i, "2026-03-%02d" % (1 + i % 27), "2026-03-%02d" % (2 + i % 27))
        pay._cache.update(v=None, sheets={})
        n = self.count(lambda: routes.me_payload(NORA, "2026-11", self.today()))
        self.assertLess(n, 120)

    def test_the_secret_is_the_same_one_every_time(self):
        a = book.token("0551234567")
        self.assertEqual(book.token("0551234567"), a)
        self.assertEqual(book._secret(), db.setting("holdout_secret"))


if __name__ == "__main__":
    unittest.main()
