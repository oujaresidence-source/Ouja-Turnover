# -*- coding: utf-8 -*-
import unittest

from owner_report import live
from owner_report.model import build_cfg
from owner_report.validate import validate
from owner_report.tests.fixtures import valid_inp, valid_meta


class FakeReader:
    """Stands in for HostawayReader — returns synthetic normalized reservations."""
    def __init__(self, rows, avail):
        self._rows = rows
        self._avail = avail

    def reservations(self, lid, start, end):
        return list(self._rows), False

    def calendar_available(self, lid, start, end, mdefs):
        return dict(self._avail)


def _r(checkout, nights, revenue, channel="Airbnb", status="confirmed"):
    return {"checkout": checkout, "nights": nights, "revenue": revenue,
            "channel": channel, "lead_days": 5, "is_repeat": False, "status": status}


class TestMonthDefs(unittest.TestCase):
    def test_six_months_from_january(self):
        md = live.month_defs("2026-01-01", 6)
        self.assertEqual([m[2] for m in md],
                         ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"])

    def test_wraps_year(self):
        md = live.month_defs("2025-11-01", 3)
        self.assertEqual([m[2] for m in md], ["2025-11", "2025-12", "2026-01"])


class TestGatherAndAssemble(unittest.TestCase):
    def setUp(self):
        self.rows = [
            _r("2026-01-20", 4, 5000), _r("2026-02-18", 3, 4000),
            _r("2026-03-22", 5, 6000), _r("2026-04-15", 4, 5200),
            _r("2026-05-19", 3, 3800), _r("2026-06-21", 4, 4600),
            _r("2026-02-25", 2, 2000, status="cancelled"),  # excluded
        ]
        self.avail = {f"2026-{m:02d}": d for m, d in
                      [(1, 31), (2, 28), (3, 31), (4, 30), (5, 31), (6, 30)]}
        self.reader = FakeReader(self.rows, self.avail)

    def test_gather_builds_six_months_excluding_cancelled(self):
        ha = live.gather_hostaway("101", "2026-01-01", "2026-06-30", 6, "net", reader=self.reader)
        self.assertEqual(len(ha["months"]), 6)
        self.assertEqual(ha["reservation_revenue_total"], 5000 + 4000 + 6000 + 5200 + 3800 + 4600)
        # cancelled Feb row not counted
        feb = ha["months"][1]
        self.assertEqual(feb[3], 3)   # booked nights, cancelled excluded
        self.assertEqual(feb[4], 4000)

    def test_vat_inclusive_nets_down_in_gather(self):
        ha = live.gather_hostaway("101", "2026-01-01", "2026-06-30", 6, "inclusive", reader=self.reader)
        self.assertEqual(ha["months"][0][4], round(5000 / 1.15))

    def test_assemble_then_build_and_validate(self):
        ha = live.gather_hostaway("101", "2026-01-01", "2026-06-30", 6, "net", reader=self.reader)
        # operator (O/M) parts from the reference template, minus the H sections
        op = valid_inp()
        for k in ("months", "channels", "booking_behaviour"):
            op.pop(k, None)
        op["costs"]["channel_fees"] = 1200
        inp = live.assemble_inputs(op, ha)
        cfg, man, disc = build_cfg(inp)
        self.assertEqual(len(cfg["MONTHS"]), 6)
        self.assertEqual(len(cfg["COMP_SET"]), 5)
        meta = valid_meta()
        meta["reservation_revenue_total"] = sum(m[4] for m in cfg["MONTHS"])
        meta["acknowledged"] = list(disc); meta["disclosures"] = list(disc)
        self.assertTrue(validate(cfg, meta).ok, msg=validate(cfg, meta).hard)


class TestRouteRegistration(unittest.TestCase):
    def test_register_adds_expected_routes(self):
        from owner_report import routes

        class FakeRouter:
            def __init__(self):
                self.gets, self.posts = [], []
            def add_get(self, path, h):
                self.gets.append(path)
            def add_post(self, path, h):
                self.posts.append(path)

        class FakeApp:
            def __init__(self):
                self.router = FakeRouter()

        app = FakeApp()
        routes.register(app)
        self.assertIn("/owner-report", app.router.gets)
        self.assertIn("/api/owner-report/units", app.router.gets)
        self.assertIn("/api/owner-report/export", app.router.posts)
        self.assertIn("/api/owner-report/reconcile", app.router.posts)


if __name__ == "__main__":
    unittest.main()
