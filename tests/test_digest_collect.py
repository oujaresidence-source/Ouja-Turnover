# -*- coding: utf-8 -*-
"""Collectors on SAVED HTML (tests/fixtures/digest/*, fetched 2026-09-02 with the honest
OujaDigest identity). Every parser is pure; fetch() is exercised through FakeHttp so the
suite never opens a socket. Expected values below were read off the real pages."""
import os
import sys
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "digest"))

from digest import dates
from digest.collect import base, platinumlist, elcinema, saff, kooora, worth, search_secondary
from _fake_http import FakeHttp, fixture, HERE as FIX

TZ = ZoneInfo("Asia/Riyadh")
NOW = datetime(2026, 9, 2, 13, 0, tzinfo=TZ)
WEEK = dates.week_for(NOW)               # Thu 2026-09-03 .. Sat 09-05


def raw(name):
    with open(os.path.join(FIX, name), "rb") as fh:
        return fh.read()


class Base(unittest.TestCase):
    def test_short_title_keeps_casing_and_caps_words(self):
        self.assertEqual(base.short_title("Fall 2: Deadpoint"), "Fall 2: Deadpoint")
        self.assertEqual(base.short_title("La La Land"), "La La Land")
        self.assertEqual(base.short_title("Big Sam Live in Riyadh"), "Big Sam")
        t = base.short_title("ذكريات سبيستون مع الفنان عاصم سكر في الرياض")
        self.assertLessEqual(base.word_count(t) if hasattr(base, "word_count") else len(t.split()), 4)
        self.assertNotIn("الرياض", t)

    def test_category_keywords(self):
        self.assertEqual(base.category_of("ذكريات سبيستون مع الفنان عاصم سكر"), "family")
        self.assertEqual(base.category_of("بيج سام", "حفل"), "concert")
        self.assertEqual(base.category_of("Noor Riyadh"), "exhibition")
        self.assertEqual(base.category_of("سوق الأول"), "market")
        self.assertEqual(base.category_of("مؤتمر التقنية المالية"), "b2b")
        self.assertEqual(base.category_of("شي ما له تصنيف"), "other")

    def test_confidence_formula(self):
        fresh = NOW.isoformat()
        self.assertEqual(base.confidence(base.TIER_PRIMARY, base.AGREE_YES, fresh, NOW), 1.0)
        self.assertEqual(base.confidence(base.TIER_PRIMARY, base.AGREE_NO, fresh, NOW), 0.85)
        stale = "2026-08-27T13:00:00+03:00"                    # 6 days old
        c = base.confidence(base.TIER_SEARCH, base.AGREE_NO, stale, NOW)
        self.assertAlmostEqual(c, 0.55 * 0.5 + 0.30 * 0.5 + 0.15 * (1 / 7.0), places=2)
        self.assertLess(base.confidence(base.TIER_SEARCH, base.AGREE_NO, fresh, NOW), 0.75)   # search-only never primary alone


class Platinumlist(unittest.TestCase):
    html = fixture("platinumlist-this-weekend-20260902.html")

    def test_parses_weekend_cards_only(self):
        cands, dropped = platinumlist.parse(self.html, WEEK, NOW)
        self.assertEqual(len(cands), 6)
        self.assertTrue(all(c["day"] in ("thu", "fri", "sat") for c in cands))
        self.assertTrue(all(c["url"].startswith("https://riyadh.platinumlist.net/ar/event-tickets/") for c in cands))
        self.assertTrue(all(c["source"]["name"] == "Platinumlist" for c in cands))
        self.assertTrue(all(len(c["ttl"].split()) <= 4 for c in cands))
        self.assertTrue(all(len(c["sub"].split()) <= 10 for c in cands))
        # Wednesday 2 Sept cards (the page's first group) are outside the week → absent
        self.assertFalse(any(c["date_iso"] == "2026-09-02" for c in cands))
        # the Sunday/Monday groups on the page are absent too
        self.assertFalse(any(c["date_iso"] >= "2026-09-06" for c in cands))

    def test_sold_out_is_dropped_with_reason(self):
        _, dropped = platinumlist.parse(self.html, WEEK, NOW)
        self.assertEqual(len(dropped), 1)
        self.assertIn("نفدت", dropped[0]["reason"])
        self.assertIn("adonis", dropped[0]["url"])

    def test_price_becomes_arabic_indic_sub(self):
        cands, _ = platinumlist.parse(self.html, WEEK, NOW)
        spacetoon = [c for c in cands if "107433" in c["url"]][0]
        self.assertEqual(spacetoon["day"], "thu")
        self.assertEqual(spacetoon["sub"], "الخميس · من ١٥٠ ريال")
        self.assertEqual(spacetoon["tags"]["category"], "family")

    def test_event_page_gives_venue_and_same_origin_og(self):
        info = platinumlist.parse_event_page(fixture("platinumlist-event-107433-20260902.html"), "")
        self.assertEqual(info["venue"], "مسرح بكر الشدي")
        self.assertTrue(info["og"].startswith("https://cdn.platinumlist.net/"))

    def test_fetch_and_enrich_through_fake_http(self):
        http = FakeHttp(pages={
            platinumlist.CALENDAR_URL: (200, "text/html", self.html),
            "https://riyadh.platinumlist.net/ar/event-tickets/107433/spacetoon-memories-with-assem-sukkar-in-riyadh":
                (200, "text/html", fixture("platinumlist-event-107433-20260902.html")),
        })
        cands, dropped, html = platinumlist.fetch(WEEK, http, NOW, enrich_top=1)
        self.assertEqual(len(cands), 6)
        sp = cands[0]
        self.assertEqual(sp["venue"], "مسرح بكر الشدي")
        self.assertEqual(sp["chip"], "حطين")
        self.assertEqual(sp["tags"]["district"], "حطين")
        self.assertIsNotNone(sp.get("latlng"))
        self.assertEqual(sp["art_hint"]["og"][:29], "https://cdn.platinumlist.net/")
        self.assertEqual(len([c for c in http.calls if c[0] == "get_text"]), 2)

    def test_dead_calendar_reports_not_crashes(self):
        cands, dropped, html = platinumlist.fetch(WEEK, FakeHttp(), NOW)
        self.assertEqual(cands, [])
        self.assertEqual(len(dropped), 1)
        self.assertIn("404", dropped[0]["reason"])


class Cinema(unittest.TestCase):
    html = fixture("elcinema-now-sa-20260902.html")

    def test_films_showing_that_weekend_newest_first(self):
        cands, dropped = elcinema.parse(self.html, WEEK, NOW)
        self.assertEqual(len(cands), 15)
        self.assertEqual(dropped, [])
        self.assertTrue(cands[0]["new_this_week"])
        self.assertEqual(cands[0]["release_iso"], "2026-09-02")
        self.assertEqual(cands[0]["ttl"], "Fall 2: Deadpoint")
        self.assertEqual(cands[0]["sub"], "٢ سبتمبر · مغامرات ودراما")
        self.assertEqual(cands[0]["age"], 12)
        rel = [c["release_iso"] for c in cands]
        self.assertEqual(rel, sorted(rel, reverse=True))
        self.assertTrue(all(c["release_iso"] <= "2026-09-05" for c in cands))

    def test_sub_format_and_chip(self):
        cands, _ = elcinema.parse(self.html, WEEK, NOW)
        import re
        for c in cands:
            with self.subTest(c=c["ttl"]):
                self.assertEqual(c["chip"], "سينما")
                self.assertRegex(c["sub"], "^[٠-٩]{1,2} \\S+( · .+)?$")
                self.assertEqual(c["art_hint"], {})          # no posters: generated art only
                self.assertTrue(c["url"].startswith("https://elcinema.com/work/"))
                self.assertLessEqual(len(c["sub"].split()), 10)

    def test_release_inside_window_sets_the_day(self):
        w = dates.week_for(datetime(2026, 8, 26, 13, tzinfo=TZ))   # Thu 08-27 .. Sat 08-29
        cands, _ = elcinema.parse(self.html, w, NOW)
        thu = [c for c in cands if c["release_iso"] == "2026-08-27"]
        self.assertTrue(thu)
        self.assertTrue(all(c["day"] == "thu" for c in thu))
        self.assertFalse(any(c["release_iso"] > "2026-08-29" for c in cands))


class Fixtures(unittest.TestCase):
    html = raw("saff-roshn-20260902.html").decode("cp1256", "replace")

    def test_riyadh_interest_matches_in_week(self):
        fx, dropped = saff.parse(self.html, WEEK, NOW)
        self.assertEqual(dropped, [])
        pairs = [(f["home"], f["away"]) for f in fx]
        self.assertIn(("الشباب", "الهلال"), pairs)
        self.assertIn(("الدرعية", "القادسية"), pairs)
        self.assertIn(("الاتحاد", "النصر"), pairs)          # Riyadh club away in Jeddah
        self.assertNotIn(("الفيحاء", "الخلود"), pairs)      # neither club nor city
        self.assertTrue(all(f["day"] in ("thu", "fri", "sat") for f in fx))

    def test_when_is_saudi_local_arabic_indic(self):
        fx, _ = saff.parse(self.html, WEEK, NOW)
        sh = [f for f in fx if f["home"] == "الشباب"][0]
        self.assertEqual(sh["when"], "الجمعة ٩:٠٠م")
        self.assertEqual(sh["kickoff_iso"], "2026-09-04T21:00:00+03:00")
        self.assertTrue(sh["in_riyadh"])
        self.assertEqual(sh["tags"]["district"], "الملقا")
        for f in fx:
            self.assertRegex(f["when"], "^(الخميس|الجمعة|السبت) [٠-٩]{1,2}:[٠-٩]{2}[صم]$")

    def test_kooora_cross_check(self):
        events = kooora.parse(fixture("kooora-roshn-20260902.html"))
        self.assertEqual(len(events), 6)
        fx, _ = saff.parse(self.html, WEEK, NOW)
        dq = [f for f in fx if f["home"] == "الدرعية"][0]
        self.assertTrue(kooora.cross_check(dq, events))
        sh = [f for f in fx if f["home"] == "الشباب"][0]
        self.assertIsNone(kooora.cross_check(sh, events))        # no counterpart on the page
        wrong = dict(dq, kickoff_iso="2026-09-03T19:00:00+03:00")
        self.assertFalse(kooora.cross_check(wrong, events))        # counterpart disagrees → False

    def test_fetch_through_fake_http_decodes_bytes(self):
        http = FakeHttp(pages={saff.SCHEDULE_URL: (200, "text/html", self.html)})
        fx, dropped, html = saff.fetch(WEEK, http, NOW)
        self.assertEqual(len(fx), 5)


class Worth(unittest.TestCase):
    def test_seed_entries_need_a_url_to_be_eligible(self):
        places_list = worth.load()
        self.assertGreaterEqual(len(places_list), 10)
        cands = worth.candidates(WEEK, NOW, places_list)
        self.assertTrue(cands)
        self.assertTrue(all(c["url"].startswith("https://") for c in cands))
        self.assertLess(len(cands), len(places_list))            # some entries have no url yet
        resolved = {"wadi-hanifah": "https://www.visitsaudi.com/ar/x"}
        more = worth.candidates(WEEK, NOW, places_list, resolved_urls=resolved)
        self.assertEqual(len(more), len(cands) + 1)

    def test_seed_copy_obeys_the_caps(self):
        for p in worth.load():
            with self.subTest(p=p["slug"]):
                self.assertLessEqual(len(p["ttl"].split()), 4)
                self.assertLessEqual(len(p["sub"].split()), 10)
                self.assertTrue(p["district"])


class Secondary(unittest.TestCase):
    def _search(self, data, urls):
        calls = []
        def s(system, user, max_tokens=0, model=None, max_uses=None, allowed_domains=None):
            calls.append({"system": system, "user": user, "allowed": allowed_domains})
            return data, urls
        s.calls = calls
        return s

    def test_keeps_only_items_whose_url_was_opened(self):
        data = {"items": [
            {"ttl": "معرض الخط العربي", "sub": "قاعة كبيرة", "venue": "المتحف الوطني", "date": "2026-09-04",
             "url": "https://www.visitsaudi.com/ar/e/1"},
            {"ttl": "مخترع", "sub": "x", "venue": "x", "date": "2026-09-04", "url": "https://www.visitsaudi.com/ar/e/2"},
            {"ttl": "خارج الأسبوع", "sub": "x", "venue": "x", "date": "2026-09-09", "url": "https://www.visitsaudi.com/ar/e/3"},
        ]}
        s = self._search(data, ["https://www.visitsaudi.com/ar/e/1", "https://www.visitsaudi.com/ar/e/3/"])
        cands, opened = search_secondary.run("events", WEEK, s, ["visitsaudi.com"], NOW, "معارض")
        self.assertEqual([c["ttl"] for c in cands], ["معرض الخط العربي"])
        self.assertEqual(cands[0]["day"], "fri")
        self.assertEqual(cands[0]["chip"], "المربع")
        self.assertEqual(cands[0]["raw_conf"], base.TIER_SEARCH)
        self.assertEqual(s.calls[0]["allowed"], ["visitsaudi.com"])

    def test_search_failure_is_empty_not_fatal(self):
        def boom(*a, **k):
            raise RuntimeError("no api key")
        self.assertEqual(search_secondary.run("events", WEEK, boom, ["x"], NOW, "q"), ([], []))
        s = self._search(None, [])
        self.assertEqual(search_secondary.run("events", WEEK, s, ["x"], NOW, "q"), ([], []))

    def test_resolve_place_url_only_from_opened_pages(self):
        s = self._search({"url": "https://www.visitsaudi.com/ar/p"}, ["https://www.visitsaudi.com/ar/p"])
        self.assertEqual(search_secondary.resolve_place_url({"search": "وادي حنيفة"}, s, ["visitsaudi.com"]),
                         "https://www.visitsaudi.com/ar/p")
        s2 = self._search({"url": "https://www.visitsaudi.com/ar/made-up"}, [])
        self.assertEqual(search_secondary.resolve_place_url({"search": "وادي حنيفة"}, s2, ["visitsaudi.com"]), "")


if __name__ == "__main__":
    unittest.main()
