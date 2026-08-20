"""T1 — shadow / canary / full, and the rollback rehearsal.

C2: in shadow every decision runs for real and send_guest_message() is a no-op returning
SEND_SHADOW. C4: ASSISTANT_SEND_KILL stays authoritative and is checked FIRST, so a kill
can never be masked by a mode or a guard verdict deciding something else first.
"""

import os
import tempfile
import unittest
from unittest import mock

import bot
from guard import mode


class ModeResolutionTest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old_state = os.environ.get("STATE_DIR")
        self._old_mode = os.environ.get("ASSISTANT_MODE")
        os.environ["STATE_DIR"] = self._tmp.name
        os.environ.pop("ASSISTANT_MODE", None)
        mode.reset_for_tests()

    def tearDown(self):
        for k, v in (("STATE_DIR", self._old_state), ("ASSISTANT_MODE", self._old_mode)):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        mode.reset_for_tests()
        self._tmp.cleanup()

    def test_the_default_is_shadow(self):
        self.assertEqual(mode.current(), mode.SHADOW)

    def test_an_unrecognised_mode_falls_back_to_shadow(self):
        os.environ["ASSISTANT_MODE"] = "banana"
        mode.reset_for_tests()
        self.assertEqual(mode.current(), mode.SHADOW)

    def test_the_stored_value_beats_the_env_var(self):
        # An env var winning would let a redeploy silently re-enable sending.
        os.environ["ASSISTANT_MODE"] = "full"
        mode.reset_for_tests()
        self.assertEqual(mode.current(), mode.FULL)
        mode.set_mode(mode.SHADOW, actor="faisal")
        self.assertEqual(mode.current(), mode.SHADOW)

    def test_going_quieter_never_needs_a_reason(self):
        os.environ["ASSISTANT_MODE"] = "full"
        mode.reset_for_tests()
        mode.set_mode(mode.SHADOW, actor="faisal")          # must not raise
        self.assertEqual(mode.current(), mode.SHADOW)

    def test_going_louder_demands_a_reason_on_the_record(self):
        with self.assertRaises(ValueError):
            mode.set_mode(mode.FULL, actor="faisal")
        mode.set_mode(mode.FULL, actor="faisal", reason="canary clean for 7 days")
        self.assertEqual(mode.current(), mode.FULL)

    def test_a_corrupt_mode_file_does_not_start_sending(self):
        mode.set_mode(mode.SHADOW, actor="faisal")
        with open(mode.path(), "w", encoding="utf-8") as fh:
            fh.write("{not json at all")
        self.assertEqual(mode.current(), mode.SHADOW, "a broken file must never mean 'send'")

    # ── THE ROLLBACK REHEARSAL (§4/T1): no redeploy, no restart ──────────────
    def test_flipping_back_to_shadow_takes_effect_on_the_very_next_call(self):
        mode.set_mode(mode.FULL, actor="faisal", reason="rollout")
        self.assertEqual(mode.current(), mode.FULL)
        mode.set_mode(mode.SHADOW, actor="faisal")
        # Same process, same module object, no re-import, no restart.
        self.assertEqual(mode.current(), mode.SHADOW)

    def test_a_flip_written_by_another_process_is_picked_up(self):
        # This is what a dashboard button or a manual volume edit actually does.
        import json, time
        mode.set_mode(mode.FULL, actor="faisal", reason="rollout")
        self.assertEqual(mode.current(), mode.FULL)
        time.sleep(0.01)
        with open(mode.path(), "w", encoding="utf-8") as fh:
            json.dump({"mode": "shadow", "actor": "someone else", "at": time.time()}, fh)
        os.utime(mode.path(), None)
        self.assertEqual(mode.current(), mode.SHADOW,
                         "a flip must not need a redeploy to take effect")


class CanaryTest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("STATE_DIR")
        os.environ["STATE_DIR"] = self._tmp.name
        mode.reset_for_tests()

    def tearDown(self):
        if self._old is None:
            os.environ.pop("STATE_DIR", None)
        else:
            os.environ["STATE_DIR"] = self._old
        mode.reset_for_tests()
        self._tmp.cleanup()

    def test_only_listed_listings_are_in_canary(self):
        mode.set_mode(mode.CANARY, actor="faisal", reason="phase 3",
                      canary_listing_ids=["111", "222"])
        self.assertTrue(mode.in_canary("111"))
        self.assertTrue(mode.in_canary(222))
        self.assertFalse(mode.in_canary("333"))
        self.assertFalse(mode.in_canary(None))


class SendPathTest(unittest.TestCase):
    """send_guest_message must not touch Hostaway unless it really is sending."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("STATE_DIR")
        os.environ["STATE_DIR"] = self._tmp.name
        mode.reset_for_tests()

    def tearDown(self):
        if self._old is None:
            os.environ.pop("STATE_DIR", None)
        else:
            os.environ["STATE_DIR"] = self._old
        mode.reset_for_tests()
        self._tmp.cleanup()

    def test_shadow_returns_the_sentinel_and_calls_no_api(self):
        mode.set_mode(mode.SHADOW, actor="test")
        with mock.patch.object(bot, "api_post") as post:
            r = bot.send_guest_message("1", "حياك الله", "email")
        self.assertEqual(r, bot.SEND_SHADOW)
        post.assert_not_called()

    def test_canary_stays_silent_for_a_listing_not_on_the_list(self):
        mode.set_mode(mode.CANARY, actor="t", reason="r", canary_listing_ids=["999"])
        with mock.patch.object(bot, "api_post") as post:
            r = bot.send_guest_message("1", "hi", "email", listing_id="123")
        self.assertEqual(r, bot.SEND_SHADOW)
        post.assert_not_called()

    def test_canary_sends_for_a_listing_on_the_list(self):
        mode.set_mode(mode.CANARY, actor="t", reason="r", canary_listing_ids=["123"])
        with mock.patch.object(bot, "api_post", return_value={"id": 1}) as post:
            r = bot.send_guest_message("1", "hi there", "email", listing_id="123")
        self.assertEqual(r, {"id": 1})
        post.assert_called_once()

    def test_full_sends_exactly_as_before(self):
        mode.set_mode(mode.FULL, actor="t", reason="r")
        with mock.patch.object(bot, "api_post", return_value={"id": 7}) as post:
            r = bot.send_guest_message("1", "a normal reply", "email")
        self.assertEqual(r, {"id": 7})
        post.assert_called_once()

    def test_the_kill_switch_is_checked_BEFORE_the_mode(self):
        # C4: a kill must never be reported as "shadow" — the team has to see the kill.
        mode.set_mode(mode.SHADOW, actor="t")
        with mock.patch.object(bot, "ASSISTANT_SEND_KILL", True), \
             mock.patch.object(bot, "api_post") as post:
            r = bot.send_guest_message("1", "anything", "email")
        self.assertEqual(r, bot.SEND_BLOCKED_KILL)
        post.assert_not_called()

    def test_the_guard_blocks_a_code_even_in_full_mode(self):
        mode.set_mode(mode.FULL, actor="t", reason="r")
        with mock.patch.object(bot, "api_post") as post:
            r = bot.send_guest_message("1", "كود الدخول للشقة: 7256172263#", "email")
        self.assertEqual(r, bot.SEND_BLOCKED_GUARD)
        post.assert_not_called()

    def test_a_delivered_send_is_written_to_the_ledger(self):
        from guard import ledger
        ledger.reset_for_tests()
        mode.set_mode(mode.FULL, actor="t", reason="r")
        with mock.patch.object(bot, "api_post", return_value={"id": 3}):
            bot.send_guest_message("77", "رد للضيف", "email", via="auto", actor="(auto)")
        rec = ledger.lookup("77", "رد للضيف")
        self.assertIsNotNone(rec, "every delivered send must be attributable")
        self.assertEqual(rec["via"], "auto")

    def test_a_shadow_send_is_NOT_written_to_the_ledger(self):
        from guard import ledger
        ledger.reset_for_tests()
        mode.set_mode(mode.SHADOW, actor="t")
        with mock.patch.object(bot, "api_post"):
            bot.send_guest_message("78", "ما انرسلت", "email")
        self.assertIsNone(ledger.lookup("78", "ما انرسلت"))

    def test_a_shadow_decision_is_logged(self):
        from guard import shadow
        mode.set_mode(mode.SHADOW, actor="t")
        with mock.patch.object(bot, "api_post"):
            bot.send_guest_message("79", "would have said this", "email", listing_id="5")
        rows = shadow.read_all()
        self.assertTrue(any(r["conversation_id"] == "79"
                            and r["would_send_body"] == "would have said this"
                            for r in rows))


class CallSitesTest(unittest.TestCase):
    """No call site may treat a non-delivery as success."""

    def test_every_undelivered_outcome_is_in_the_shared_tuple(self):
        for sentinel in (bot.SEND_BLOCKED_KILL, bot.SEND_SHADOW, bot.SEND_BLOCKED_GUARD):
            self.assertIn(sentinel, bot._SEND_NOT_DELIVERED)

    def test_no_call_site_still_compares_against_the_kill_switch_alone(self):
        import inspect
        src = inspect.getsource(bot)
        self.assertNotIn("== SEND_BLOCKED_KILL", src,
                         "a site comparing only to the kill switch treats shadow as sent")

    def test_each_outcome_has_plain_arabic_for_the_team(self):
        for sentinel in bot._SEND_NOT_DELIVERED:
            self.assertTrue(bot._send_block_reason_ar(sentinel).strip())


if __name__ == "__main__":
    unittest.main()
