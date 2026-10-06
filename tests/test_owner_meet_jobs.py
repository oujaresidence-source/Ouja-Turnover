# -*- coding: utf-8 -*-
"""The build queue (live finding 2026-10-06: a build sat at «في الطابور» on oujares.com).

Locked here:
  * pressing «تجهيز» twice for the same owner/units/period/day reuses the meeting — no second build,
  * a meeting left «building» with no live job is started again when its status is read,
  * the status says how many builds are ahead and how long it has been,
  * a failing progress write never kills the build; a failure always leaves «error», never «building»,
  * the job thread AND every month thread mark their Hostaway calls as a person waiting.

Run: python3 -m unittest tests.test_owner_meet_jobs
"""
import datetime
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aiohttp import web  # noqa: E402

from brain import db as bdb  # noqa: E402
import owner_meet  # noqa: E402
from owner_meet import db, jobs, routes, snapshot  # noqa: E402

TZ = datetime.timezone(datetime.timedelta(hours=3))
FULL = json.loads((ROOT / "tests" / "fixtures" / "owner_meet" / "snapshot_full.json").read_text(encoding="utf-8"))


class _Q(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        db._inited.clear()
        jobs._running.clear()
        jobs._info.clear()
        self.started = []
        self.prio = []
        owner_meet.wire({"state_dir": self.tmp, "web": web, "owner_lids": lambda o: [77],
                         "now": lambda: datetime.datetime(2026, 10, 6, 12, tzinfo=TZ),
                         "user_priority": lambda: self.prio.append(threading.current_thread().name)})
        owner_meet.bootstrap()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class Dedupe(_Q):
    def test_a_second_press_reuses_the_meeting(self):
        orig = jobs.start
        jobs.start = lambda mid, params: self.started.append(mid) or True
        try:
            st1, a = routes.core_create({"owner": "مالك", "lids": [77], "kind": "quarter"}, "Faisal")
            db.set_build(a["id"], state="building")
            jobs._running[a["id"]] = type("F", (), {"done": lambda self: False})()
            st2, b = routes.core_create({"owner": "مالك", "lids": [77], "kind": "quarter"}, "Faisal")
        finally:
            jobs.start = orig
        self.assertEqual(a["id"], b["id"])
        self.assertTrue(b["existing"])
        self.assertEqual(self.started, [a["id"]], "only ONE build was queued")
        self.assertEqual(len(db.meetings_for("مالك")), 1)

    def test_a_different_period_is_a_different_meeting(self):
        orig = jobs.start
        jobs.start = lambda mid, params: True
        try:
            _s, a = routes.core_create({"owner": "مالك", "lids": [77], "kind": "quarter"}, "Faisal")
            _s, b = routes.core_create({"owner": "مالك", "lids": [77], "kind": "ytd"}, "Faisal")
        finally:
            jobs.start = orig
        self.assertNotEqual(a["id"], b["id"])


class Heal(_Q):
    def test_building_without_a_live_job_is_started_again(self):
        orig = jobs.start
        jobs.start = lambda mid, params: self.started.append((mid, params)) or True
        try:
            _s, a = routes.core_create({"owner": "مالك", "lids": [77], "kind": "quarter"}, "Faisal")
            self.started.clear()
            db.set_build(a["id"], state="building", step="في الطابور")
            routes.core_status(a["id"])
        finally:
            jobs.start = orig
        self.assertEqual(len(self.started), 1)
        self.assertEqual(self.started[0][1]["period"]["months"], ["2026-07", "2026-08", "2026-09"])


class Queue(_Q):
    def test_queue_info_counts_builds_ahead(self):
        gate = threading.Event()
        orig = snapshot.build
        snapshot.build = lambda params, progress=None, today=None: gate.wait(5) and FULL
        try:
            p = FULL["meta"]["period"]
            ids = [db.create_meeting("o%d" % i, [77], p, "2026-10-06", "t") for i in range(3)]
            for mid in ids:
                jobs.start(mid, {"owner": "x", "lids": [], "period": p, "meeting_date": "2026-10-06"})
            time.sleep(0.2)
            third = jobs.queue_info(ids[2])
            self.assertFalse(third["started"])
            self.assertEqual(third["waiting_ahead"], 2)
            self.assertTrue(jobs.queue_info(ids[0])["started"])
        finally:
            gate.set()
            for f in list(jobs._running.values()):
                f.result(timeout=10)
            snapshot.build = orig
        self.assertTrue(all(db.meeting(m)["state"] == "ready" for m in ids))

    def test_the_job_thread_runs_as_a_person_waiting(self):
        orig = snapshot.build
        snapshot.build = lambda params, progress=None, today=None: FULL
        try:
            mid = db.create_meeting("o", [77], FULL["meta"]["period"], "2026-10-06", "t")
            jobs.start(mid, {"owner": "o", "lids": [], "period": FULL["meta"]["period"], "meeting_date": "2026-10-06"})
            jobs._running[mid].result(timeout=10)
        finally:
            snapshot.build = orig
        self.assertTrue(any(n.startswith("meet-build") for n in self.prio), self.prio)


class Robust(_Q):
    def test_a_failing_progress_write_does_not_kill_the_build(self):
        orig_b, orig_s = snapshot.build, db.set_build
        calls = {"n": 0}

        def flaky_set_build(mid, **kw):
            if kw.get("step") and kw.get("state") is None:
                calls["n"] += 1
                raise RuntimeError("database is locked")
            return orig_s(mid, **kw)

        def build(params, progress=None, today=None):
            progress(5, "تجهيز الشقق")
            return FULL
        snapshot.build, db.set_build = build, flaky_set_build
        try:
            mid = db.create_meeting("o", [77], FULL["meta"]["period"], "2026-10-06", "t")
            self.assertEqual(jobs.run(mid, {"owner": "o", "lids": [], "period": FULL["meta"]["period"],
                                            "meeting_date": "2026-10-06"}), 1)
        finally:
            snapshot.build, db.set_build = orig_b, orig_s
        self.assertEqual(calls["n"], 1)
        self.assertEqual(db.meeting(mid)["state"], "ready")

    def test_a_crash_always_ends_in_error_never_building(self):
        orig = snapshot.build

        def boom(params, progress=None, today=None):
            raise KeyError("x")
        snapshot.build = boom
        try:
            mid = db.create_meeting("o", [77], FULL["meta"]["period"], "2026-10-06", "t")
            db.set_build(mid, state="building")
            self.assertIsNone(jobs.run(mid, {"owner": "o", "lids": [], "period": FULL["meta"]["period"],
                                             "meeting_date": "2026-10-06"}))
        finally:
            snapshot.build = orig
        self.assertEqual(db.meeting(mid)["state"], "error")


if __name__ == "__main__":
    unittest.main()
