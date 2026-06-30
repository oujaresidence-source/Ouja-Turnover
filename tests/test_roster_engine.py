# -*- coding: utf-8 -*-
"""
Invariant tests for roster.engine.compute_roster — these MUST be green before any UI
(build spec §4). They run on a SYNTHETIC 5-custodian fixture that mirrors the real ops
shape (12/12/12/11/8 = 55 units, one weekly day off each) so the engine math is proven
independently of whatever the live DB happens to hold.

Run:  python3 -m unittest tests.test_roster_engine
"""
import os
import sys
import datetime
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from roster.engine import compute_roster, weekday_name  # noqa: E402

# Custodians (role 'employee') with the real off-days from the build spec §3.
#   ناصر/tue, مآثر/sun, نورة/mon, محمد اليامي/wed, عهود/sat
EMP = [
    {"id": 1, "name_ar": "ناصر",       "initial_ar": "ن", "weekly_off": "tue", "role": "employee", "is_active": 1},
    {"id": 2, "name_ar": "مآثر",       "initial_ar": "م", "weekly_off": "sun", "role": "employee", "is_active": 1},
    {"id": 3, "name_ar": "نورة",       "initial_ar": "ن", "weekly_off": "mon", "role": "employee", "is_active": 1},
    {"id": 4, "name_ar": "محمد اليامي", "initial_ar": "م", "weekly_off": "wed", "role": "employee", "is_active": 1},
    {"id": 5, "name_ar": "عهود",       "initial_ar": "ع", "weekly_off": "sat", "role": "employee", "is_active": 1},
]
# 12 / 12 / 12 / 11 / 8 = 55
COUNTS = {1: 12, 2: 12, 3: 12, 4: 11, 5: 8}


def _make_props():
    props, pid = [], 1
    for owner, n in COUNTS.items():
        for _ in range(n):
            props.append({"id": pid, "display_name_ar": "U%d" % pid,
                          "primary_owner_id": owner, "zone": None,
                          "turnover_weight": 1, "status": "active"})
            pid += 1
    return props


# Dates whose weekday lands on each name. 2026-06 anchors (verified below in test).
def _date_for(day_name):
    base = datetime.date(2026, 6, 28)  # a Sunday
    for i in range(7):
        d = base + datetime.timedelta(days=i)
        if weekday_name(d) == day_name:
            return d
    raise AssertionError("no date for " + day_name)


class TestRosterInvariants(unittest.TestCase):
    def setUp(self):
        self.props = _make_props()

    def test_total_is_55(self):
        self.assertEqual(len(self.props), 55)

    def test_every_weekday_zero_gaps(self):
        """Core invariant: gaps==0 and assigned==55 for ALL seven weekdays."""
        for day in ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]:
            d = _date_for(day)
            r = compute_roster(d, EMP, self.props, [])
            self.assertEqual(r["gaps"], 0, "%s gaps" % day)
            self.assertEqual(r["assigned"], 55, "%s assigned" % day)
            self.assertFalse(r["escalate"], "%s escalate" % day)

    def test_single_off_day_load_13_14(self):
        """On a day with exactly one custodian off (4 available), balanced load is 13-14."""
        for day in ["sun", "mon", "tue", "wed", "sat"]:   # each maps to one off-custodian
            d = _date_for(day)
            r = compute_roster(d, EMP, self.props, [])
            self.assertEqual(len(r["available"]), 4, "%s available" % day)
            loads = [r["load"][i] for i in r["available"]]
            self.assertTrue(min(loads) >= 13 and max(loads) <= 14,
                            "%s loads=%s" % (day, loads))
            self.assertEqual(sum(loads), 55)

    def test_thu_fri_nobody_off(self):
        """Thu/Fri: nobody is off → all 5 available, everyone keeps only their own units."""
        for day in ["thu", "fri"]:
            d = _date_for(day)
            r = compute_roster(d, EMP, self.props, [])
            self.assertEqual(len(r["available"]), 5, "%s available" % day)
            self.assertEqual(r["gaps"], 0)
            self.assertEqual(sorted(r["load"].values()), [8, 11, 12, 12, 12])

    def test_stacked_off_plus_one_sick(self):
        """Off-day + 1 approved sick leave → 3 available, still gaps==0."""
        d = _date_for("sun")                 # مآثر(2) off
        absences = [{"employee_id": 1, "status": "approved", "type": "sick"}]  # ناصر sick
        r = compute_roster(d, EMP, self.props, absences)
        self.assertEqual(len(r["available"]), 3)
        self.assertEqual(r["gaps"], 0)
        self.assertEqual(r["assigned"], 55)

    def test_stacked_off_plus_two_sick(self):
        """Off-day + 2 sick → 2 available, still gaps==0 (capacity not yet exceeded)."""
        d = _date_for("sun")                 # مآثر(2) off
        absences = [{"employee_id": 1, "status": "approved", "type": "sick"},
                    {"employee_id": 3, "status": "approved", "type": "vacation"}]
        r = compute_roster(d, EMP, self.props, absences)
        self.assertEqual(len(r["available"]), 2)
        self.assertEqual(r["gaps"], 0)
        self.assertEqual(r["assigned"], 55)

    def test_requested_absence_does_not_count(self):
        """Only status=='approved' removes a custodian; 'requested' must NOT."""
        d = _date_for("thu")
        absences = [{"employee_id": 1, "status": "requested", "type": "vacation"}]
        r = compute_roster(d, EMP, self.props, absences)
        self.assertNotIn(1, r["absent"])
        self.assertEqual(len(r["available"]), 5)

    def test_capacity_guard_whole_team_out(self):
        """Everyone out → no silent drop: all units become gaps and escalate fires."""
        d = _date_for("thu")
        absences = [{"employee_id": i, "status": "approved", "type": "emergency"}
                    for i in [1, 2, 3, 4, 5]]
        r = compute_roster(d, EMP, self.props, absences)
        self.assertEqual(r["available"], [])
        self.assertEqual(r["gaps"], 55)
        self.assertEqual(len(r["gap_properties"]), 55)
        self.assertTrue(r["escalate"])

    def test_lock_pins_assignment(self):
        """A locked override stays on its target and is counted, not re-balanced away."""
        d = _date_for("thu")
        locks = [{"property_id": 1, "responsible_id": 4, "original_owner_id": 1}]
        r = compute_roster(d, EMP, self.props, [], locks=locks)
        covered_pids = [c["property"]["id"] for c in r["board"][4]["covered"]]
        self.assertIn(1, covered_pids)
        self.assertNotIn(1, [p["id"] for p in r["board"][1]["primary"]])
        self.assertEqual(r["gaps"], 0)

    def test_lock_to_absent_person_is_a_gap(self):
        """Locking a unit to someone who is OUT today cannot be honored → a gap (escalate)."""
        d = _date_for("tue")                  # ناصر(1) off
        locks = [{"property_id": 50, "responsible_id": 1, "original_owner_id": 4}]
        r = compute_roster(d, EMP, self.props, [], locks=locks)
        self.assertTrue(r["escalate"])
        self.assertIn(50, [p["id"] for p in r["gap_properties"]])

    def test_unowned_unit_is_covered(self):
        """A unit with no primary owner must still be assigned to someone available."""
        props = _make_props()
        props.append({"id": 999, "display_name_ar": "ORPHAN", "primary_owner_id": None,
                      "zone": None, "turnover_weight": 1, "status": "active"})
        d = _date_for("thu")
        r = compute_roster(d, EMP, props, [])
        placed = any(999 in [c["property"]["id"] for c in r["board"][i]["covered"]]
                     for i in r["available"])
        self.assertTrue(placed)
        self.assertEqual(r["gaps"], 0)

    def test_paused_unit_excluded(self):
        """A paused/offboarded unit is not counted and not assigned."""
        props = _make_props()
        props[0]["status"] = "paused"
        d = _date_for("thu")
        r = compute_roster(d, EMP, props, [])
        self.assertEqual(r["total"], 54)
        self.assertEqual(r["assigned"], 54)

    def test_deterministic(self):
        """Same inputs → identical board twice (reproducible, id-tiebroken)."""
        d = _date_for("sun")
        a = compute_roster(d, EMP, self.props, [])
        b = compute_roster(d, EMP, self.props, [])
        self.assertEqual(a["load"], b["load"])

    def test_pluggable_pick_target(self):
        """A custom strategy is honored (here: always the highest-id available person)."""
        def always_last(prop, available, board, load):
            return max(available, key=lambda e: e["id"])["id"]
        d = _date_for("sun")                  # مآثر(2) off → her 12 units are orphans
        r = compute_roster(d, EMP, self.props, [], pick_target=always_last)
        # id 5 (عهود) is the highest available id → all orphans land on عهود.
        self.assertEqual(len(r["board"][5]["covered"]), 12)


if __name__ == "__main__":
    unittest.main()
