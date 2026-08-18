# -*- coding: utf-8 -*-
"""
Step 1 of «مخطط الإجازات والتغطية» — DATE-SCOPED overrides.

The calendar could already pin an apartment to a coverer for a WEEKDAY (recurring, forever).
It could not say "on 2026-08-24 only, نورة takes حطين 6b". This file locks that primitive down
BEFORE the engine learns it (TDD), because every later phase — the leave preview, the
reassignment popup, the saved plan — is just this primitive plus a UI.

The rules being locked:
  * precedence is  date_overrides  ->  recurring overrides  ->  auto-balance.
  * a date override applies to the WHOLE apartment list, not only to the pool of apartments
    belonging to off employees: moving one apartment on one day must work with NOBODY absent.
  * a date override aimed at someone who is off/absent that day is SKIPPED (exactly like the
    existing stale-recurring-override behaviour) and REPORTED so the UI can flag it.
  * pinned load counts toward the balance before the remaining pool is distributed.
  * with no date overrides passed, every existing invariant is untouched.

Run:  python3 -m unittest tests.test_schedule_date_overrides
"""
import datetime
import os
import sys
import tempfile
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb                      # noqa: E402
from schedule import db as sdb                   # noqa: E402
import schedule                                  # noqa: E402
from schedule import routes, coverage, seed      # noqa: E402
from schedule.engine import compute_day          # noqa: E402

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

# concrete dates used by the DB/route half (verified against engine.to_weekday)
SUN = "2026-06-28"    # مآثر off
THU = "2026-07-02"    # nobody off


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


def _apt_of(apts, owner_id, n=0):
    return [a for a in apts if a["owner_id"] == owner_id][n]


def _find_cov(day, emp_id, apt_id):
    """The coverage entry for `apt_id` on `emp_id`'s board, or None."""
    w = [x for x in day["working"] if x["id"] == emp_id]
    if not w:
        return None
    return next((c for c in w[0]["coverage"] if c["apartment"]["id"] == apt_id), None)


def _owns(day, emp_id, apt_id):
    w = [x for x in day["working"] if x["id"] == emp_id]
    return bool(w) and apt_id in [a["id"] for a in w[0]["own"]]


# =====================================================================
#  A. the pure engine
# =====================================================================
class DateOverrideEngineTest(unittest.TestCase):
    def setUp(self):
        self.emps, self.apts, self.ids = _fixture()

    # ---- the headline rule: this date wins over the weekday rule ----
    def test_date_override_beats_recurring_override(self):
        apt = _apt_of(self.apts, self.ids["مآثر"])          # مآثر is off on Sunday
        rec = [{"day_of_week": 0, "apartment_id": apt["id"],
                "covering_employee_id": self.ids["عهود"]}]
        dov = [{"apartment_id": apt["id"], "covering_employee_id": self.ids["نورة"]}]
        r = compute_day(0, self.emps, self.apts, overrides=rec, date_overrides=dov)
        self.assertIsNotNone(_find_cov(r, self.ids["نورة"], apt["id"]),
                             "the date override must win over the recurring one")
        self.assertIsNone(_find_cov(r, self.ids["عهود"], apt["id"]))
        self.assertTrue(_find_cov(r, self.ids["نورة"], apt["id"])["overridden"])
        self.assertEqual(sum(w["load"] for w in r["working"]), 53)

    # ---- it must work when NOBODY is absent (move one unit on one day) ----
    def test_date_override_with_nobody_absent(self):
        """Thursday: everyone works. Moving one of ناصر's apartments to نورة must still work —
        the override applies to the whole list, not just to an off employee's pool."""
        apt = _apt_of(self.apts, self.ids["ناصر"], 3)
        dov = [{"apartment_id": apt["id"], "covering_employee_id": self.ids["نورة"]}]
        r = compute_day(4, self.emps, self.apts, date_overrides=dov)
        self.assertFalse(_owns(r, self.ids["ناصر"], apt["id"]),
                         "the apartment must leave its owner's base for that day")
        c = _find_cov(r, self.ids["نورة"], apt["id"])
        self.assertIsNotNone(c)
        self.assertTrue(c["overridden"])
        self.assertEqual(c["owner_name"], "ناصر", "the card must still say whose apartment it is")
        loads = {w["name"]: w["load"] for w in r["working"]}
        self.assertEqual(loads["ناصر"], 10)      # 11 - 1
        self.assertEqual(loads["نورة"], 10)      # 9 + 1
        self.assertEqual(sum(loads.values()), 53)

    # ---- a pin at someone who is off that day is refused, and SAID OUT LOUD ----
    def test_target_off_is_skipped_and_reported(self):
        apt = _apt_of(self.apts, self.ids["ناصر"])
        dov = [{"apartment_id": apt["id"], "covering_employee_id": self.ids["مآثر"]}]  # مآثر off Sunday
        r = compute_day(0, self.emps, self.apts, date_overrides=dov)
        self.assertTrue(_owns(r, self.ids["ناصر"], apt["id"]),
                        "a skipped override falls back to normal — the owner keeps it")
        skipped = r.get("skipped_date_overrides")
        self.assertEqual(len(skipped or []), 1, "the UI must be told the pin did not apply")
        self.assertEqual(skipped[0]["apartment_id"], apt["id"])
        self.assertEqual(skipped[0]["covering_employee_id"], self.ids["مآثر"])
        self.assertEqual(skipped[0]["reason"], "target_off")

    def test_target_on_leave_is_skipped_too(self):
        """Same rule when the target is out on ad-hoc LEAVE rather than their weekly day off."""
        apt = _apt_of(self.apts, self.ids["ناصر"])
        dov = [{"apartment_id": apt["id"], "covering_employee_id": self.ids["عهود"]}]
        r = compute_day(4, self.emps, self.apts, absent_ids={self.ids["عهود"]}, date_overrides=dov)
        self.assertEqual([s["reason"] for s in r["skipped_date_overrides"]], ["target_off"])

    def test_unknown_employee_and_apartment_are_reported_not_crashes(self):
        dov = [{"apartment_id": 9999, "covering_employee_id": self.ids["نورة"]},
               {"apartment_id": _apt_of(self.apts, self.ids["ناصر"])["id"],
                "covering_employee_id": 9999}]
        r = compute_day(4, self.emps, self.apts, date_overrides=dov)
        reasons = sorted(s["reason"] for s in r["skipped_date_overrides"])
        self.assertEqual(reasons, ["unknown_apartment", "unknown_employee"])
        self.assertEqual(sum(w["load"] for w in r["working"]), 53)

    # ---- pinning an apartment at its own working owner is a no-op, not a fake "coverage" ----
    def test_pin_to_own_working_owner_stays_own(self):
        apt = _apt_of(self.apts, self.ids["نورة"])
        dov = [{"apartment_id": apt["id"], "covering_employee_id": self.ids["نورة"]}]
        r = compute_day(4, self.emps, self.apts, date_overrides=dov)
        self.assertTrue(_owns(r, self.ids["نورة"], apt["id"]))
        self.assertIsNone(_find_cov(r, self.ids["نورة"], apt["id"]),
                          "an apartment must never be listed as covering yourself")
        self.assertEqual({w["name"]: w["load"] for w in r["working"]}["نورة"], 9)

    # ---- pinned load must be visible to the balancer, not added after it ----
    def test_pinned_load_counts_before_auto_balance(self):
        """Sunday: مآثر's 12 apartments redistribute. Pin 4 of them to عهود by date; the
        auto-balancer must SEE those 4 and give عهود fewer of the rest, not pile on top."""
        ma = [a for a in self.apts if a["owner_id"] == self.ids["مآثر"]]
        dov = [{"apartment_id": a["id"], "covering_employee_id": self.ids["عهود"]} for a in ma[:4]]
        r = compute_day(0, self.emps, self.apts, date_overrides=dov)
        loads = {w["name"]: w["load"] for w in r["working"]}
        self.assertEqual(sum(loads.values()), 53)
        self.assertEqual(loads["عهود"], 14, "10 base + 4 pinned, and nothing auto-added on top")
        self.assertEqual(len(r["skipped_date_overrides"]), 0)

    # ---- the off employee's own card must name the right coverer ----
    def test_off_card_shows_the_date_coverer(self):
        apt = _apt_of(self.apts, self.ids["مآثر"])
        dov = [{"apartment_id": apt["id"], "covering_employee_id": self.ids["نورة"]}]
        r = compute_day(0, self.emps, self.apts, date_overrides=dov)
        ma = next(o for o in r["off"] if o["name"] == "مآثر")
        row = next(a for a in ma["apartments"] if a["apartment"]["id"] == apt["id"])
        self.assertEqual(row["covering_name"], "نورة")

    # ---- nothing passed = nothing changed ----
    def test_no_date_overrides_keeps_every_existing_invariant(self):
        for dov in (None, []):
            r = compute_day(0, self.emps, self.apts, date_overrides=dov)
            self.assertEqual(sorted(w["load"] for w in r["working"]), [13, 13, 13, 14])
            self.assertEqual(r["total"], 53)
            self.assertTrue(r["balanced"])
            self.assertEqual(r.get("skipped_date_overrides"), [])
        for wd in (4, 5):
            r = compute_day(wd, self.emps, self.apts, date_overrides=[])
            self.assertEqual({w["name"]: w["load"] for w in r["working"]},
                             {"ناصر": 11, "مآثر": 12, "نورة": 9, "محمد اليامي": 11, "عهود": 10})

    def test_deterministic_with_date_overrides(self):
        apt = _apt_of(self.apts, self.ids["مآثر"])
        dov = [{"apartment_id": apt["id"], "covering_employee_id": self.ids["نورة"]}]
        a = compute_day(0, self.emps, self.apts, date_overrides=dov)
        b = compute_day(0, self.emps, self.apts, date_overrides=dov)
        self.assertEqual([w["load"] for w in a["working"]], [w["load"] for w in b["working"]])

    def test_nothing_is_lost_or_duplicated(self):
        """Whatever the pins, every apartment is assigned exactly once."""
        ma = [a for a in self.apts if a["owner_id"] == self.ids["مآثر"]]
        na = [a for a in self.apts if a["owner_id"] == self.ids["ناصر"]]
        dov = ([{"apartment_id": a["id"], "covering_employee_id": self.ids["عهود"]} for a in ma[:3]]
               + [{"apartment_id": a["id"], "covering_employee_id": self.ids["نورة"]} for a in na[:2]])
        r = compute_day(0, self.emps, self.apts, date_overrides=dov)
        seen = []
        for w in r["working"]:
            seen += [a["id"] for a in w["own"]] + [c["apartment"]["id"] for c in w["coverage"]]
        self.assertEqual(len(seen), 53)
        self.assertEqual(len(set(seen)), 53)


# =====================================================================
#  B. storage + the routes/Discord surfaces that read it
# =====================================================================
class DateOverrideStoreTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="sched_dov_")
        bdb.set_db_path_for_tests(os.path.join(cls.tmp, "brain.db"))
        sdb.reset_init_cache()
        schedule.wire({
            "dash_auth": lambda req: True,
            "req_role": lambda req: "admin",
            "json_response": lambda data, status=200: types.SimpleNamespace(data=data, status=status),
            "web": types.SimpleNamespace(Response=lambda **k: k),
            "notify": None,
            "now": lambda: datetime.datetime(2026, 6, 28, 9, 0),
            "load_json": lambda n, d=None: d, "save_json": lambda n, o: None,
        })

    def setUp(self):
        sdb.execute("DELETE FROM schedule_date_overrides")

    def _ids(self):
        e = {r["name"]: r["id"] for r in sdb.employees()}
        return e

    def _pin(self, date_iso, apt_id, emp_id, plan_id=None):
        return sdb.execute(
            "INSERT INTO schedule_date_overrides(date,apartment_id,covering_employee_id,plan_id,"
            "note,created_by,created_at) VALUES(?,?,?,?,?,?,?)",
            (date_iso, apt_id, emp_id, plan_id, "t", "tester", sdb.now_iso()))

    # ---- schema ----
    def test_table_and_reader_exist(self):
        e = self._ids()
        apt = sdb.q1("SELECT id FROM schedule_apartments LIMIT 1")["id"]
        self._pin(SUN, apt, e["نورة"])
        rows = sdb.date_overrides_on(SUN)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["covering_employee_id"], e["نورة"])
        self.assertEqual(sdb.date_overrides_on(THU), [])

    def test_one_pin_per_apartment_per_date(self):
        e = self._ids()
        apt = sdb.q1("SELECT id FROM schedule_apartments LIMIT 1")["id"]
        self._pin(SUN, apt, e["نورة"])
        with self.assertRaises(Exception):
            self._pin(SUN, apt, e["عهود"])          # UNIQUE(date, apartment_id)

    def test_migration_is_additive_and_guarded(self):
        """An existing brain.db that predates this table gets it WITHOUT losing anything else."""
        before_apts = len(sdb.apartments())
        sdb.executescript("DROP TABLE schedule_date_overrides")
        sdb.reset_init_cache()
        sdb._ensure()
        self.assertEqual(sdb.date_overrides_on(SUN), [])          # re-created
        self.assertEqual(len(sdb.apartments()), before_apts)      # nothing else touched
        self.assertEqual(len(sdb.employees()), 5)

    # ---- the read path everything renders from ----
    def test_schedule_day_applies_the_pin(self):
        e = self._ids()
        apt = sdb.q1("SELECT a.id id, a.name name FROM schedule_apartments a "
                     "JOIN schedule_employees x ON a.owner_id=x.id WHERE x.name='ناصر' LIMIT 1")
        self._pin(THU, apt["id"], e["نورة"])
        day = routes.schedule_day(THU)
        self.assertIsNotNone(_find_cov(day, e["نورة"], apt["id"]))
        self.assertFalse(_owns(day, e["ناصر"], apt["id"]))
        self.assertEqual(day["total"], 53)
        # ...and a day with no pin is untouched
        self.assertEqual(sorted(w["load"] for w in routes.schedule_day(SUN)["working"]),
                         [13, 13, 13, 14])

    def test_week_matrix_honors_the_pin(self):
        """M11's lesson applied to pins: the weekly matrix resolves each weekday to a CONCRETE
        date, so it must not disagree with the Today tab for that same date."""
        e = self._ids()
        apt = sdb.q1("SELECT a.id id FROM schedule_apartments a JOIN schedule_employees x "
                     "ON a.owner_id=x.id WHERE x.name='ناصر' LIMIT 1")["id"]
        self._pin(THU, apt, e["نورة"])           # THU is inside schedule_week's today..+6 window
        row = next(r for r in routes.schedule_week()["rows"] if r["date"] == THU)
        self.assertEqual(row["cells"][e["ناصر"]]["load"], 10, "11 base - 1 handed away")
        self.assertEqual(row["cells"][e["نورة"]]["load"], 10, "9 base + 1 taken on")
        self.assertEqual(sum(c["load"] for c in row["cells"].values()), 53)

    def test_discord_cover_map_follows_the_pin(self):
        """cover_map feeds the OujaCT channel emoji — a plan must reach Discord automatically."""
        e = self._ids()
        apt = sdb.q1("SELECT a.id id FROM schedule_apartments a JOIN schedule_employees x "
                     "ON a.owner_id=x.id WHERE x.name='ناصر' LIMIT 1")["id"]
        before, _ = coverage.cover_map(THU)
        self.assertEqual(before[apt]["name"], "ناصر")
        self._pin(THU, apt, e["نورة"])
        after, _ = coverage.cover_map(THU)
        self.assertEqual(after[apt]["name"], "نورة")

    # ---- cleanup rules ----
    def test_apartment_delete_removes_its_pins(self):
        e = self._ids()
        apt = sdb.apartments()[0]["id"]
        self._pin(SUN, apt, e["نورة"])
        run = _runner()
        run(routes.api_apartment_delete(_Req(match={"id": str(apt)})))
        self.assertEqual(sdb.date_overrides_on(SUN), [])

    def test_employee_delete_removes_pins_aimed_at_them(self):
        e = self._ids()
        apt = sdb.apartments()[0]["id"]
        # عهود covers it; deleting عهود must not leave a pin pointing at a ghost
        self._pin(SUN, apt, e["عهود"])
        sdb.execute("UPDATE schedule_apartments SET owner_id=? WHERE owner_id=?",
                    (e["ناصر"], e["عهود"]))
        run = _runner()
        run(routes.api_employee_delete(_Req(match={"id": str(e["عهود"])})))
        self.assertEqual(sdb.date_overrides_on(SUN), [])
        seed.reset_to_default()      # restore the full roster for the tests after this one

    def test_reset_to_default_clears_them(self):
        e = self._ids()
        self._pin(SUN, sdb.apartments()[0]["id"], e["نورة"])
        seed.reset_to_default()
        self.assertEqual(sdb.date_overrides_on(SUN), [])


class _Req:
    def __init__(self, query=None, match=None, role="admin", body=None):
        self.query = query or {}
        self.match_info = match or {}
        self._role = role
        self._body = body or {}
        self.headers = {}

    async def json(self):
        return self._body


def _runner():
    import asyncio

    def run(coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    return run


if __name__ == "__main__":
    unittest.main()
