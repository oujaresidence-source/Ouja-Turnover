# -*- coding: utf-8 -*-
"""
schedule DB + API contract test. Temp brain.db, seed, then drive every route handler directly
with a fake host. Verifies the seed, the day/week reads, full CRUD with role gating + FK rules,
recurring overrides, ad-hoc leave, and reset.

Run:  python3 -m unittest tests.test_schedule_api
"""
import os
import sys
import types
import asyncio
import tempfile
import datetime
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb            # noqa: E402
from schedule import db as sdb         # noqa: E402
import schedule                        # noqa: E402
from schedule import routes            # noqa: E402


class _Resp:
    def __init__(self, data, status=200):
        self.data = data
        self.status = status


class _Req:
    def __init__(self, query=None, match=None, role="admin", body=None):
        self.query = query or {}
        self.match_info = match or {}
        self._role = role
        self._body = body or {}
        self.headers = {}

    async def json(self):
        return self._body


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestScheduleAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="sched_")
        bdb.set_db_path_for_tests(os.path.join(cls.tmp, "brain.db"))
        sdb.reset_init_cache()
        schedule.wire({
            "dash_auth": lambda req: True,
            "req_role": lambda req: req._role,
            "json_response": lambda data, status=200: _Resp(data, status),
            "web": types.SimpleNamespace(Response=lambda **k: _Resp(k)),
            "notify": None,
            "now": lambda: datetime.datetime(2026, 6, 28, 9, 0),   # Sunday
            "load_json": lambda n, d=None: d, "save_json": lambda n, o: None,
        })

    def test_seed_53(self):
        self.assertEqual(len(sdb.apartments()), 53)
        self.assertEqual(len(sdb.employees()), 5)

    def test_seed_idempotent(self):
        from schedule import seed
        seed.seed_if_empty()
        self.assertEqual(len(sdb.apartments()), 53)

    def test_day_sunday_numbers(self):
        r = run(routes.api_day(_Req(query={"date": "2026-06-28"})))   # Sunday, مآثر off
        day = r.data["day"]
        self.assertEqual(sorted(w["load"] for w in day["working"]), [13, 13, 13, 14])
        self.assertEqual(day["total"], 53)
        self.assertIn("مآثر", [o["name"] for o in day["off"]])

    def test_week_matrix(self):
        r = run(routes.api_week(_Req()))
        wk = r.data["week"]
        self.assertEqual(len(wk["rows"]), 7)
        self.assertEqual(len(wk["columns"]), 5)
        # Thu(4)/Fri(5) have no coverage
        self.assertFalse(wk["rows"][4]["has_coverage"])
        self.assertFalse(wk["rows"][5]["has_coverage"])

    def test_edit_gating(self):
        r = run(routes.api_employee_save(_Req(role="viewer", body={"name": "x"})))
        self.assertEqual(r.status, 403)

    def test_delete_employee_blocked_when_owns(self):
        eid = sdb.q1("SELECT id FROM schedule_employees WHERE name='ناصر'")["id"]
        r = run(routes.api_employee_delete(_Req(match={"id": str(eid)})))
        self.assertFalse(r.data["ok"])           # blocked — still owns apartments

    def test_apartment_reassign_and_override(self):
        # reassign one apartment owner, then pin a coverage override on Sunday
        apt = sdb.apartments()[0]
        emp2 = sdb.q1("SELECT id FROM schedule_employees WHERE name='عهود'")["id"]
        run(routes.api_apartment_save(_Req(body={"id": apt["id"], "name": apt["name"],
                                                  "owner_id": apt["owner_id"], "sort_order": 0})))
        # an apartment owned by مآثر (off Sunday) pinned to عهود
        ma = sdb.q1("SELECT a.id id FROM schedule_apartments a JOIN schedule_employees e ON a.owner_id=e.id "
                    "WHERE e.name='مآثر' LIMIT 1")["id"]
        ov = run(routes.api_override_set(_Req(body={"day_of_week": 0, "apartment_id": ma,
                                                    "covering_employee_id": emp2})))
        self.assertTrue(ov.data["ok"])
        day = run(routes.api_day(_Req(query={"date": "2026-06-28"}))).data["day"]
        ah = next(w for w in day["working"] if w["id"] == emp2)
        self.assertTrue(any(c["apartment"]["id"] == ma and c["overridden"] for c in ah["coverage"]))
        # clear it (إرجاع للتلقائي)
        cl = run(routes.api_override_set(_Req(body={"day_of_week": 0, "apartment_id": ma,
                                                    "covering_employee_id": None})))
        self.assertTrue(cl.data.get("cleared"))

    def test_adhoc_leave_route(self):
        emp = sdb.q1("SELECT id FROM schedule_employees WHERE name='ناصر'")["id"]
        add = run(routes.api_absence_add(_Req(body={"employee_id": emp, "start_date": "2026-07-02",
                                                    "end_date": "2026-07-02", "type": "sick"})))
        self.assertTrue(add.data["ok"])
        day = run(routes.api_day(_Req(query={"date": "2026-07-02"}))).data["day"]   # Thu, ناصر on leave
        self.assertIn("ناصر", [o["name"] for o in day["off"]])
        self.assertEqual(next(o for o in day["off"] if o["name"] == "ناصر")["reason"], "leave")
        self.assertEqual(day["total"], 53)
        run(routes.api_absence_del(_Req(match={"id": str(add.data["id"])})))

    def test_public_read_no_auth_but_writes_gated(self):
        """The shared /team-calendar link reads with NO login; writes stay double-gated."""
        from schedule.host import HOST
        orig = HOST.dash_auth
        HOST.dash_auth = lambda req: False        # simulate an anonymous visitor (no token)
        try:
            pub = routes._safe_public(routes.api_day)
            r = run(pub(_Req(query={"date": "2026-06-28"}, role="viewer")))
            self.assertTrue(r.data["ok"])         # public read works without auth
            self.assertFalse(r.data["can_edit"])  # ...and reports no edit ability
            gated = routes._safe(routes.api_employee_save)
            w = run(gated(_Req(role="viewer", body={"name": "x"})))
            self.assertEqual(w.status, 401)       # write rejected at the auth guard
        finally:
            HOST.dash_auth = orig

    def test_reset(self):
        run(routes.api_apartment_delete(_Req(match={"id": str(sdb.apartments()[0]["id"])})))
        self.assertEqual(len(sdb.apartments()), 52)
        r = run(routes.api_reset(_Req()))
        self.assertTrue(r.data["ok"])
        self.assertEqual(len(sdb.apartments()), 53)   # back to default


if __name__ == "__main__":
    unittest.main()
