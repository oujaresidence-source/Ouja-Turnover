# -*- coding: utf-8 -*-
"""
roster DB + seed integration test. Points brain.db at a throwaway temp file, seeds from the
real assignments.json (repo fallback), and asserts the store is consistent and the engine
runs gaps==0 from real DB data on every weekday.

Run:  python3 -m unittest tests.test_roster_db
"""
import os
import sys
import tempfile
import datetime
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb           # noqa: E402
from roster import db as rdb          # noqa: E402
from roster import seed as rseed      # noqa: E402
from roster.engine import compute_roster, weekday_name  # noqa: E402


class TestRosterDB(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="roster_test_")
        bdb.set_db_path_for_tests(os.path.join(cls.tmp, "brain.db"))
        rdb.reset_init_cache()
        cls.report = rseed.seed_all()

    def test_seed_idempotent(self):
        before = (len(rdb.employees()), len(rdb.properties()))
        rseed.seed_all()                       # run again
        after = (len(rdb.employees()), len(rdb.properties()))
        self.assertEqual(before, after, "re-seeding must not duplicate")

    def test_employees_seeded(self):
        names = {e["name_ar"] for e in rdb.employees()}
        for n in ["ناصر", "مآثر", "نورة", "محمد اليامي", "عهود", "وجدان", "أسيل"]:
            self.assertIn(n, names)

    def test_live_property_count(self):
        # assignments.json (the live rota) holds 54 DISTINCT units, not the spec's "55".
        # The 55-unit math is proven separately in test_roster_engine on a synthetic fixture.
        self.assertEqual(len(rdb.properties()), 54)

    def test_offdays_present(self):
        by = {e["name_ar"]: e["weekly_off"] for e in rdb.employees()}
        self.assertEqual(by["ناصر"], "tue")
        self.assertEqual(by["مآثر"], "sun")
        self.assertEqual(by["نورة"], "mon")
        self.assertEqual(by["محمد اليامي"], "wed")
        self.assertEqual(by["عهود"], "sat")

    def test_discord_ids_linked(self):
        by = {e["name_ar"]: e.get("discord_id") for e in rdb.employees()}
        self.assertTrue(by["ناصر"])            # from assignments.json discord_ids
        self.assertTrue(by["محمد اليامي"])

    def test_engine_gaps_zero_from_real_data(self):
        """The engine must produce gaps==0 on every weekday for the live seeded data,
        when run over the coverage-eligible workforce (role 'employee')."""
        emps = [e for e in rdb.employees() if e["is_active"] and e["role"] == "employee"]
        props = rdb.properties()
        base = datetime.date(2026, 6, 28)
        for i in range(7):
            d = base + datetime.timedelta(days=i)
            r = compute_roster(d, emps, props, rdb.absences_on(d.isoformat()),
                               locks=rdb.locks_on(d.isoformat()))
            self.assertEqual(r["gaps"], 0, "%s gaps != 0" % weekday_name(d))
            self.assertEqual(r["assigned"], r["total"])

    def test_absence_window_query(self):
        emp_id = rdb.employees()[0]["id"]
        rdb.execute("INSERT INTO roster_absences(employee_id,start_date,end_date,type,status,created_at)"
                    " VALUES(?,?,?,?,?,?)",
                    (emp_id, "2026-07-01", "2026-07-03", "vacation", "approved", rdb.now_iso()))
        self.assertEqual(len(rdb.absences_on("2026-07-02")), 1)
        self.assertEqual(len(rdb.absences_on("2026-07-05")), 0)

    def test_report_reasonable(self):
        self.assertGreaterEqual(self.report["properties_added"], 50)
        self.assertIn("owner_counts", self.report)


if __name__ == "__main__":
    unittest.main()
