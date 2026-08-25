# -*- coding: utf-8 -*-
"""TDD lock for the Ouja Studio v3 SIGNAL contract (pure — no network, no db).

The whole v3 promise is spec Section C: every idea references a REAL signal.
That promise is only real if it is machine-enforced, so these are the locks:

  * signal_ok FAILS CLOSED — no fact, no signal; external without url/date, no signal.
  * make_signal validates + stamps a stable id (same fact => same sid, always).
  * parse_signals tolerates model junk and drops anything ungrounded.
  * the trigger set is the spec's 7 (+ legacy 'emotion'), formats include the two
    new signal-native ones (data_reveal / news_reaction).
  * novelty: two ways of saying the same angle collide, different angles don't.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from studio import engine  # noqa: E402


class TestVocabulary(unittest.TestCase):
    def test_seven_spec_triggers_present(self):
        for t in ("curiosity", "loss", "identity", "provocation",
                  "authority", "social_proof", "news"):
            self.assertIn(t, engine.TRIGGERS, t)

    def test_legacy_emotion_trigger_still_accepted(self):
        # v2 rows in brain.db carry trigger_kind='emotion' — must not become invalid.
        self.assertIn("emotion", engine.TRIGGERS)

    def test_signal_native_formats(self):
        self.assertIn("data_reveal", engine.VIDEO_TYPES)
        self.assertIn("news_reaction", engine.VIDEO_TYPES)

    def test_families_and_sources_are_disjoint_and_complete(self):
        self.assertEqual(set(engine.SIGNAL_FAMILIES), {"internal", "external", "manual"})
        self.assertIn("occupancy", engine.INTERNAL_SOURCES)
        self.assertIn("guest_story", engine.INTERNAL_SOURCES)
        self.assertIn("regulation", engine.EXTERNAL_SOURCES)
        self.assertIn("manual", engine.SIGNAL_SOURCES)
        self.assertFalse(set(engine.INTERNAL_SOURCES) & set(engine.EXTERNAL_SOURCES))


class TestSignalGate(unittest.TestCase):
    def test_internal_signal_needs_only_a_fact(self):
        s = engine.make_signal("internal", "occupancy", "إشغال الويكند",
                               "٤٧ من ٥٣ شقة محجوزة الخميس الجاي", as_of="2026-07-23")
        self.assertIsNotNone(s)
        self.assertTrue(engine.signal_ok(s))

    def test_empty_fact_is_rejected(self):
        self.assertIsNone(engine.make_signal("internal", "occupancy", "عنوان", "   "))

    def test_external_without_url_is_rejected(self):
        self.assertIsNone(engine.make_signal(
            "external", "regulation", "نظام جديد",
            "منع استضافة نفس الضيف أكثر من ٢٩ يوم", as_of="2026-06-01"))

    def test_external_without_date_is_rejected(self):
        self.assertIsNone(engine.make_signal(
            "external", "regulation", "نظام جديد", "منع ٢٩ يوم",
            url="https://mt.gov.sa/x"))

    def test_external_with_url_and_date_passes(self):
        s = engine.make_signal("external", "regulation", "نظام جديد", "منع ٢٩ يوم",
                               url="https://mt.gov.sa/x", as_of="2026-06-01")
        self.assertIsNotNone(s)
        self.assertEqual(s["family"], "external")

    def test_bad_url_scheme_rejected(self):
        self.assertIsNone(engine.make_signal(
            "external", "market", "t", "f", url="ftp://x.com", as_of="2026-06-01"))

    def test_unknown_family_or_source_rejected(self):
        self.assertIsNone(engine.make_signal("cosmic", "occupancy", "t", "f"))
        self.assertIsNone(engine.make_signal("internal", "vibes", "t", "f"))

    def test_signal_ok_fails_closed_on_junk(self):
        for junk in (None, {}, [], "signal", {"fact": "x"}):
            self.assertFalse(engine.signal_ok(junk))

    def test_sid_is_stable_and_content_addressed(self):
        a = engine.make_signal("internal", "pricing", "عنوان", "السعر ارتفع ٣٥٪ شتاءً")
        b = engine.make_signal("internal", "pricing", "عنوان ثاني", "السعر ارتفع ٣٥٪ شتاءً")
        c = engine.make_signal("internal", "pricing", "عنوان", "السعر نزل ١٠٪")
        self.assertEqual(a["sid"], b["sid"])       # same fact = same signal
        self.assertNotEqual(a["sid"], c["sid"])


class TestFreshness(unittest.TestCase):
    def test_days_since(self):
        self.assertEqual(engine.freshness_days("2026-07-20", "2026-07-23"), 3)
        self.assertEqual(engine.freshness_days("2026-07-23", "2026-07-23"), 0)

    def test_bad_date_is_none_not_zero(self):
        self.assertIsNone(engine.freshness_days("", "2026-07-23"))
        self.assertIsNone(engine.freshness_days("soon", "2026-07-23"))


class TestParseSignals(unittest.TestCase):
    def test_parses_and_drops_ungrounded_items(self):
        raw = {"signals": [
            {"source": "regulation", "title": "نظام", "fact": "حقيقة موثقة",
             "url": "https://mt.gov.sa/a", "as_of": "2026-06-01"},
            {"source": "regulation", "title": "بدون مصدر", "fact": "ادعاء"},   # no url
            {"source": "market", "title": "سوق", "fact": "",                    # no fact
             "url": "https://x.com/b", "as_of": "2026-06-02"},
            "garbage",
        ]}
        out = engine.parse_signals(raw, "external")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["source"], "regulation")

    def test_unknown_source_falls_back_to_default(self):
        raw = {"signals": [{"source": "zzz", "title": "t", "fact": "f",
                            "url": "https://x.com/a", "as_of": "2026-06-01"}]}
        out = engine.parse_signals(raw, "external", default_source="market")
        self.assertEqual(out[0]["source"], "market")

    def test_junk_returns_empty(self):
        for junk in (None, {}, {"signals": "no"}, []):
            self.assertEqual(engine.parse_signals(junk, "external"), [])


class TestNovelty(unittest.TestCase):
    def test_same_angle_worded_differently_collides(self):
        a = engine.novelty_key("٩٠٪ من ضيوفنا يحجزون قبل يوم واحد من الوصول")
        b = engine.novelty_key("٩٠٪ من الضيوف عندنا يحجزون قبل يوم من الوصول!")
        self.assertFalse(engine.is_novel(a, [b]))

    def test_different_angle_is_novel(self):
        a = engine.novelty_key("٩٠٪ من ضيوفنا يحجزون قبل يوم واحد")
        b = engine.novelty_key("كيف نحوّل شقة عادية لفندق خلال أسبوع")
        self.assertTrue(engine.is_novel(a, [b]))

    def test_empty_history_is_always_novel(self):
        self.assertTrue(engine.is_novel(engine.novelty_key("أي شي"), []))

    def test_empty_text_is_not_novel(self):
        self.assertFalse(engine.is_novel(engine.novelty_key("  "), []))


if __name__ == "__main__":
    unittest.main()
