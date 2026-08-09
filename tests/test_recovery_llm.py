# -*- coding: utf-8 -*-
"""
TDD lock for recovery.llm — §3.3's model ladder and §3.4's money.

The bill is the part of this feature nobody can eyeball. If the SAR figure in the monthly
report is wrong, it is wrong quietly and forever, so the arithmetic is pinned here against
the published price list rather than trusted.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from recovery import llm  # noqa: E402

GOOD = {
    "headline_ar": "المكيف ما اشتغل من أول يوم",
    "timeline": [{"when": "اليوم الأول", "what_ar": "الضيف بلّغ عن المكيف"}],
    "quotes": ["المكيف ما يشتغل"],
    "root_cause": "maintenance",
    "physical_issue": True,
    "already_promised_ar": None,
    "unresolved_ar": "الفني ما جا",
    "severity": 4,
    "call_opener_ar": "أعتذر منك عن موضوع المكيف",
}


def scripted(*replies):
    """A fake Claude that returns each reply in turn and records how it was called."""
    calls = []

    def call(model, prompt, max_tokens, temperature):
        i = len(calls)
        calls.append({"model": model, "prompt": prompt, "max_tokens": max_tokens,
                      "temperature": temperature})
        text = replies[i] if i < len(replies) else replies[-1]
        return {"text": text, "input_tokens": 1000, "output_tokens": 200}

    call.calls = calls
    return call


class TestPricing(unittest.TestCase):

    def test_haiku_matches_the_published_rate(self):
        p = llm.price_for("claude-haiku-4-5")
        self.assertEqual((p["in"], p["out"]), (1.00, 5.00))

    def test_sonnet_uses_the_introductory_rate_before_september(self):
        p = llm.price_for("claude-sonnet-5", on_date="2026-08-06")
        self.assertEqual((p["in"], p["out"]), (2.00, 10.00))

    def test_sonnet_switches_to_full_price_on_the_first_of_september(self):
        # The intro window ends 2026-08-31. A report run in September must not keep
        # billing August's rate.
        p = llm.price_for("claude-sonnet-5", on_date="2026-09-01")
        self.assertEqual((p["in"], p["out"]), (3.00, 15.00))

    def test_cost_in_sar_is_usd_times_the_peg(self):
        # 1M in + 1M out on Haiku = $1 + $5 = $6 = 22.50 SAR
        self.assertAlmostEqual(llm.cost_sar("claude-haiku-4-5", 1_000_000, 1_000_000),
                               22.50, places=4)

    def test_a_typical_ticket_costs_fractions_of_a_halala(self):
        # ~2000 input, ~350 output on Haiku
        sar = llm.cost_sar("claude-haiku-4-5", 2000, 350)
        self.assertLess(sar, 0.02)
        self.assertGreater(sar, 0)

    def test_an_unknown_model_costs_a_visible_zero_not_a_guess(self):
        self.assertEqual(llm.cost_sar("claude-something-6", 1000, 1000), 0.0)
        self.assertIsNone(llm.price_for("claude-something-6"))


class TestExtractionLadder(unittest.TestCase):

    def test_a_clean_first_answer_costs_exactly_one_call(self):
        call = scripted(json.dumps(GOOD, ensure_ascii=False))
        clean, meta = llm.extract("الضيف: المكيف ما يشتغل", call)
        self.assertIsNotNone(clean)
        self.assertEqual(meta["calls"], 1)
        self.assertEqual(call.calls[0]["model"], llm.MODEL_PRIMARY)
        self.assertFalse(meta["escalated"])

    def test_the_cheap_model_and_parameters_are_the_ones_the_spec_names(self):
        call = scripted(json.dumps(GOOD, ensure_ascii=False))
        llm.extract("x", call)
        c = call.calls[0]
        self.assertEqual(c["model"], "claude-haiku-4-5")
        self.assertEqual(c["max_tokens"], 700)
        self.assertEqual(c["temperature"], 0)

    def test_fenced_json_is_still_accepted(self):
        call = scripted("```json\n" + json.dumps(GOOD, ensure_ascii=False) + "\n```")
        clean, meta = llm.extract("x", call)
        self.assertIsNotNone(clean)
        self.assertEqual(meta["calls"], 1)

    def test_one_bad_answer_retries_on_the_same_cheap_model(self):
        call = scripted("sorry, here you go:", json.dumps(GOOD, ensure_ascii=False))
        clean, meta = llm.extract("x", call)
        self.assertIsNotNone(clean)
        self.assertEqual(meta["calls"], 2)
        self.assertEqual(call.calls[1]["model"], llm.MODEL_PRIMARY)
        self.assertIn("invalid JSON", call.calls[1]["prompt"])
        self.assertFalse(meta["escalated"])

    def test_escalation_happens_only_after_two_failures(self):
        call = scripted("nope", "still nope", json.dumps(GOOD, ensure_ascii=False))
        clean, meta = llm.extract("x", call)
        self.assertIsNotNone(clean)
        self.assertEqual(meta["calls"], 3)
        self.assertEqual(call.calls[2]["model"], llm.MODEL_ESCALATION)
        self.assertTrue(meta["escalated"])       # §3.3: log every escalation

    def test_a_total_failure_returns_none_with_a_reason_and_stops(self):
        call = scripted("nope")
        clean, meta = llm.extract("x", call)
        self.assertIsNone(clean)
        self.assertEqual(meta["calls"], 3)       # never loops past the ladder
        self.assertTrue(meta["error"])

    def test_schema_violations_count_as_failures_not_just_bad_json(self):
        # Valid JSON, invalid severity — must still retry rather than store nonsense.
        bad = json.dumps(dict(GOOD, severity=99), ensure_ascii=False)
        call = scripted(bad, json.dumps(GOOD, ensure_ascii=False))
        clean, meta = llm.extract("x", call)
        self.assertIsNotNone(clean)
        self.assertEqual(meta["calls"], 2)

    def test_every_attempt_is_billed_not_just_the_one_that_worked(self):
        call = scripted("nope", "still nope", json.dumps(GOOD, ensure_ascii=False))
        _, meta = llm.extract("x", call)
        self.assertEqual(meta["input_tokens"], 3000)
        self.assertEqual(meta["output_tokens"], 600)
        self.assertEqual(len(meta["attempts"]), 3)
        self.assertAlmostEqual(meta["cost_sar"],
                               round(sum(a["cost_sar"] for a in meta["attempts"]), 4))

    def test_the_conversation_is_placed_into_the_prompt(self):
        call = scripted(json.dumps(GOOD, ensure_ascii=False))
        llm.extract("الضيف: المكيف ما يشتغل", call)
        self.assertIn("الضيف: المكيف ما يشتغل", call.calls[0]["prompt"])
        self.assertNotIn("<<<CONVERSATION>>>", call.calls[0]["prompt"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
