# -*- coding: utf-8 -*-
"""
No request may compute. Three outages came from one shape: a screen asked for a
month, the month meant years of Hostaway history, and Railway's proxy gave up
before the app did — "Application failed to respond" on a service that was
merely busy.

Run: python3 -m unittest tests.test_monthly_nonblocking
"""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monthly import collect                              # noqa: E402


class NoRequestComputesTest(unittest.TestCase):
    def setUp(self):
        collect._CACHE.clear()
        collect._JOBS.clear()
        self._real = collect.month_state

    def tearDown(self):
        collect.month_state = self._real
        collect._CACHE.clear()
        collect._JOBS.clear()

    def test_units_report_returns_none_on_a_cold_month_instead_of_computing(self):
        called = []
        collect.month_state = lambda *a, **k: called.append(1)
        self.assertIsNone(collect.units_report("2026-10"))
        self.assertEqual(called, [], "units_report computed inside a request")

    def test_ensure_month_returns_immediately(self):
        def slow(*_a, **_k):
            time.sleep(1.5)
            return {"at": collect._now_ts(), "unit_meta": {}}
        collect.month_state = slow
        t0 = time.time()
        state = collect.ensure_month("2026-10")
        self.assertLess(time.time() - t0, 0.5, "ensure_month blocked the caller")
        self.assertEqual(state, "running")

    def test_a_second_call_does_not_start_a_second_job(self):
        starts = []

        def slow(*_a, **_k):
            starts.append(1)
            time.sleep(0.6)
            return {"at": collect._now_ts(), "unit_meta": {}}

        collect.month_state = slow
        collect.ensure_month("2026-10")
        collect.ensure_month("2026-10")
        collect.ensure_month("2026-10")
        time.sleep(1.0)
        self.assertEqual(len(starts), 1, "duplicate background jobs for one month")

    def test_a_finished_job_reports_ready(self):
        collect.month_state = lambda *a, **k: collect._CACHE.__setitem__(
            "2026-10", {"at": collect._now_ts(), "unit_meta": {}})
        collect.ensure_month("2026-10")
        time.sleep(0.4)
        self.assertEqual(collect.month_status("2026-10")["state"], "ready")

    def test_a_failing_job_reports_the_error_and_does_not_raise(self):
        def boom(*_a, **_k):
            raise RuntimeError("hostaway down")
        collect.month_state = boom
        collect.ensure_month("2026-10")
        time.sleep(0.4)
        st = collect.month_status("2026-10")
        self.assertEqual(st["state"], "error")
        self.assertIn("hostaway down", st["error"])

    def test_a_failed_month_can_be_retried(self):
        def boom(*_a, **_k):
            raise RuntimeError("down")
        collect.month_state = boom
        collect.ensure_month("2026-10")
        time.sleep(0.3)
        self.assertEqual(collect.ensure_month("2026-10"), "running")

    def test_an_unstarted_month_is_cold_not_an_error(self):
        self.assertEqual(collect.month_status("2027-05")["state"], "cold")


class GuestPathStillNeverComputesTest(unittest.TestCase):
    def setUp(self):
        collect._CACHE.clear()

    def test_price_one_cached_is_none_on_a_cold_month(self):
        self.assertIsNone(collect.price_one_cached(1, "2026-10"))


if __name__ == "__main__":
    unittest.main()
