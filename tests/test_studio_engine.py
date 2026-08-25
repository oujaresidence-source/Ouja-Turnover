# -*- coding: utf-8 -*-
"""TDD lock for studio.engine — pure story-mining logic (no network, no db).

Locked invariants:
  * qualification: inquiries excluded, short threads (<6 msgs) excluded,
    needs >=2 inbound guest messages, cancelled stays still qualify (stories!)
  * transcript builder: role labels, chronological order, middle-trim on huge threads
  * triage/story/idea parsing: tolerant of model junk, strict on required fields
  * scrub_names: guest name never leaks into a card
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from studio import engine  # noqa: E402


def _msg(body, incoming=1, ts="2026-06-01 10:00:00"):
    return {"body": body, "isIncoming": incoming, "date": ts, "id": len(body)}


def _convo(status="confirmed", cid=11, lid=101):
    return {"id": cid, "listingMapId": lid, "recipientName": "محمد العتيبي",
            "reservation": {"status": status, "guestName": "محمد العتيبي",
                            "arrivalDate": "2026-06-01", "departureDate": "2026-06-03"}}


def _thread(n_in=3, n_out=4):
    msgs = []
    for i in range(max(n_in, n_out)):
        if i < n_in:
            msgs.append(_msg("سؤال الضيف رقم %d" % i, 1, "2026-06-01 1%d:00:00" % i))
        if i < n_out:
            msgs.append(_msg("رد الفريق رقم %d" % i, 0, "2026-06-01 1%d:30:00" % i))
    return msgs


class TestQualifies(unittest.TestCase):
    def test_confirmed_long_thread_qualifies(self):
        ok, why = engine.qualifies(_convo("confirmed"), _thread(3, 4))
        self.assertTrue(ok, why)

    def test_new_and_modified_count_as_confirmed(self):
        for st in ("new", "modified", "checked-in", "checked-out"):
            ok, why = engine.qualifies(_convo(st), _thread(3, 4))
            self.assertTrue(ok, "%s: %s" % (st, why))

    def test_cancelled_still_qualifies(self):
        # a last-minute cancellation IS a story — don't drop it
        ok, _ = engine.qualifies(_convo("cancelled"), _thread(3, 4))
        self.assertTrue(ok)

    def test_inquiry_excluded(self):
        for st in ("inquiry", "inquiryPreapproved", "inquiryDenied",
                   "inquiryTimedout", "declined", "expired", "pending"):
            ok, why = engine.qualifies(_convo(st), _thread(3, 4))
            self.assertFalse(ok, st)
            self.assertEqual(why, "inquiry")

    def test_no_reservation_excluded(self):
        c = _convo()
        c["reservation"] = None
        ok, why = engine.qualifies(c, _thread(3, 4))
        self.assertFalse(ok)
        self.assertEqual(why, "inquiry")

    def test_short_thread_excluded(self):
        # owner rule: «exclude messages that ended after four or five»
        ok, why = engine.qualifies(_convo(), _thread(2, 3))
        self.assertTrue(len(_thread(2, 3)) == 5)
        self.assertFalse(ok)
        self.assertEqual(why, "short")

    def test_six_messages_is_enough(self):
        ok, _ = engine.qualifies(_convo(), _thread(3, 3))
        self.assertTrue(ok)

    def test_monologue_excluded(self):
        # 6+ messages but only one from the guest = automation blast, no story
        msgs = [_msg("رسالة آلية %d" % i, 0) for i in range(7)] + [_msg("شكرا", 1)]
        ok, why = engine.qualifies(_convo(), msgs)
        self.assertFalse(ok)
        self.assertEqual(why, "monologue")


class TestTranscript(unittest.TestCase):
    def test_labels_and_order(self):
        msgs = [_msg("مرحبا ابغى اسال", 1, "2026-06-01 10:00:00"),
                _msg("حياك الله", 0, "2026-06-01 10:05:00")]
        t = engine.build_transcript(msgs)
        self.assertIn("الضيف: مرحبا ابغى اسال", t)
        self.assertIn("الفريق: حياك الله", t)
        self.assertLess(t.index("الضيف"), t.index("الفريق"))

    def test_sorts_out_of_order_messages(self):
        msgs = [_msg("ثاني", 0, "2026-06-01 12:00:00"),
                _msg("أول", 1, "2026-06-01 09:00:00")]
        t = engine.build_transcript(msgs)
        self.assertLess(t.index("أول"), t.index("ثاني"))

    def test_huge_thread_keeps_head_and_tail(self):
        msgs = [_msg("رسالة رقم %03d وفيها كلام طويل شوي عشان الطول" % i, i % 2,
                     "2026-06-01 %02d:%02d:00" % (10 + i // 60, i % 60)) for i in range(200)]
        t = engine.build_transcript(msgs, max_msgs=60)
        self.assertIn("رسالة رقم 000", t)     # head kept
        self.assertIn("رسالة رقم 199", t)     # tail kept
        self.assertNotIn("رسالة رقم 100", t)  # middle trimmed
        self.assertIn(engine.TRIM_MARK, t)

    def test_char_cap(self):
        msgs = [_msg("ك" * 500, 1, "2026-06-01 10:00:%02d" % i) for i in range(40)]
        t = engine.build_transcript(msgs, max_chars=3000)
        self.assertLessEqual(len(t), 3400)  # cap + labels slack

    def test_empty_bodies_skipped(self):
        msgs = [_msg("", 1), _msg("موجود", 0)]
        t = engine.build_transcript(msgs)
        self.assertNotIn("الضيف:", t)
        self.assertIn("موجود", t)


class TestParseTriage(unittest.TestCase):
    def test_valid(self):
        d = engine.parse_triage({"story": True, "score": 8, "type": "hero_save",
                                 "brand_safe": True, "positive": True,
                                 "one_line": "عطل تكييف انحلّ بأقل من ساعة والضيف انبسط"})
        self.assertEqual(d["score"], 8)
        self.assertEqual(d["type"], "hero_save")
        self.assertTrue(d["brand_safe"])
        self.assertTrue(d["positive"])

    def test_none_and_junk(self):
        self.assertIsNone(engine.parse_triage(None))
        self.assertIsNone(engine.parse_triage({"score": "high"}))

    def test_score_clamped_and_type_defaulted(self):
        d = engine.parse_triage({"story": True, "score": 25, "type": "alien", "one_line": "x"})
        self.assertEqual(d["score"], 10)
        self.assertEqual(d["type"], "other")

    def test_new_positive_taxonomy_accepted(self):
        for t in ("hero_save", "transformation", "transparency_numbers", "day_in_life",
                  "hospitality_wow", "weird_delight", "heartwarming", "loyal_return",
                  "operational_craft"):
            d = engine.parse_triage({"story": True, "score": 6, "type": t, "one_line": "x"})
            self.assertEqual(d["type"], t)

    def test_old_negative_types_normalize_to_other(self):
        # the retired negative buckets must not survive as labels
        for t in ("sad_exit", "conflict", "cancellation", "angry_to_happy", "emergency"):
            d = engine.parse_triage({"story": True, "score": 6, "type": t, "one_line": "x"})
            self.assertEqual(d["type"], "other")

    def test_brand_flags_fail_closed(self):
        # absent flags must default False (never leak an unjudged story through the gate)
        d = engine.parse_triage({"story": True, "score": 9, "type": "hero_save", "one_line": "x"})
        self.assertFalse(d["brand_safe"])
        self.assertFalse(d["positive"])

    def test_no_story_normalizes(self):
        d = engine.parse_triage({"story": False, "score": 2, "type": "other", "one_line": ""})
        self.assertFalse(d["story"])


class TestBrandGate(unittest.TestCase):
    def _t(self, **kw):
        base = {"story": True, "score": 8, "type": "hero_save",
                "brand_safe": True, "positive": True, "one_line": "x"}
        base.update(kw)
        return engine.parse_triage(base)

    def test_clean_hero_save_passes(self):
        self.assertTrue(engine.brand_ok(self._t()))

    def test_unsafe_blocked(self):
        self.assertFalse(engine.brand_ok(self._t(brand_safe=False)))

    def test_negative_blocked(self):
        self.assertFalse(engine.brand_ok(self._t(positive=False)))

    def test_not_a_story_blocked(self):
        self.assertFalse(engine.brand_ok(self._t(story=False)))

    def test_none_blocked(self):
        self.assertFalse(engine.brand_ok(None))


class TestHookBanList(unittest.TestCase):
    def test_clean_hook_passes(self):
        self.assertTrue(engine.hook_is_clean("لو عندك شقة في الرياض، خلني أوريك رقم"))

    def test_banned_arabic_phrases_rejected(self):
        for bad in ("لن تصدق وش صار", "انتظر للنهاية عشان تشوف", "ما راح تصدق النتيجة",
                    "هل تعلم إن", "قصة صادمة"):
            self.assertFalse(engine.hook_is_clean(bad), bad)

    def test_banned_english_phrases_rejected(self):
        for bad in ("You won't believe this", "wait for it", "POV: you booked"):
            self.assertFalse(engine.hook_is_clean(bad), bad)

    def test_empty_hook_not_clean(self):
        self.assertFalse(engine.hook_is_clean(""))


class TestParseStory(unittest.TestCase):
    def test_valid(self):
        d = engine.parse_story({"title": "الضيف اللي حجز غلط", "summary": "قصة كاملة هنا",
                                "beats": ["وصل", "انصدم", "انحلّت"],
                                "quotes": ["وش ذا"], "emotion": "توتر ثم ارتياح",
                                "lesson": "سرعة الرد تنقذ"})
        self.assertEqual(d["title"], "الضيف اللي حجز غلط")
        self.assertEqual(len(d["beats"]), 3)

    def test_missing_title_rejected(self):
        self.assertIsNone(engine.parse_story({"summary": "x"}))

    def test_beats_coerced_to_strings(self):
        d = engine.parse_story({"title": "ع", "summary": "س", "beats": [1, "اثنين"],
                                "quotes": [], "emotion": "", "lesson": ""})
        self.assertEqual(d["beats"], ["1", "اثنين"])


class TestParseIdeas(unittest.TestCase):
    def _idea(self, **kw):
        base = {"hook_spoken": "لو عندك شقة في الرياض شوف هالرقم",
                "visual_title": "٣ ليالي، تقييم كامل",
                "visual_sub": "كيف صار",
                "angle": "قصة موقف", "script": ["افتح بالرقم", "القصة", "النهاية"],
                "video_type": "talking", "cta": "تابع للمزيد",
                "audience": "escape", "trigger": "curiosity",
                "why_it_works": "هوك الهوية أقوى صيغة مثبتة ٢٠٢٦ + رقم حقيقي أول ٣ ثواني"}
        base.update(kw)
        return base

    def test_valid_list(self):
        ideas = engine.parse_ideas({"ideas": [self._idea()]})
        self.assertEqual(len(ideas), 1)
        self.assertEqual(ideas[0]["audience"], "escape")
        self.assertTrue(ideas[0]["why_it_works"])

    def test_bad_audience_defaults_niche(self):
        ideas = engine.parse_ideas({"ideas": [self._idea(audience="everyone")]})
        self.assertEqual(ideas[0]["audience"], "niche")

    def test_missing_hook_dropped(self):
        self.assertEqual(engine.parse_ideas({"ideas": [{"visual_title": "بدون هوك"}]}), [])

    def test_missing_why_dropped(self):
        # every card must justify itself — no rationale, no card
        self.assertEqual(engine.parse_ideas({"ideas": [self._idea(why_it_works="")]}), [])

    def test_banned_hook_dropped(self):
        # a card whose hook trips the burned-out ban-list is dropped
        self.assertEqual(engine.parse_ideas({"ideas": [self._idea(hook_spoken="لن تصدق وش صار")]}), [])
        self.assertEqual(engine.parse_ideas({"ideas": [self._idea(visual_title="قصة صادمة")]}), [])

    def test_junk(self):
        self.assertEqual(engine.parse_ideas(None), [])
        self.assertEqual(engine.parse_ideas({"ideas": "lots"}), [])


class TestScrubNames(unittest.TestCase):
    def test_full_name_scrubbed(self):
        out = engine.scrub_names("وصل محمد العتيبي وقال محمد إن الشقة روعة", "محمد العتيبي")
        self.assertNotIn("محمد", out)
        self.assertNotIn("العتيبي", out)
        self.assertIn("الضيف", out)

    def test_short_tokens_ignored(self):
        # single/two-letter tokens must not nuke the whole text
        out = engine.scrub_names("ابو فهد وصل", "بو")
        self.assertEqual(out, "ابو فهد وصل")

    def test_empty_name_noop(self):
        self.assertEqual(engine.scrub_names("نص", ""), "نص")


if __name__ == "__main__":
    unittest.main()
