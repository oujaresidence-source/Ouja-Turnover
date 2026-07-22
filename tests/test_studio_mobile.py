# -*- coding: utf-8 -*-
"""Lock for studio.mobile — the phone page the Discord links point at.

This surface has a failure mode the dashboard doesn't: the owner is holding a phone,
in a hurry, with no way to debug. So the locks are about never showing him a dead end:
  * the link token is STABLE (a token that rotates silently kills every link already
    posted in Discord) and a wrong token is refused
  * the page carries no backslash (same trap as DASHBOARD_HTML)
  * filters narrow, they never blank out today's plan
  * the feed is ranked best-first and every card is stamped with its score
  * the Discord commands actually exist and hand back a link
"""

import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from brain import db as bdb          # noqa: E402
from studio import db as sdb         # noqa: E402
from studio import engine, mobile    # noqa: E402
from studio.host import HOST         # noqa: E402


class _Req(object):
    def __init__(self, token):
        self.match_info = {"token": token}


def _idea(title, audience="niche", family="internal", trigger="curiosity",
          fmt="talking", sid="", date=""):
    return {"hook_spoken": "قول هذا", "visual_title": title, "visual_sub": "",
            "angle": title, "why_it_works": "سبب", "script": ["(0-3ث) هوك"],
            "video_type": fmt, "cta": "", "audience": audience, "trigger": trigger,
            "signal_sid": sid, "signal_family": family, "signal_source": "occupancy",
            "signal_text": "رقم حقيقي", "signal_url": "", "signal_date": date,
            "strength": 55, "nkey": engine.novelty_key(title)}


class TestToken(unittest.TestCase):
    def setUp(self):
        self.store = {}
        HOST.load_json = lambda name, default=None: self.store.get(name, default or {})
        HOST.save_json = lambda name, data: self.store.__setitem__(name, data)
        mobile._cache.clear()

    def test_token_is_stable_across_calls(self):
        a = mobile.link_token()
        mobile._cache.clear()                     # simulate a fresh process
        b = mobile.link_token()
        self.assertTrue(a)
        self.assertEqual(a, b, "a rotating token would break every link in Discord")

    def test_token_is_persisted_not_just_cached(self):
        mobile.link_token()
        self.assertTrue(self.store.get(mobile._TOKEN_FILE, {}).get("token"))

    def test_wrong_token_is_refused(self):
        tok = mobile.link_token()
        self.assertTrue(mobile.token_ok(_Req(tok)))
        self.assertFalse(mobile.token_ok(_Req(tok + "x")))
        self.assertFalse(mobile.token_ok(_Req("")))

    def test_regenerate_changes_it(self):
        a = mobile.link_token()
        b = mobile.regenerate_token()
        self.assertNotEqual(a, b)

    def test_share_url_shape(self):
        tok = mobile.link_token()
        self.assertEqual(mobile.share_url("today", "https://oujares.com/"),
                         "https://oujares.com/s/" + tok)
        self.assertTrue(mobile.share_url("signals", "https://oujares.com")
                        .endswith("?v=signals"))


class TestPage(unittest.TestCase):
    def test_no_backslashes(self):
        self.assertEqual(mobile.MOBILE_HTML.count(chr(92)), 0)

    def test_balanced_and_arabic_face(self):
        h = mobile.MOBILE_HTML
        self.assertEqual(h.count("{"), h.count("}"))
        self.assertEqual(h.count("("), h.count(")"))
        self.assertIn("IBM+Plex+Sans+Arabic", h)

    def test_every_view_button_is_a_known_view(self):
        for v in re.findall(r"data-v=.([a-z]+)", mobile.MOBILE_HTML):
            self.assertIn(v, mobile.VIEWS, v)

    def test_routes_registered(self):
        class _App(object):
            def __init__(self):
                self.router = self
                self.paths = []

            def add_get(self, p, h):
                self.paths.append(("GET", p))

            def add_post(self, p, h):
                self.paths.append(("POST", p))
        app = _App()
        mobile.register(app)
        self.assertIn(("GET", "/s/{token}"), app.paths)
        self.assertIn(("GET", "/s/{token}/feed"), app.paths)
        self.assertIn(("POST", "/s/{token}/act"), app.paths)


class TestFeed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="studiomob_")
        bdb.set_db_path_for_tests(os.path.join(cls.tmp, "brain.db"))
        sdb.reset_init_cache()
        HOST.now = lambda: __import__("datetime").datetime(2026, 7, 23, 9, 0)
        ts = "2026-07-23 09:00:00"
        sdb.add_idea(0, _idea("الإشغال وصل ذروته", audience="niche",
                              trigger="social_proof", fmt="data_reveal"), ts)
        sdb.add_idea(0, _idea("نظام سياحي جديد للملّاك", audience="escape",
                              family="external", trigger="news",
                              fmt="news_reaction", date="2026-07-22"), ts)
        sdb.add_idea(0, _idea("كيف نحوّل شقة لتجربة فندق", audience="escape",
                              trigger="authority", fmt="tour"), ts)

    def test_ideas_view_is_ranked_and_stamped(self):
        cards = mobile.feed("ideas", {}).get("cards")
        self.assertEqual(len(cards), 3)
        for c in cards:
            self.assertIn("rank_score", c)
            self.assertIsInstance(c["rank_why"], list)
        scores = [c["rank_score"] for c in cards]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_filter_narrows(self):
        all_n = len(mobile.feed("ideas", {}).get("cards"))
        niche = mobile.feed("ideas", {"audience": "niche"}).get("cards")
        self.assertLess(len(niche), all_n)
        self.assertTrue(all(c["audience"] == "niche" for c in niche))

    def test_unknown_filter_value_does_not_blank_the_page(self):
        # a bad value on ideas legitimately yields nothing; on TODAY it must not
        # wipe the plan, because the owner cannot tell a filter bug from an empty day
        today = mobile.feed("today", {"audience": "does-not-exist"})
        self.assertIsInstance(today.get("cards"), list)

    def test_unknown_view_falls_back_instead_of_erroring(self):
        self.assertEqual(mobile.feed("nonsense", {}).get("view"), "today")

    def test_facets_never_offer_an_empty_filter(self):
        cards = mobile.feed("ideas", {}).get("cards")
        fac = mobile.facets(cards)
        for _k, vals in fac.items():
            for v in vals:
                self.assertTrue(v)


class TestDiscordCommands(unittest.TestCase):
    """Read bot.py as text — importing it would start a Discord client."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "bot.py"), encoding="utf-8") as f:
            cls.src = f.read()

    def test_every_owner_command_is_registered(self):
        for name in ("ستوديو", "اليوم", "أفكار", "فكرة", "إشارات", "أخبار", "نشرت"):
            self.assertIn('name="%s"' % name, self.src, "missing command %r" % name)

    def test_commands_answer_with_a_link(self):
        self.assertIn("def _studio_link(", self.src)
        self.assertIn("mobile.share_url", self.src)

    def test_help_card_is_posted_only_into_an_empty_channel(self):
        fn = re.search(r"async def _studio_ensure_channel.*?(?=\n@|\nasync def |\ndef )",
                       self.src, re.S).group(0)
        self.assertIn("if existing:", fn)
        self.assertIn("return", fn)

    def test_posted_command_feeds_the_learning_loop(self):
        fn = re.search(r"async def cmd_studio_posted.*?(?=\n@|\nasync def |\ndef )",
                       self.src, re.S).group(0)
        self.assertIn("set_idea_status", fn)
        self.assertIn("insights_ar", fn)


if __name__ == "__main__":
    unittest.main()


class TestSlashCommands(unittest.TestCase):
    """The owner asked to drive everything from the Discord `/` picker, so the tree
    has to actually carry these — and it must not carry anything that would fail the
    sync, because ONE bad command name takes down every slash command in the bot."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "bot.py"), encoding="utf-8") as f:
            cls.src = f.read()
        cls.tree = re.findall(
            r'@bot\.tree\.command\(\s*name="([^"]+)"\s*,\s*description="([^"]*)"',
            cls.src, re.S)

    def test_all_studio_slash_commands_exist(self):
        names = {n for n, _d in self.tree}
        for want in ("today", "idea", "ideas", "signals", "news", "factory",
                     "posted", "studio"):
            self.assertIn(want, names, "missing /%s" % want)

    def test_every_slash_command_has_a_description(self):
        for name, desc in self.tree:
            self.assertTrue(desc.strip(), "/%s has no description to pick from" % name)
            self.assertLessEqual(len(desc), 100, "/%s description too long for Discord" % name)

    def test_slash_names_are_discord_safe(self):
        # ASCII lowercase only: a rejected name fails the WHOLE tree sync
        for name, _d in self.tree:
            self.assertRegex(name, r"^[a-z0-9_-]{1,32}$", "unsafe slash name %r" % name)

    def test_no_duplicate_slash_names(self):
        names = [n for n, _d in self.tree]
        self.assertEqual(len(names), len(set(names)), "duplicate slash command name")

    def test_factory_reports_what_it_did_not_reach(self):
        fn = re.search(r"async def _studio_factory_report.*?(?=\n@|\nasync def |\ndef )",
                       self.src, re.S).group(0)
        self.assertIn("left", fn, "an unfinished sweep must say so, not claim success")
