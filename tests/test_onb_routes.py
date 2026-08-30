# -*- coding: utf-8 -*-
"""
The HTTP boundary of «ضم الوحدات».

The rules that matter are attacked where they are actually reachable: a blank reason, a third
operations person, an ops user pressing publish, a second publish trying to rewrite a frozen
snapshot. A business-rule refusal is a 200 with ok:false — it is an answer, not a failure.

Run: python3 -m unittest tests.test_onb_routes
"""

import inspect
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from onboarding import db, routes                                          # noqa: E402
from tests.test_onb_harness import (_Req, body, boot, make_ready,          # noqa: E402
                                    READY, run)


class RoutesCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rec = boot("onbroutes_")

    def mk(self, **over):
        f = dict(READY)
        f.update(over)
        r = body(run(routes.api_create(_Req(f))))
        self.assertTrue(r.get("ok"), r)
        return r["project"]


class TestCreate(RoutesCase):

    def test_15_a_blank_required_field_is_refused_with_a_field_map(self):
        for missing in ("client_name", "unit_name", "district"):
            f = dict(READY)
            f[missing] = "  "
            r = body(run(routes.api_create(_Req(f))))
            self.assertFalse(r["ok"])
            self.assertIn(missing, r.get("fields") or {})

    def test_16_the_ouja_prefix_is_forced_and_50_chars_is_the_ceiling(self):
        p = self.mk(unit_name="النرجس 4")
        self.assertTrue(p["unit_name"].startswith("Ouja |"))
        self.assertLessEqual(len(p["unit_name"]), 50)
        # an already-prefixed name is not double-prefixed
        p2 = self.mk(unit_name="Ouja | حطين 9")
        self.assertEqual(p2["unit_name"], "Ouja | حطين 9")
        # over the ceiling is refused, not silently truncated
        r = body(run(routes.api_create(_Req(dict(READY, unit_name="ا" * 60)))))
        self.assertFalse(r["ok"])
        self.assertIn("unit_name", r.get("fields") or {})

    def test_17_creating_seeds_63_unit_tasks_and_zero_company_tasks(self):
        p = self.mk()
        ts = db.tasks(p["id"])
        self.assertEqual(len(ts), 63)
        self.assertEqual([t for t in ts if t["stage"] == "ongoing"], [])


class TestAssignees(RoutesCase):

    def test_18_a_third_person_is_refused_and_the_first_two_get_distinct_tokens(self):
        p = self.mk()
        for eid in (1, 2):
            r = body(run(routes.api_assignee_add(_Req({"project_id": p["id"],
                                                       "employee_id": eid}))))
            self.assertTrue(r["ok"], r)
        r = body(run(routes.api_assignee_add(_Req({"project_id": p["id"], "employee_id": 3}))))
        self.assertFalse(r["ok"])
        self.assertIn("موظفين اثنين", r["error"])
        rows = db.assignees(p["id"])
        self.assertEqual(len(rows), 2, "a third row reached the database")
        toks = [a["access_token"] for a in rows]
        self.assertTrue(all(toks))
        self.assertEqual(len(set(toks)), 2, "two people shared one token")
        self.assertEqual(rows[0]["is_primary"], 1)

    def test_18b_removing_a_person_releases_the_tasks_they_held(self):
        p = self.mk()
        run(routes.api_assignee_add(_Req({"project_id": p["id"], "employee_id": 1})))
        t = db.tasks(p["id"])[0]
        run(routes.task_assign(_Req({"project_id": p["id"],
                                     "changes": [{"task_id": t["id"], "employee_id": 1}]})))
        self.assertIsNotNone(db.task(t["id"])["assignee_id"])
        run(routes.api_assignee_remove(_Req({"project_id": p["id"], "employee_id": 1})))
        self.assertIsNone(db.task(t["id"])["assignee_id"])


class TestTasks(RoutesCase):

    def test_19_one_outsider_in_a_batch_refuses_the_WHOLE_batch(self):
        """All-or-nothing. A half-applied delegation is worse than a rejected one."""
        p = self.mk()
        run(routes.api_assignee_add(_Req({"project_id": p["id"], "employee_id": 1})))
        ts = db.tasks(p["id"])
        before = [(t["id"], t["assignee_id"]) for t in ts]
        r = body(run(routes.task_assign(_Req({
            "project_id": p["id"],
            "changes": [{"task_id": ts[0]["id"], "employee_id": 1},
                        {"task_id": ts[1]["id"], "employee_id": 3}],   # عهود is NOT on it
        }))))
        self.assertFalse(r["ok"])
        self.assertIn("عهود", r["error"])
        after = [(t["id"], t["assignee_id"]) for t in db.tasks(p["id"])]
        self.assertEqual(before, after, "a refused batch still wrote rows")

    def test_20_na_without_a_reason_is_refused_and_with_one_is_stamped(self):
        p = self.mk()
        t = db.tasks(p["id"])[0]
        for res in ("na", "blocked"):
            r = body(run(routes.api_task_resolve(_Req({"project_id": p["id"], "task_id": t["id"],
                                                       "resolution": res, "reason": "   "}))))
            self.assertFalse(r["ok"])
            self.assertIn("السبب", r["error"])
        r = body(run(routes.api_task_resolve(_Req({"project_id": p["id"], "task_id": t["id"],
                                                   "resolution": "na", "reason": "الوحدة جاهزة"}))))
        self.assertTrue(r["ok"], r)
        row = db.task(t["id"])
        self.assertEqual(row["resolution"], "na")
        self.assertEqual(row["reason"], "الوحدة جاهزة")
        self.assertEqual(row["resolved_by"], "فيصل")
        self.assertTrue(row["resolved_at"])


class TestPublish(RoutesCase):

    def test_21a_ops_may_not_publish(self):
        p = self.mk()
        r = run(routes.publish(_Req({"id": p["id"]}, role="ops")))
        self.assertEqual(r["status"], 403)
        self.assertFalse(r["data"]["ok"])

    def test_21b_admin_with_blockers_gets_the_named_list_and_nothing_moves(self):
        p = self.mk()
        r = run(routes.publish(_Req({"id": p["id"]})))
        self.assertEqual(r["status"], 200)
        self.assertFalse(r["data"]["ok"])
        self.assertTrue(len(r["data"]["blockers"]) > 0)
        for b in r["data"]["blockers"]:
            self.assertTrue(b.get("ar"))
            self.assertTrue(b.get("field") or b.get("stage"), "a blocker with nowhere to jump")
        self.assertEqual(db.project(p["id"])["status"], "active")
        self.assertIsNone(db.handover(p["id"]))

    def test_21c_admin_with_a_clean_gate_publishes_and_freezes_one_snapshot(self):
        p = self.mk()
        make_ready(routes, p["id"])
        r = body(run(routes.publish(_Req({"id": p["id"]}))))
        self.assertTrue(r["ok"], r)
        row = db.project(p["id"])
        self.assertEqual(row["status"], "published")
        self.assertEqual(row["published_by"], "فيصل")
        self.assertTrue(row["published_at"])
        self.assertEqual(db.counts()["handovers"],
                         len([x for x in db.projects() if x["status"] == "published"]))
        self.assertTrue(db.handover(p["id"]))

    def test_22_publishing_twice_never_rewrites_the_snapshot(self):
        p = self.mk()
        make_ready(routes, p["id"])
        self.assertTrue(body(run(routes.publish(_Req({"id": p["id"]}))))["ok"])
        frozen = json.dumps(db.handover(p["id"])["snapshot"], ensure_ascii=False, sort_keys=True)
        r = body(run(routes.publish(_Req({"id": p["id"]}))))
        self.assertFalse(r["ok"])
        again = json.dumps(db.handover(p["id"])["snapshot"], ensure_ascii=False, sort_keys=True)
        self.assertEqual(frozen, again, "the second publish rewrote history")

    def test_23_a_published_project_refuses_every_edit(self):
        p = self.mk()
        make_ready(routes, p["id"])
        run(routes.publish(_Req({"id": p["id"]})))
        r = body(run(routes.api_update(_Req({"id": p["id"], "house_rules": "تعديل"}))))
        self.assertFalse(r["ok"])
        self.assertIn("منشورة", r["error"])
        t = db.tasks(p["id"])[0]
        r2 = body(run(routes.api_task_resolve(_Req({"project_id": p["id"], "task_id": t["id"],
                                                    "resolution": "done"}))))
        self.assertFalse(r2["ok"])
        r3 = body(run(routes.api_assignee_add(_Req({"project_id": p["id"], "employee_id": 3}))))
        self.assertFalse(r3["ok"])

    def test_24_no_publish_path_can_ever_skip_the_gate(self):
        """Structural, in the spirit of tests/test_decor_flow.py: an edit that adds a second
        publish route without the gate fails HERE, not in production."""
        src = inspect.getsource(routes.publish)
        self.assertIn("readiness", src,
                      "routes.publish no longer consults the readiness gate")
        self.assertIn("can_publish", src)


if __name__ == "__main__":
    unittest.main()
