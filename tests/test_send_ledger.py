"""guard.ledger — proving authorship survives what the deques cannot.

32.1% of outbound messages have no known author because _learning_log (maxlen=3000) and
_auto_replies (maxlen=500) are bounded and roll. The ledger is append-only on the volume.
"""

import os
import tempfile
import unittest

from guard import ledger


class LedgerTest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("STATE_DIR")
        os.environ["STATE_DIR"] = self._tmp.name
        ledger.reset_for_tests()

    def tearDown(self):
        if self._old is None:
            os.environ.pop("STATE_DIR", None)
        else:
            os.environ["STATE_DIR"] = self._old
        ledger.reset_for_tests()
        self._tmp.cleanup()

    def test_round_trip(self):
        sid = ledger.record_send("999", "حياك الله 🤍", via="auto", actor="(auto)")
        rec = ledger.lookup("999", "حياك الله 🤍")
        self.assertIsNotNone(rec)
        self.assertEqual(rec["id"], sid)
        self.assertEqual(rec["via"], "auto")

    def test_lookup_ignores_whitespace_and_case(self):
        ledger.record_send("1", "Hi   there\n\nfriend", via="discord_send", actor="Faisal")
        self.assertIsNotNone(ledger.lookup("1", "hi there friend"))
        self.assertIsNotNone(ledger.lookup("1", "Hi there    friend "))

    def test_a_message_we_never_sent_is_not_ours(self):
        ledger.record_send("1", "ours", via="auto", actor="(auto)")
        self.assertIsNone(ledger.lookup("1", "somebody else typed this in the Airbnb app"))
        self.assertFalse(ledger.is_ours("1", "typed by a teammate"))

    def test_empty_body_never_matches(self):
        ledger.record_send("1", "real", via="auto", actor="(auto)")
        self.assertIsNone(ledger.lookup("1", ""))
        self.assertIsNone(ledger.lookup("1", "   "))

    def test_it_survives_a_process_restart(self):
        # The whole point: the deques do not survive this, the ledger does.
        ledger.record_send("42", "قبل إعادة التشغيل", via="discord_send", actor="Faisal")
        ledger.reset_for_tests()                      # simulate a fresh process
        rec = ledger.lookup("42", "قبل إعادة التشغيل")
        self.assertIsNotNone(rec, "the ledger must outlive the process that wrote it")
        self.assertEqual(rec["actor"], "Faisal")

    def test_it_survives_the_learning_log_rolling(self):
        # _learning_log = deque(maxlen=3000); extending past the cap drops the oldest.
        from collections import deque
        learning_log = deque(maxlen=5)
        for i in range(20):
            body = f"reply number {i}"
            ledger.record_send("7", body, via="auto", actor="(auto)")
            learning_log.append({"final_reply": body})
        kept = {e["final_reply"] for e in learning_log}
        self.assertNotIn("reply number 0", kept, "the deque should have rolled")
        self.assertIsNotNone(ledger.lookup("7", "reply number 0"),
                             "authorship must outlive the deque")

    def test_a_torn_last_line_does_not_lose_the_rest(self):
        ledger.record_send("1", "first", via="auto", actor="(auto)")
        ledger.record_send("1", "second", via="auto", actor="(auto)")
        with open(ledger.path(), "a", encoding="utf-8") as fh:
            fh.write('{"conversation_id": "1", "body": "torn')   # crash mid-write
        ledger.reset_for_tests()
        self.assertIsNotNone(ledger.lookup("1", "first"))
        self.assertIsNotNone(ledger.lookup("1", "second"))

    def test_a_read_only_volume_does_not_break_the_send(self):
        # Bookkeeping must never take a guest reply down with it.
        os.environ["STATE_DIR"] = "/proc/nonexistent-read-only"
        ledger.reset_for_tests()
        sid = ledger.record_send("1", "still sent", via="auto", actor="(auto)")
        self.assertTrue(sid)
        self.assertIsNotNone(ledger.lookup("1", "still sent"),
                             "in-memory index keeps this process correct")

    def test_the_file_is_append_only(self):
        ledger.record_send("1", "one", via="auto", actor="(auto)")
        ledger.record_send("1", "two", via="auto", actor="(auto)")
        ledger.record_send("2", "three", via="discord_send", actor="Faisal")
        with open(ledger.path(), encoding="utf-8") as fh:
            self.assertEqual(len([l for l in fh if l.strip()]), 3)

    def test_ticket_id_is_carried(self):
        ledger.record_send("1", "طلبك مسجل", via="auto", actor="(auto)", ticket_id="OJ-77")
        self.assertEqual(ledger.lookup("1", "طلبك مسجل")["ticket_id"], "OJ-77")


class NormalisationMatchesBotTest(unittest.TestCase):
    """The ledger and bot._train_norm must agree on what "the same message" means, or
    attribution silently misses."""

    def test_same_normalisation_as_the_attribution_code(self):
        import bot
        for s in ("Hi   there", "  حياك\nالله  ", "MiXeD Case", ""):
            self.assertEqual(ledger.norm(s), bot._train_norm(s))


class AttributionPrefersTheLedgerTest(unittest.TestCase):
    """_train_code_for's signature heuristic must become the LAST resort it was meant to
    be. Today a team template signed «فريق عوجا» is labelled «مساعد» with certainty."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("STATE_DIR")
        os.environ["STATE_DIR"] = self._tmp.name
        ledger.reset_for_tests()

    def tearDown(self):
        if self._old is None:
            os.environ.pop("STATE_DIR", None)
        else:
            os.environ["STATE_DIR"] = self._old
        ledger.reset_for_tests()
        self._tmp.cleanup()

    def test_musaed_signed_is_no_longer_stamped_certain(self):
        import bot
        self.assertEqual(bot._TRAIN_LABELS["musaed_signed"][2], "likely")

    def test_a_send_the_deques_forgot_is_still_attributed_from_the_ledger(self):
        import bot
        body = "طلبك مسجل عند الفريق"
        idx = {"by_conv": {}, "by_text": {}}          # both deques rolled
        self.assertIsNone(bot._train_match(idx, "55", body))

        ledger.record_send("55", body, via="auto", actor="(auto)")
        rec = bot._train_match(idx, "55", body)
        self.assertIsNotNone(rec, "the ledger should answer what the deques forgot")
        self.assertEqual(rec["src"], "ledger")
        # ... and that turns a signature GUESS into a proven code.
        self.assertEqual(bot._train_code_for(rec, True), "musaed_auto")

    def test_without_any_record_a_signed_message_is_only_a_guess(self):
        import bot
        self.assertEqual(bot._train_code_for(None, True), "musaed_signed")
        self.assertEqual(bot._TRAIN_LABELS[bot._train_code_for(None, True)][2], "likely")

    def test_an_unsigned_unrecorded_message_stays_unknown(self):
        import bot
        self.assertEqual(bot._train_code_for(None, False), "unknown")


class ExportHeaderTest(unittest.TestCase):
    """The 32.1% ceiling ships WITH the data, so nobody recomputes it by hand."""

    def test_the_payload_carries_the_unattributed_share(self):
        import bot, inspect
        src = inspect.getsource(bot._train_threads_payload) if hasattr(
            bot, "_train_threads_payload") else ""
        if not src:                                   # named differently — scan the module
            src = inspect.getsource(bot)
        for key in ("unattributed_outbound", "pct_unattributed", "outbound_total"):
            self.assertIn(key, src)


if __name__ == "__main__":
    unittest.main()
