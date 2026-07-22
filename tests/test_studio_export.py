# -*- coding: utf-8 -*-
"""TDD lock for studio.export — the single ready file.

He reads this on a phone with nothing else open, so the file has to be *complete*:
if the script, the hook, the grounding signal or the fixes are missing from the
document, they effectively don't exist. And it must never claim to be fresher than
it is — a stale timestamp on a file about time-sensitive news is a real failure.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from studio import export, learn  # noqa: E402


def _card(title="الإشغال وصل ذروته", **kw):
    c = {"id": 7, "visual_title": title, "visual_sub": "لو عندك شقة بالرياض",
         "hook_spoken": "٩٠٪ من ضيوفنا يحجزون قبل يوم",
         "angle": "نشرح الحجز اللحظي",
         "script": ["(٠-٣ث) الهوك", "(٣-١٢ث) الشرح", "(١٢-٢٢ث) الخلاصة"],
         "cta": "احفظ الفيديو", "why_it_works": "رقم حقيقي أول ٣ث",
         "audience": "niche", "trigger_kind": "social_proof", "video_type": "data_reveal",
         "signal_text": "وسيط مهلة الحجز يوم واحد", "signal_source": "occupancy",
         "signal_date": "2026-07-23", "signal_url": "",
         "rank_score": 78, "virality": 91, "fixes": [], "status": "new"}
    c.update(kw)
    return c


def _signal(fact="٤٧ من ٥٣ شقة محجوزة", family="internal", **kw):
    s = {"sid": "abc", "family": family, "source": "occupancy", "fact": fact,
         "detail": "تفصيل", "url": "", "as_of": "2026-07-23", "strength": 80,
         "status": "new"}
    s.update(kw)
    return s


class TestCompleteness(unittest.TestCase):
    def setUp(self):
        self.doc = export.render(
            [_card()], [_card(title="فكرة ثانية", id=8)],
            [_signal(), _signal("نظام جديد يمنع تجاوز ٢٩ يوم", family="external",
                                source="regulation", url="https://mt.gov.sa/x")],
            learn.stats([]), generated_at="2026-07-23 09:00:00",
            link="https://oujares.com/s/tok", day="2026-07-23")

    def test_everything_needed_to_film_is_in_the_file(self):
        for must in ("٩٠٪ من ضيوفنا يحجزون قبل يوم",     # the hook
                     "(٣-١٢ث) الشرح",                     # the script beat
                     "وسيط مهلة الحجز يوم واحد",          # the grounding signal
                     "احفظ الفيديو",                       # the CTA
                     "لو عندك شقة بالرياض"):               # on-screen line
            self.assertIn(must, self.doc, must)

    def test_scores_and_the_card_id_are_present(self):
        self.assertIn("78", self.doc)
        self.assertIn("91", self.doc)
        self.assertIn("`7`", self.doc, "the id is how he logs the video later")

    def test_timestamp_and_live_link_are_stated(self):
        self.assertIn("2026-07-23 09:00:00", self.doc)
        self.assertIn("https://oujares.com/s/tok", self.doc)

    def test_external_source_url_survives_into_the_file(self):
        self.assertIn("https://mt.gov.sa/x", self.doc)

    def test_both_signal_families_get_their_own_section(self):
        self.assertIn("من برّا", self.doc)
        self.assertIn("من بيانات عوجا", self.doc)


class TestFixesAndStatus(unittest.TestCase):
    def test_fixes_are_written_out(self):
        doc = export.render([_card(fixes=["قصّر الهوك", "خلّ النهاية ترجع للبداية"])],
                            [], [], learn.stats([]))
        self.assertIn("قصّر الهوك", doc)
        self.assertIn("عدّل قبل ما تصوّر", doc)

    def test_posted_card_shows_its_views_and_is_not_counted_as_ready(self):
        doc = export.render([], [_card(status="posted", views=84000)], [],
                            learn.stats([]))
        self.assertIn("84,000", doc)
        self.assertIn("0 فكرة جاهزة", doc)


class TestEmptyStates(unittest.TestCase):
    def test_empty_studio_still_renders_a_usable_file(self):
        doc = export.render([], [], [], learn.stats([]))
        self.assertIn("استوديو عوجا", doc)
        self.assertIn("ما فيه خطة لليوم", doc)
        self.assertIn("الرف فاضي", doc)
        self.assertIn("ما فيه إشارات", doc)

    def test_no_learning_data_says_so_instead_of_faking_insight(self):
        doc = export.render([], [], [], learn.stats([]))
        self.assertIn("ما فيه بيانات كافية", doc)

    def test_junk_inputs_do_not_raise(self):
        self.assertTrue(export.render(None, None, None, None))


class TestLearningSection(unittest.TestCase):
    def test_findings_appear_once_there_is_history(self):
        rows = ([{"status": "posted", "views": 200, "trigger_kind": "curiosity",
                  "audience": "niche", "video_type": "talking",
                  "signal_family": "internal"}] * 3
                + [{"status": "posted", "views": 4000, "trigger_kind": "news",
                    "audience": "niche", "video_type": "talking",
                    "signal_family": "internal"}] * 3)
        doc = export.render([], [], [], learn.stats(rows))
        self.assertIn("6", doc)
        self.assertNotIn("ما فيه بيانات كافية", doc)


class TestFilename(unittest.TestCase):
    def test_is_markdown(self):
        self.assertTrue(("ouja-studio-2026-07-23.md").endswith(".md"))


class TestOneCommandContract(unittest.TestCase):
    """The single command and the single file, as the owner asked for them."""

    @classmethod
    def setUpClass(cls):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "bot.py"), encoding="utf-8") as f:
            cls.src = f.read()
        with open(os.path.join(root, "studio", "mobile.py"), encoding="utf-8") as f:
            cls.mob = f.read()

    def test_everything_command_exists_on_the_slash_tree(self):
        self.assertIn('name="everything"', self.src)
        self.assertIn('name="file"', self.src)

    def test_everything_attaches_the_file_not_just_a_summary(self):
        import re as _re
        fn = _re.search(r"async def _studio_everything_report.*?(?=\n@|\nasync def |\ndef )",
                        self.src, _re.S).group(0)
        self.assertIn("discord.File", fn)
        self.assertIn("rep.get(\"doc\")", fn)

    def test_a_failed_attachment_is_reported_not_hidden(self):
        import re as _re
        fn = _re.search(r"async def _studio_everything_report.*?(?=\n@|\nasync def |\ndef )",
                        self.src, _re.S).group(0)
        self.assertIn("ما زبط", fn, "a silent failure would look like success")

    def test_public_base_is_wired_so_the_file_carries_a_live_link(self):
        self.assertIn('"public_base"', self.src)

    def test_always_fresh_file_url_is_registered(self):
        self.assertIn("/s/{token}/export.md", self.mob)


if __name__ == "__main__":
    unittest.main()
