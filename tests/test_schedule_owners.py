# -*- coding: utf-8 -*-
"""
schedule.owners — the SHARED permanent-owner resolver + apartment-delete propagation.
Temp brain.db + seed, then verify:
  * permanent_map() reflects the calendar exactly (owner per apartment, employees list),
  * owner_for() resolves by listing_id first, exact name fallback, None when unassigned,
  * /api/schedule/owners returns the snapshot for any logged-in reader,
  * deleting an apartment removes it from the map, the day/week counts, and cascades
    its coverage overrides (no dangling references anywhere).

Run:  python3 -m unittest tests.test_schedule_owners
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
from schedule import routes, owners    # noqa: E402


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


class TestScheduleOwners(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="sched_own_")
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

    def setUp(self):
        # every test starts from the pristine seed (53 apartments / 5 employees)
        run(routes.api_reset(_Req()))

    def test_map_matches_calendar(self):
        pm = owners.permanent_map()
        self.assertEqual(len(pm["apartments"]), 53)
        self.assertEqual(len(pm["employees"]), 5)
        emp_names = {e["name"] for e in pm["employees"]}
        for a in pm["apartments"]:
            self.assertIn(a["owner_name"], emp_names)   # every seed apartment is owned

    def test_owner_for_by_name_and_listing(self):
        apt = sdb.apartments()[0]
        expected = sdb.q1("SELECT name FROM schedule_employees WHERE id=?",
                          (apt["owner_id"],))["name"]
        self.assertEqual(owners.owner_for(name=apt["name"]), expected)
        # listing_id takes precedence over name
        sdb.execute("UPDATE schedule_apartments SET listing_id=999001 WHERE id=?", (apt["id"],))
        self.assertEqual(owners.owner_for(listing_id=999001, name="اسم غلط"), expected)
        self.assertEqual(owners.owner_for(listing_id="999001"), expected)  # str/int agnostic
        self.assertIsNone(owners.owner_for(name="شقة غير موجودة"))

    def test_unassigned_apartment_is_graceful(self):
        aid = sdb.execute("INSERT INTO schedule_apartments(name,owner_id,sort_order,created_at) "
                          "VALUES('Ouja | Test بدون مالك',NULL,99,?)", (sdb.now_iso(),))
        pm = owners.permanent_map()
        rec = next(a for a in pm["apartments"] if a["id"] == aid)
        self.assertIsNone(rec["owner_name"])            # blank, no crash
        self.assertIsNone(owners.owner_for(name="Ouja | Test بدون مالك"))

    def test_api_owners_route(self):
        r = run(routes.api_owners(_Req(role="viewer")))  # any logged-in reader
        self.assertTrue(r.data["ok"])
        self.assertEqual(len(r.data["employees"]), 5)
        self.assertEqual(len(r.data["apartments"]), 53)
        self.assertTrue(all("owner_name" in a for a in r.data["apartments"]))

    def test_delete_apartment_propagates_everywhere(self):
        # pick an apartment owned by مآثر (off Sunday) and pin an override on it
        row = sdb.q1("SELECT a.id id, a.name name FROM schedule_apartments a "
                     "JOIN schedule_employees e ON a.owner_id=e.id WHERE e.name='مآثر' LIMIT 1")
        other = sdb.q1("SELECT id FROM schedule_employees WHERE name='عهود'")["id"]
        run(routes.api_override_set(_Req(body={"day_of_week": 0, "apartment_id": row["id"],
                                               "covering_employee_id": other})))
        # delete (viewer blocked, editor allowed)
        blocked = run(routes.api_apartment_delete(_Req(role="viewer", match={"id": str(row["id"])})))
        self.assertEqual(blocked.status, 403)
        ok = run(routes.api_apartment_delete(_Req(match={"id": str(row["id"])})))
        self.assertTrue(ok.data["ok"])
        # gone from the permanent-owner map (shared resolver)
        self.assertIsNone(owners.owner_for(name=row["name"]))
        self.assertNotIn(row["id"], [a["id"] for a in owners.permanent_map()["apartments"]])
        # gone from EVERY day, not just one: totals drop to 52 across the whole week
        for d in ("2026-06-28", "2026-06-29", "2026-06-30", "2026-07-01",
                  "2026-07-02", "2026-07-03", "2026-07-04"):
            day = run(routes.api_day(_Req(query={"date": d}))).data["day"]
            self.assertEqual(day["total"], 52)
            for w in day["working"]:
                self.assertNotIn(row["id"], [x["id"] for x in w["own"]])
                self.assertNotIn(row["id"], [c["apartment"]["id"] for c in w["coverage"]])
        # its coverage override cascaded away — no dangling reference
        self.assertFalse(sdb.q("SELECT * FROM schedule_coverage_overrides WHERE apartment_id=?",
                               (row["id"],)))
        # weekly matrix still balances on Sunday with 52 units
        wk = run(routes.api_week(_Req())).data["week"]
        sun = wk["rows"][0]
        self.assertEqual(sum(c["load"] for c in sun["cells"].values()), 52)


if __name__ == "__main__":
    unittest.main()
