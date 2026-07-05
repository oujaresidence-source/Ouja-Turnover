# tests/test_finchat_answer.py
# -*- coding: utf-8 -*-
"""finchat.answer — confidence routing: Haiku high-conf answers direct; low-conf retries
Sonnet once; still-low offers escalation. Daily cap + kill behavior."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb
from finchat import db as fdb
from finchat import answer as fans


def fake_claude(replies):
    """Returns a claude_text(system, user, max_tokens, model) stub popping canned replies."""
    calls = []

    def _c(system, user, max_tokens=700, model=None):
        calls.append({"model": model, "user": user})
        return replies.pop(0) if replies else None
    _c.calls = calls
    return _c


class TestAnswer(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.mkdtemp(prefix="fcans_")
        bdb.set_db_path_for_tests(os.path.join(tmp, "brain.db"))
        fdb.reset_init_cache()
        fdb.kb_upsert("كيف اعتمد مصروف؟", "من المصاريف اضغط اعتماد",
                      links=[{"label_ar": "المصاريف", "route": "#exp"}], tags="مصاريف اعتماد")
        fans.CFG.update({"conf": 0.6, "model_fast": "fast-m", "model_smart": "smart-m",
                         "daily_cap": 5, "enabled": True})

    def test_high_confidence_haiku_only(self):
        c = fake_claude([json.dumps({"answer": "اضغط اعتماد", "confidence": 0.9,
                                     "links": [{"label_ar": "المصاريف", "route": "#exp"}]})])
        fans.CFG["claude"] = c
        r = fans.answer_question("acc1", "كيف اعتمد مصروف")
        self.assertTrue(r["ok"])
        self.assertEqual(r["model"], "fast-m")
        self.assertFalse(r["esc_offer"])
        self.assertEqual(len(c.calls), 1)
        self.assertEqual(r["links"][0]["route"], "#exp")
        # history persisted: user + bot
        roles = [m["role"] for m in fdb.msgs_for("acc1")]
        self.assertEqual(roles[-2:], ["user", "bot"])

    def test_low_confidence_retries_smart_once(self):
        c = fake_claude([json.dumps({"answer": "مم", "confidence": 0.3, "links": []}),
                         json.dumps({"answer": "الجواب الاكيد", "confidence": 0.85, "links": []})])
        fans.CFG["claude"] = c
        r = fans.answer_question("acc1", "سؤال غامض عن الاعتماد")
        self.assertEqual(len(c.calls), 2)
        self.assertEqual(c.calls[1]["model"], "smart-m")
        self.assertEqual(r["answer"], "الجواب الاكيد")
        self.assertFalse(r["esc_offer"])

    def test_still_low_offers_escalation(self):
        c = fake_claude([json.dumps({"answer": "؟", "confidence": 0.2, "links": []}),
                         json.dumps({"answer": "؟؟", "confidence": 0.3, "links": []})])
        fans.CFG["claude"] = c
        r = fans.answer_question("acc1", "شي ما له علاقة")
        self.assertTrue(r["esc_offer"])

    def test_unparseable_reply_treated_as_low_conf(self):
        c = fake_claude(["not json at all",
                         json.dumps({"answer": "تمام", "confidence": 0.9, "links": []})])
        fans.CFG["claude"] = c
        r = fans.answer_question("acc1", "كيف اعتمد")
        self.assertEqual(r["answer"], "تمام")

    def test_json_wrapped_in_prose_is_extracted(self):
        c = fake_claude(['هذا الجواب: {"answer": "زين", "confidence": 0.9, "links": []} انتهى'])
        fans.CFG["claude"] = c
        r = fans.answer_question("acc1", "كيف اعتمد")
        self.assertEqual(r["answer"], "زين")

    def test_daily_cap_blocks(self):
        fans.CFG["claude"] = fake_claude(
            [json.dumps({"answer": "ج", "confidence": 0.9, "links": []}) for _ in range(9)])
        fans.CFG["daily_cap"] = 2
        fans.answer_question("acc9", "س1")
        fans.answer_question("acc9", "س2")
        r = fans.answer_question("acc9", "س3")
        self.assertEqual(r.get("error"), "daily_cap")

    def test_api_dead_returns_api_error(self):
        fans.CFG["claude"] = fake_claude([None, None])
        r = fans.answer_question("acc1", "كيف اعتمد")
        self.assertEqual(r.get("error"), "api_error")


if __name__ == "__main__":
    unittest.main()
