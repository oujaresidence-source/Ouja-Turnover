# -*- coding: utf-8 -*-
"""The WhatsApp «reader» (hatif.brain + answers + firewall + service.shadow) — offline.

Locked here:
  * the bank: every seeded answer passes the firewall (no counts, no «تم الحجز», no stray price)
  * firewall: blocks COUNT / BOOKED / READY / unknown PRICE / blanks; passes a clean reply
  * brain: the AI only routes — the reply is the bank text word for word; unknown ids, low
    confidence, an unlocatable place, or the AI being down all become «human»
  * dates in the message always use the live search reply (same as the site)
  * service.shadow is SILENT: it never sends, never assigns, posts once to Discord, dedups,
    ignores our own messages and button taps, and HATIF_AI=0 turns it off

Run: python3 -m unittest tests.test_hatif_reader
"""
import datetime
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb                                          # noqa: E402
from hatif import answers, brain, client, db, firewall, host, service  # noqa: E402

TODAY = datetime.date(2026, 11, 22)        # a Sunday
NOW = datetime.datetime(2026, 11, 22, 14, 0)
CH = "chan-1"
HOODS = [("al_malqa", "الملقا", "Al Malqa"), ("al_nuzha", "النزهة", "Al Nuzha")]
CATALOG = [
    {"id": 483841, "name_ar": "سطح خاص وشاشة 80\" | 3 غرف عصرية", "name_en": "Private Rooftop & 80\" Living",
     "area": "العارض", "lat": 24.8856, "lng": 46.6290},
    {"id": 578603, "name_ar": "غرفتين · إطلالة على برج المملكة", "name_en": "Skyline 2BR Kingdom Tower view",
     "area": "العليا", "lat": 24.7096, "lng": 46.6740},
    {"id": 592596, "name_ar": "ستوديو فاخر | النزهة | دخول ذاتي", "name_en": "Ouja Luxury Studio",
     "area": "النزهة", "lat": 24.7583, "lng": 46.7100},
]


def search_ok(ci, co, guests, typ, hood):
    return {"avail_error": False, "results": [
        {"id": 592596, "name_ar": "ستوديو فاخر | النزهة", "area": "النزهة", "available": True,
         "est_total": 530, "est_avg": 265}]}


def fixed(d):
    return lambda system, user: d


class BankTests(unittest.TestCase):
    def setUp(self):
        answers.reset_for_tests()

    def test_every_seed_answer_is_clean(self):
        b = answers.bank()
        allowed = set()
        for a in b.values():
            allowed |= firewall.money_in(a["text"])
        for k, a in b.items():
            self.assertEqual(firewall.check(a["text"], allowed), [], k)
            self.assertNotIn("{{", a["text"], k)

    def test_human_answer_required(self):
        with self.assertRaises(ValueError):
            answers.validate({"answers": {"prices": {"text": "x"}}})

    def test_override_wins_and_bad_edit_keeps_last_good(self):
        tmp = tempfile.mkdtemp()
        old = os.environ.get("STATE_DIR")
        os.environ["STATE_DIR"] = tmp
        try:
            path = os.path.join(tmp, "hatif_answers.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"answers": {"human": {"kind": "human", "text": "H"},
                                       "pets": {"text": "لا حيوانات"}}}, f, ensure_ascii=False)
            self.assertEqual(answers.bank()["pets"]["text"], "لا حيوانات")
            with open(path, "w", encoding="utf-8") as f:
                f.write("{broken")
            os.utime(path, (1, 1))
            self.assertEqual(answers.bank()["pets"]["text"], "لا حيوانات")
        finally:
            answers.reset_for_tests()
            if old is None:
                os.environ.pop("STATE_DIR", None)
            else:
                os.environ["STATE_DIR"] = old


class FirewallTests(unittest.TestCase):
    def test_blocks(self):
        self.assertIn("COUNT", firewall.check("عندنا 53 شقة بالرياض"))
        self.assertIn("COUNT", firewall.check("في الملقا ٩ شقق"))
        self.assertIn("BOOKED", firewall.check("تم الحجز بنجاح"))
        self.assertIn("READY", firewall.check("الشقة جاهزة الحين"))
        self.assertIn("PRICE", firewall.check("السعر 450 ر.س", allowed_money=[300]))
        self.assertIn("PLACEHOLD", firewall.check("السعر None"))

    def test_clean_reply_passes(self):
        self.assertEqual(firewall.check("• ستوديو | النزهة — 530 ر.س (265 لليلة)", [530]), [])
        self.assertEqual(firewall.check("سطح خاص | 3 غرف عصرية"), [])


class BrainTests(unittest.TestCase):
    def setUp(self):
        answers.reset_for_tests()
        self.bank = answers.bank()

    def run_(self, text, d):
        dec = brain.decide(text, fixed(d), self.bank)
        return dec, brain.compose(text, TODAY, HOODS, dec, self.bank, CATALOG, search_ok, "oujares.com")

    def test_answer_is_bank_text_word_for_word(self):
        dec, c = self.run_("عندكم ستوديو لعزاب؟", {"door": "answer", "answers": ["singles"], "confidence": 0.9})
        self.assertEqual(c["reply"], self.bank["singles"]["text"])
        self.assertEqual(c["violations"], [])

    def test_two_answers_joined(self):
        dec, c = self.run_("التدخين؟ والحيوانات؟", {"door": "answer", "answers": ["smoking", "pets"], "confidence": 0.9})
        self.assertIn(self.bank["smoking"]["text"], c["reply"])
        self.assertIn(self.bank["pets"]["text"], c["reply"])

    def test_unknown_id_and_low_confidence_go_human(self):
        dec, c = self.run_("x", {"door": "answer", "answers": ["made_up"], "confidence": 0.99})
        self.assertEqual(c["door"], "human")
        dec, c = self.run_("x", {"door": "answer", "answers": ["pets"], "confidence": 0.3})
        self.assertEqual(c["door"], "human")
        self.assertEqual(c["reply"], self.bank["human"]["text"])

    def test_ai_down_goes_human(self):
        def boom(s, u):
            raise RuntimeError("down")
        dec = brain.decide("مرحبا عندي سؤال", boom, self.bank)
        self.assertEqual((dec["door"], dec["why"]), ("human", "ai_unavailable"))
        self.assertEqual(brain.decide("x", fixed(None), self.bank)["door"], "human")

    def test_dates_use_live_search(self):
        dec, c = self.run_("ابي ليلتين من الخميس", {"door": "dates", "confidence": 0.9})
        self.assertEqual(c["door"], "dates")
        self.assertIn("oujares.com/apartments/592596", c["reply"])
        self.assertEqual(c["violations"], [])

    def test_dates_win_even_if_ai_says_answer(self):
        dec, c = self.run_("كم السعر ليلتين من الخميس", {"door": "answer", "answers": ["prices"], "confidence": 0.9})
        self.assertEqual(c["door"], "dates")

    def test_unit_hint_penthouse(self):
        dec, c = self.run_("البنتهاوس اللي فتيك توك", {"door": "unit", "unit_hint": "البنتهاوس", "confidence": 0.8})
        self.assertIn("483841", c["reply"])
        self.assertTrue(c["reply"].startswith("تقصد هذي؟"))

    def test_unit_no_match_goes_human(self):
        dec, c = self.run_("الشقة الزرقا", {"door": "unit", "unit_hint": "الزرقا", "confidence": 0.8})
        self.assertEqual(c["door"], "human")

    def test_near_picks_closest(self):
        dec, c = self.run_("وش اقرب شي للتخصصي", {"door": "near", "place": "مستشفى التخصصي",
                                                  "place_lat": 24.672, "place_lng": 46.675, "confidence": 0.8})
        self.assertIn("578603", c["reply"].split("\n")[1] + c["reply"].split("\n")[2])
        self.assertEqual(c["violations"], [])

    def test_near_outside_riyadh_goes_human(self):
        dec, c = self.run_("قريب من الحرم", {"door": "near", "place": "الحرم", "place_lat": 21.42,
                                             "place_lng": 39.82, "confidence": 0.9})
        self.assertEqual(c["door"], "human")

    def test_menu_greeting_has_no_reply(self):
        dec, c = self.run_("هلا", {"door": "menu", "confidence": 0.9})
        self.assertIsNone(c["reply"])

    def test_urgent_door_marked(self):
        dec, c = self.run_("الباب ما يفتح", {"door": "answer", "answers": ["door"], "confidence": 0.9})
        self.assertTrue(c["urgent"])
        self.assertTrue(c["handoff"])


def inbound(text, eid="ev-1", **over):
    p = {"direction": "Inbound", "messageType": "Text", "channelId": CH, "conversationId": "c1",
         "conversationEventId": eid, "body": text}
    p.update(over)
    return p


class ShadowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="hatif_ai_")
        bdb.set_db_path_for_tests(os.path.join(self.tmp, "brain.db"))
        db.reset_init_cache()
        answers.reset_for_tests()
        for k in list(os.environ):
            if k.startswith("HATIF_"):
                os.environ.pop(k)
        os.environ.update({"HATIF_CHANNEL_ID": CH, "HATIF_DRYRUN": "0"})
        service.reset_for_tests()
        self.msgs, self.calls = [], []

        class NoNet:
            def request(s, *a, **k):
                raise AssertionError("the silent reader must never call Hatif")
            post = get = request
        client.set_session_for_tests(NoNet())
        self.decision = {"door": "answer", "answers": ["pets"], "confidence": 0.9, "summary_ar": "يسأل عن الحيوانات"}

        def classify(s, u):
            self.calls.append(u)
            return self.decision
        host.wire({"now": lambda: NOW, "notify": lambda t: self.msgs.append(t), "search": search_ok,
                   "neighborhoods": lambda: HOODS, "site_host": lambda: "oujares.com",
                   "classify": classify, "catalog": lambda: CATALOG})

    def tearDown(self):
        host.wire({"classify": None, "catalog": None})

    def test_posts_once_and_never_sends(self):
        r = service.shadow(inbound("مسموح القطط؟ رقمي 0551234567"))
        self.assertEqual(r["outcome"], "shadow")
        self.assertEqual(len(self.msgs), 1)
        self.assertIn("صامت", self.msgs[0])
        self.assertIn(answers.bank()["pets"]["text"], self.msgs[0])
        self.assertNotIn("0551234567", self.msgs[0])
        self.assertEqual(service.shadow(inbound("مسموح القطط؟"))["outcome"], "duplicate")
        self.assertEqual(len(self.msgs), 1)

    def test_ignores_outbound_taps_other_channel(self):
        self.assertEqual(service.shadow(inbound("x", direction="Outbound"))["outcome"], "ignored")
        self.assertEqual(service.shadow(inbound("x", eid="e2", interactiveReply={"id": "1"}))["outcome"], "ignored")
        self.assertEqual(service.shadow(inbound("x", eid="e3", channelId="other"))["outcome"], "ignored")
        self.assertEqual(self.calls, [])

    def test_kill_switch(self):
        os.environ["HATIF_AI"] = "0"
        self.assertEqual(service.shadow(inbound("مسموح القطط؟"))["outcome"], "ignored")
        self.assertEqual((self.calls, self.msgs), ([], []))

    def test_menu_greeting_posts_nothing(self):
        self.decision = {"door": "menu", "confidence": 0.9}
        self.assertEqual(service.shadow(inbound("هلا"))["outcome"], "menu")
        self.assertEqual(self.msgs, [])

    def test_throttle(self):
        os.environ["HATIF_AI_MAX_PER_MIN"] = "1"
        service.shadow(inbound("a", eid="t1"))
        self.assertEqual(service.shadow(inbound("b", eid="t2"))["outcome"], "throttled")

    def test_blocked_reply_is_flagged(self):
        os.environ["STATE_DIR"] = self.tmp
        try:
            with open(os.path.join(self.tmp, "hatif_answers.json"), "w", encoding="utf-8") as f:
                json.dump({"answers": {"human": {"kind": "human", "text": "H"},
                                       "pets": {"text": "عندنا 53 شقة"}}}, f, ensure_ascii=False)
            answers.reset_for_tests()
            r = service.shadow(inbound("سؤال", eid="b1"))
            self.assertIn("COUNT", r["violations"])
            self.assertIn("⛔", self.msgs[-1])
        finally:
            os.environ.pop("STATE_DIR", None)
            answers.reset_for_tests()


if __name__ == "__main__":
    unittest.main()
