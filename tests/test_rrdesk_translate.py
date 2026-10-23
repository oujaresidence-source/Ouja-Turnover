# -*- coding: utf-8 -*-
"""
«طلبات سام» translation — cost and faithfulness. A fake model stands in for Haiku (no network);
a temporary brain.db holds the cache and counters.

Locked: phrase table and cache make zero calls; glossary terms reach the prompt; the JSON
contract (bad output = safe «not a request»); the daily cap; a timeout ends in ⚠️ + an event,
never an exception; numbers, codes and mentions survive; code blocks / our own / bot English
are skipped and bot Arabic is translated.

Run: python3 -m unittest tests.test_rrdesk_translate
"""

import datetime
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb                          # noqa: E402
from ops import engine as oeng                        # noqa: E402
from rrdesk import db, engine, flow, translate        # noqa: E402
from rrdesk.host import HOST                          # noqa: E402

RIY = oeng.tz()
NOW = datetime.datetime(2026, 10, 20, 14, 0, tzinfo=RIY)


class FakeModel:
    """Answers like the Messages API. `reply` is a function(payload) -> text."""

    def __init__(self, reply=None, fail=0):
        self.calls = []
        self.reply = reply or (lambda p: json.dumps({"translation": "TRANSLATED"}))
        self.fail = fail

    def __call__(self, payload):
        self.calls.append(payload)
        if self.fail:
            self.fail -= 1
            raise TimeoutError("read timed out")
        return {"content": [{"type": "text", "text": self.reply(payload)}],
                "usage": {"input_tokens": 400, "output_tokens": 60}}


def user_text(payload):
    c = payload["messages"][0]["content"]
    return c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rrdesk_tr_")
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        db.reset_init_cache()
        translate.reset_glossary_cache()
        self.env = {k: os.environ.pop(k, None) for k in ("RRDESK_DAILY_CALLS", "ANTHROPIC_API_KEY")}

    def tearDown(self):
        for k, v in self.env.items():
            if v is not None:
                os.environ[k] = v


class PhraseAndCache(Base):
    def test_phrase_table_makes_no_call(self):
        fm = FakeModel()
        r = translate.translate_text("تم", "ar2en", now=NOW, poster=fm)
        self.assertEqual((r["translation"], r["source"]), ("Done.", "phrase"))
        self.assertEqual(fm.calls, [])
        self.assertEqual(translate.calls_today(NOW), 0)

    def test_second_identical_message_is_free(self):
        fm = FakeModel()
        a = translate.translate_text("الكنب فيه بقعة كبيرة", "ar2en", now=NOW, poster=fm)
        b = translate.translate_text("الكنب فيه بقعة كبيرة!", "ar2en", now=NOW, poster=fm)
        self.assertEqual(len(fm.calls), 1)
        self.assertEqual((a["source"], b["source"]), ("model", "cache"))
        self.assertEqual(b["translation"], "TRANSLATED")
        self.assertGreater(a["cost_usd"], 0)
        self.assertEqual(b["cost_usd"], 0)

    def test_cost_uses_published_haiku_price(self):
        self.assertAlmostEqual(translate.cost_usd(1000000, 1000000), 6.0)


class Glossary(Base):
    def test_terms_in_the_message_reach_the_prompt(self):
        db.set_setting("glossary", json.dumps([{"term_ar": "تعويض", "term_en": "reimbursement"},
                                               {"term_ar": "مكيف", "term_en": "AC unit"}]))
        translate.reset_glossary_cache()
        fm = FakeModel()
        translate.translate_text("ابي تعويض عن المكيف اللي انكسر", "ar2en", now=NOW, poster=fm)
        prompt = user_text(fm.calls[0])
        self.assertIn("تعويض = reimbursement", prompt)
        self.assertNotIn("AC unit", prompt)        # «المكيف» ≠ «مكيف» as a whole word

    def test_glossary_version_changes_the_cache_key(self):
        fm = FakeModel()
        translate.translate_text("الضيف كسر الطاولة", "ar2en", now=NOW, poster=fm)
        db.set_setting("glossary", json.dumps([{"term_ar": "طاولة", "term_en": "table"}]))
        translate.reset_glossary_cache()
        translate.translate_text("الضيف كسر الطاولة", "ar2en", now=NOW, poster=fm)
        self.assertEqual(len(fm.calls), 2)


class Contract(Base):
    def test_classification_contract(self):
        fm = FakeModel(lambda p: json.dumps({
            "translation": "أرسل الفاتورة", "is_request": True, "confidence": 0.93,
            "asks": ["invoice", "bogus"], "urgent": False, "addressed_to_hint": "Nasser",
            "summary_en": "Send the invoice", "summary_ar": "أرسل الفاتورة"}))
        r = translate.translate_text("Please send the invoice", "en2ar", classify=True, now=NOW, poster=fm)
        c = r["classify"]
        self.assertTrue(c["is_request"])
        self.assertEqual(c["asks"], ["invoice"])
        self.assertAlmostEqual(c["confidence"], 0.93)
        self.assertIn("is_request", user_text(fm.calls[0]))

    def test_garbage_classification_is_the_safe_answer(self):
        fm = FakeModel(lambda p: json.dumps({"translation": "x", "is_request": "yes",
                                             "confidence": "high"}))
        c = translate.translate_text("hello there team", "en2ar", classify=True, now=NOW, poster=fm)["classify"]
        self.assertFalse(c["is_request"])
        self.assertEqual(c["confidence"], 0.0)

    def test_fenced_json_is_accepted_and_no_translation_fails(self):
        fm = FakeModel(lambda p: "```json" + chr(10) + '{"translation": "ok then"}' + chr(10) + "```")
        self.assertEqual(translate.translate_text("طيب خلاص", "ar2en", now=NOW, poster=fm)["translation"],
                         "ok then")
        fm2 = FakeModel(lambda p: '{"nope": 1}')
        with self.assertRaises(translate.TranslateFailed):
            translate.translate_text("وش السالفة", "ar2en", now=NOW, poster=fm2)


class Faithful(Base):
    def test_numbers_codes_mentions_survive(self):
        def reply(p):
            # a model that "rounds" the amount and drops the mention must not win
            return json.dumps({"translation": "The guest ⟦1⟧ broke the AC, cost ⟦0⟧"})
        fm = FakeModel(reply)
        r = translate.translate_text("الضيف كسر المكيف التكلفة 3,722 ريال <@123456789012345678> HMPDWX82SK",
                                     "ar2en", now=NOW, poster=fm)
        t = r["translation"]
        self.assertIn("3,722", t)
        self.assertIn("<@123456789012345678>", t)   # put back even though the model dropped it
        self.assertIn("HMPDWX82SK", t)
        sent = user_text(fm.calls[0])
        self.assertNotIn("3,722", sent)
        self.assertNotIn("HMPDWX82SK", sent)

    def test_embed_keeps_numbers_and_structure(self):
        def reply(p):
            body = user_text(p)
            obj = json.loads(body[body.index("{"):])
            obj["title"] = "Claim " + obj["title"].split(" ")[-1]
            obj["fields"] = [{"name": "Amount", "value": f["value"]} for f in obj["fields"]]
            return json.dumps(obj, ensure_ascii=False)
        fm = FakeModel(reply)
        emb = {"title": "طلب تعويض RR #047", "description": "صار له 24 ساعة",
               "fields": [{"name": "المبلغ المطلوب", "value": "3,722 ر.س"}]}
        out, meta = translate.translate_embed(emb, "ar2en", now=NOW, poster=fm)
        self.assertIn("047", out["title"])
        self.assertEqual(out["fields"][0]["value"].split(" ")[0], "3,722")
        self.assertEqual(meta["source"], "model")
        out2, meta2 = translate.translate_embed(emb, "ar2en", now=NOW, poster=fm)
        self.assertEqual(meta2["source"], "cache")      # same template paid once
        self.assertEqual(len(fm.calls), 1)

    def test_split_long_text(self):
        parts = translate.split_for_embeds(("word " * 2000).strip(), 4000)
        self.assertTrue(all(len(p) <= 4000 for p in parts))
        self.assertEqual(" ".join(parts).count("word"), 2000)


class Cap(Base):
    def test_cap_stops_calls(self):
        os.environ["RRDESK_DAILY_CALLS"] = "2"
        fm = FakeModel()
        translate.translate_text("رسالة أولى طويلة", "ar2en", now=NOW, poster=fm)
        translate.translate_text("رسالة ثانية طويلة", "ar2en", now=NOW, poster=fm)
        with self.assertRaises(translate.CapReached):
            translate.translate_text("رسالة ثالثة طويلة", "ar2en", now=NOW, poster=fm)
        self.assertEqual(len(fm.calls), 2)
        # phrases and cache still work past the cap
        self.assertEqual(translate.translate_text("شكرا", "ar2en", now=NOW, poster=fm)["source"], "phrase")
        self.assertEqual(translate.translate_text("رسالة أولى طويلة", "ar2en", now=NOW, poster=fm)["source"],
                         "cache")
        # a new day resets
        self.assertFalse(translate.cap_reached(NOW + datetime.timedelta(days=1)))

    def test_stored_cap_wins_over_env(self):
        os.environ["RRDESK_DAILY_CALLS"] = "5"
        db.set_setting("daily_calls", "0")
        self.assertTrue(translate.cap_reached(NOW))


class Timeout(Base):
    def test_one_retry_then_failure(self):
        fm = FakeModel(fail=1)
        self.assertEqual(translate.translate_text("الحين جاي", "ar2en", now=NOW, poster=fm)["source"], "model")
        self.assertEqual(len(fm.calls), 2)
        fm2 = FakeModel(fail=5)
        with self.assertRaises(translate.TranslateFailed):
            translate.translate_text("وش صار بالموضوع", "ar2en", now=NOW, poster=fm2)
        self.assertEqual(len(fm2.calls), 2)


class FlowLevel(Base):
    """The listener level: timeout → ⚠️ + event and no raise; skip rules."""

    def setUp(self):
        super().setUp()
        HOST.rr_record = lambda cid: {"kind": "rr", "seq": 47, "code": "HMWR4AS5WC",
                                      "status": "new"} if cid == "900" else None
        HOST.now = lambda: NOW
        HOST.employees = lambda: []
        HOST.lead_id = lambda: ""
        HOST.once_claim = lambda name, ttl=None: True
        db.set_setting("sam_ids", "555")
        self._orig = translate.call_model

    def tearDown(self):
        translate.call_model = self._orig
        super().tearDown()

    def msg(self, mid, text, author="111", is_bot=False, embeds=None, is_self=False):
        return {"id": mid, "channel_id": "900", "parent_id": None, "author_id": author,
                "author_name": "Nasser", "is_bot": is_bot, "is_self": is_self, "text": text,
                "embeds": embeds or [], "media": [], "voice": False, "mention_ids": [],
                "reference_author_id": None, "role_mentioned": False, "at": NOW}

    def test_timeout_reacts_and_logs_without_raising(self):
        def boom(*a, **k):
            raise translate.TranslateFailed("timeout")
        translate.call_model = boom
        rep = flow.on_message(self.msg("m1", "الفاتورة بالطريق"))
        self.assertEqual(rep["translation"], "failed")
        ob = db.outbox("warn:m1")
        self.assertEqual((ob["kind"], ob["payload"]["emoji"]), ("react", "⚠️"))
        self.assertTrue(db.events(kinds=["tr_failed"]))
        self.assertIsNone(db.translation("m1"))          # claim released → an edit may retry

    def test_skips(self):
        translate.call_model = lambda *a, **k: ('{"translation": "x"}', 1, 1)
        cb = "```" + chr(10) + "copy for the owner" + chr(10) + "```"
        self.assertEqual(flow.on_message(self.msg("m2", cb, is_bot=True))["translation"], "skip:code_block")
        self.assertEqual(flow.on_message(self.msg("m3", "RR TICKET — #047 Reservation code", is_bot=True))
                         ["translation"], "skip:bot_english")
        self.assertEqual(flow.on_message(self.msg("m4", "x" + engine.INVISIBLE_MARK, is_self=True,
                                                  is_bot=True))["translation"], "skip:own")
        self.assertEqual(flow.on_message(self.msg("m5", "👍"))["translation"], "skip:trivial")

    def test_bot_arabic_is_translated_for_sam(self):
        translate.call_model = lambda *a, **k: ('{"translation": "Close-out summary waiting 24 hours"}', 10, 5)
        rep = flow.on_message(self.msg("m6", "ملخص إغلاق RR #47 صار له 24 ساعة ينتظر الاعتماد", is_bot=True))
        self.assertEqual(rep["translation"], "model")
        p = db.outbox("tr:m6")["payload"]
        self.assertEqual(p["reply_to"], "m6")
        self.assertEqual(p["mentions"], "none")
        self.assertEqual(p["embeds"][0]["footer"], "Auto-translation · AR→EN")
        self.assertIn("24", p["embeds"][0]["description"])

    def test_bot_arabic_embed_card(self):
        def fake(content, max_tokens=0, system=None, poster=None):
            body = content if isinstance(content, str) else ""
            obj = json.loads(body[body.index("{"):])
            obj["title"] = "Reimbursement RR #" + obj["title"].split("#")[-1]   # keeps ⟦0⟧
            return json.dumps(obj, ensure_ascii=False), 50, 20
        translate.call_model = fake
        emb = {"title": "طلب تعويض RR #047", "description": "هذا تعويض سابق", "fields": [], "footer": ""}
        rep = flow.on_message(self.msg("m7", "", is_bot=True, embeds=[emb]))
        self.assertEqual(rep["translation"], "model")
        self.assertEqual(db.outbox("tr:m7")["payload"]["embeds"][0]["title"], "Reimbursement RR #047")


if __name__ == "__main__":
    unittest.main()
