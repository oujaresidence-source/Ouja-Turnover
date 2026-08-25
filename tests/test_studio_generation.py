# -*- coding: utf-8 -*-
"""End-to-end lock for the rewritten Signal→card generation (2026-07-24).

Uses a fake model so it runs offline. Proves the six defects are actually fixed at
the generation layer:
  * one grounding sid → at most one card (S2)
  * a card always carries a resolvable signal (S1); no ungrounded render
  * number-first is enforced when the fact has a number (S3)
  * no timestamp grid survives into the stored script (S3)
  * a guest story is minted into a feed-visible guest_story signal (S1)
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb            # noqa: E402
from studio import db as sdb           # noqa: E402
from studio import engine, ideas as ideas_mod  # noqa: E402
from studio.host import HOST           # noqa: E402


def _fake_model(cards):
    def gen(system, user, max_tokens=0, model=None):
        return {"ideas": cards}
    return gen


class _Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="studiogen_")
        bdb.set_db_path_for_tests(os.path.join(cls.tmp, "brain.db"))
        sdb.reset_init_cache()
        sdb._ensure()
        import datetime
        HOST.now = lambda: datetime.datetime(2026, 7, 24, 9, 0)
        HOST.model_premium = "x"

    def setUp(self):
        for t in ("studio_ideas", "studio_signals", "studio_stories", "studio_plan"):
            sdb.execute("DELETE FROM " + t)

    def _sig(self, fact="٩٠٪ من ضيوفنا يحجزون قبل يوم واحد", source="occupancy",
             family="internal", **kw):
        s = engine.make_signal(family, source, "ع", fact, strength=80, **kw)
        sdb.add_signal(s, nkey=engine.novelty_key(fact), ts="2026-07-24 09:00:00")
        return s["sid"]


class TestOneSidOneCard(_Base):
    def test_one_signal_yields_one_card(self):
        sid = self._sig()
        HOST.claude_json = _fake_model([
            {"hook_spoken": "٩٠٪ من ضيوفنا يحجزون قبل يوم", "visual_title": "السوق لحظي",
             "why_it_works": "رقم أول ٣ث", "script": ["(٠-٣ث) ٩٠٪ يحجزون قبل يوم",
                                                       "طيب ليش؟", "عشان كذا ٩٠٪ يحجزون قبل يوم"],
             "shape": "cold_number", "audience": "niche", "trigger": "social_proof"},
            {"hook_spoken": "٩٠٪ يحجزون بسرعة", "visual_title": "شي غريب",
             "why_it_works": "رقم", "script": ["٩٠٪", "شرح", "٩٠٪"],
             "shape": "half_of_us", "audience": "escape", "trigger": "identity"}])
        cards = ideas_mod.generate_for_signal(sid)
        self.assertEqual(len(cards), 1, "one fact must produce exactly one card")

    def test_second_call_on_same_sid_is_skipped(self):
        sid = self._sig()
        HOST.claude_json = _fake_model([
            {"hook_spoken": "٩٠٪ من ضيوفنا يحجزون قبل يوم", "visual_title": "السوق لحظي",
             "why_it_works": "رقم", "script": ["٩٠٪ يحجزون", "شرح", "٩٠٪ يحجزون"],
             "shape": "cold_number", "audience": "niche", "trigger": "social_proof"}])
        self.assertEqual(len(ideas_mod.generate_for_signal(sid)), 1)
        self.assertEqual(ideas_mod.generate_for_signal(sid), [],
                         "the same sid must not produce a second card")


class TestGrounding(_Base):
    def test_every_stored_card_resolves_to_a_signal(self):
        sid = self._sig()
        HOST.claude_json = _fake_model([
            {"hook_spoken": "٩٠٪ من ضيوفنا يحجزون قبل يوم", "visual_title": "السوق لحظي",
             "why_it_works": "رقم", "script": ["٩٠٪ يحجزون", "شرح", "٩٠٪ يحجزون"],
             "shape": "cold_number", "audience": "niche", "trigger": "social_proof"}])
        card = ideas_mod.generate_for_signal(sid)[0]
        self.assertEqual(card["signal_sid"], sid)
        self.assertTrue(ideas_mod.card_grounded(card))
        self.assertEqual(card["signal_text"], "٩٠٪ من ضيوفنا يحجزون قبل يوم واحد")


class TestNumberFirst(_Base):
    def test_generator_keeps_the_number_first_candidate(self):
        sid = self._sig()
        HOST.claude_json = _fake_model([
            {"hook_spoken": "تعرف كم ضيف يحجز عندنا بسرعة؟ ٩٠٪",  # buries it
             "visual_title": "الحجز اللحظي", "why_it_works": "فضول",
             "script": ["سؤال", "٩٠٪", "جواب"], "shape": "owner_question",
             "audience": "niche", "trigger": "curiosity"},
            {"hook_spoken": "٩٠٪ من ضيوفنا يحجزون قبل يوم",       # leads with it
             "visual_title": "السوق لحظي", "why_it_works": "رقم",
             "script": ["٩٠٪ يحجزون", "شرح", "٩٠٪ يحجزون"], "shape": "cold_number",
             "audience": "niche", "trigger": "social_proof"}])
        card = ideas_mod.generate_for_signal(sid)[0]
        self.assertTrue(engine.leads_with_number(card["hook_spoken"],
                                                 "٩٠٪ من ضيوفنا يحجزون قبل يوم واحد"))


class TestNoTimestampGrid(_Base):
    def test_stored_script_has_no_beat_grid(self):
        sid = self._sig()
        HOST.claude_json = _fake_model([
            {"hook_spoken": "٩٠٪ من ضيوفنا يحجزون قبل يوم", "visual_title": "السوق لحظي",
             "why_it_works": "رقم", "script": ["(٠-٣ث) ٩٠٪ يحجزون قبل يوم",
                                               "(٣-٨ث) طيب ليش الاستعجال", "(٨-١٦ث) ٩٠٪ يحجزون"],
             "shape": "cold_number", "audience": "niche", "trigger": "social_proof"}])
        card = ideas_mod.generate_for_signal(sid)[0]
        joined = " ".join(card["script"])
        self.assertNotRegex(joined, r"[（(]\s*\d+\s*[-–—]\s*\d+")
        self.assertNotIn("ث)", joined)


class TestStoryPath(_Base):
    def test_story_is_minted_into_a_feed_visible_guest_story_signal(self):
        sto = sdb.add_story("c1", "1", "Ouja | A", 8, "hero_save",
                            {"title": "الفريق أنقذ الموقف", "summary": "صار عطل وانحل",
                             "angle": "احتراف الفريق", "beats": [], "quotes": ["شكراً ما قصرتوا"],
                             "emotion": "ارتياح", "lesson": "السرعة تفرق"}, "2026-07-24 09:00:00")
        HOST.claude_json = _fake_model([
            {"hook_spoken": "ضيف كتب لنا شكراً ما قصرتوا", "visual_title": "لحظة صدق",
             "why_it_works": "اقتباس حقيقي", "script": ["الاقتباس", "القصة", "الاقتباس"],
             "shape": "quote_reaction", "audience": "escape", "trigger": "emotion"}])
        cards = ideas_mod.generate_for_story(sto)
        self.assertEqual(len(cards), 1)
        c = cards[0]
        self.assertEqual(c["signal_source"], "guest_story")
        self.assertTrue(c["signal_sid"])
        # the anecdote is now a real signal in the feed (the owner's complaint)
        feed = [s for s in sdb.signals() if s["source"] == "guest_story"]
        self.assertTrue(feed)
        self.assertEqual(feed[0]["sid"], c["signal_sid"])

    def test_story_with_no_usable_fact_does_not_render(self):
        sto = sdb.add_story("c2", "1", "Ouja | A", 5, "other",
                            {"title": "", "summary": "", "angle": "", "beats": [],
                             "quotes": [], "emotion": "", "lesson": ""}, "2026-07-24 09:00:00")
        HOST.claude_json = _fake_model([{"hook_spoken": "x", "visual_title": "y",
                                         "why_it_works": "z", "script": ["a"]}])
        self.assertEqual(ideas_mod.generate_for_story(sto), [])


class TestDailySetEndToEnd(_Base):
    """The whole contract, on real signals: a day's set must be diverse, grounded,
    number-first, and free of any beat-grid (owner verdict 2026-07-24)."""

    def _fake_per_signal(self):
        import re as _re

        def gen(system, user, max_tokens=0, model=None):
            m = _re.search(r'"الحقيقة":\s*"([^"]+)"', user)
            fact = m.group(1) if m else "٥٠ رقم"
            aud = "escape" if "تقييم" in fact else "niche"
            return {"ideas": [
                {"hook_spoken": fact[:38], "visual_title": "الزاوية: " + fact[:14],
                 "visual_sub": "لمن يهمه", "why_it_works": "رقم أول ٣ث",
                 # a timestamp is planted here on purpose — it must be stripped
                 "script": ["(٠-٣ث) " + fact[:28], "طيب شوف ليش صار كذا", fact[:16]],
                 "audience": aud, "trigger": "social_proof"}]}
        return gen

    def test_full_day_is_diverse_grounded_and_number_first(self):
        from studio import plan
        HOST.claude_json = self._fake_per_signal()
        facts = [
            ("occupancy", "internal", "٩٠٪ من ضيوفنا يحجزون قبل يوم واحد", {}),
            ("pricing", "internal", "٨٠٢ ريال أغلى ليلة عندنا مقابل ٥٣١", {}),
            ("reviews", "internal", "٤.٨ نجوم من ٢٣٣٠ تقييم حقيقي", {}),
            ("ops", "internal", "٢٣ تسليم بنفس اليوم خلال أسبوعين", {}),
            ("regulation", "external", "٢٩ يوم أقصى مدة للضيف بالنظام الجديد",
             {"url": "https://mt.gov.sa/x", "as_of": "2026-07-20"}),
        ]
        sids = []
        for source, family, fact, extra in facts:
            s = engine.make_signal(family, source, "ع", fact, strength=80, **extra)
            sdb.add_signal(s, nkey=engine.novelty_key(fact), ts="2026-07-24 09:00:00")
            sids.append(s["sid"])
            ideas_mod.generate_for_signal(s["sid"])

        day = plan.choose([c for c in sdb.ideas(status="new")], [], n=3, today="2026-07-24")
        self.assertEqual(len(day), 3)

        # ≥3 distinct grounding sids
        self.assertEqual(len({c["signal_sid"] for c in day}), 3)
        # ≥3 distinct shapes
        self.assertGreaterEqual(len({c["shape"] for c in day}), 3)
        # ≥1 escape-the-niche card
        self.assertTrue(any(c["audience"] == "escape" for c in day))
        # every card grounded, number-first, and NO timestamp grid anywhere
        for c in day:
            self.assertTrue(ideas_mod.card_grounded(c))
            self.assertTrue(engine.leads_with_number(c["hook_spoken"], c["signal_text"]),
                            c["hook_spoken"])
            joined = " ".join(c["script"])
            self.assertNotRegex(joined, r"[（(]\s*\d+\s*[-–—]\s*\d+")
            self.assertNotIn("ث)", joined)


if __name__ == "__main__":
    unittest.main()
