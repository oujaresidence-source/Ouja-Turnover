# -*- coding: utf-8 -*-
"""
The REAL seed (Faisal's ouja_permits_official.xlsx) against the verified oracle,
tests/fixtures/permits/expected_seed.csv — 45 Ministry of Tourism permits, row for row.

The xlsx is git-ignored (it carries owners' national IDs), so the file-reading tests SKIP
when it is absent. The committed normalized JSON is checked unconditionally, and the
plan() checks run off that JSON — exactly what a fresh deploy loads.

Run: python3 -m unittest tests.test_permits_seed_real
"""

import csv
import datetime
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb                                   # noqa: E402
from permits import dates, db, engine, service                # noqa: E402
from permits.seed import build_seed, seed                     # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XLSX = os.path.join(ROOT, "permits", "seed", "source", "ouja_permits_official.xlsx")
ORACLE = os.path.join(ROOT, "tests", "fixtures", "permits", "expected_seed.csv")
TZ = datetime.timezone(datetime.timedelta(hours=3))
ID_SHAPE = re.compile(r"\b[12][0-9]{9}\b")


def oracle():
    with open(ORACLE, encoding="utf-8") as f:
        return {int(r["serial"]): r for r in csv.DictReader(f)}


def committed():
    with open(build_seed.OUT, encoding="utf-8") as f:
        return json.load(f)


@unittest.skipUnless(os.path.exists(XLSX), "seed xlsx is git-ignored and absent on this machine")
class TestImporterAgainstTheOracle(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not dates.hijri_available():
            if sys.version_info >= (3, 10):
                raise AssertionError("hijridate must be installed on Python >= 3.10 (requirements.txt)")
            raise unittest.SkipTest("hijridate unavailable on this Python")
        cls.built = build_seed.build(XLSX)
        cls.rows = {r["serial"]: r for r in cls.built["rows"]}

    def test_45_rows_nothing_dropped(self):
        self.assertEqual(self.built["source_rows"], 45)
        self.assertEqual(sorted(self.rows), list(range(1, 46)))

    def test_header_row_is_2_and_the_title_is_ignored(self):
        self.assertEqual(self.built["header_row"], 2)
        self.assertNotIn("شركة عوجا", json.dumps(self.built["rows"], ensure_ascii=False))

    def test_every_row_and_column_matches_the_oracle(self):
        for serial, want in oracle().items():
            got = self.rows[serial]
            for col_got, col_want in (("unit_text", "unit_text"), ("permit_no", "permit_no"),
                                      ("start_date_raw", "start_hijri"), ("start_date", "start_date"),
                                      ("end_date_raw", "end_hijri"), ("end_date", "end_date"),
                                      ("district", "district"), ("building_no", "building_no"),
                                      ("unit_no", "unit_no"), ("ownership_kind", "ownership_kind")):
                self.assertEqual(str(got[col_got]), want[col_want], "serial %d · %s" % (serial, col_got))
            self.assertEqual(bool(got["doc_url"]), want["has_drive_link"] == "1", serial)

    def test_every_issue_to_expiry_gap_is_365_days(self):
        for r in self.rows.values():
            a = datetime.date.fromisoformat(r["start_date"])
            b = datetime.date.fromisoformat(r["end_date"])
            self.assertEqual((b - a).days, 365, r["serial"])

    def test_45_drive_links(self):
        links = [r["doc_url"] for r in self.rows.values()]
        self.assertEqual(len(links), 45)
        for u in links:
            self.assertTrue(u.startswith("https://drive.google.com/"), u)

    def test_bidi_marks_are_stripped_on_serial_3(self):
        name = self.rows[3]["doc_name"]
        self.assertTrue(name)
        for ch in ("\u200e", "\u2068", "\u2069"):
            self.assertNotIn(ch, name)

    def test_review_issues(self):
        codes = {s: [i["code"] for i in r["review_issues"]] for s, r in self.rows.items()}
        self.assertIn("dup_permit_no", codes[19])
        self.assertIn("dup_permit_no", codes[44])
        for s in (1, 19, 43):
            self.assertIn("unit_mismatch", codes[s], s)
        flagged = {s for s, c in codes.items() if c}
        self.assertEqual(flagged, {1, 19, 43, 44})

    def test_seed_constants(self):
        for r in self.rows.values():
            self.assertEqual(r["permit_type"], engine.SEED_TYPE)
            self.assertEqual(r["issuer"], "وزارة السياحة")
            self.assertEqual(r["scope"], "unit")
            self.assertEqual(r["source"], "seed")

    def test_no_national_id_anywhere_and_last4_everywhere(self):
        blob = json.dumps(self.built, ensure_ascii=False)
        self.assertIsNone(ID_SHAPE.search(blob))
        for r in self.rows.values():
            self.assertRegex(r["holder_id_last4"], r"^\d{4}$")

    def test_the_committed_json_equals_a_fresh_build(self):
        fresh = dict(self.built)
        old = committed()
        fresh.pop("built_at", None)
        old.pop("built_at", None)
        self.assertEqual(json.loads(json.dumps(fresh, ensure_ascii=False)), old)


class TestTheCommittedSeed(unittest.TestCase):
    """What a fresh deploy actually loads — checked even without the xlsx."""

    def test_shape(self):
        d = committed()
        self.assertEqual(d["source_rows"], 45)
        self.assertEqual(len(d["rows"]), 45)
        by_no = {}
        for r in d["rows"]:
            by_no.setdefault(r["permit_no"], []).append(r["serial"])
        self.assertEqual(by_no["50035533"], [13])
        self.assertEqual(sorted(by_no["50037629"]), [19, 44])

    def test_no_national_id_in_the_committed_file(self):
        with open(build_seed.OUT, encoding="utf-8") as f:
            self.assertIsNone(ID_SHAPE.search(f.read()))


class TestSeededPlan(unittest.TestCase):
    """F2 (serial 13, permit 50035533) ends 2026-10-12: 11 days left on 10-01, 10 on 10-02."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="permits_seed_")
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        db.reset_init_cache()
        self.n = seed.seed_if_empty(listings=lambda: [])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_seed_loads_45_once(self):
        self.assertEqual(self.n, 45)
        self.assertEqual(seed.seed_if_empty(listings=lambda: []), 0)
        self.assertEqual(db.count_permits(), 45)

    def test_oct_1_opens_nothing(self):
        p = service.plan(datetime.datetime(2026, 10, 1, 13, 0, tzinfo=TZ))
        self.assertEqual(p["open"], [])

    def test_oct_2_live_opens_exactly_f2(self):
        service.set_mode("live", "تشغيل", "test")
        p = service.plan(datetime.datetime(2026, 10, 2, 13, 0, tzinfo=TZ))
        self.assertEqual(len(p["open"]), 1)
        self.assertEqual(db.permit(p["open"][0])["permit_no"], "50035533")

    def test_oct_2_dry_opens_nothing_and_records_one_would_open(self):
        from tests.permits_fakes import FakePort
        import asyncio
        port = FakePort()
        asyncio.run(service.tick(port, datetime.datetime(2026, 10, 2, 13, 0, tzinfo=TZ)))
        self.assertEqual(db.q("SELECT * FROM permits_tickets"), [])
        dry = db.outbox_rows("dry")
        opens = [o for o in dry if o["kind"] == "open_ticket"]
        self.assertEqual(len(opens), 1)
        self.assertEqual(json.loads(opens[0]["payload_json"])["permit_no"], "50035533")
        self.assertEqual(port.calls, [])
        names = [w["unit"] for w in service.would_open(datetime.datetime(2026, 10, 2, 13, 0, tzinfo=TZ))]
        self.assertEqual(names, ["F2"])


if __name__ == "__main__":
    unittest.main()
