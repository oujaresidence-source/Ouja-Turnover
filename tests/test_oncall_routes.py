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

    def test_rebuild_offered_only_before_the_first_check(self):
        self.publish_sunday()
        self.assertTrue(routes.state_payload(at(SUN, 16, 0))["tonight"]["rebuildable"])
        self.walk(at(SUN, 17, 0), at(SUN, 17, 1))
        self.assertFalse(routes.state_payload(at(SUN, 17, 2))["tonight"]["rebuildable"])
        self.assertIn("/api/oncall/rebuild", inspect.getsource(routes.register_routes))

    def test_first_slot_setting(self):
        from oncall import db
        self.assertEqual(routes.state_payload(at(SUN, 12, 0))["settings"]["first_slot"], "عهود")
        ok, err = routes._save_settings({"first_slot": "فلان"}, "tester", at(SUN, 12, 0))
        self.assertFalse(ok)
        ok, _ = routes._save_settings({"first_slot": "نورة"}, "tester", at(SUN, 12, 0))
        self.assertTrue(ok)
        self.assertEqual(db.config_get("first_slot"), "نورة")
        ok, _ = routes._save_settings({"first_slot": ""}, "tester", at(SUN, 12, 0))
        self.assertTrue(ok)
        self.assertEqual(routes.state_payload(at(SUN, 12, 0))["settings"]["first_slot"], "")

    def test_settings_refuse_an_empty_roster(self):
        ok, err = routes._save_settings({"roster": []}, "tester", at(SUN, 12, 0))
        self.assertFalse(ok)
        ok, _ = routes._save_settings({"supervisor_did": "<@123>"}, "tester", at(SUN, 12, 0))
        self.assertTrue(ok)
        from oncall import db
        self.assertEqual(db.config_get("supervisor_did"), "123")


class HandlersNeverAccuse(Case):
    """Behaviour, not text search: drive every button/route path while a second miss is one
    judgement away, and prove ops_warnings never moves. Only the tick may accuse."""

    def test_no_handler_creates_a_warning(self):
        from ops import db as odb
        from oncall import db
        slots = self.publish_sunday()
        first = slots[0]
        self.walk(at(SUN, 17, 0), at(SUN, 17, 10))             # miss #1 (alert only)
        self.walk(at(SUN, 17, 11), at(SUN, 17, 24))            # 17:15 sent, window over
        c = [x for x in db.checks_on(SUN.isoformat()) if x["due_at"][11:16] == "17:15"][0]
        before = odb.counts()["ops_warnings"]
        notify.answer_check_id(c["id"], first["employee_did"], at(SUN, 17, 26))
        notify.answer_check(c["dm_message_id"], first["employee_did"], at(SUN, 17, 26))
        notify.request_swap(first["id"], slots[1]["employee_did"], at(SUN, 17, 26))
        notify.resolve_press("nope", first["employee_did"], True, at(SUN, 17, 26))
        notify.rebuild_night(SUN.isoformat(), "اسيل", at(SUN, 17, 26))
        routes.state_payload(at(SUN, 17, 26))
        routes._save_settings({"supervisor_did": "1"}, "tester", at(SUN, 17, 26))
        self.assertEqual(odb.counts()["ops_warnings"], before)
        self.assertEqual(db.check(c["id"])["status"], "pending")   # still the tick's to judge


class Invariant(unittest.TestCase):
    """The system accuses, humans only forgive — same rule as ops/."""

    def test_no_route_can_reach_a_warning(self):
        self.assertNotIn("issue_warning", inspect.getsource(routes))

    def test_one_warning_call_site(self):
        self.assertEqual(inspect.getsource(notify).count("odb.issue_warning("), 1)


if __name__ == "__main__":
    unittest.main()
