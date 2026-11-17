# -*- coding: utf-8 -*-
"""«عوجا فريق» routes: who sees what, and the page cannot die on a bad token."""

import json
import re
import unittest

import staff
from staff import routes, page
from tests.test_staff_engine import _day, _snap, NAMES


class _Req:
    def __init__(self, query=None, **who):
        self.query = query or {}
        self.who = who


def _wire(role="ops", employee="نورة", perms=(), manager=False):
    staff.wire({
        "req_role": lambda r: r.who.get("role", role),
        "actor": lambda r: r.who.get("name", "Nora"),
        "can": lambda r, tab, act: (tab, act) in set(r.who.get("perms", perms)),
        "employee_of": lambda r: r.who.get("employee", employee),
        "is_manager": lambda r: r.who.get("manager", manager),
        "has_targets": lambda: True,
    })


def _g():
    return {"day": _day(), "snap": _snap(), "tickets": [], "promises": [], "cleaning": {},
            "oncall": {"now": None, "tonight": []}, "name_to_lid": NAMES,
            "week_days": [_day()], "reviews": [{"lid": 1013, "name": "Ouja | A3",
                                                "status": "submitted_for_review"}],
            "replies": 3, "escalations": 0, "snap_age_min": 4}


def payload(req):
    return routes.build_payload(req, _g(), "2026-11-17", "2026-11-17T10:00:00")


class Identity(unittest.TestCase):
    def setUp(self):
        _wire()

    def test_linked_employee_gets_own_day(self):
        r = payload(_Req(role="ops", employee="نورة"))
        self.assertEqual(r["status"], "working")
        self.assertEqual(r["employee"], "نورة")
        self.assertEqual(sorted(a["lid"] for a in r["apartments"]), [1012, 1013, 1031])
        self.assertEqual(r["employees"], [])          # no picker for a normal employee

    def test_unlinked_sees_nothing(self):
        r = payload(_Req(role="viewer", employee=""))
        self.assertEqual(r["status"], "unlinked")
        self.assertNotIn("apartments", r)
        self.assertNotIn("tasks", r)

    def test_view_as_ignored_for_employee(self):
        r = payload(_Req({"as": "خالد"}, role="ops", employee="نورة"))
        self.assertEqual(r["employee"], "نورة")
        self.assertFalse(r["viewing_as"])

    def test_admin_can_view_as(self):
        r = payload(_Req({"as": "خالد"}, role="admin", employee=""))
        self.assertEqual(r["employee"], "خالد")
        self.assertTrue(r["viewing_as"])
        self.assertIn("سارة", r["employees"])

    def test_view_as_needs_a_real_employee(self):
        r = payload(_Req({"as": "أي أحد"}, role="admin", employee=""))
        self.assertEqual(r["status"], "pick")

    def test_manager_can_view_as(self):
        r = payload(_Req({"as": "سارة"}, role="ops", employee="", manager=True))
        self.assertEqual(r["employee"], "سارة")


class Supervisor(unittest.TestCase):
    def setUp(self):
        _wire()

    def test_plain_employee_has_no_supervisor_items(self):
        self.assertEqual(payload(_Req(role="ops", employee="نورة", perms=()))["supervisor"], [])

    def test_clean_center_writer_sees_reviews(self):
        r = payload(_Req(role="ops", employee="نورة", perms=[("clean_center", "write")]))
        kinds = [x["kind"] for x in r["supervisor"]]
        self.assertIn("review", kinds)
        self.assertIn("replies", kinds)
        for x in r["supervisor"]:
            self.assertTrue(x["href"].startswith("/dashboard#"))

    def test_perms_flags(self):
        r = payload(_Req(role="ops", employee="نورة", perms=[("tickets", "create"),
                                                             ("targets", "read")]))
        self.assertTrue(r["perms"]["ticket_create"])
        self.assertTrue(r["perms"]["targets"])
        self.assertFalse(r["perms"]["book"])


class Page(unittest.TestCase):
    def test_zero_backslashes(self):
        self.assertEqual(page.HTML.count(chr(92)), 0)

    def test_script_parses(self):
        try:
            import esprima
        except ImportError:
            self.skipTest("esprima not installed")
        for js in re.findall(r"<script>(.*?)</script>", page.HTML, re.S):
            esprima.parseScript(js)

    def test_brand_world(self):
        h = page.HTML
        self.assertIn("thmanyah-serif-display-black.v20260827a.woff2", h)
        self.assertIn("#F4EFE7", h)
        self.assertIn('dir="rtl"', h)
        self.assertNotIn("maximum-scale", h)        # never block pinch-zoom

    def test_manifest_is_its_own_app(self):
        m = json.loads(json.dumps(routes.MANIFEST, ensure_ascii=False))
        self.assertEqual(m["id"], "/team")
        self.assertEqual(m["start_url"], "/team")
        self.assertEqual(m["scope"], "/team")


if __name__ == "__main__":
    unittest.main()
