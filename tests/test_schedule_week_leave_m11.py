# -*- coding: utf-8 -*-
"""M11 regression — the WEEKLY matrix must honor ad-hoc leave, not just the
Today view.

The bug: schedule_week called compute_day with no absent_ids while
schedule_day passed them — the week view showed an employee working on their
approved leave day.

Run: python3 -m unittest tests.test_schedule_week_leave_m11
"""
import datetime
import os
import sys
import tempfile
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb            # noqa: E402
from schedule import db as sdb         # noqa: E402
import schedule                        # noqa: E402
from schedule import routes, engine    # noqa: E402


class _Resp:
    def __init__(self, data, status=200):
        self.data = data
        self.status = status


NOW = datetime.datetime(2026, 6, 28, 9, 0)   # Sunday


class WeekLeaveM11Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="sched_m11_")
        bdb.set_db_path_for_tests(os.path.join(cls.tmp, "brain.db"))
        sdb.reset_init_cache()
        schedule.wire({
            "dash_auth": lambda req: True,
            "req_role": lambda req: "admin",
            "json_response": lambda data, status=200: _Resp(data, status),
            "web": types.SimpleNamespace(Response=lambda **k: _Resp(k)),
            "notify": None,
            "now": lambda: NOW,
            "load_json": lambda n, d=None: d, "save_json": lambda n, o: None,
        })

    def test_week_matrix_shows_leave_as_off(self):
        emp = sdb.q1("SELECT id, off_day FROM schedule_employees WHERE name='ناصر'")
        # pick a leave date in the coming week that is NOT his weekly off day
        leave_date = None
        for i in range(7):
            d = NOW.date() + datetime.timedelta(days=i)
            if engine.to_weekday(d) != emp["off_day"] and engine.to_weekday(d) not in (4, 5):
                leave_date = d
                break
        self.assertIsNotNone(leave_date)
        sdb.execute("INSERT INTO schedule_absences(employee_id,start_date,end_date,type,status,note,created_by,created_at) "
                    "VALUES(?,?,?,?,?,?,?,?)",
                    (emp["id"], leave_date.isoformat(), leave_date.isoformat(),
                     "annual", "approved", "m11", "test", sdb.now_iso()))
        try:
            wk = routes.schedule_week()
            row = next(r for r in wk["rows"] if r["weekday"] == engine.to_weekday(leave_date))
            self.assertEqual(row.get("date"), leave_date.isoformat())
            cell = row["cells"][emp["id"]]
            self.assertTrue(cell["off"], "an approved leave day must show OFF in the week view")
            self.assertEqual(cell["load"], 0)
            # his apartments must be redistributed, not dropped
            total = sum(c["load"] for c in row["cells"].values())
            self.assertEqual(total, 53)
        finally:
            sdb.execute("DELETE FROM schedule_absences WHERE note='m11'")

    def test_week_without_leave_unchanged(self):
        wk = routes.schedule_week()
        for r in wk["rows"]:
            total = sum(c["load"] for c in r["cells"].values())
            self.assertEqual(total, 53 if r["has_coverage"] else 53)


if __name__ == "__main__":
    unittest.main()
