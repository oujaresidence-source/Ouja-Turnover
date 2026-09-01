# -*- coding: utf-8 -*-
"""digest.schema — the frozen content contract between research and render.
Every cap and word limit is a rule here (not discipline), and fewer items must be
legal: a missing slot renders a smaller grid, never a placeholder."""
import copy
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from digest import schema

HERE = os.path.dirname(os.path.abspath(__file__))
GOOD = os.path.join(HERE, "fixtures", "digest", "payload_good.json")


def good():
    with open(GOOD, encoding="utf-8") as fh:
        return json.load(fh)


def section(p, key):
    return [s for s in p["sections"] if s["key"] == key][0]


class GoodPayload(unittest.TestCase):
    def test_good_payload_validates_clean(self):
        self.assertEqual(schema.validate(good()), [])
        schema.assert_valid(good())          # must not raise

    def test_section_titles_are_the_brief_verbatim(self):
        self.assertEqual(schema.SECTIONS["events"]["title"], "فعاليات ومعارض")
        self.assertEqual(schema.SECTIONS["cinema"]["title"], "جديد في السينما")
        self.assertEqual(schema.SECTIONS["worth"]["title"], "يستاهل الزيارة")
        self.assertEqual(schema.SECTIONS["fixtures"]["title"], "مباريات الأسبوع")


class Caps(unittest.TestCase):
    def _errs(self, p):
        return schema.validate(p)

    def test_events_need_two_to_four(self):
        p = good(); section(p, "events")["items"] = section(p, "events")["items"][:1]
        self.assertTrue(any("events" in e for e in self._errs(p)))
        p = good(); s = section(p, "events")
        s["items"] = s["items"] + [copy.deepcopy(s["items"][0]) for _ in range(2)]   # 5
        self.assertTrue(any("events" in e for e in self._errs(p)))

    def test_cinema_is_exactly_three_or_absent(self):
        p = good(); section(p, "cinema")["items"] = section(p, "cinema")["items"][:2]
        self.assertTrue(any("cinema" in e for e in self._errs(p)))
        p = good(); section(p, "cinema")["items"] = []
        self.assertEqual(self._errs(p), [])
        p = good(); p["sections"] = [s for s in p["sections"] if s["key"] != "cinema"]
        self.assertEqual(self._errs(p), [])

    def test_worth_is_at_most_one(self):
        p = good(); s = section(p, "worth"); s["items"] = s["items"] * 2
        self.assertTrue(any("worth" in e for e in self._errs(p)))

    def test_fixtures_cap_six(self):
        p = good(); s = section(p, "fixtures"); s["items"] = s["items"] * 4     # 8
        self.assertTrue(any("fixtures" in e for e in self._errs(p)))

    def test_unknown_section_key_refused(self):
        p = good(); p["sections"].append({"title": "x", "key": "gossip", "layout": "g1", "items": []})
        self.assertTrue(any("gossip" in e for e in self._errs(p)))


class Items(unittest.TestCase):
    def test_title_over_four_words_named_in_error(self):
        p = good(); it = section(p, "events")["items"][0]
        it["ttl"] = "نور الرياض يرجع مرة ثانية السنة"
        errs = schema.validate(p)
        self.assertTrue(any("نور الرياض يرجع" in e and "4" in e for e in errs), errs)

    def test_sub_over_ten_words_refused(self):
        p = good(); it = section(p, "events")["items"][0]
        it["sub"] = " ".join(["كلمة"] * 11)
        self.assertTrue(any("sub" in e for e in schema.validate(p)))

    def test_url_must_be_https_and_verified(self):
        p = good(); it = section(p, "events")["items"][0]
        it["url"] = "http://riyadh.platinumlist.net/event/noor-riyadh-2026"
        self.assertTrue(any("https" in e for e in schema.validate(p)))
        p = good(); it = section(p, "events")["items"][0]
        it["url"] = "https://riyadh.platinumlist.net/event/not-verified"
        self.assertTrue(any("verified" in e for e in schema.validate(p)))

    def test_primary_confidence_floor(self):
        p = good(); section(p, "events")["items"][0]["confidence"] = 0.6
        self.assertTrue(any("confidence" in e for e in schema.validate(p)))

    def test_day_must_be_in_window(self):
        p = good(); section(p, "events")["items"][0]["day"] = "sun"
        self.assertTrue(any("day" in e for e in schema.validate(p)))

    def test_source_required(self):
        p = good(); section(p, "events")["items"][0]["source"] = {}
        self.assertTrue(any("source" in e for e in schema.validate(p)))

    def test_fixture_needs_home_away_when(self):
        p = good(); del section(p, "fixtures")["items"][0]["away"]
        self.assertTrue(any("away" in e for e in schema.validate(p)))

    def test_art_kind_enum(self):
        p = good(); section(p, "events")["items"][0]["art"]["kind"] = "stock"
        self.assertTrue(any("art" in e for e in schema.validate(p)))

    def test_assert_valid_raises_schema_error(self):
        p = good(); section(p, "events")["items"] = []
        with self.assertRaises(schema.SchemaError):
            schema.assert_valid(p)


class Layouts(unittest.TestCase):
    def test_layout_follows_item_count(self):
        self.assertEqual(schema.layout_for("events", 2), "g2h")
        self.assertEqual(schema.layout_for("events", 3), "g3v")
        self.assertEqual(schema.layout_for("events", 4), "g2")
        self.assertEqual(schema.layout_for("cinema", 3), "g3")
        self.assertEqual(schema.layout_for("worth", 1), "g1")
        self.assertEqual(schema.layout_for("fixtures", 2), "fix")
        self.assertEqual(schema.layout_for("fixtures", 6), "fix")

    def test_layout_mismatch_is_an_error(self):
        p = good(); section(p, "events")["layout"] = "g2"      # 3 items → g3v
        self.assertTrue(any("layout" in e for e in schema.validate(p)))

    def test_word_count_is_whitespace_tokens(self):
        self.assertEqual(schema.word_count("  نور   الرياض يرجع "), 3)
        self.assertEqual(schema.word_count(""), 0)

    def test_empty_payload_skeleton_validates(self):
        p = schema.empty_payload("2026-09-03", "٣–٥ سبتمبر", 12, "2026-09-02T13:00:00+03:00")
        # events below its floor is the ONE thing an empty issue is allowed to violate;
        # the build refuses to ship it, but the skeleton itself must be well-formed.
        errs = schema.validate(p)
        self.assertTrue(all("events" in e for e in errs), errs)


if __name__ == "__main__":
    unittest.main()
