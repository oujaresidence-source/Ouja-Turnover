# -*- coding: utf-8 -*-
"""
roster API contract test. Wires a fake host (auth + json + listings) onto a temp brain.db,
seeds, then drives every NOW route handler directly and asserts the contract + role gating +
idempotency. No live network, no real aiohttp server.

Run:  python3 -m unittest tests.test_roster_api
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
from roster import db as rdb           # noqa: E402
import roster                          # noqa: E402
from roster import routes              # noqa: E402
from roster.host import HOST           # noqa: E402


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


def _wire(tmp):
    bdb.set_db_path_for_tests(os.path.join(tmp, "brain.db"))
    rdb.reset_init_cache()
    roster.wire({
        "dash_auth": lambda req: True,
        "req_role": lambda req: req._role,
        "json_response": lambda data, status=200: _Resp(data, status),
        "web": types.SimpleNamespace(Response=lambda **k: _Resp(k)),
        "get_listings_map": lambda: {},
        "ls_get": lambda: {"listings": {}},
        "notify": None,
        "now": lambda: datetime.datetime(2026, 6, 28, 9, 0),  # a Sunday
        "load_json": lambda name, default=None: default,
        "save_json": lambda name, obj: None,
    })


def run(coro):
    # Fresh loop per call: a prior async test in the discover run may have closed the
    # thread's default loop, so get_event_loop() would raise.
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestRosterAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="roster_api_")
        _wire(cls.tmp)

    def test_get_roster_zero_gaps(self):
        r = run(routes.api_roster(_Req()))
        self.assertTrue(r.data["ok"])
        self.assertEqual(r.data["roster"]["status"]["gaps"], 0)
        self.assertTrue(r.data["can_write"])

    def test_get_roster_bad_date(self):
        r = run(routes.api_roster(_Req(query={"date": "nonsense"})))
        self.assertFalse(r.data["ok"])

    def test_absence_flow_and_idempotency(self):
        emp = rdb.q1("SELECT id FROM roster_employees WHERE role='employee' LIMIT 1")["id"]
        day = "2026-07-10"
        add = run(routes.api_absence_add(_Req(body={"employee_id": emp, "start_date": day,
                                                    "end_date": day, "type": "sick"})))
        self.assertTrue(add.data["ok"])
        aid = add.data["id"]
        # the absent employee shows up in the roster for that date
        rr = run(routes.api_roster(_Req(query={"date": day})))
        self.assertIn(emp, [a["id"] for a in rr.data["roster"]["absent"]])
        self.assertEqual(rr.data["roster"]["status"]["gaps"], 0)
        # duplicate overlapping absence is rejected
        dup = run(routes.api_absence_add(_Req(body={"employee_id": emp, "start_date": day,
                                                    "end_date": day, "type": "sick"})))
        self.assertFalse(dup.data["ok"])
        # delete is idempotent
        d1 = run(routes.api_absence_del(_Req(match={"id": str(aid)})))
        self.assertEqual(d1.data["deleted"], 1)
        d2 = run(routes.api_absence_del(_Req(match={"id": str(aid)})))
        self.assertEqual(d2.data["deleted"], 0)

    def test_absence_role_gating(self):
        emp = rdb.q1("SELECT id FROM roster_employees LIMIT 1")["id"]
        r = run(routes.api_absence_add(_Req(role="viewer",
                                            body={"employee_id": emp, "type": "sick"})))
        self.assertEqual(r.status, 403)

    def test_properties_and_owner_change(self):
        r = run(routes.api_properties(_Req()))
        self.assertTrue(r.data["ok"])
        self.assertEqual(len(r.data["properties"]), 54)
        pid = r.data["properties"][0]["id"]
        emp = rdb.q1("SELECT id FROM roster_employees WHERE name_ar='عهود'")["id"]
        chg = run(routes.api_property_owner(_Req(match={"id": str(pid)}, body={"owner_id": emp})))
        self.assertTrue(chg.data["ok"])
        self.assertEqual(rdb.q1("SELECT primary_owner_id o FROM roster_properties WHERE id=?", (pid,))["o"], emp)

    def test_owner_change_forbidden_for_viewer(self):
        r = run(routes.api_property_owner(_Req(role="viewer", match={"id": "1"}, body={"owner_id": 1})))
        self.assertEqual(r.status, 403)

    def test_override_locks_and_persists(self):
        day = "2026-07-15"
        prop = rdb.q1("SELECT id, primary_owner_id FROM roster_properties WHERE primary_owner_id IS NOT NULL LIMIT 1")
        other = rdb.q1("SELECT id FROM roster_employees WHERE id<>? AND role='employee' LIMIT 1",
                       (prop["primary_owner_id"],))["id"]
        r = run(routes.api_override(_Req(body={"date": day, "property": prop["id"],
                                               "to": other, "reason": "اختبار"})))
        self.assertTrue(r.data["ok"])
        locks = rdb.locks_on(day)
        self.assertEqual(len(locks), 1)
        self.assertEqual(locks[0]["responsible_id"], other)
        # the locked unit appears under the override target in the board
        board = {b["id"]: b for b in r.data["roster"]["board"]}
        covered_ids = [c["id"] for c in board[other]["covered"]] + [p["id"] for p in board[other]["primary"]]
        self.assertIn(prop["id"], covered_ids)

    def test_override_requires_reason(self):
        r = run(routes.api_override(_Req(body={"date": "2026-07-16", "property": 1, "to": 1})))
        self.assertFalse(r.data["ok"])

    def test_sync_runs(self):
        r = run(routes.api_sync(_Req()))
        self.assertTrue(r.data["ok"])
        self.assertIn("report", r.data)


if __name__ == "__main__":
    unittest.main()
