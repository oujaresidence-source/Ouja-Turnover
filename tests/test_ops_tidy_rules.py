# -*- coding: utf-8 -*-
"""Pins the owner-approved tidy decisions (2026-10-02) against the REAL audit.

If any of these fail, the classifier changed behaviour — do not "fix the test",
re-read docs/superpowers/specs/2026-10-02-discord-tidy-design.md first.
Run: python3 -m unittest tests.test_ops_tidy_rules -v
"""
import copy
import json
import os
import sys
import unittest
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import ops_tidy_rules as R  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures", "tidy")
NOW = datetime(2026, 10, 2, 13, 15, 30, tzinfo=timezone.utc)   # the audit's generated_at


def _load(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return json.load(f)


INV = _load("audit_2026-10-02.json")
EXPECTED = _load("expected_decisions_2026-10-02.json")
PLAN = R.build_plan(INV, NOW)
BY_NAME = {}
for _r in PLAN["channels"]:
    BY_NAME.setdefault(_r["name"], []).append(_r)


class TestCountsAndParity(unittest.TestCase):
    def test_counts_match_owner_page(self):
        self.assertEqual(PLAN["counts"], {"keep": 94, "restrict": 24, "archive": 196})

    def test_every_channel_matches_the_approved_decision(self):
        diffs = [(r["name"], r["category"], r["decision"], EXPECTED[r["id"]]["decision"])
                 for r in PLAN["channels"] if EXPECTED[r["id"]]["decision"] != r["decision"]]
        self.assertEqual(diffs, [])

    def test_all_314_channels_covered(self):
        self.assertEqual(len(PLAN["channels"]), 314)
        self.assertEqual(set(r["id"] for r in PLAN["channels"]), set(EXPECTED))

    def test_four_archive_categories_with_arabic_digits(self):
        self.assertEqual(PLAN["archive_categories"],
                         ["📦 أرشيف ١", "📦 أرشيف ٢", "📦 أرشيف ٣", "📦 أرشيف ٤"])
        per = {}
        for r in PLAN["channels"]:
            if r["action"] == "archive":
                per[r["archive_category"]] = per.get(r["archive_category"], 0) + 1
        self.assertTrue(all(v <= 50 for v in per.values()), per)


class TestOwnerRules(unittest.TestCase):
    PANELS = ["فتح-تذكرة-rr", "افتحت-تكت-طلب-اموال", "افتح-تكت-دره-جديد", "فتح-تذكرة-مشتريات",
              "تكت-اشتراك-النت", "افتح-مشروع-جديد", "فتح-تذكرة-صيانة", "rr-tickets"]

    def test_ticket_opening_rooms_are_never_touched(self):
        for n in self.PANELS:
            for r in BY_NAME[n]:
                self.assertEqual((r["decision"], r["action"]), ("keep", None), n)

    def test_panel_rule_beats_closed_and_dead(self):
        ch = {"name": "مغلقة-فتح-تذكرة-x", "category": "DUMP", "accessible": False}
        self.assertEqual(R.classify_channel(ch, NOW)[0], "keep")

    def test_bot_owned_channels_never_move(self):
        for r in PLAN["channels"]:
            if r["name"] in R.BOT_OWNED_DEFAULT:
                self.assertNotEqual(r["action"], "archive", r["name"])

    def test_stale_bot_channel_still_kept(self):
        r = BY_NAME["ouja-studio"][0]                 # 65 days old, bot-owned
        self.assertEqual(r["decision"], "keep")

    def test_price_channels_become_management_only(self):
        for n in R.MGMT_ONLY:
            self.assertEqual(BY_NAME[n][0]["action"], "mgmt_only", n)

    def test_untouched_categories(self):
        for r in PLAN["channels"]:
            if r["category"] in ("Managment", "الالتزام"):
                self.assertEqual(r["decision"], "keep", r["name"])

    def test_live_turnover_and_maintenance_permissions_unchanged(self):
        for r in PLAN["channels"]:
            if r["category"] in ("🧹 Turnovers", "صيانه", "مشتريات") and r["decision"] != "archive":
                self.assertIn(r["action"], (None, "mgmt_only"), r["name"])

    def test_rr2_live_tickets_follow_category(self):
        rr2 = [r for r in PLAN["channels"] if r["category"] == "RR ٢"]
        self.assertEqual(len(rr2), 16)
        self.assertEqual(sum(1 for r in rr2 if r["action"] == "sync_to_category"), 15)
        self.assertEqual(sum(1 for r in rr2 if r["action"] == "archive"), 1)   # مغلقة-rr-040

    def test_directpay_closed_rooms_archived_open_rooms_locked(self):
        dp = [r for r in PLAN["channels"] if r["category"] == R.DIRECTPAY_CATEGORY]
        self.assertEqual(len(dp), 38)
        self.assertEqual(sum(1 for r in dp if r["action"] == "archive"), 33)
        self.assertEqual(sum(1 for r in dp if r["action"] == "sync_to_category"), 5)

    def test_category_fixes(self):
        fx = {f["category"]: f for f in PLAN["category_fixes"]}
        self.assertEqual(fx["RR ٢"]["kind"], "copy_parent")
        self.assertEqual(fx["RR ٢"]["parent"], "RR")
        self.assertEqual(fx["صيانه ٢"]["parent"], "صيانه")          # empty but OPEN today
        self.assertEqual(fx[R.DIRECTPAY_CATEGORY]["kind"], "lock_directpay")
        self.assertEqual(len(fx), 3)


class TestIdempotence(unittest.TestCase):
    def test_second_plan_after_run_moves_nothing(self):
        inv = copy.deepcopy(INV)
        moved = {r["id"]: r["archive_category"] for r in PLAN["channels"] if r["action"] == "archive"}
        counts = {}
        for ch in inv["channels"]:
            if ch["id"] in moved:
                ch["category"] = moved[ch["id"]]
                counts[moved[ch["id"]]] = counts.get(moved[ch["id"]], 0) + 1
        for name, n in counts.items():
            inv["categories"].append({"name": name, "id": name, "position": 99, "channel_count": n,
                                      "overwrites": []})
        plan2 = R.build_plan(inv, NOW)
        self.assertEqual(plan2["counts"]["archive"], 0)

    def test_new_moves_fill_existing_archive_first(self):
        self.assertEqual(R.assign_archive_slots(3, {1: 49}), [1, 2, 2])
        self.assertEqual(R.assign_archive_slots(2, {1: 50, 2: 50}), [3, 3])


class TestPeopleReport(unittest.TestCase):
    def _visible_to(self, roles):
        """Approximate 'can view now' from the audit overwrites (role-level)."""
        out = set()
        for ch in INV["channels"]:
            if R.everyone_can_view(ch) or set(R.view_roles(ch)) & set(roles):
                out.add(ch["id"])
        return out

    def test_roleless_member_loses_only_leaks_and_archive(self):
        m = {"id": "1", "name": "عامل", "roles": [], "is_admin": False}
        rep = R.people_report(PLAN, [m], {"1": self._visible_to([])})[0]
        lost = set(rep["loses_live"])
        self.assertIn("pricing-log", lost)
        self.assertIn("rr-063-hmmj52tqjp", lost)          # RR ٢ leak closed
        self.assertIn("تحصيل-037-f2", lost)               # directpay leak closed
        for keep in ("e15-oujact-checkin🟡", "oujact-schedule", "فتح-تذكرة-مشتريات", "news"):
            self.assertNotIn(keep, lost)
        self.assertGreater(rep["loses_archive"], 0)

    def test_admin_loses_nothing(self):
        m = {"id": "2", "name": "أسيل", "roles": ["Head of Operation"], "is_admin": True}
        rep = R.people_report(PLAN, [m], {"2": {r["id"] for r in PLAN["channels"]}})[0]
        self.assertEqual((rep["loses_live"], rep["loses_archive"]), ([], 0))

    def test_manager_keeps_archive_and_numbers(self):
        m = {"id": "3", "name": "مدير", "roles": ["Managment"], "is_admin": False}
        rep = R.people_report(PLAN, [m], {"3": self._visible_to(["Managment"])})[0]
        self.assertEqual(rep["loses_archive"], 0)
        self.assertNotIn("revenue-report", rep["loses_live"])

    def test_directpay_closer_keeps_collection_rooms(self):
        m = {"id": "777", "name": "مقفل", "roles": [], "is_admin": False}
        rep = R.people_report(PLAN, [m], {"777": self._visible_to([])}, directpay_extra_ids=[777])[0]
        self.assertNotIn("تحصيل-037-f2", rep["loses_live"])


class TestSnapshotAndPurity(unittest.TestCase):
    def test_snapshot_row_normalises(self):
        s = R.snapshot_row({"id": 5, "category_id": 9, "position": 3, "synced": 1,
                            "overwrites": [{"type": "role", "id": 2, "allow": "1024", "deny": 0}]})
        self.assertEqual(s["id"], "5")
        self.assertEqual(s["overwrites"][0], {"type": "role", "id": "2", "allow": 1024, "deny": 0})

    def test_undo_is_reverse_order(self):
        self.assertEqual(R.undo_order([1, 2, 3]), [3, 2, 1])

    def test_rules_module_never_imports_discord(self):
        with open(os.path.join(ROOT, "ops_tidy_rules.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("import discord", src)
        self.assertNotIn("import bot", src)


if __name__ == "__main__":
    unittest.main()
