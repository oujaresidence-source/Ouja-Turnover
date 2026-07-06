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
        d = engine.parse_triage({"story": True, "score": 8, "type": "mistake_fixed",
                                 "one_line": "الفريق أرسل كود شقة خاطئ وعوّض الضيف"})
        self.assertEqual(d["score"], 8)
        self.assertEqual(d["type"], "mistake_fixed")

    def test_none_and_junk(self):
        self.assertIsNone(engine.parse_triage(None))
        self.assertIsNone(engine.parse_triage({"score": "high"}))

    def test_score_clamped_and_type_defaulted(self):
        d = engine.parse_triage({"story": True, "score": 25, "type": "alien", "one_line": "x"})
        self.assertEqual(d["score"], 10)
        self.assertEqual(d["type"], "other")

    def test_no_story_normalizes(self):
        d = engine.parse_triage({"story": False, "score": 2, "type": "other", "one_line": ""})
        self.assertFalse(d["story"])


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
    def test_valid_list(self):
        raw = {"ideas": [{"hook_spoken": "خمس كلمات توقف السكرول هنا",
                          "visual_title": "الضيف طلب شي غريب",
                          "visual_sub": "وسويناه له",
                          "angle": "قصة موقف", "script": ["افتح بالسؤال", "القصة", "النهاية"],
                          "video_type": "talking", "cta": "تابع للمزيد",
                          "audience": "escape", "trigger": "curiosity"}]}
        ideas = engine.parse_ideas(raw)
        self.assertEqual(len(ideas), 1)
        self.assertEqual(ideas[0]["audience"], "escape")

    def test_bad_audience_defaults_niche(self):
        raw = {"ideas": [{"hook_spoken": "ه", "visual_title": "ع", "visual_sub": "",
                          "angle": "", "script": [], "video_type": "talking",
                          "cta": "", "audience": "everyone", "trigger": "curiosity"}]}
        self.assertEqual(engine.parse_ideas(raw)[0]["audience"], "niche")

    def test_missing_hook_dropped(self):
        raw = {"ideas": [{"visual_title": "بدون هوك"}]}
        self.assertEqual(engine.parse_ideas(raw), [])

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
