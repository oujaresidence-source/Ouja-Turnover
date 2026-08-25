# -*- coding: utf-8 -*-
"""
Contract tests for the simplified "Apartments → who cleans" redesign (2026-06-30 spec).
New route handlers: api_apartment_owner (auto-save), api_sync (Hostaway-driven), and
api_remove_unlinked (clear pre-Hostaway leftovers). Isolated temp brain.db; each test
re-seeds for independence.

Run:  python3 -m unittest tests.test_schedule_redesign
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
from schedule import routes, seed      # noqa: E402
from schedule.host import HOST         # noqa: E402


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


class TestRedesign(unittest.TestCase):
    LISTINGS = [
        {"id": 1001, "name": "NRJS 103", "active": True, "oujact": True},
        {"id": 1002, "name": "MLQ 1", "active": True, "oujact": True},
        {"id": 1003, "name": "A5 MLQ", "active": True, "oujact": False},
    ]

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="sched_redesign_")
        bdb.set_db_path_for_tests(os.path.join(cls.tmp, "brain.db"))
        sdb.reset_init_cache()
        schedule.wire({
            "dash_auth": lambda req: True,
            "req_role": lambda req: req._role,
            "json_response": lambda data, status=200: _Resp(data, status),
            "web": types.SimpleNamespace(Response=lambda **k: _Resp(k)),
            "notify": None, "listings": lambda: list(TestRedesign.LISTINGS),
            "now": lambda: datetime.datetime(2026, 6, 28, 9, 0),
            "load_json": lambda n, d=None: d, "save_json": lambda n, o: None,
        })

    def setUp(self):
        seed.reset_to_default()                 # 53 apartments, 5 employees, all unlinked
        HOST.listings = lambda: [dict(x) for x in TestRedesign.LISTINGS]

    # ---- auto-save "who cleans it" ----
    def test_apartment_owner_set(self):
        apt = sdb.apartments()[0]
        emp = sdb.q1("SELECT id FROM schedule_employees WHERE name='عهود'")["id"]
        r = run(routes.api_apartment_owner(_Req(body={"id": apt["id"], "owner_id": emp})))
        self.assertTrue(r.data["ok"])
        self.assertEqual(sdb.q1("SELECT owner_id FROM schedule_apartments WHERE id=?", (apt["id"],))["owner_id"], emp)

    def test_apartment_owner_clear(self):
        apt = sdb.apartments()[0]
        r = run(routes.api_apartment_owner(_Req(body={"id": apt["id"], "owner_id": None})))
        self.assertTrue(r.data["ok"])
        self.assertIsNone(sdb.q1("SELECT owner_id FROM schedule_apartments WHERE id=?", (apt["id"],))["owner_id"])

    def test_apartment_owner_unknown_rejected(self):
        apt = sdb.apartments()[0]
        r = run(routes.api_apartment_owner(_Req(body={"id": apt["id"], "owner_id": 999999})))
        self.assertFalse(r.data["ok"])

    def test_apartment_owner_gated(self):
        apt = sdb.apartments()[0]
        r = run(routes.api_apartment_owner(_Req(role="viewer", body={"id": apt["id"], "owner_id": None})))
        self.assertEqual(r.status, 403)

    # ---- sync (Hostaway-driven) ----
    def test_sync_adds_all_listings(self):
        before = len(sdb.apartments())
        r = run(routes.api_sync(_Req()))
        self.assertTrue(r.data["ok"])
        self.assertEqual(r.data["report"]["added"], 3)
        self.assertEqual(len(sdb.apartments()), before + 3)
        linked = {a["listing_id"] for a in sdb.apartments() if a.get("listing_id") is not None}
        self.assertEqual(linked, {1001, 1002, 1003})

    def test_sync_idempotent(self):
        run(routes.api_sync(_Req()))
        r = run(routes.api_sync(_Req()))
        self.assertEqual(r.data["report"]["added"], 0)

    def test_sync_refreshes_changed_name(self):
        run(routes.api_sync(_Req()))
        HOST.listings = lambda: [{"id": 1001, "name": "NRJS 103 RENAMED", "active": True, "oujact": True}]
        r = run(routes.api_sync(_Req()))
        self.assertGreaterEqual(r.data["report"]["updated"], 1)
        self.assertEqual(sdb.q1("SELECT name FROM schedule_apartments WHERE listing_id=1001")["name"], "NRJS 103 RENAMED")

    def test_sync_gated(self):
        r = run(routes.api_sync(_Req(role="viewer")))
        self.assertEqual(r.status, 403)

    # ---- remove pre-Hostaway leftovers ----
    def test_remove_unlinked_only(self):
        run(routes.api_sync(_Req()))                 # 53 seed (unlinked) + 3 synced (linked)
        r = run(routes.api_remove_unlinked(_Req()))
        self.assertTrue(r.data["ok"])
        self.assertEqual(r.data["report"]["removed"], 53)
        remaining = sdb.apartments()
        self.assertEqual(len(remaining), 3)
        self.assertTrue(all(a.get("listing_id") is not None for a in remaining))

    def test_remove_unlinked_gated(self):
        r = run(routes.api_remove_unlinked(_Req(role="viewer")))
        self.assertEqual(r.status, 403)


if __name__ == "__main__":
    unittest.main()
