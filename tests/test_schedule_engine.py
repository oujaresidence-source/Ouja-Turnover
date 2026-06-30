# -*- coding: utf-8 -*-
"""
Invariant tests for schedule.engine.compute_day — MUST be green before any UI (build spec §8).
Runs on the EXACT seed from the spec (53 apartments, 5 employees), proving the acceptance
numbers: Sunday 13/13/13/14, Thu/Fri base counts, the balance invariant, and override pinning,
plus the Ouja ad-hoc-leave extension.

Run:  python3 -m unittest tests.test_schedule_engine
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from schedule.engine import compute_day, to_weekday  # noqa: E402

# day map: الأحد=0 الاثنين=1 الثلاثاء=2 الأربعاء=3 الخميس=4 الجمعة=5 السبت=6
EMP_SEED = [
    {"name": "ناصر",        "off_day": 2, "color": "#4A6246", "sort_order": 0},
    {"name": "مآثر",        "off_day": 0, "color": "#8B593C", "sort_order": 1},
    {"name": "نورة",        "off_day": 1, "color": "#6A3A5D", "sort_order": 2},
    {"name": "محمد اليامي", "off_day": 3, "color": "#3C5462", "sort_order": 3},
    {"name": "عهود",        "off_day": 6, "color": "#36655E", "sort_order": 4},
]
APT_SEED = {
    "ناصر":        ["الملقا 1", "A5", "FD1", "103", "H8", "202 الملقا", "A2 (التعاون)", "Jood12", "Jood13", "حطين 6b", "نزل فاتن"],
    "مآثر":        ["201a", "201b", "101a", "101b", "202a", "202b", "102a", "102b", "قرطبه B20", "قرطبه A1", "هاجر 22", "كالما 90"],
    "نورة":        ["F1", "6b", "3b", "C2 (العارض)", "C2 (النفل)", "C08", "Heu9", "F2", "شقة 11 (الملقا)"],
    "محمد اليامي": ["C204", "B10", "B03", "B02", "التعاون b13", "رافال 4101", "رافال 4511", "C03", "العارض A11", "نصل العقيق", "14B البدور"],
    "عهود":        ["رويال B11", "القيروان ديار 20", "القيروان D7", "حطين (صاد)", "B06 الملقا", "103 النرجس", "9b", "12b", "عرقه E15", "C118 (الربيع)"],
}
BASE_COUNTS = {"ناصر": 11, "مآثر": 12, "نورة": 9, "محمد اليامي": 11, "عهود": 10}  # Thu/Fri


def _fixture():
    emps, name_to_id = [], {}
    for i, e in enumerate(EMP_SEED, start=1):
        emps.append(dict(e, id=i))
        name_to_id[e["name"]] = i
    apts, pid = [], 1
    for owner, names in APT_SEED.items():
        for so, nm in enumerate(names):
            apts.append({"id": pid, "name": nm, "owner_id": name_to_id[owner], "sort_order": so})
            pid += 1
    return emps, apts, name_to_id


class TestScheduleEngine(unittest.TestCase):
    def setUp(self):
        self.emps, self.apts, self.ids = _fixture()

    def test_total_is_53(self):
        self.assertEqual(len(self.apts), 53)

    def test_sunday_13_13_13_14(self):
        r = compute_day(0, self.emps, self.apts)            # مآثر off
        self.assertEqual(len(r["working"]), 4)
        self.assertEqual(sorted(w["load"] for w in r["working"]), [13, 13, 13, 14])
        self.assertEqual(r["total"], 53)
        self.assertTrue(r["balanced"])
        # مآثر shown as on leave/off, and at least one working list covers her apartments
        self.assertIn("مآثر", [o["name"] for o in r["off"]])
        tagged = any(c["owner_name"] == "مآثر" for w in r["working"] for c in w["coverage"])
        self.assertTrue(tagged)

    def test_thu_fri_base_only(self):
        for wd in (4, 5):                                   # nobody off
            r = compute_day(wd, self.emps, self.apts)
            self.assertEqual(len(r["working"]), 5)
            self.assertFalse(r["has_coverage"])
            loads = {w["name"]: w["load"] for w in r["working"]}
            self.assertEqual(loads, BASE_COUNTS)
            self.assertTrue(all(len(w["coverage"]) == 0 for w in r["working"]))

    def test_balance_invariant_every_coverage_day(self):
        """Mon/Tue/Wed/Sun/Sat all have exactly one off -> max-min<=1, sum==53, zero uncovered."""
        for wd in (0, 1, 2, 3, 6):
            r = compute_day(wd, self.emps, self.apts)
            loads = [w["load"] for w in r["working"]]
            self.assertLessEqual(max(loads) - min(loads), 1, "wd %d not balanced" % wd)
            self.assertEqual(sum(loads), 53, "wd %d sum" % wd)
            self.assertTrue(r["balanced"])
            # every off apartment is covered by exactly one working employee
            uncovered = [a for o in r["off"] for a in o["apartments"] if not a["covering_id"]]
            self.assertEqual(uncovered, [], "wd %d has uncovered" % wd)

    def test_override_pins_and_persists(self):
        r0 = compute_day(0, self.emps, self.apts)
        # take one of مآثر's apartments and pin it to عهود on Sunday
        apt = next(a for a in self.apts if a["owner_id"] == self.ids["مآثر"])
        ov = [{"day_of_week": 0, "apartment_id": apt["id"], "covering_employee_id": self.ids["عهود"]}]
        r = compute_day(0, self.emps, self.apts, overrides=ov)
        ahoud = next(w for w in r["working"] if w["id"] == self.ids["عهود"])
        pinned = [c for c in ahoud["coverage"] if c["apartment"]["id"] == apt["id"]]
        self.assertEqual(len(pinned), 1)
        self.assertTrue(pinned[0]["overridden"])
        self.assertEqual(r["total"], 53)
        self.assertEqual(sum(w["load"] for w in r["working"]), 53)  # nothing lost

    def test_stale_override_skipped(self):
        """An override whose owner is NOT off that weekday is ignored (apartment stays base)."""
        # ناصر's apartment, but pin it on Sunday (ناصر works Sunday) -> stale, skipped
        apt = next(a for a in self.apts if a["owner_id"] == self.ids["ناصر"])
        ov = [{"day_of_week": 0, "apartment_id": apt["id"], "covering_employee_id": self.ids["عهود"]}]
        r = compute_day(0, self.emps, self.apts, overrides=ov)
        naser = next(w for w in r["working"] if w["id"] == self.ids["ناصر"])
        self.assertIn(apt["id"], [a["id"] for a in naser["own"]])  # still his base

    def test_adhoc_leave_extension(self):
        """Ouja extension: a date-specific leave id is treated like an extra day off."""
        # Thursday (nobody normally off) but ناصر on leave -> his 11 apts redistribute, balanced
        r = compute_day(4, self.emps, self.apts, absent_ids={self.ids["ناصر"]})
        self.assertEqual(len(r["working"]), 4)
        self.assertTrue(r["has_coverage"])
        self.assertIn("ناصر", [o["name"] for o in r["off"]])
        self.assertEqual(next(o for o in r["off"] if o["name"] == "ناصر")["reason"], "leave")
        loads = [w["load"] for w in r["working"]]
        self.assertLessEqual(max(loads) - min(loads), 1)
        self.assertEqual(sum(loads), 53)

    def test_to_weekday_mapping(self):
        import datetime
        self.assertEqual(to_weekday(datetime.date(2026, 6, 28)), 0)   # a Sunday
        self.assertEqual(to_weekday(datetime.date(2026, 6, 29)), 1)   # Monday
        self.assertEqual(to_weekday("2026-07-04"), 6)                 # a Saturday

    def test_deterministic(self):
        a = compute_day(0, self.emps, self.apts)
        b = compute_day(0, self.emps, self.apts)
        self.assertEqual([w["load"] for w in a["working"]], [w["load"] for w in b["working"]])


if __name__ == "__main__":
    unittest.main()
