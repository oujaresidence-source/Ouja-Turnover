# -*- coding: utf-8 -*-
"""digest.rank — scoring + the district/category SPREAD invariant, on synthetic
candidates. Pure; no db, no network."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from digest import rank


def cand(ttl, cat, district, conf=0.9, day="fri", url=None, latlng=None, section="events", **kw):
    c = {"section": section, "ttl": ttl, "sub": "x", "chip": district or "الرياض",
         "url": url or "https://x.example/%s" % ttl, "day": day, "confidence": conf,
         "tags": {"category": cat, "district": district}, "latlng": latlng,
         "source": {"name": "Platinumlist", "url": "https://x", "fetched_at": "2026-09-02T12:00:00+03:00"}}
    c.update(kw)
    return c


class Score(unittest.TestCase):
    def test_weights_sum_to_one_and_parts_in_range(self):
        self.assertAlmostEqual(sum(rank.WEIGHTS.values()), 1.0)
        s, parts = rank.score(cand("أ", "exhibition", "حطين", latlng=(24.766, 46.621)))
        for k, v in parts.items():
            lo = -1.0 if k == "history" else 0.0
            self.assertTrue(lo <= v <= 1.0, (k, v))
        self.assertTrue(0 <= s <= 1)

    def test_b2b_never_beats_an_exhibition_of_equal_confidence(self):
        a, _ = rank.score(cand("معرض", "exhibition", "الدرعية"))
        b, _ = rank.score(cand("مؤتمر", "b2b", "الدرعية"))
        self.assertGreater(a, b)

    def test_novelty_zero_for_a_recently_shipped_url_or_title(self):
        ctx = {"recent_urls": {"https://x.example/أ"}, "recent_titles": {"بينالي الدرعية"}}
        self.assertEqual(rank.novelty(cand("أ", "exhibition", "x"), ctx), 0.0)
        self.assertEqual(rank.novelty(cand("بينالي الدرعيّة", "exhibition", "x", url="https://y"), ctx), 0.0)
        self.assertEqual(rank.novelty(cand("جديد", "exhibition", "x", url="https://z"), ctx), 1.0)

    def test_owner_history_learns_from_rulings(self):
        rulings = [{"action": "drop", "detail": {"district": "حطين"}},
                   {"action": "drop", "detail": {"district": "حطين"}},
                   {"action": "approve", "detail": {"districts": ["الدرعية"], "categories": ["exhibition"]}}]
        self.assertEqual(rank.owner_history(cand("a", "concert", "حطين"), rulings), -1.0)
        self.assertEqual(rank.owner_history(cand("b", "exhibition", "الدرعية"), rulings), 0.5)
        self.assertEqual(rank.owner_history(cand("c", "market", "العليا"), rulings), 0.0)
        # a twice-dropped district sinks below an otherwise equal candidate
        ctx = {"rulings": rulings}
        a, _ = rank.score(cand("a", "concert", "حطين"), ctx)
        b, _ = rank.score(cand("b", "concert", "العليا"), ctx)
        self.assertLess(a, b)

    def test_cinema_prefers_new_this_week(self):
        new = cand("f1", "cinema", "", section="cinema", new_this_week=True)
        old = cand("f2", "cinema", "", section="cinema", new_this_week=False)
        self.assertGreater(rank.score(new)[0], rank.score(old)[0])

    def test_sold_out_has_zero_decision_value(self):
        self.assertEqual(rank.decision_value(cand("x", "concert", "حطين", sold_out=True)), 0.0)

    def test_reasons_are_arabic_and_auditable(self):
        s, parts = rank.score(cand("أ", "exhibition", "حطين", latlng=(24.766, 46.621), conf=0.95))
        r = rank.reasons_ar(cand("أ", "exhibition", "حطين"), parts)
        self.assertTrue(any("مصدر" in x for x in r))
        self.assertTrue(any("قريب" in x for x in r))


class Spread(unittest.TestCase):
    def test_three_boulevard_concerts_lose_to_a_mixed_set(self):
        cs = [cand("حفلة ١", "concert", "حطين", conf=0.95, latlng=(24.766, 46.621)),
              cand("حفلة ٢", "concert", "حطين", conf=0.95, latlng=(24.766, 46.621)),
              cand("حفلة ٣", "concert", "حطين", conf=0.95, latlng=(24.766, 46.621)),
              cand("معرض", "exhibition", "الدرعية", conf=0.85, latlng=(24.737, 46.576)),
              cand("سوق", "market", "العليا", conf=0.8, latlng=(24.711, 46.674))]
        got = rank.choose({"events": cs})
        prim = got["primary"]["events"]
        cats = [c["tags"]["category"] for c in prim]
        districts = [c["tags"]["district"] for c in prim]
        self.assertEqual(sorted(cats), ["concert", "exhibition", "market"])
        self.assertEqual(len(set(districts)), len(districts))
        self.assertIn("حفلة ١", [c["ttl"] for c in prim])   # the best of the three concerts is the one kept

    def test_alternates_are_next_three_and_respect_spread_against_the_others(self):
        cs = [cand("حفلة ١", "concert", "حطين", conf=0.95),
              cand("حفلة ٢", "concert", "حطين", conf=0.9),
              cand("معرض", "exhibition", "الدرعية", conf=0.85),
              cand("سوق", "market", "العليا", conf=0.8),
              cand("مسرحية", "theatre", "الملز", conf=0.8),
              cand("سيرك", "family", "الياسمين", conf=0.78)]
        got = rank.choose({"events": cs})
        prim = got["primary"]["events"]
        self.assertEqual(len(prim), 4)
        alts0 = got["alternates"]["events.0"]
        self.assertLessEqual(len(alts0), 3)
        self.assertTrue(alts0)
        for a in alts0:
            self.assertNotIn(a["ttl"], [p["ttl"] for p in prim])
        # the FIRST alternate respects the spread against the other three primaries
        a = alts0[0]
        for p in prim[1:]:
            self.assertNotEqual(a["tags"]["category"], p["tags"]["category"])
            self.assertNotEqual(a["tags"]["district"], p["tags"]["district"])

    def test_spread_relaxes_rather_than_starve_the_floor(self):
        cs = [cand("حفلة ١", "concert", "حطين", conf=0.95), cand("حفلة ٢", "concert", "حطين", conf=0.9)]
        prim = rank.choose({"events": cs})["primary"]["events"]
        self.assertEqual(len(prim), 2)          # two concerts beat an empty digest

    def test_low_confidence_never_primary(self):
        cs = [cand("بحث", "exhibition", "الدرعية", conf=0.6), cand("موثوق", "market", "العليا", conf=0.9),
              cand("موثوق ٢", "family", "الملز", conf=0.9)]
        got = rank.choose({"events": cs})
        self.assertNotIn("بحث", [p["ttl"] for p in got["primary"]["events"]])
        self.assertIn("بحث", [a["ttl"] for a in got["alternates"]["events.0"]])

    def test_cinema_is_three_or_nothing_and_worth_is_one(self):
        films = [cand("f%d" % i, "cinema", "", section="cinema", new_this_week=(i == 0)) for i in range(5)]
        got = rank.choose({"cinema": films, "worth": [cand("w1", "park", "الدرعية", section="worth"), cand("w2", "museum", "المربع", section="worth")]})
        self.assertEqual(len(got["primary"]["cinema"]), 3)
        self.assertEqual(got["primary"]["cinema"][0]["ttl"], "f0")
        self.assertEqual(len(got["primary"]["worth"]), 1)
        self.assertEqual(len(rank.choose({"cinema": films[:2]})["primary"]["cinema"]), 0)

    def test_fixtures_riyadh_first_then_kickoff_order_cap_six(self):
        fx = [{"section": "fixtures", "home": "h%d" % i, "away": "a", "confidence": 0.9, "in_riyadh": i % 2 == 0,
               "kickoff_iso": "2026-09-0%dT%02d:00:00+03:00" % (3 + i % 3, 18 + i % 4), "tags": {"category": "sport", "district": ""}}
              for i in range(8)]
        prim = rank.choose({"fixtures": fx})["primary"]["fixtures"]
        self.assertEqual(len(prim), 6)
        self.assertEqual(sum(1 for f in prim if f["in_riyadh"]), 4)        # every Riyadh match is kept
        self.assertEqual([f["kickoff_iso"] for f in prim], sorted(f["kickoff_iso"] for f in prim))

    def test_stable_for_equal_scores(self):
        cs = [cand("أ", "exhibition", "x"), cand("ب", "exhibition", "x", url="https://b")]
        r1 = rank._ranked(cs, {})
        self.assertEqual([c["ttl"] for c in r1], ["أ", "ب"])


if __name__ == "__main__":
    unittest.main()
