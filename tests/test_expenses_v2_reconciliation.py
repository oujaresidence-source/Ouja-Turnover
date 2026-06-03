import unittest
from unittest.mock import patch

import bot


class ExpensesV2ReconciliationTest(unittest.TestCase):
    def setUp(self):
        self.old_expenses = dict(bot._expenses)
        self.old_dryrun = bot.EXPENSE_POST_DRYRUN
        bot.EXPENSE_POST_DRYRUN = False
        bot._expenses.clear()

    def tearDown(self):
        bot.EXPENSE_POST_DRYRUN = self.old_dryrun
        bot._expenses.clear()
        bot._expenses.update(self.old_expenses)

    def _expense(self, **overrides):
        exp = {
            "id": overrides.pop("id", "ex_1"),
            "ref": overrides.pop("ref", "OJ-EXP-0178"),
            "submission_id": overrides.pop("submission_id", "gs-row-1"),
            "status": overrides.pop("status", "ready"),
            "apartment": overrides.pop("apartment", "Ouja | Test"),
            "listing_id": overrides.pop("listing_id", 441508),
            "amount": overrides.pop("amount", 400.0),
            "expense_date": overrides.pop("expense_date", "2026-06-02"),
            "category": overrides.pop("category", "صيانة وإصلاحات"),
            "maintenance_type": overrides.pop("maintenance_type", "Paint"),
            "hostaway_ref": overrides.pop("hostaway_ref", None),
            "hostaway_verified": overrides.pop("hostaway_verified", False),
            "events": overrides.pop("events", []),
        }
        exp.update(overrides)
        bot._expenses[exp["id"]] = exp
        return exp

    def test_real_hostaway_ref_not_found_is_not_safe_repair_queue(self):
        exp = self._expense(status="stale_pending", hostaway_ref="3287443")

        snapshot = bot._exp_v2_reconcile_items(hostaway_items=[])
        row = next(r for r in snapshot["rows"] if r["id"] == exp["id"])

        self.assertEqual(row["v2_status"], "sent_not_verified")
        self.assertEqual(row["recommended_action"], "verify_hostaway_id")
        self.assertFalse(row["can_export"])
        self.assertEqual(row["repair_action"], "manual_verify")

    def test_ready_without_hostaway_ref_can_be_safe_missing_export(self):
        exp = self._expense(status="ready", hostaway_ref=None)

        snapshot = bot._exp_v2_reconcile_items(hostaway_items=[])
        row = next(r for r in snapshot["rows"] if r["id"] == exp["id"])

        self.assertEqual(row["v2_status"], "ready")
        self.assertTrue(row["can_export"])
        self.assertEqual(row["repair_action"], "export_safe_missing")

    def test_hostaway_reference_match_is_verified_only_when_refetch_found(self):
        exp = self._expense(status="sent_unverified", hostaway_ref="3287443")
        hostaway_item = {
            "id": 3287443,
            "listingMapId": 441508,
            "amount": -400,
            "expenseDate": "2026-06-02",
            "reference": "OJ-EXP-0178",
        }

        snapshot = bot._exp_v2_reconcile_items(hostaway_items=[hostaway_item])
        row = next(r for r in snapshot["rows"] if r["id"] == exp["id"])

        self.assertEqual(row["v2_status"], "verified")
        self.assertTrue(row["hostaway_state"]["present_in_hostaway"])
        self.assertEqual(row["hostaway_state"]["match_method"], "reference")

    def test_hostaway_only_rows_are_visible_as_orphans(self):
        hostaway_item = {
            "id": 9001,
            "listingMapId": 999,
            "amount": -61,
            "expenseDate": "2026-06-02",
            "concept": "Electrical",
        }

        snapshot = bot._exp_v2_reconcile_items(hostaway_items=[hostaway_item])
        row = next(r for r in snapshot["rows"] if r["source_kind"] == "hostaway_only")

        self.assertEqual(row["v2_status"], "duplicate")
        self.assertTrue(row["hostaway_state"]["present_in_hostaway"])
        self.assertFalse(row["dashboard_state"]["present_in_dashboard"])

    def test_repair_plan_never_queues_real_ref_not_found(self):
        self._expense(status="stale_pending", hostaway_ref="3287443")
        self._expense(id="ex_2", ref="OJ-EXP-0179", status="ready", hostaway_ref=None)

        plan = bot._exp_v2_repair_plan(hostaway_items=[])

        self.assertEqual(plan["counts"]["manual_verify"], 1)
        self.assertEqual(plan["counts"]["export_safe_missing"], 1)
        self.assertEqual(plan["actions"]["manual_verify"][0]["ref"], "OJ-EXP-0178")
        self.assertEqual(plan["actions"]["export_safe_missing"][0]["ref"], "OJ-EXP-0179")

    def test_split_percentage_preview_creates_child_refs_and_balances(self):
        parent = self._expense(amount=300.0)

        preview = bot._exp_v2_split_preview(parent["id"], "percentage", [
            {"listing_id": 1, "apartment": "Ouja | A", "value": 50},
            {"listing_id": 2, "apartment": "Ouja | B", "value": 30},
            {"listing_id": 3, "apartment": "Ouja | C", "value": 20},
        ])

        self.assertTrue(preview["ok"])
        self.assertEqual([c["ref"] for c in preview["children"]],
                         ["OJ-EXP-0178-A", "OJ-EXP-0178-B", "OJ-EXP-0178-C"])
        self.assertEqual(sum(c["amount"] for c in preview["children"]), 300.0)

    def test_split_sar_preview_rejects_unbalanced_total(self):
        parent = self._expense(amount=300.0)

        preview = bot._exp_v2_split_preview(parent["id"], "amount", [
            {"listing_id": 1, "apartment": "Ouja | A", "value": 100},
            {"listing_id": 2, "apartment": "Ouja | B", "value": 100},
        ])

        self.assertFalse(preview["ok"])
        self.assertEqual(preview["error"], "split_not_balanced")

    def test_verify_tries_direct_hostaway_id_before_bulk_search(self):
        exp = self._expense(status="sent_unverified", hostaway_ref="3287443")
        direct_item = {
            "id": 3287443,
            "listingMapId": 441508,
            "amount": -400,
            "expenseDate": "2026-06-02",
        }

        with patch.object(bot, "_exp_fetch_hostaway_one", return_value=(direct_item, True, None)):
            with patch.object(bot, "_exp_fetch_hostaway", return_value=([], True, None)):
                ok = bot._exp_verify_in_hostaway(exp)

        self.assertTrue(ok)
        self.assertTrue(exp["hostaway_verified"])
        self.assertEqual(exp["verification_method"], "hostaway_id")


if __name__ == "__main__":
    unittest.main()
