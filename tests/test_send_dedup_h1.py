# -*- coding: utf-8 -*-
"""H1 regression — a FAILED guest send must not poison the dedup claim,
and suppressed/blocked no-ops must be distinguishable from real sends.

The bug: send_guest_message claimed the (conversation, body) dedup key BEFORE
posting to Hostaway. If the POST failed, the claim survived for 6h, so when a
human approved the same draft again the send was silently suppressed — and all
callers treated the None return as success ("✅ تم الإرسال" with no message sent).

Run: python3 tests/test_send_dedup_h1.py
"""
import os
import sys
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("STATE_DIR", "/tmp/ouja-test-state-h1")
os.makedirs("/tmp/ouja-test-state-h1", exist_ok=True)

import bot  # noqa: E402


class SendGuestMessageH1Test(unittest.TestCase):
    def setUp(self):
        self._api_post = bot.api_post
        self._kill = bot.ASSISTANT_SEND_KILL
        bot.ASSISTANT_SEND_KILL = False

    def tearDown(self):
        bot.api_post = self._api_post
        bot.ASSISTANT_SEND_KILL = self._kill

    def test_sent_then_identical_send_suppressed(self):
        body = "مرحبا " + uuid.uuid4().hex
        bot.api_post = lambda p, b: {"status": "success", "result": {"id": 1}}
        r1 = bot.send_guest_message(999001, body)
        self.assertIsInstance(r1, dict, "a real send returns the Hostaway result")
        r2 = bot.send_guest_message(999001, body)
        self.assertEqual(r2, bot.SEND_SUPPRESSED,
                         "an identical resend must be reported as suppressed, not success")

    def test_failed_send_releases_claim_so_retry_works(self):
        body = "الرد " + uuid.uuid4().hex

        def boom(p, b):
            raise RuntimeError("hostaway 500")
        bot.api_post = boom
        with self.assertRaises(RuntimeError):
            bot.send_guest_message(999002, body)
        # the retry (e.g. a human approving the same draft) must actually POST
        sent = []
        bot.api_post = lambda p, b: (sent.append(b), {"status": "success"})[1]
        r = bot.send_guest_message(999002, body)
        self.assertTrue(sent, "retry after a failed send must reach Hostaway (claim released)")
        self.assertNotIn(r, (bot.SEND_SUPPRESSED, bot.SEND_BLOCKED_KILL))

    def test_kill_switch_blocks_without_consuming_the_claim(self):
        body = "تجربة " + uuid.uuid4().hex
        called = []
        bot.api_post = lambda p, b: (called.append(b), {"status": "success"})[1]
        bot.ASSISTANT_SEND_KILL = True
        r = bot.send_guest_message(999003, body)
        self.assertEqual(r, bot.SEND_BLOCKED_KILL)
        self.assertFalse(called, "kill switch must block the POST entirely")
        bot.ASSISTANT_SEND_KILL = False
        r2 = bot.send_guest_message(999003, body)
        self.assertIsInstance(r2, dict, "after kill-off the same body must still send")


if __name__ == "__main__":
    unittest.main()
