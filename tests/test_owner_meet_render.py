# -*- coding: utf-8 -*-
"""owner_meet.render — the presentation is built from the OWNER half only, opens fast, and says
nothing internal (gates G17 + the S2 part of G12).

Fixtures: tests/fixtures/owner_meet/snapshot_full.json (one unit, 12 months) and snapshot_multi.json
(two units) — synthetic, built through the real statement path by tests/owner_meet_fixture_build.py.

Run: python3 -m unittest tests.test_owner_meet_render
"""
import copy
import json
import re
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from owner_meet import render, texts  # noqa: E402

FX = ROOT / "tests" / "fixtures" / "owner_meet"
FULL = json.loads((FX / "snapshot_full.json").read_text(encoding="utf-8"))
MULTI = json.loads((FX / "snapshot_multi.json").read_text(encoding="utf-8"))
ISO = re.compile("20[0-9]{2}-[0-9]{2}-[0-9]{2}")


def _visible(html):
    """Text the viewer can read: tags, scripts and styles stripped."""
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S)
    return re.sub(r"<[^>]+>", " ", html)


class Speed(unittest.TestCase):
    def test_a_12_month_snapshot_renders_in_under_a_second(self):
        render.presentation_html(FULL, 1)                       # warm imports
        t0 = time.perf_counter()
        for _ in range(5):
            render.presentation_html(FULL, 1)
        per = (time.perf_counter() - t0) / 5
        self.assertLess(per, 1.0, "presentation render took %.3fs" % per)


class Structure(unittest.TestCase):
    KEYS = ("cover", "summary", "money", "monthly", "peers", "funnel", "log", "maint", "claims", "reviews", "plan",
            "forecast")

    def test_one_unit_has_every_chapter_in_order_and_one_starts_on(self):
        html = render.presentation_html(FULL, 7)
        self.assertEqual(html.count('<section class="slide'), len(render.chapters(FULL)))
        self.assertEqual(html.count('class="slide on"'), 1)
        self.assertIn('data-meeting="7"', html)
        order = re.findall('data-key="([a-z]+)"', html)
        self.assertEqual([k for i, k in enumerate(order) if i == 0 or order[i - 1] != k], list(self.KEYS))

    def test_a_multi_unit_owner_gets_a_portfolio_cover_then_each_unit(self):
        chs = render.chapters(MULTI)
        self.assertEqual(chs[0]["key"], "portfolio")
        self.assertEqual(sum(1 for c in chs if c["key"] == "cover"), len(MULTI["owner"]["units"]))

    def test_long_lists_continue_on_extra_slides(self):
        snap = copy.deepcopy(FULL)
        u = snap["owner"]["units"][0]
        u["log"]["events"] = [dict(u["log"]["events"][0]) for _ in range(20)]
        u["reviews"]["rows"] = [dict(u["reviews"]["rows"][0], text="ن" * 400) for _ in range(5)]
        chs = render.chapters(snap)
        self.assertEqual(sum(1 for c in chs if c["key"] == "log"), 3)
        self.assertGreaterEqual(sum(1 for c in chs if c["key"] == "reviews"), 3)
        self.assertTrue(any(c["title"].endswith("(تابع)") for c in chs))

    def test_every_chapter_names_its_source(self):
        for c in render.chapters(FULL):
            self.assertIn("المصدر", c["html"], c["key"])

    def test_no_admin_chrome_and_no_sample_words(self):
        html = render.presentation_html(FULL, 1)
        self.assertNotIn("مثال", html)
        self.assertNotIn("<nav", html)
        self.assertNotIn("/api/meet/meetings", html.split("<script")[0])

    def test_no_iso_date_in_visible_text(self):
        for snap in (FULL, MULTI):
            self.assertIsNone(ISO.search(_visible(render.presentation_html(snap, 1))))


class OwnerHalfOnly(unittest.TestCase):
    """Nothing from snapshot["presenter"] may reach the shared tab — not even hidden."""

    def test_presenter_material_never_reaches_the_presentation(self):
        snap = copy.deepcopy(FULL)
        snap["presenter"]["readiness"].append({"level": "red", "key": "x", "text_ar": "سرّ داخلي لا يُعرض"})
        snap["presenter"]["notes"].append({"key": "y", "text_ar": "ملاحظة داخلية خاصة"})
        html = render.presentation_html(snap, 1)
        self.assertNotIn("سرّ داخلي لا يُعرض", html)
        self.assertNotIn("ملاحظة داخلية خاصة", html)
        self.assertNotIn("داخلي", html)
        notes = render.notes_html(snap, 1)
        self.assertIn("سرّ داخلي لا يُعرض", notes)
        self.assertIn("ملاحظة داخلية خاصة", notes)

    def test_peer_counts_appear_only_in_the_presenter_window(self):
        n = FULL["presenter"]["peer_internal"][str(FULL["owner"]["units"][0]["lid"])]["income"]["n"]
        self.assertIn("قورنت بـ %d شقة" % n, render.notes_html(FULL, 1))
        self.assertNotIn("قورنت", render.presentation_html(FULL, 1))

    def test_a_degraded_snapshot_has_no_headline(self):
        snap = copy.deepcopy(FULL)
        snap["owner"]["units"][0]["headline"] = None
        html = render.presentation_html(snap, 1)
        self.assertIn("أرقام هذه الفترة", html)


class EmptyStates(unittest.TestCase):
    def test_missing_data_says_so_honestly(self):
        snap = copy.deepcopy(FULL)
        u = snap["owner"]["units"][0]
        u["trend"], u["peers"] = [], {}
        u["money"]["waterfall"]["reconciled"] = False
        u["log"] = {"events": [], "counters": {}}
        u["maint"] = {"rows": [], "stats": {}}
        u["claims"] = {"rows": [], "ring": {}}
        u["reviews"] = {"rows": [], "summary": {}}
        u["airbnb"], u["actions"], u["forecast"] = None, [], None
        html = render.presentation_html(snap, 1)
        for key in ("monthly", "peers", "funnel", "money", "log", "maint", "claims", "reviews", "plan", "forecast"):
            self.assertIn(texts.EMPTY[key], html, key)


if __name__ == "__main__":
    unittest.main()
