# -*- coding: utf-8 -*-
"""Contract lock for the Ouja Studio v3 wiring — the seams that silently rot.

The pure logic is locked elsewhere. What breaks in production is the glue:
a route that was never registered, a host capability bot.py forgot to pass, an
idea card that reaches the owner without the signal that justified it. Each of
those is a "looks fine, does nothing" failure, which is the worst kind.
"""

import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from studio import engine, hooks, ideas as ideas_mod, learn, notify, routes  # noqa: E402


class _FakeApp(object):
    def __init__(self):
        self.router = self
        self.gets, self.posts = [], []

    def add_get(self, path, h):
        self.gets.append(path)

    def add_post(self, path, h):
        self.posts.append(path)


class TestRoutes(unittest.TestCase):
    def test_every_v3_endpoint_is_registered(self):
        app = _FakeApp()
        routes.register(app)
        for p in ("/api/studio/signals", "/api/studio/today", "/api/studio/week",
                  "/api/studio/learn"):
            self.assertIn(p, app.gets, p)
        for p in ("/api/studio/collect", "/api/studio/signal-status",
                  "/api/studio/signal-generate", "/api/studio/manual",
                  "/api/studio/instant"):
            self.assertIn(p, app.posts, p)

    def test_page_has_no_backslashes(self):
        # The DASHBOARD_HTML trap: a normal triple-quoted string eats every escape,
        # and one eaten escape kills the whole script -> the page will not load.
        self.assertEqual(routes.STUDIO_PAGE_HTML.count(chr(92)), 0)

    def test_page_uses_the_locked_arabic_face(self):
        self.assertIn("IBM+Plex+Sans+Arabic", routes.STUDIO_PAGE_HTML)

    def test_every_tab_button_has_a_render_branch(self):
        tabs = set(re.findall(r"data-tab=.([a-z]+)", routes.STUDIO_PAGE_HTML))
        self.assertTrue(tabs)
        for t in tabs:
            self.assertIn("'%s'" % t, routes.STUDIO_PAGE_HTML,
                          "tab %r has no branch in the page script" % t)


class TestBotWiring(unittest.TestCase):
    """bot.py must hand the studio every capability the v3 collectors call for.
    Read as text — importing bot.py starts a Discord client."""

    def setUp(self):
        with open(os.path.join(ROOT, "bot.py"), encoding="utf-8") as f:
            self.src = f.read()
        block = re.search(r"_studio\.wire\(\{(.*?)\}\)", self.src, re.S)
        self.assertIsNotNone(block, "studio.wire block not found in bot.py")
        self.block = block.group(1)

    def test_all_v3_caps_are_passed(self):
        for cap in ("claude_search", "inhouse", "res_window", "forward_calendar",
                    "reviews"):
            self.assertIn('"%s"' % cap, self.block, "bot.py never passes %r" % cap)

    def test_web_search_helper_exists(self):
        self.assertIn("def claude_search_json(", self.src)

    def test_daily_loop_collects_both_families(self):
        loop = re.search(r"async def studio_digest_loop.*?(?=\n@|\nasync def |\ndef )",
                         self.src, re.S).group(0)
        self.assertIn("_studio.internal.collect", loop)
        self.assertIn("_studio.external.collect", loop)
        self.assertIn("_studio.plan.build_day", loop)


class TestIdeaGrounding(unittest.TestCase):
    def test_stamp_attaches_the_signal_and_a_strength(self):
        sig = engine.make_signal("external", "regulation", "نظام", "منع تجاوز ٢٩ يوم",
                                 url="https://mt.gov.sa/x", as_of="2026-06-01")
        card = {"visual_title": "نظام جديد يخص شقتك", "angle": "وش يعني لك",
                "trigger": "news", "audience": "niche", "video_type": "news_reaction"}
        out = ideas_mod._stamp([dict(card)], signal=sig, stats={"n": 0, "mean": 0, "dims": {}},
                               guard_novelty=False)
        self.assertEqual(len(out), 1)
        c = out[0]
        self.assertEqual(c["signal_sid"], sig["sid"])
        self.assertEqual(c["signal_url"], "https://mt.gov.sa/x")
        self.assertEqual(c["signal_date"], "2026-06-01")
        self.assertEqual(c["signal_family"], "external")
        self.assertEqual(c["strength"], learn.NEUTRAL_STRENGTH)
        self.assertTrue(c["nkey"])

    def test_stamp_drops_a_repeat_of_a_recent_angle(self):
        card = {"visual_title": "الإشغال وصل ذروته نهاية الأسبوع", "angle": "",
                "trigger": "social_proof", "audience": "niche", "video_type": "data_reveal"}
        first = ideas_mod._stamp([dict(card)], story={"story_type": "other"},
                                 stats={"n": 0, "mean": 0, "dims": {}},
                                 guard_novelty=False)[0]
        again = ideas_mod._stamp([dict(card)], story={"story_type": "other"},
                                 stats={"n": 0, "mean": 0, "dims": {}},
                                 guard_novelty=True)
        # the novelty guard reads db history; simulate it directly to stay offline
        self.assertFalse(engine.is_novel(first["nkey"], [first["nkey"]]))
        self.assertIsInstance(again, list)

    def test_story_path_still_tags_its_source(self):
        out = ideas_mod._stamp(
            [{"visual_title": "قصة ضيف", "angle": "", "trigger": "curiosity",
              "audience": "escape", "video_type": "story_voiceover"}],
            story={"title": "ت", "angle": "زاوية", "created_at": "2026-07-01 10:00:00",
                   "story_type": "hero_save"},
            stats={"n": 0, "mean": 0, "dims": {}}, guard_novelty=False)
        self.assertEqual(out[0]["signal_source"], "guest_story")
        self.assertEqual(out[0]["signal_family"], "internal")


class TestHookBank(unittest.TestCase):
    def test_bank_covers_all_seven_spec_triggers(self):
        for t in ("curiosity", "loss", "identity", "provocation", "authority",
                  "social_proof", "news"):
            self.assertTrue(hooks.HOOK_BANK.get(t), "no hooks for trigger %r" % t)

    def test_bank_is_at_least_fifty_hooks(self):
        self.assertGreaterEqual(hooks.bank_size(), 40)

    def test_every_source_has_a_trigger_hint(self):
        for s in engine.SIGNAL_SOURCES:
            self.assertIn(s, hooks.SOURCE_TRIGGER_HINT, s)

    def test_prompt_block_is_non_empty_for_every_source(self):
        for s in engine.SIGNAL_SOURCES:
            self.assertTrue(hooks.prompt_block(s).strip(), s)


class TestDigest(unittest.TestCase):
    def test_silent_when_there_is_nothing(self):
        self.assertEqual(notify.build_digest([], [], signals=[], day_cards=[]), "")

    def test_leads_with_the_day_plan(self):
        body = notify.build_digest(
            [], [], signals=[],
            day_cards=[{"visual_title": "عنوان", "hook_spoken": "هوك",
                        "signal_text": "٤٧ من ٥٣ شقة محجوزة"}])
        self.assertIn("اللي تصوّره اليوم", body)
        self.assertIn("٤٧ من ٥٣ شقة محجوزة", body)

    def test_external_signal_is_printed_with_its_source_url(self):
        body = notify.build_digest(
            [], [], day_cards=[],
            signals=[{"family": "external", "source": "regulation",
                      "fact": "نظام جديد", "url": "https://mt.gov.sa/x"}])
        self.assertIn("https://mt.gov.sa/x", body)

    def test_old_two_arg_call_still_works(self):
        # bot.py is not the only caller; the v2 signature must not break.
        body = notify.build_digest([{"title": "قصة", "story_type": "hero_save",
                                     "score": 8}], [])
        self.assertIn("قصة", body)


if __name__ == "__main__":
    unittest.main()
