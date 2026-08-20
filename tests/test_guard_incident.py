"""guard.incident — the tier that did not exist.

Before this file, bot.py contained zero occurrences of injury / blood / إصابة / نزيف /
ambulance across 66,090 lines. That is why T014 i25 — «the blood on the pillow due to my
head injury» — was answered with a 10% discount-for-review offer.
"""

import json
import os
import tempfile
import unittest

from guard import incident


class ClassifyTest(unittest.TestCase):

    def setUp(self):
        incident.reset_for_tests()

    def test_the_case_that_started_this(self):
        self.assertEqual(
            incident.classify_incident("the blood on the pillow due to my head injury"),
            incident.HARM)

    def test_harm_words(self):
        for t in ("فيه إصابة بالشقة", "طاح ابني من الدرج", "فيه دخان بالمطبخ",
                  "we need an ambulance", "my son fell and is bleeding",
                  "there is a fire in the kitchen"):
            with self.subTest(t):
                self.assertEqual(incident.classify_incident(t), incident.HARM)

    def test_habitability_words(self):
        for t in ("الباب مايفتح", "ما فيه ماء من الصبح", "مافي كهرباء",
                  "I'm locked out", "there is no water", "no electricity at all"):
            with self.subTest(t):
                self.assertEqual(incident.classify_incident(t), incident.HABITABILITY)

    def test_security_words(self):
        for t in ("القفل مكسور", "حد دخل الشقة", "broken lock", "someone entered"):
            with self.subTest(t):
                self.assertEqual(incident.classify_incident(t), incident.SECURITY)

    def test_ordinary_maintenance_is_not_an_incident(self):
        for t in ("المكيف ما يبرد", "الواي فاي ضعيف", "متى وقت الخروج؟",
                  "the AC is not cooling", "wifi is slow", "fellow guests were lovely"):
            with self.subTest(t):
                self.assertIsNone(incident.classify_incident(t))

    def test_empty_input(self):
        self.assertIsNone(incident.classify_incident(""))
        self.assertIsNone(incident.classify_incident(None))

    def test_an_electric_shock_is_harm_but_a_power_cut_is_not(self):
        # «كهربا» used to be a harm term and matched «مافي كهرباء» — a power cut — as
        # harm. Arabic terms match as substrings, so a harm word must never be a prefix
        # of an innocent longer word. Both directions are pinned here.
        for t in ("صعقتني الكهرباء", "فيه صعقة كهربائية", "electric shock", "كهربتني الفيشة"):
            with self.subTest(t):
                self.assertEqual(incident.classify_incident(t), incident.HARM)
        for t in ("مافي كهرباء", "ما فيه كهرب", "انقطعت الكهرباء"):
            with self.subTest(t):
                self.assertEqual(incident.classify_incident(t), incident.HABITABILITY)

    def test_the_highest_tier_wins(self):
        # Habitability AND harm in one message is a harm message.
        self.assertEqual(
            incident.classify_incident("ما فيه ماء وزوجتي طاحت وفيه دم"), incident.HARM)

    def test_match_detail_shows_a_human_why_it_fired(self):
        tier, phrase = incident.match_detail("there is blood on the sheets")
        self.assertEqual(tier, incident.HARM)
        self.assertTrue(phrase)


class ConfigOverrideTest(unittest.TestCase):
    """Owner-editable live, mirroring _musaed_issue_terms."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("STATE_DIR")
        os.environ["STATE_DIR"] = self._tmp.name
        incident.reset_for_tests()

    def tearDown(self):
        if self._old is None:
            os.environ.pop("STATE_DIR", None)
        else:
            os.environ["STATE_DIR"] = self._old
        incident.reset_for_tests()
        self._tmp.cleanup()

    def test_a_team_added_word_takes_effect(self):
        self.assertIsNone(incident.classify_incident("فيه عقرب بالغرفة"))
        with open(incident.path(), "w", encoding="utf-8") as fh:
            json.dump({"harm": ["عقرب", "ثعبان"]}, fh, ensure_ascii=False)
        incident.reset_for_tests()
        self.assertEqual(incident.classify_incident("فيه عقرب بالغرفة"), incident.HARM)

    def test_a_broken_edit_keeps_the_defaults(self):
        with open(incident.path(), "w", encoding="utf-8") as fh:
            fh.write("{ not json")
        incident.reset_for_tests()
        self.assertEqual(incident.classify_incident("there is blood"), incident.HARM)


class HarmHoldTest(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("STATE_DIR")
        os.environ["STATE_DIR"] = self._tmp.name
        incident.reset_for_tests()

    def tearDown(self):
        if self._old is None:
            os.environ.pop("STATE_DIR", None)
        else:
            os.environ["STATE_DIR"] = self._old
        self._tmp.cleanup()

    def test_a_hold_blocks_subsequent_ordinary_sends(self):
        self.assertIsNone(incident.held("55"))
        incident.set_hold("55", ticket_id="OJ-9", detail="head injury")
        h = incident.held("55")
        self.assertIsNotNone(h)
        self.assertEqual(h["tier"], incident.HARM)
        self.assertEqual(h["ticket_id"], "OJ-9")

    def test_only_a_named_human_clears_it(self):
        incident.set_hold("55")
        with self.assertRaises(ValueError):
            incident.clear_hold("55", actor="")
        self.assertIsNotNone(incident.held("55"))
        incident.clear_hold("55", actor="Faisal")
        self.assertIsNone(incident.held("55"))

    def test_a_hold_survives_a_restart(self):
        incident.set_hold("77", detail="fire")
        # a fresh read from disk, as a new process would do
        self.assertIsNotNone(incident.held("77"))

    def test_holds_are_per_conversation(self):
        incident.set_hold("1")
        self.assertIsNone(incident.held("2"))


class WiringTest(unittest.TestCase):
    """A tier nobody consults is a list of words in a file."""

    def test_the_card_path_classifies_the_guest_message(self):
        import inspect, bot
        src = inspect.getsource(bot.post_assistant_card)
        self.assertIn("match_detail", src)
        self.assertIn('_incident == "harm"', src)

    def test_harm_forces_escalation_and_unsafe_sentiment(self):
        import inspect, bot
        src = inspect.getsource(bot.post_assistant_card)
        i = src.index('if _incident == "harm":')
        window = src[i:i + 400]
        self.assertIn("escalate = True", window)
        self.assertIn('sentiment = "unsafe"', window)

    def test_harm_opens_an_urgent_ticket_under_its_own_category(self):
        import inspect, bot
        src = inspect.getsource(bot.post_assistant_card)
        self.assertIn('priority="urgent"', src)
        self.assertIn('category="سلامة"', src)

    def test_the_send_path_refuses_everything_while_a_hold_is_open(self):
        import inspect, bot
        src = inspect.getsource(bot.send_guest_message)
        self.assertIn("SEND_BLOCKED_HOLD", src)
        self.assertIn("safety_notice", src)
        # ... and the kill switch still comes first.
        self.assertLess(src.index("ASSISTANT_SEND_KILL"), src.index("SEND_BLOCKED_HOLD"))

    def test_a_hold_is_a_non_delivery_not_a_success(self):
        import bot
        self.assertIn(bot.SEND_BLOCKED_HOLD, bot._SEND_NOT_DELIVERED)
        self.assertTrue(bot._send_block_reason_ar(bot.SEND_BLOCKED_HOLD).strip())

    def test_the_card_says_hostaway_is_NOT_under_control(self):
        # The hold stops OUR sends only. Nobody may believe otherwise.
        import inspect, bot
        src = inspect.getsource(bot.post_assistant_card)
        self.assertIn("Hostaway", src)
        self.assertIn("يدوياً", src)


if __name__ == "__main__":
    unittest.main()
