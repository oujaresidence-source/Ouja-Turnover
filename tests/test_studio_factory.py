# -*- coding: utf-8 -*-
"""TDD lock for studio.factory — the «ولّد كل شي» sweep.

Money is spent per item here, so the locks are mostly about NOT spending it twice:
  * anything that already produced a card is never regenerated
  * the budget is a hard ceiling, and whatever it didn't reach is REPORTED, never
    silently dropped (a run that says "done" while skipping half the shelf is a lie)
  * one failing item never kills the sweep
  * an empty result is distinguished from an error — the brand gate returning nothing
    is the system working, not failing
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import db as bdb            # noqa: E402
from studio import db as sdb           # noqa: E402
from studio import engine, factory     # noqa: E402
from studio import ideas as ideas_mod  # noqa: E402


def _idea(title):
    return {"hook_spoken": "قول " + title, "visual_title": title, "visual_sub": "",
            "angle": title, "why_it_works": "سبب", "script": ["(٠-٣ث) هوك"],
            "video_type": "talking", "cta": "", "audience": "niche",
            "trigger": "curiosity", "signal_sid": "", "signal_family": "internal",
            "signal_source": "occupancy", "signal_text": "رقم", "signal_url": "",
            "signal_date": "", "strength": 50, "nkey": engine.novelty_key(title)}


class _Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="studiofac_")
        bdb.set_db_path_for_tests(os.path.join(cls.tmp, "brain.db"))
        sdb.reset_init_cache()
        sdb._ensure()

    def setUp(self):
        for t in ("studio_ideas", "studio_signals", "studio_stories", "studio_plan"):
            sdb.execute("DELETE FROM " + t)
        self.calls = []
        self._real_sig = ideas_mod.generate_for_signal
        self._real_story = ideas_mod.generate_for_story
        factory.PROGRESS.clear()

    def tearDown(self):
        ideas_mod.generate_for_signal = self._real_sig
        ideas_mod.generate_for_story = self._real_story

    def _signal(self, fact, strength=50):
        s = engine.make_signal("internal", "occupancy", "ع", fact, strength=strength)
        sdb.add_signal(s, nkey=engine.novelty_key(fact), ts="2026-07-23 09:00:00")
        return s["sid"]

    def _story(self, cid, title, score=7):
        return sdb.add_story(cid, "1", "Ouja | A", score, "hero_save",
                             {"title": title, "summary": "س", "angle": "ز",
                              "beats": [], "quotes": [], "emotion": "e",
                              "lesson": "l"}, "2026-07-23 09:00:00")


class TestPending(_Base):
    def test_lists_signals_and_stories(self):
        self._signal("٤٧ من ٥٣ شقة محجوزة")
        self._story("c1", "قصة إنقاذ")
        kinds = sorted(x["kind"] for x in factory.pending_sources())
        self.assertEqual(kinds, ["signal", "story"])

    def test_skips_anything_that_already_made_a_card(self):
        sid = self._signal("٤٧ من ٥٣ شقة محجوزة")
        card = _idea("عنوان")
        card["signal_sid"] = sid
        sdb.add_idea(0, card, "2026-07-23 09:00:00")
        self.assertEqual([x for x in factory.pending_sources() if x["kind"] == "signal"], [])

    def test_skips_a_story_that_already_made_a_card(self):
        sto = self._story("c9", "قصة")
        sdb.add_idea(sto, _idea("من القصة"), "2026-07-23 09:00:00")
        self.assertEqual([x for x in factory.pending_sources() if x["kind"] == "story"], [])

    def test_strongest_source_comes_first(self):
        self._signal("إشارة ضعيفة جداً", strength=10)
        self._signal("إشارة قوية مرة", strength=95)
        first = factory.pending_sources()[0]
        self.assertIn("قوية", first["label"])

    def test_hidden_signal_is_not_offered(self):
        sid = self._signal("إشارة مخفية")
        sdb.set_signal_status(sid, "hidden")
        self.assertEqual(factory.pending_sources(), [])


class TestRun(_Base):
    def _fake(self, per_item=2, fail_on=None, empty_on=None):
        def gen(ref, *a, **k):
            self.calls.append(ref)
            if fail_on is not None and ref == fail_on:
                raise RuntimeError("boom")
            if empty_on is not None and ref == empty_on:
                return []
            return [_idea("فكرة %s %s" % (ref, i)) for i in range(per_item)]
        return gen

    def test_generates_across_everything(self):
        self._signal("إشارة أولى عن الإشغال")
        self._signal("إشارة ثانية عن التسعير")
        ideas_mod.generate_for_signal = self._fake()
        rep = factory.run(budget=10)
        self.assertEqual(rep["used"], 2)
        self.assertEqual(rep["cards"], 4)
        self.assertEqual(rep["left"], 0)

    def test_budget_is_a_hard_ceiling_and_the_rest_is_reported(self):
        for i in range(5):
            self._signal("إشارة مختلفة رقم %s عن موضوع %s" % (i, "أبجد"[i % 4] * (i + 1)))
        ideas_mod.generate_for_signal = self._fake(per_item=1)
        rep = factory.run(budget=2)
        self.assertEqual(rep["used"], 2)
        self.assertGreater(rep["left"], 0, "unreached sources must be reported, not hidden")

    def test_absurd_budget_is_clamped(self):
        self._signal("إشارة وحدة")
        ideas_mod.generate_for_signal = self._fake(per_item=1)
        rep = factory.run(budget=10 ** 9)
        self.assertLessEqual(rep["used"], factory.HARD_CAP)

    def test_one_failure_does_not_stop_the_sweep(self):
        a = self._signal("إشارة أولى عن الإشغال")
        self._signal("إشارة ثانية عن التسعير")
        ideas_mod.generate_for_signal = self._fake(fail_on=a)
        rep = factory.run(budget=10)
        self.assertEqual(rep["errors"], 1)
        self.assertEqual(rep["cards"], 2, "the healthy source must still produce")

    def test_empty_result_is_not_counted_as_an_error(self):
        a = self._signal("إشارة أولى عن الإشغال")
        ideas_mod.generate_for_signal = self._fake(empty_on=a)
        rep = factory.run(budget=10)
        self.assertEqual(rep["errors"], 0)
        self.assertEqual(rep["empty"], 1)

    def test_nothing_pending_is_a_clean_zero(self):
        rep = factory.run(budget=5)
        self.assertEqual((rep["used"], rep["cards"], rep["errors"]), (0, 0, 0))
        self.assertFalse(factory.snapshot().get("running"))

    def test_progress_clears_running_when_done(self):
        self._signal("إشارة وحدة عن الإشغال")
        ideas_mod.generate_for_signal = self._fake(per_item=1)
        factory.run(budget=1)
        snap = factory.snapshot()
        self.assertFalse(snap.get("running"))
        self.assertEqual(snap.get("phase"), "done")

    def test_top_new_returns_ranked_cards(self):
        cards = [_idea("فكرة عن الإشغال والأرقام"), _idea("فكرة ثانية عن التسعير")]
        top = factory.top_new(cards, 2)
        self.assertEqual(len(top), 2)
        self.assertIn("rank_score", top[0])
        self.assertGreaterEqual(top[0]["rank_score"], top[1]["rank_score"])

    def test_top_new_survives_empty(self):
        self.assertEqual(factory.top_new([], 3), [])


if __name__ == "__main__":
    unittest.main()
