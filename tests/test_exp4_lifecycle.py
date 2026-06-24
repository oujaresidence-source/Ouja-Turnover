# -*- coding: utf-8 -*-
"""V4 expense lifecycle state machine — synthetic, no network.

The screen that rots the most finally gets a test of its real transitions:
approval honesty (no silent no-ops), tab precedence, the export gate, and the
dry-run recheck contract.
"""
import unittest

import bot


def mk(**kw):
    e = {"id": "L", "amount": 250.0, "expense_date": "2026-05-01",
         "apartment": "Ouja | شقة 7", "listing_id": 7001, "category": "صيانة"}
    e.update(kw)
    return e


class ApproveHonesty(unittest.TestCase):
    def test_pending_with_fields_approves_and_moves(self):
        e = mk(approval_status="pending_approval")
        ok, why = bot._exp4_approve(e)
        self.assertTrue(ok)
        self.assertEqual(why, "approved")
        self.assertEqual(bot._exp4_tab(e), "approved")

    def test_missing_fields_block_to_needs_edit(self):
        e = mk(approval_status="pending_approval", category="")
        ok, why = bot._exp4_approve(e)
        self.assertFalse(ok)
        self.assertTrue(why.startswith("needs_edit:"))
        self.assertNotEqual(bot._exp4_approval_status(e), "approved")

    def test_verified_is_refused_not_a_silent_noop(self):
        e = mk(hostaway_verified=True, hostaway_ref="55502", approval_status="approved")
        self.assertEqual(bot._exp4_tab(e), "verified")
        ok, why = bot._exp4_approve(e)
        self.assertFalse(ok)
        self.assertEqual(why, "already_verified")
        self.assertEqual(bot._exp4_tab(e), "verified")           # unchanged, honestly

    def test_exported_unverified_is_refused(self):
        e = mk(status="sent_unverified", hostaway_ref="60123", approval_status="approved",
               sent_at="2026-05-20T00:00:00")
        self.assertEqual(bot._exp4_tab(e), "exported")
        ok, why = bot._exp4_approve(e)
        self.assertFalse(ok)
        self.assertEqual(why, "already_exported")

    def test_split_parent_is_refused(self):
        e = mk(is_split_parent=True, approval_status="approved")
        ok, why = bot._exp4_approve(e)
        self.assertFalse(ok)
        self.assertEqual(why, "split_parent")


class TabCounts(unittest.TestCase):
    def test_counts_equal_rows_per_tab(self):
        bot._expenses.clear()
        bot._expenses["p"] = mk(id="p", approval_status="pending_approval")
        bot._expenses["a"] = mk(id="a", approval_status="approved")
        bot._expenses["v"] = mk(id="v", hostaway_verified=True, hostaway_ref="9", approval_status="approved")
        counts = bot._exp4_tab_counts()
        self.assertEqual(counts["pending"]["count"], 1)
        self.assertEqual(counts["approved"]["count"], 1)
        self.assertEqual(counts["verified"]["count"], 1)
        # the overview must agree with the standalone counter (single source of truth)
        ov = bot._exp4_overview_data(tab="pending")
        self.assertEqual(ov["tabs"], counts)


class TabPrecedence(unittest.TestCase):
    def test_each_state_lands_in_the_right_tab(self):
        self.assertEqual(bot._exp4_tab(mk(approval_status="pending_approval")), "pending")
        self.assertEqual(bot._exp4_tab(mk(approval_status="approved")), "approved")
        self.assertEqual(bot._exp4_tab(mk(approval_status="approved", hostaway_verified=True, hostaway_ref="9")), "verified")
        self.assertEqual(bot._exp4_tab(mk(approval_status="approved", status="sent_unverified",
                                          hostaway_ref="9", sent_at="2026-05-20T00:00:00")), "exported")
        self.assertEqual(bot._exp4_tab(mk(approval_status="needs_edit", category="")), "needs_action")
        self.assertEqual(bot._exp4_tab(mk(approval_status="approved", is_split_parent=True)), "needs_action")
        self.assertEqual(bot._exp4_tab(mk(approval_status="rejected", archived=True)), "archived")

    def test_verified_precedence_beats_approval(self):
        # both flags set: export status (verified) must win over the approval lane
        e = mk(approval_status="approved", hostaway_verified=True, hostaway_ref="9")
        self.assertEqual(bot._exp4_tab(e), "verified")


class ExportGate(unittest.TestCase):
    def test_export_refuses_non_approved(self):
        ok, why = bot._exp4_request_export(mk(approval_status="pending_approval"))
        self.assertFalse(ok)
        self.assertEqual(why, "needs_approval")

    def test_export_refuses_split_parent(self):
        ok, why = bot._exp4_request_export(mk(approval_status="approved", is_split_parent=True))
        self.assertFalse(ok)
        self.assertEqual(why, "split_parent_not_exportable")

    def test_export_accepts_approved(self):
        ok, why = bot._exp4_request_export(mk(id="okexp", approval_status="approved"))
        self.assertTrue(ok)


class RecheckDryRun(unittest.TestCase):
    def test_dryrun_never_verifies(self):
        import asyncio
        orig = bot.EXPENSE_POST_DRYRUN
        bot.EXPENSE_POST_DRYRUN = True
        try:
            e = mk(approval_status="approved", hostaway_ref="9")
            self.assertFalse(asyncio.run(bot._exp4_verify(e)))
            self.assertNotEqual(bot._exp4_tab(e), "verified")
        finally:
            bot.EXPENSE_POST_DRYRUN = orig


if __name__ == "__main__":
    unittest.main()
