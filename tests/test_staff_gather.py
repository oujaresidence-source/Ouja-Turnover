# -*- coding: utf-8 -*-
"""staff.gather: reads the bridges, normalises them, and survives any one of them failing."""

import unittest

import staff
from staff import gather as G
from tests.test_staff_engine import _day


def _boom():
    raise RuntimeError("store down")


def _wire(**over):
    caps = {
        "schedule_day": lambda d: dict(_day(), date=d),
        "today_snapshot": lambda: ({"date": "2026-11-17", "arrivals": [], "departures": [],
                                    "empty": []}, 1000.0),
        "listing_names": lambda: {"1012": "Ouja | 12B"},
        "catalog_units": lambda: [{"id": 1013, "name": "Ouja | A3"}],
        "tickets": lambda: [{"id": "t1", "lid": "1012", "status": "open", "priority": "med",
                             "title": "x", "due_date": None, "vendor_phone": "0500000000"},
                            {"id": "t2", "lid": 1013, "status": "fixed"}],
        "promises": lambda: [{"id": "p1"}],
        "cleaning_reports": lambda: [
            {"date": "2026-11-17", "listing_id": "1012", "status": "approved",
             "apartment_name": "Ouja | 12B"},
            {"date": "2026-11-16", "listing_id": 1013, "status": "approved"}],
        "route_status": lambda: {"1013|2026-11-17": {"lid": "1013", "action": "started"},
                                 "1013|2026-11-16": {"lid": 1013, "action": "done"}},
        "oncall_state": lambda: {"now": None, "tonight": {"slots": [
            {"employee": "خالد", "from": "22:00", "to": "02:00", "source": "auto"}]}},
        "pending_replies": lambda: 2,
        "open_escalations": lambda: 1,
    }
    caps.update(over)
    staff.wire(caps)


class Gather(unittest.TestCase):
    def test_normalises_everything(self):
        _wire()
        g = G.gather("2026-11-17", clock=lambda: 1000.0 + 300)
        self.assertEqual(g["day"]["date"], "2026-11-17")
        self.assertEqual(len(g["week_days"]), 7)
        self.assertEqual(g["week_days"][6]["date"], "2026-11-23")
        self.assertEqual(g["snap_age_min"], 5)
        self.assertEqual(g["name_to_lid"], {"Ouja | 12B": 1012, "Ouja | A3": 1013})
        self.assertEqual([t["id"] for t in g["tickets"]], ["t1"])         # fixed dropped
        self.assertEqual(g["tickets"][0]["lid"], 1012)                     # "1012" -> 1012
        self.assertNotIn("vendor_phone", g["tickets"][0])                  # only what is shown
        self.assertEqual(g["cleaning"], {1012: {"report": "approved"}, 1013: {"action": "started"}})
        self.assertEqual(len(g["reviews"]), 1)
        self.assertEqual(g["oncall"]["tonight"], [{"employee": "خالد", "from": "22:00", "to": "02:00"}])
        self.assertEqual((g["replies"], g["escalations"]), (2, 1))

    def test_stale_snapshot_is_ignored(self):
        _wire(today_snapshot=lambda: ({"date": "2026-11-16"}, 1000.0))
        g = G.gather("2026-11-17", clock=lambda: 1000.0)
        self.assertNotIn("snap", g)

    def test_one_broken_store_does_not_blank_the_rest(self):
        _wire(tickets=_boom, schedule_day=lambda d: _boom())
        g = G.gather("2026-11-17", clock=lambda: 1000.0)
        self.assertNotIn("tickets", g)
        self.assertNotIn("day", g)
        self.assertIn("cleaning", g)
        self.assertIn("snap", g)

    def test_missing_optional_bridges(self):
        _wire(schedule_day=None, oncall_state=None)
        g = G.gather("2026-11-17", clock=lambda: 1000.0)
        self.assertNotIn("day", g)
        self.assertNotIn("oncall", g)


if __name__ == "__main__":
    unittest.main()
