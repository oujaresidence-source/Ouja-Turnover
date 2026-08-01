"""Evidence-based 0-10 scoring for every current in-house guest."""

import unittest
from datetime import datetime, timedelta

import bot


class TestGuestScoreNormalization(unittest.TestCase):
    def test_open_escalation_caps_score_at_six(self):
        raw = {"score": 9, "reason": "", "quote": "", "resolved": False,
               "confidence": 0.9}
        got = bot._normalize_guest_score(raw, {"open_escalation": True})
        self.assertEqual(got["score"], 6)

    def test_open_promise_caps_score_at_six(self):
        raw = {"score": 10, "resolved": True, "confidence": 0.9}
        got = bot._normalize_guest_score(raw, {"open_promise": True})
        self.assertEqual(got["score"], 6)
        self.assertFalse(got["resolved"])

    def test_severe_open_complaint_caps_score_at_three(self):
        raw = {"score": 8, "severity": "angry", "resolved": False,
               "reason": "مشكلة دخول", "quote": "ما قدرت أدخل", "confidence": 0.9}
        got = bot._normalize_guest_score(raw, {"open_complaint": True})
        self.assertEqual(got["score"], 3)

    def test_objective_open_complaint_overrides_model_resolved_claim(self):
        raw = {"score": 9, "severity": "angry", "resolved": True,
               "reason": "مشكلة دخول", "quote": "ما قدرت أدخل", "confidence": 0.9}
        got = bot._normalize_guest_score(raw, {"open_complaint": True})
        self.assertEqual(got["score"], 3)
        self.assertFalse(got["resolved"])

    def test_any_open_complaint_cannot_look_perfect(self):
        raw = {"score": 10, "severity": "upset", "resolved": False,
               "reason": "مشكلة تكييف", "confidence": 0.9}
        got = bot._normalize_guest_score(raw, {"open_complaint": True})
        self.assertLessEqual(got["score"], 6)

    def test_repeated_unanswered_request_caps_score_at_five(self):
        raw = {"score": 9, "resolved": True, "confidence": 0.8}
        got = bot._normalize_guest_score(raw, {"inbound_after_last_host": 2})
        self.assertEqual(got["score"], 5)
        self.assertFalse(got["resolved"])

    def test_resolved_issue_without_positive_followup_is_not_perfect(self):
        raw = {"score": 10, "resolved": True, "severity": "upset",
               "reason": "تأخر الدخول", "confidence": 0.8}
        got = bot._normalize_guest_score(raw, {"positive_after_issue": False})
        self.assertEqual(got["score"], 9)

    def test_failed_analysis_is_unknown(self):
        got = bot._normalize_guest_score(None, {})
        self.assertIsNone(got["score"])
        self.assertEqual(got["evidence_state"], "unknown")


class TestGuestScoreFacts(unittest.TestCase):
    @staticmethod
    def msg(incoming, body, minutes_ago):
        stamp = datetime.now(bot.TZ) - timedelta(minutes=minutes_ago)
        return {"isIncoming": 1 if incoming else 0, "body": body,
                "date": stamp.strftime("%Y-%m-%d %H:%M:%S")}

    def test_unanswered_inbound_and_open_flags_are_objective_facts(self):
        msgs = [
            self.msg(False, "How can we help?", 90),
            self.msg(True, "ما قدرت أدخل", 70),
            self.msg(True, "وين الرد؟", 20),
        ]
        facts = bot._guest_score_facts(
            msgs, open_promise=True, open_escalation=True)
        self.assertEqual(facts["inbound_after_last_host"], 2)
        self.assertTrue(facts["open_promise"])
        self.assertTrue(facts["open_escalation"])
        self.assertTrue(facts["open_complaint"])
        self.assertGreaterEqual(facts["unanswered_minutes"], 19)

    def test_whole_stay_history_filters_prearrival_messages_only(self):
        msgs = [
            {"isIncoming": 1, "body": "قبل الإقامة", "date": "2026-07-31 12:00:00"},
            {"isIncoming": 1, "body": "أثناء الإقامة 1", "date": "2026-08-01 12:00:00"},
            {"isIncoming": 0, "body": "أثناء الإقامة 2", "date": "2026-08-02 12:00:00"},
        ]
        text = bot._guest_history_text(msgs, since="2026-08-01")
        self.assertNotIn("قبل الإقامة", text)
        self.assertIn("أثناء الإقامة 1", text)
        self.assertIn("أثناء الإقامة 2", text)


if __name__ == "__main__":
    unittest.main()
