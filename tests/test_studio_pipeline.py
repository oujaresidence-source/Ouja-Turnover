# -*- coding: utf-8 -*-
"""TDD lock for studio.pipeline — the one-command full run.

This is the command he will actually use, so its failure modes matter most:
  * a broken step must NOT cost him the remaining steps (a dead web search should
    never mean no ideas and no file)
  * the file is produced even when everything upstream returned nothing
  * the summary states what each step did, including what it could NOT reach —
    a run that reports success while skipping half the shelf is the worst outcome
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from studio import pipeline  # noqa: E402


class _Stub(object):
    """Stands in for the collector modules pipeline imports at call time."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


class TestRun(unittest.TestCase):
    def setUp(self):
        import studio
        self.real = {}
        for name in ("internal", "external", "mine", "factory", "plan", "export"):
            self.real[name] = getattr(studio, name)
        self.studio = studio
        pipeline.PROGRESS.clear()

    def tearDown(self):
        for name, mod in self.real.items():
            setattr(self.studio, name, mod)

    def _wire(self, internal=None, external=None, mine=None, factory=None,
              plan=None, export=None):
        self.studio.internal = internal or _Stub(collect=lambda: [{"sid": "a"}])
        self.studio.external = external or _Stub(collect=lambda: [{"sid": "b"}])
        self.studio.mine = mine or _Stub(run_daily_scan=lambda: [{"id": 1}])
        self.studio.factory = factory or _Stub(
            DEFAULT_BUDGET=60,
            pending_sources=lambda: [{"kind": "signal", "id": "a"}],
            run=lambda budget=None, sources=None: {"cards": 2, "left": 0, "empty": 0})
        self.studio.plan = plan or _Stub(DAILY_N=3,
                                         build_day=lambda *a, **k: [{"id": 1}, {"id": 2}])
        self.studio.export = export or _Stub(
            document=lambda: ("# ملف", "ouja-studio-2026-07-23.md"))

    def test_happy_path_reports_every_step(self):
        self._wire()
        r = pipeline.run()
        self.assertEqual(r["internal"], 1)
        self.assertEqual(r["external"], 1)
        self.assertEqual(r["stories"], 1)
        self.assertEqual(r["cards"], 2)
        self.assertEqual(r["planned"], 2)
        self.assertTrue(r["doc"])
        self.assertTrue(r["filename"].endswith(".md"))
        self.assertEqual(r["failed"], [])

    def test_a_broken_step_does_not_cost_the_later_steps(self):
        def boom():
            raise RuntimeError("search is down")
        self._wire(external=_Stub(collect=boom))
        r = pipeline.run()
        self.assertIn("external", r["failed"])
        self.assertEqual(r["cards"], 2, "generation must still run")
        self.assertTrue(r["doc"], "he must still get the file")

    def test_every_step_can_fail_and_the_file_still_arrives(self):
        def boom():
            raise RuntimeError("down")
        self._wire(internal=_Stub(collect=boom), external=_Stub(collect=boom),
                   mine=_Stub(run_daily_scan=boom),
                   factory=_Stub(DEFAULT_BUDGET=60, pending_sources=boom, run=boom),
                   plan=_Stub(DAILY_N=3, build_day=boom))
        r = pipeline.run()
        self.assertTrue(r["doc"])
        self.assertGreaterEqual(len(r["failed"]), 4)

    def test_web_search_can_be_skipped(self):
        self._wire()
        r = pipeline.run(web_search=False)
        self.assertTrue(r.get("skipped_external"))
        self.assertEqual(r["external"], 0)
        self.assertIn("متخطّى", pipeline.summary_ar(r))

    def test_empty_everything_is_a_clean_zero_not_an_error(self):
        self._wire(internal=_Stub(collect=lambda: []),
                   external=_Stub(collect=lambda: []),
                   mine=_Stub(run_daily_scan=lambda: []),
                   factory=_Stub(DEFAULT_BUDGET=60, pending_sources=lambda: [],
                                 run=lambda budget=None, sources=None:
                                 {"cards": 0, "left": 0, "empty": 0}),
                   plan=_Stub(DAILY_N=3, build_day=lambda *a, **k: []))
        r = pipeline.run()
        self.assertEqual(r["failed"], [])
        self.assertEqual(r["cards"], 0)
        self.assertTrue(r["doc"])

    def test_progress_is_cleared_when_finished(self):
        self._wire()
        pipeline.run()
        self.assertFalse(pipeline.snapshot().get("running"))

    def test_budget_reaches_the_factory(self):
        seen = {}
        self._wire(factory=_Stub(
            DEFAULT_BUDGET=60,
            pending_sources=lambda: [{"kind": "signal", "id": "a"}],
            run=lambda budget=None, sources=None: seen.update(b=budget) or
            {"cards": 0, "left": 0, "empty": 0}))
        pipeline.run(budget=7)
        self.assertEqual(seen.get("b"), 7)


class TestSummary(unittest.TestCase):
    def test_unreached_sources_are_named_not_hidden(self):
        s = pipeline.summary_ar({"internal": 1, "external": 2, "stories": 3,
                                 "cards": 4, "sources": 20, "planned": 3, "left": 11})
        self.assertIn("11", s)
        self.assertIn("مرة ثانية", s)

    def test_failed_steps_are_named_in_arabic(self):
        s = pipeline.summary_ar({"failed": ["external"]})
        self.assertIn("يبحث بالويب", s)

    def test_clean_run_has_no_warning(self):
        s = pipeline.summary_ar({"internal": 1, "external": 1, "stories": 1,
                                 "cards": 5, "sources": 5, "planned": 3,
                                 "left": 0, "failed": []})
        self.assertNotIn("⚠️", s)


if __name__ == "__main__":
    unittest.main()
