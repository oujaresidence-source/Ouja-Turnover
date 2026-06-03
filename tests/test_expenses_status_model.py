import unittest
from datetime import timedelta

import bot


class ExpenseStatusModelTest(unittest.TestCase):
    def test_legacy_statuses_map_to_canonical_truth(self):
        self.assertEqual(bot._exp_canonical_status({"status": "captured"}), "draft")
        self.assertEqual(bot._exp_canonical_status({"status": "held"}), "needs_review")
        self.assertEqual(bot._exp_canonical_status({"status": "discarded"}), "archived")

    def test_posted_without_hostaway_verification_is_not_verified(self):
        exp = {"status": "posted", "hostaway_verified": False, "sent_at": bot._exp_now().isoformat()}
        self.assertEqual(bot._exp_canonical_status(exp), "sent_unverified")

    def test_hostaway_verified_is_single_verified_gate(self):
        exp = {"status": "in_transit", "hostaway_verified": True}
        self.assertEqual(bot._exp_canonical_status(exp), "verified")

    def test_stale_pending_thresholds(self):
        now = bot._exp_now()
        old_queue = now - timedelta(minutes=bot.EXPENSE_QUEUE_STALE_MIN + 1)
        old_sending = now - timedelta(minutes=bot.EXPENSE_SENDING_STALE_MIN + 1)
        old_sent = now - timedelta(minutes=bot.EXPENSE_SENT_UNVERIFIED_STALE_MIN + 1)

        self.assertEqual(
            bot._exp_canonical_status({"status": "queued", "queued_at": old_queue.isoformat()}, now=now),
            "stale_pending",
        )
        self.assertEqual(
            bot._exp_canonical_status({"status": "sending", "sending_at": old_sending.isoformat()}, now=now),
            "stale_pending",
        )
        self.assertEqual(
            bot._exp_canonical_status({"status": "in_transit", "sent_at": old_sent.isoformat()}, now=now),
            "stale_pending",
        )

    def test_view_exposes_raw_and_canonical_status(self):
        exp = {
            "id": "ex_test",
            "status": "posted",
            "hostaway_verified": False,
            "sent_at": bot._exp_now().isoformat(),
        }
        view = bot._exp_view(exp)
        self.assertEqual(view["raw_status"], "posted")
        self.assertEqual(view["status"], "sent_unverified")


if __name__ == "__main__":
    unittest.main()
