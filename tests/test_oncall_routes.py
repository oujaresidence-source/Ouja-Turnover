# -*- coding: utf-8 -*-
"""
«المناوبة» dashboard data + the accountability invariant.

Run: python3 -m unittest tests.test_oncall_routes
"""

import inspect
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from oncall import notify, routes                   # noqa: E402
from tests.test_oncall_flow import Case, SUN, at     # noqa: E402


class State(Case):
    def test_state_before_and_during_a_night(self):
        s = routes.state_payload(at(SUN, 12, 0))
        self.assertEqual(s["tonight"]["status"], "none")
        self.publish_sunday()
        s = routes.state_payload(at(SUN, 17, 20))
        self.assertTrue(s["in_window"])
        self.assertEqual(s["tonight"]["status"], "published")
        self.assertEqual(len(s["tonight"]["slots"]), 4)
        self.assertEqual(s["now"]["employee"], s["tonight"]["slots"][0]["employee"])
        self.assertEqual(s["now"]["next_check"], "5:30")
        self.assertEqual(s["settings"]["supervisor_name"], "اسيل")

    def test_settings_refuse_an_empty_roster(self):
        ok, err = routes._save_settings({"roster": []}, "tester", at(SUN, 12, 0))
        self.assertFalse(ok)
        ok, _ = routes._save_settings({"supervisor_did": "<@123>"}, "tester", at(SUN, 12, 0))
        self.assertTrue(ok)
        from oncall import db
        self.assertEqual(db.config_get("supervisor_did"), "123")


class Invariant(unittest.TestCase):
    """The system accuses, humans only forgive — same rule as ops/."""

    def test_no_route_can_reach_a_warning(self):
        self.assertNotIn("issue_warning", inspect.getsource(routes))

    def test_one_warning_call_site(self):
        self.assertEqual(inspect.getsource(notify).count("odb.issue_warning("), 1)


if __name__ == "__main__":
    unittest.main()
