# -*- coding: utf-8 -*-
"""
The rules of «ضم الوحدات», driven directly — no DB, no event loop, no HTTP.

engine.readiness() is the ONLY producer of a publish blocker in this package. If it is right
here, the API, the page and the Discord message are right too, because all three render this
one list. Everything below exists so a future edit cannot quietly widen the gate.

Run: python3 -m unittest tests.test_onb_engine
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from onboarding import engine          # noqa: E402


def complete_project(**over):
    """A project with nothing missing — the baseline every blocker test breaks exactly once."""
    p = {
        "ref": "OJ-ONB-0001",
        "client_name": "عبدالله الشمري", "client_type": "owner", "client_whatsapp": "0555000000",
        "client_email": "a@b.c", "sublet_ok": None,
        "unit_name": "Ouja | الملقا 1 — دخول ذاتي", "district": "الملقا", "unit_kind": "tower",
        "bedrooms": 2, "area_sqm": 120.0, "furnish_state": "furnished",
        "strategy": "weekly_nightly", "ouja_rate_pct": 22.0, "cleaning_sar": 900.0,
        "contract_signed_at": "2026-08-01", "ceo_approval": "not_needed",
        "license_no": "LIC-99", "license_expiry": "2027-12-31",
        "photos_url": "https://drive/x", "photos_approved": 1,
        "access_notes": "المفتاح مع الحارس", "wifi_notes": "Ouja-Malqa / 12345678",
        "house_rules": "ممنوع الحفلات", "checkin_time": "15:00", "checkout_time": "12:00",
        "client_promises": "", "client_prefs": "",
        "status": "active", "stage": "handover",
    }
    p.update(over)
    return p


def task(key="s1.1", stage="lead", gate=0, resolution="done", reason=None, seq=1, **over):
    t = {"id": abs(hash(key)) % 100000, "catalogue_key": key, "stage": stage, "seq": seq,
         "title_ar": "مهمة " + key, "owner_role": "coordinator", "gate": gate,
         "resolution": resolution, "reason": reason, "assignee_id": None, "assignee_name": None}
    t.update(over)
    return t


def two_people():
    return [{"employee_id": 1, "employee_name": "ناصر", "is_primary": 1},
            {"employee_id": 2, "employee_name": "نورة", "is_primary": 0}]


TODAY = "2026-08-30"


def codes(project, tasks=None, asg=None):
    r = engine.readiness(project, tasks if tasks is not None else [task()],
                         asg if asg is not None else two_people(), today=TODAY)
    return [b["code"] for b in r["blockers"]]


class TestAssigneeCap(unittest.TestCase):
    """R3 — two means a primary and a backup; three means no owner."""

    def test_01_first_and_second_allowed_third_refused_naming_both(self):
        self.assertEqual(engine.can_add_assignee([], 1), (True, ""))
        one = [{"employee_id": 1, "employee_name": "ناصر"}]
        self.assertEqual(engine.can_add_assignee(one, 2), (True, ""))
        ok, err = engine.can_add_assignee(two_people(), 3)
        self.assertFalse(ok)
        self.assertIn("ناصر", err)
        self.assertIn("نورة", err)

    def test_02_duplicate_gets_the_duplicate_message_not_the_capacity_one(self):
        """'Already on it' is not a capacity problem. Reporting it as one makes the account
        manager delete somebody to make room that was never needed."""
        ok, err = engine.can_add_assignee([{"employee_id": 1, "employee_name": "ناصر"}], 1)
        self.assertFalse(ok)
        self.assertIn("مضاف أصلاً", err)
        self.assertNotIn("موظفين اثنين", err)


class TestReadiness(unittest.TestCase):

    def test_03_a_complete_project_is_ready(self):
        r = engine.readiness(complete_project(), [task()], two_people(), today=TODAY)
        self.assertTrue(r["ok"])
        self.assertEqual(r["blockers"], [])

    # ---- test 04: each of the 14 codes fires in isolation -------------------------------
    def test_04a_client_incomplete(self):
        self.assertEqual(codes(complete_project(client_whatsapp="")), ["client_incomplete"])

    def test_04b_sublet_unchecked(self):
        p = complete_project(client_type="tenant", sublet_ok=None)
        self.assertEqual(codes(p), ["sublet_unchecked"])

    def test_04c_unit_incomplete(self):
        self.assertEqual(codes(complete_project(bedrooms=None)), ["unit_incomplete"])

    def test_04d_terms_incomplete(self):
        self.assertEqual(codes(complete_project(contract_signed_at="")), ["terms_incomplete"])

    def test_04e_ceo_pending(self):
        p = complete_project(ouja_rate_pct=18.0, ceo_approval="pending")
        self.assertEqual(codes(p), ["ceo_pending"])

    def test_04f_license_missing(self):
        self.assertEqual(codes(complete_project(license_no="")), ["license_missing"])

    def test_04g_license_expired(self):
        self.assertEqual(codes(complete_project(license_expiry="2026-01-01")),
                         ["license_expired"])

    def test_04h_photos_missing(self):
        self.assertEqual(codes(complete_project(photos_approved=0)), ["photos_missing"])

    def test_04i_handover_incomplete(self):
        self.assertEqual(codes(complete_project(wifi_notes="")), ["handover_incomplete"])

    def test_04j_no_assignee(self):
        self.assertEqual(codes(complete_project(), asg=[]), ["no_assignee"])

    def test_04k_too_many_assignees(self):
        three = two_people() + [{"employee_id": 3, "employee_name": "عهود"}]
        self.assertEqual(codes(complete_project(), asg=three), ["too_many_assignees"])

    def test_04l_open_gate_tasks_counts_in_the_message(self):
        ts = [task("s5.1", gate=1, resolution="open"), task("s5.2", gate=1, resolution="open")]
        r = engine.readiness(complete_project(), ts, two_people(), today=TODAY)
        self.assertEqual([b["code"] for b in r["blockers"]], ["open_gate_tasks"])
        self.assertEqual(r["blockers"][0]["count"], 2)
        self.assertIn("2", r["blockers"][0]["ar"])

    def test_04m_blocked_gate_tasks(self):
        ts = [task("s5.1", gate=1, resolution="blocked", reason="المورد متأخر")]
        self.assertEqual(codes(complete_project(), ts), ["blocked_gate_tasks"])

    def test_04n_unreasoned_resolution(self):
        ts = [task("s2.8", gate=0, resolution="na", reason="")]
        self.assertEqual(codes(complete_project(), ts), ["unreasoned_resolution"])

    def test_05_blocker_order_is_stable(self):
        """Order is what makes the gate panel readable — it must never depend on dict order."""
        p = complete_project(client_name="", client_type="tenant", sublet_ok=None,
                             bedrooms=None, strategy="", license_no="")
        ts = [task("s5.1", gate=1, resolution="open")]
        r = engine.readiness(p, ts, [], today=TODAY)
        self.assertEqual([b["code"] for b in r["blockers"]],
                         ["client_incomplete", "sublet_unchecked", "unit_incomplete",
                          "terms_incomplete", "license_missing", "no_assignee",
                          "open_gate_tasks"])

    def test_06_open_gate_counts_only_gate_tasks(self):
        ts = [task("s2.8", gate=0, resolution="open"), task("s5.1", gate=1, resolution="done")]
        self.assertNotIn("open_gate_tasks", codes(complete_project(), ts))

    def test_07_unreasoned_fires_on_na_and_never_on_done(self):
        self.assertIn("unreasoned_resolution",
                      codes(complete_project(), [task("s1.1", resolution="na", reason="")]))
        self.assertNotIn("unreasoned_resolution",
                         codes(complete_project(), [task("s1.1", resolution="done", reason="")]))

    def test_07b_a_zero_is_a_real_answer_not_a_hole(self):
        """cleaning_sar = 0 is a decision (absorbed). Reading it as missing would block a
        legitimate deal from ever publishing."""
        self.assertNotIn("terms_incomplete", codes(complete_project(cleaning_sar=0)))

    def test_08_progress_excludes_ongoing_na_counts_blocked_does_not(self):
        ts = [task("a", resolution="done"), task("b", resolution="na", reason="x"),
              task("c", resolution="blocked", reason="y"), task("d", resolution="open"),
              task("o.1", stage="ongoing", resolution="open")]
        self.assertEqual(engine.progress(ts), 50)          # 2 of 4, ongoing excluded
        self.assertEqual(engine.progress([]), 0)

    def test_09_snapshot_carries_every_handover_field_and_both_names(self):
        p = complete_project(client_promises="وعدناه بتقرير شهري", client_prefs="ما يبي حفلات")
        snap = engine.handover_snapshot(p, [task()], two_people())
        for k in ("access_notes", "wifi_notes", "house_rules", "checkin_time", "checkout_time",
                  "client_promises", "client_prefs"):
            self.assertEqual(snap["handover"][k], p[k], "handover lost %s" % k)
        self.assertEqual([a["employee_name"] for a in snap["assignees"]], ["ناصر", "نورة"])
        self.assertEqual(snap["license"]["license_no"], "LIC-99")
        self.assertEqual(len(snap["tasks"]), 1)


if __name__ == "__main__":
    unittest.main()
