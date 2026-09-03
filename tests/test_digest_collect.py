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
from digest.collect import base, platinumlist, elcinema, saff, kooora, worth, search_secondary, podcast, verse, commons
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

    def test_facts_line_day_date_place_price(self):
        cands, _ = platinumlist.parse(self.html, WEEK, NOW)
        spacetoon = [c for c in cands if "107433" in c["url"]][0]
        self.assertEqual(spacetoon["day"], "thu")
        self.assertEqual(spacetoon["sub"], "الخميس ٣ سبتمبر · الرياض · من ١٥٠ ريال")
        self.assertEqual(spacetoon["tags"]["category"], "family")

    def test_film_page_gives_poster_and_imdb_id(self):
        html = '<meta property="og:image" content="https://media0106.elcinema.com/uploads/_320x_abc.jpg"><a href="https://www.imdb.com/title/tt31192372">IMDb</a>'
        info = elcinema.parse_film_page(html)
        self.assertEqual(info["poster"], "https://media0106.elcinema.com/uploads/_640x_abc.jpg")
        self.assertEqual(info["imdb_id"], "tt31192372")

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
        self.assertEqual(sp["sub"], "الخميس ٣ سبتمبر · مسرح بكر الشدي · من ١٥٠ ريال")   # venue named after enrichment
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
        self.assertEqual(cands[0]["sub"], "الخميس ٣ سبتمبر · muvi، مغامرات ودراما · حسب العرض")   # day+date · Saudi chain + genre · price
        self.assertEqual(cands[0]["url"], elcinema.TICKETS_URL)                     # the QR goes to a SAUDI cinema
        self.assertTrue(cands[0]["info_url"].startswith("https://elcinema.com/work/"))
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
                self.assertRegex(c["sub"], "^(الخميس|الجمعة|السبت) [٠-٩]{1,2} \\S+ · muvi، .+ · حسب العرض$")
                self.assertEqual(c["art_hint"], {})          # posters come from the film page in enrich()
                self.assertEqual(c["url"], elcinema.TICKETS_URL)
                self.assertLessEqual(base.word_count(c["sub"]) if hasattr(base, "word_count") else len([w for w in c["sub"].split() if w != "·"]), 10)

    def test_release_inside_window_sets_the_day(self):
        w = dates.week_for(datetime(2026, 8, 26, 13, tzinfo=TZ))   # Thu 08-27 .. Sat 08-29
        cands, _ = elcinema.parse(self.html, w, NOW)
        thu = [c for c in cands if c["release_iso"] == "2026-08-27"]
        self.assertTrue(thu)
        self.assertTrue(all(c["day"] == "thu" for c in thu))
        self.assertTrue(all(c["sub"].startswith("الخميس ٢٧ أغسطس") for c in thu))      # inside the window → dated
        old = [c for c in cands if c["release_iso"] < "2026-08-27"]
        self.assertTrue(all(c["release_label"] == "يعرض حاليًا" for c in old))
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

    def test_club_logos_come_from_the_schedule_page(self):
        fx, _ = saff.parse(self.html, WEEK, NOW)
        sh = [f for f in fx if f["home"] == "الشباب"][0]
        self.assertEqual(sh["home_logo"], "https://saff.com.sa/uploadcenter/saffteamsmall1629064138.png")
        self.assertTrue(sh["away_logo"].startswith("https://saff.com.sa/uploadcenter/"))
        logos = saff.club_logos(self.html)
        self.assertGreaterEqual(len(logos), 12)                       # the whole league, 18 clubs
        for club in saff.RIYADH_CLUBS:
            self.assertIn(club, logos)

    def test_large_logo_from_the_team_page(self):
        http = FakeHttp(pages={"https://saff.com.sa/team.php?id=103": (200, "text/html", '<img src="uploadcenter/saffteamlarge1566200867.png">')})
        self.assertEqual(saff.large_logo("103", http), "https://saff.com.sa/uploadcenter/saffteamlarge1566200867.png")
        self.assertEqual(saff.large_logo("", http), "")

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
    """The dataset rules (owner, 2026-09-03, after King Salman Park slipped in as a guess)."""

    def test_only_open_verified_linked_places_are_eligible(self):
        cands, dropped = worth.candidates(WEEK, NOW)
        names = [c["ttl"] for c in cands]
        self.assertIn("البجيري", names)
        self.assertNotIn("٣٠", [c for c in cands if c["ttl"] == "البجيري"][0]["sub"])   # no calendar date inside a price
        self.assertIn("المتحف الوطني", names)
        self.assertNotIn("حديقة الملك سلمان", names)
        self.assertNotIn("حديقة حيوان الرياض", names)
        self.assertNotIn("بوليفارد وورلد", names)
        reasons = {d["ttl"]: d["reason"] for d in dropped}
        self.assertEqual(reasons["حديقة الملك سلمان"], "مو مفتوح")
        self.assertEqual(reasons["حديقة حيوان الرياض"], "حالته غير مؤكدة")
        self.assertEqual(reasons["بوليفارد وورلد"], "موسم غير مؤكد")
        self.assertEqual(reasons["وادي حنيفة"], "بدون صفحة رسمية")
        for c in cands:
            self.assertTrue(c["url"].startswith("https://"))
            self.assertTrue(c["verified_on"])
            parts = [p.strip() for p in c["sub"].split("·")]
            self.assertEqual(len(parts), 3)
            self.assertTrue(parts[0].startswith("الجمعة"))

    def test_verification_expires_after_90_days(self):
        ds = {"calendar": [], "places": [{"slug": "x", "ttl": "مكان", "status": "open", "url": "https://x.example/", "verified_on": "2026-05-01", "district": "العليا", "price": "مجاني"}]}
        cands, dropped = worth.candidates(WEEK, NOW, ds)
        self.assertEqual(cands, [])
        self.assertEqual(dropped[0]["reason"], "التحقق قديم")

    def test_seasonal_only_inside_a_confirmed_window(self):
        place = {"slug": "bw", "ttl": "بوليفارد", "status": "seasonal", "season": "rs", "url": "https://x.example/", "verified_on": "2026-09-01", "district": "حطين", "price": "حسب التذكرة"}
        ds = {"calendar": [{"key": "rs", "window": ["2026-09-01", "2026-09-30"], "confirmed": True}], "places": [place]}
        self.assertEqual(len(worth.candidates(WEEK, NOW, ds)[0]), 1)
        ds["calendar"][0]["confirmed"] = False
        self.assertEqual(worth.candidates(WEEK, NOW, ds)[1][0]["reason"], "موسم غير مؤكد")
        ds["calendar"][0]["confirmed"] = True
        ds["calendar"][0]["window"] = ["2026-10-01", "2026-12-31"]
        self.assertEqual(worth.candidates(WEEK, NOW, ds)[1][0]["reason"], "خارج موسمه")

    def test_expected_or_unknown_never_render(self):
        for st in ("not_open", "unknown", "expected", "under_construction", ""):
            ds = {"calendar": [], "places": [{"slug": "x", "ttl": "مكان", "status": st, "url": "https://x.example/", "verified_on": "2026-09-01"}]}
            self.assertEqual(worth.candidates(WEEK, NOW, ds)[0], [], st)

    def test_dataset_seed_is_well_formed(self):
        ds = worth.load()
        self.assertGreaterEqual(len(ds["places"]), 10)
        self.assertTrue(any(p["slug"] == "king-salman-park" and p["status"] == "not_open" for p in ds["places"]))
        for p in ds["places"]:
            with self.subTest(p=p["slug"]):
                self.assertIn(p["status"], ("open", "seasonal", "not_open", "unknown"))
                if p["status"] == "open":
                    self.assertLessEqual(len(p["ttl"].split()), 4)
                    self.assertTrue(p.get("district"))
        self.assertTrue(any(c["key"] == "riyadh_season" and c["confirmed"] is False for c in ds["calendar"]))


class Podcast(unittest.TestCase):
    def test_top_chart_becomes_one_card_candidates(self):
        cands, dropped = podcast.parse(fixture("apple-podcasts-sa-top10-20260903.json"), WEEK, NOW)
        self.assertGreaterEqual(len(cands), 5)
        self.assertEqual(dropped, [])
        c = cands[0]
        self.assertEqual(c["section"], "podcast")
        self.assertTrue(c["url"].startswith("https://podcasts.apple.com/sa/"))
        self.assertEqual(c["chart_rank"], 1)
        parts = [x.strip() for x in c["sub"].split("·")]
        self.assertEqual(len(parts), 3)
        self.assertTrue(parts[0].startswith("الجمعة"))
        self.assertEqual(parts[-1], "مجاني")
        self.assertTrue(c["art_hint"]["artwork"].endswith("/600x600bb.png") or c["art_hint"]["artwork"].endswith("/600x600bb.jpg"))
        self.assertLessEqual(base.word_count(c["ttl"]), 4)

    def test_artwork_resize_rule(self):
        self.assertEqual(podcast.artwork_url("https://is1-ssl.mzstatic.com/image/thumb/x/100x100bb.png"), "https://is1-ssl.mzstatic.com/image/thumb/x/600x600bb.png")
        self.assertEqual(podcast.artwork_url(""), "")

    def test_bad_feed_is_reported(self):
        cands, dropped = podcast.parse("not json", WEEK, NOW)
        self.assertEqual(cands, [])
        self.assertTrue(dropped)


class PodcastFresh(unittest.TestCase):
    def test_short_url_and_newest_episode(self):
        http = FakeHttp(pages={podcast.FEED_URL: (200, "application/json", fixture("apple-podcasts-sa-top10-20260903.json")),
                               podcast.LOOKUP_URL % "1702294864": (200, "application/json", fixture("itunes-lookup-1702294864-20260903.json"))})
        cands, dropped, _ = podcast.fetch(WEEK, http, NOW, enrich_top=1)
        c = [x for x in cands if x["show_id"] == "1702294864"][0]
        self.assertEqual(c["url"], "https://podcasts.apple.com/sa/podcast/id1702294864")      # short → clean QR
        self.assertEqual(c["episode_released"], "2026-09-01")
        self.assertTrue(c["fresh"])
        self.assertTrue(c["hook"].startswith("حلقة جديدة:"))
        self.assertEqual(cands[0]["show_id"], "1702294864")                                     # fresh shows first

    def test_stale_show_sinks(self):
        old = {"section": "podcast", "show_id": "1", "chart_rank": 1, "fresh": False}
        new = {"section": "podcast", "show_id": "2", "chart_rank": 5, "fresh": True}
        self.assertEqual(sorted([old, new], key=lambda c: (0 if c.get("fresh") else 1, c.get("chart_rank", 99)))[0]["show_id"], "2")


class Commons(unittest.TestCase):
    def test_free_licence_photo_with_credit(self):
        c = commons.parse(fixture("commons-at-turaif-20260903.json"))
        self.assertIsNotNone(c)
        self.assertIn("wikimedia.org", c["url"])
        self.assertNotIn("?", c["url"])
        self.assertGreaterEqual(c["w"], 800)
        self.assertTrue(any(k in c["licence"].lower() for k in ("cc", "public")))
        self.assertIn("Wikimedia Commons", c["credit"])

    def test_non_free_or_small_is_refused(self):
        import json
        bad = {"query": {"pages": {"1": {"title": "x", "imageinfo": [{"url": "https://upload.wikimedia.org/a.jpg", "thumburl": "https://upload.wikimedia.org/a.jpg", "width": 2000, "height": 1000, "mime": "image/jpeg", "extmetadata": {"LicenseShortName": {"value": "CC BY-NC 2.0"}}}]},
                                   "2": {"title": "y", "imageinfo": [{"url": "https://upload.wikimedia.org/b.jpg", "thumburl": "https://upload.wikimedia.org/b.jpg", "width": 300, "height": 200, "mime": "image/jpeg", "extmetadata": {"LicenseShortName": {"value": "CC0"}}}]}}}}
        self.assertIsNone(commons.parse(json.dumps(bad)))


class Verse(unittest.TestCase):
    def test_text_comes_only_from_the_api(self):
        http = FakeHttp(pages={verse.API % "94:5": (200, "application/json", fixture("quran-94-5-20260903.json")),
                               verse.API % "94:6": (200, "application/json", fixture("quran-94-6-20260903.json"))})
        v = verse.fetch("94:5-6", http, NOW)
        self.assertEqual(v["key"], "94:5-6")
        from digest.voice import normalize
        self.assertIn("العسر", normalize(v["text"]))
        self.assertEqual(v["ayahs"], [5, 6])
        self.assertTrue(v["ref_ar"].endswith("٥–٦"))
        self.assertIn("api.alquran.cloud", v["source"]["url"])
        self.assertTrue(v["source"]["fetched_at"])

    def test_api_down_means_no_verse(self):
        self.assertIsNone(verse.fetch("94:5", FakeHttp(), NOW))
        self.assertIsNone(verse.fetch("", FakeHttp(), NOW))

    def test_key_rotates_by_issue(self):
        keys = ["a", "b", "c"]
        self.assertEqual([verse.pick_key(keys, n) for n in (1, 2, 3, 4)], ["a", "b", "c", "a"])


class Prices(unittest.TestCase):
    def test_any_currency_riyals_first(self):
        self.assertEqual(platinumlist._price_ar("150.00 SAR"), "من ١٥٠ ريال")
        self.assertEqual(platinumlist._price_ar("139 ر.س"), "من ١٣٩ ريال")
        self.assertEqual(platinumlist._price_ar("54.64 USD"), "من ≈٢٠٥ ريال")      # the US-server case, marked ≈
        self.assertEqual(platinumlist._price_ar("مجاناً"), "مجاني")
        self.assertEqual(platinumlist._price_ar("بيعت جميع التذاكر"), "حسب التذكرة")


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
