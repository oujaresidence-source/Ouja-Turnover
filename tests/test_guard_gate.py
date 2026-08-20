"""guard.gate — the silence decision. Synthetic threads, no network.

54.8% of «مساعد»'s messages had no guest message before them. These are the shapes that
produced that number, rebuilt from the export.
"""

import unittest

from guard.gate import Decision, should_speak

NOW = 1_000_000.0
MIN = 60.0


def guest(body, ago_min=0):
    return {"isIncoming": 1, "body": body, "ts": NOW - ago_min * MIN}


def host(body, ago_min=0):
    return {"isIncoming": 0, "body": body, "ts": NOW - ago_min * MIN}


# Stand-in for bot._looks_automated: our templates all carry this marker in the fixtures.
def looks_automated(body):
    return "[TEMPLATE]" in (body or "")


def decide(msgs, guest_idx=None, claimed=False, is_ours=None, **kw):
    if guest_idx is None:
        guest_idx = max((i for i, m in enumerate(msgs) if m.get("isIncoming")), default=None)
    return should_speak(msgs=msgs, guest_idx=guest_idx, claimed=claimed, now=NOW,
                        looks_automated=looks_automated, is_ours=is_ours, **kw)


class SpeaksWhenItShouldTest(unittest.TestCase):
    """The gate has to let the assistant work, or it will simply be turned off."""

    def test_a_normal_unanswered_question_is_answered(self):
        d = decide([host("أهلاً", 60), guest("متى وقت الخروج؟", 2)])
        self.assertEqual(d, Decision(True, "ok"))

    def test_a_template_firing_after_the_guest_does_not_silence_us(self):
        # The guest asked and is still waiting; a scheduled template landing on top of
        # the question does not answer it. THIS is the case the assistant exists for.
        d = decide([guest("أي دور الشقة؟", 5), host("[TEMPLATE] welcome to Ouja", 4)])
        self.assertEqual(d, Decision(True, "ok"))


class StaysSilentTest(unittest.TestCase):

    def test_a_human_reply_after_the_guest_closes_it(self):
        # T007 i13 -> i14: the guest asked which floor, a teammate answered «الدور الاول».
        d = decide([guest("which floor?", 20), host("الدور الاول", 18)])
        self.assertEqual(d, Decision(False, "already_answered"))

    def test_our_own_reply_after_the_guest_is_an_echo_not_an_answer(self):
        # T014 i17 -> i18: we spoke, then spoke again.
        ours = host("رديت عليك قبل شوي", 18)
        d = decide([guest("أي دور؟", 20), ours], is_ours=lambda m: m is ours)
        self.assertEqual(d, Decision(False, "own_echo"))

    def test_a_claimed_conversation_is_never_ours_to_answer(self):
        # bot.py checks this in the escalate branch only — can_auto (11806) does not.
        d = decide([guest("عندي مشكلة", 1)], claimed=True)
        self.assertEqual(d, Decision(False, "claimed"))

    def test_a_teammate_active_moments_ago_holds_the_thread(self):
        # T006 i11: a human wrote «تنورنا» and the bot piped up on top of them.
        d = decide([host("تنورنا 🤍", 4), guest("تسلم", 2)])
        self.assertEqual(d, Decision(False, "human_active"))

    def test_a_teammate_from_yesterday_does_not_hold_the_thread(self):
        d = decide([host("تنورنا 🤍", 60 * 26), guest("متى الخروج؟", 2)])
        self.assertEqual(d, Decision(True, "ok"))

    def test_a_thread_with_no_guest_message_at_all_is_a_template_echo(self):
        # T010 i4 / T003 i5 / T009 i4 — speaking into our own automation.
        d = decide([host("[TEMPLATE] welcome", 10)], guest_idx=None)
        self.assertEqual(d, Decision(False, "template_echo"))

    def test_a_cold_question_under_a_template_is_a_template_echo_not_a_prompt(self):
        # Guest asked yesterday, only a template followed, nobody is waiting now.
        d = decide([guest("سؤال قديم", 60 * 20), host("[TEMPLATE] reminder", 60 * 2)])
        self.assertEqual(d, Decision(False, "template_echo"))

    def test_a_cold_question_with_nothing_after_it_is_stale(self):
        d = decide([guest("سؤال قديم", 60 * 20)])
        self.assertEqual(d, Decision(False, "stale"))


class PrecedenceTest(unittest.TestCase):

    def test_claimed_beats_everything(self):
        d = decide([guest("مشكلة", 1)], claimed=True)
        self.assertEqual(d.reason, "claimed")

    def test_a_template_after_the_guest_is_not_an_answer(self):
        d = decide([guest("سؤال", 3), host("[TEMPLATE] auto", 2)])
        self.assertTrue(d.speak)

    def test_never_raises_on_junk(self):
        self.assertFalse(should_speak(msgs=None, guest_idx=5, claimed=False, now=NOW,
                                      looks_automated=looks_automated).speak)
        self.assertFalse(should_speak(msgs=[{}], guest_idx=99, claimed=False, now=NOW,
                                      looks_automated=looks_automated).speak)


class RegressionTest(unittest.TestCase):
    """The three sequences from the audit. Each one must now be silent."""

    def test_T006_i11_bot_spoke_over_a_human(self):
        msgs = [guest("وصلنا", 30), host("تنورنا 🤍", 5), guest("🤍", 3)]
        self.assertFalse(decide(msgs).speak)

    def test_T010_i4_bot_answered_a_welcome_template(self):
        msgs = [host("[TEMPLATE] welcome to Ouja", 12)]
        self.assertEqual(decide(msgs, guest_idx=None).reason, "template_echo")

    def test_T014_i18_bot_replied_to_itself(self):
        ours = host("تم رفع طلبك", 6)
        msgs = [guest("فيه دم على المخدة", 10), ours]
        self.assertEqual(decide(msgs, is_ours=lambda m: m is ours).reason, "own_echo")


class WiringTest(unittest.TestCase):
    """The gate is only worth anything if it actually reaches the send decision."""

    def test_conv_to_item_attaches_a_decision(self):
        import inspect, bot
        src = inspect.getsource(bot._conv_to_item)
        self.assertIn("_gate_decision", src)
        self.assertIn('"_gate"', src)

    def test_ops_capture_still_runs_for_every_conversation(self):
        # C5: response-time capture must keep running for EVERY scanned conversation,
        # gate-silenced ones included. It sits before every early return and the gate
        # was added after it — assert the order, not the intention.
        import inspect, bot
        src = inspect.getsource(bot._conv_to_item)
        self.assertLess(src.index("_ops_capture_conversation"), src.index("_gate_decision"),
                        "the gate must never be able to skip response-time capture")

    def test_can_auto_consults_both_the_gate_and_the_claim(self):
        import inspect, bot
        src = inspect.getsource(bot.post_assistant_card)
        i = src.index("can_auto = (")
        window = src[i:i + 600]
        self.assertIn("_gate", window)
        self.assertIn("_claimed_convos", window,
                      "an auto-send could land on a conversation a human already took")

    def test_a_silent_decision_is_shown_on_the_card_and_counted(self):
        import inspect, bot
        src = inspect.getsource(bot.post_assistant_card)
        self.assertIn("🔇 صامت", src)
        self.assertIn('metric_bump("silent_total")', src)

    def test_the_send_time_recheck_exists_and_counts_collisions(self):
        import inspect, bot
        self.assertTrue(callable(bot._gate_recheck))
        src = inspect.getsource(bot.post_assistant_card)
        self.assertIn("_gate_recheck", src)
        self.assertIn('metric_bump("collisions_avoided")', src)

    def test_every_reason_has_arabic_for_the_team(self):
        import bot
        from guard.gate import REASONS
        for r in REASONS:
            if r == "ok":
                continue
            self.assertIn(r, bot._GATE_REASON_AR)
            self.assertTrue(bot._GATE_REASON_AR[r].strip())

    def test_a_broken_gate_does_not_become_an_accidental_kill_switch(self):
        import bot
        from unittest import mock as _m
        with _m.patch.object(bot, "_guard_gate") as g:
            g.should_speak.side_effect = RuntimeError("boom")
            self.assertIsNone(bot._gate_decision("1", [{"body": "hi"}], 0))


if __name__ == "__main__":
    unittest.main()
