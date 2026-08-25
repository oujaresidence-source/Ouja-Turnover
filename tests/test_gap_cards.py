# -*- coding: utf-8 -*-
"""Elite v5 Brain decision engine — synthetic, no network, no DB.

Drives brain.cards (segments + guardrails + recommend_today + send-list CSV) and brain.gaps
(open-apartment inventory) with hand-built guests/availability and asserts the build spec:
the right campaign fires for the right calendar day, the segment + guardrails select the audience,
the fill estimate Y never exceeds the open apartments X, and the CSV is deduped + filtered.
"""
import csv
import io
import unittest
from datetime import date

from brain import cards, gaps


def member(mid, tier="Silver", stays=5, days_since=400, lastmin=0, occasion=0,
           opted_out=0, in_house=0, upcoming=0, recent_contact=0, recent_campaigns=(),
           first_name=None, phone=None):
    return {"id": mid, "first_name": first_name or ("G%d" % mid),
            "phone": phone or ("+96650000%04d" % mid), "tier": tier, "stays_count": stays,
            "days_since": days_since, "lastmin": lastmin, "occasion_soon": occasion,
            "opted_out": opted_out, "in_house": in_house, "has_upcoming_booking": upcoming,
            "recent_contact": recent_contact, "recent_campaigns": set(recent_campaigns)}


AVAIL = {"open_units": 5, "open_unit_nights": 9}
A = {"click_through": 0.12, "click_to_book": 0.08}


# --------------------------- segments ---------------------------

class Segments(unittest.TestCase):
    def test_all_members_matches_any_non_quarantine_tier(self):
        for t in ("Silver", "Gold", "Turaif"):
            self.assertTrue(cards.match_segment(member(1, tier=t), "HEATWAVE"))
        self.assertFalse(cards.match_segment(member(1, tier="Quarantine"), "HEATWAVE"))

    def test_loyal_thanks_is_gold_and_turaif_only(self):
        self.assertTrue(cards.match_segment(member(1, tier="Gold"), "LOYAL-THANKS"))
        self.assertTrue(cards.match_segment(member(1, tier="Turaif"), "LOYAL-THANKS"))
        self.assertFalse(cards.match_segment(member(1, tier="Silver"), "LOYAL-THANKS"))

    def test_dormant_window(self):
        self.assertTrue(cards.match_segment(member(1, days_since=120), "DORMANT-COMEBACK"))
        self.assertFalse(cards.match_segment(member(1, days_since=30), "DORMANT-COMEBACK"))
        self.assertFalse(cards.match_segment(member(1, days_since=400), "DORMANT-COMEBACK"))

    def test_first_timer_stays(self):
        self.assertTrue(cards.match_segment(member(1, stays=2, days_since=30), "FIRST-TIMER"))
        self.assertFalse(cards.match_segment(member(1, stays=5, days_since=30), "FIRST-TIMER"))

    def test_last_minute_flag(self):
        self.assertTrue(cards.match_segment(member(1, lastmin=1), "LAST-MINUTE"))
        self.assertFalse(cards.match_segment(member(1, lastmin=0), "LAST-MINUTE"))

    def test_post_stay_recency(self):
        self.assertTrue(cards.match_segment(member(1, days_since=2), "POST-STAY"))
        self.assertFalse(cards.match_segment(member(1, days_since=10), "POST-STAY"))


# --------------------------- guardrails ---------------------------

class Guardrails(unittest.TestCase):
    def test_opt_out_kill_on_book_fatigue_and_same_campaign(self):
        people = [
            member(1),                                   # clean -> kept
            member(2, opted_out=1),                      # opted out
            member(3, in_house=1),                       # kill-on-book (in house)
            member(4, upcoming=1),                       # kill-on-book (has upcoming)
            member(5, recent_contact=1),                 # messaged within 7d
            member(6, recent_campaigns=["HEATWAVE"]),    # same campaign within 14d
        ]
        aud = cards.segment_audience("HEATWAVE", people)
        self.assertEqual([m["id"] for m in aud], [1])

    def test_same_campaign_block_is_per_campaign(self):
        # blocked for HEATWAVE but still reachable by a DIFFERENT campaign
        m = member(1, recent_campaigns=["HEATWAVE"])
        self.assertEqual(cards.segment_audience("HEATWAVE", [m]), [])
        self.assertEqual(len(cards.segment_audience("MIDWEEK-RESET", [m])), 1)

    def test_dedupe_by_phone(self):
        people = [member(1, phone="+966500000001"), member(2, phone="+966500000001")]
        self.assertEqual(len(cards.segment_audience("HEATWAVE", people)), 1)


# --------------------------- recommend_today ---------------------------

class RecommendToday(unittest.TestCase):
    def _people(self, n=50, tier="Silver"):
        return [member(i, tier=tier) for i in range(1, n + 1)]

    def test_day_27_picks_payday(self):
        recs = cards.recommend_today(date(2026, 4, 27), AVAIL, self._people(), A)
        self.assertTrue(recs)
        self.assertEqual(recs[0]["campaign"], "PAYDAY-DROPPED")

    def test_day_23_picks_end_of_month(self):
        recs = cards.recommend_today(date(2026, 4, 23), AVAIL, self._people(), A)
        self.assertTrue(recs)
        self.assertEqual(recs[0]["campaign"], "END-OF-MONTH")

    def test_july_makes_heatwave_eligible(self):
        recs = cards.recommend_today(date(2026, 7, 13), AVAIL, self._people(), A, limit=20)
        self.assertIn("HEATWAVE", [r["campaign"] for r in recs])

    def test_y_never_exceeds_x(self):
        recs = cards.recommend_today(date(2026, 4, 27), {"open_units": 3, "open_unit_nights": 6},
                                     self._people(1000), {"click_through": 0.5, "click_to_book": 0.5})
        top = recs[0]
        self.assertEqual(top["X"], 3)
        self.assertEqual(top["Y"], 3)            # raw 250 capped to 3
        self.assertTrue(top["capped"])

    def test_assumptions_flow_through_to_y(self):
        big = self._people(1000)
        low = cards.recommend_today(date(2026, 4, 27), {"open_units": 999}, big,
                                    {"click_through": 0.10, "click_to_book": 0.10})[0]
        high = cards.recommend_today(date(2026, 4, 27), {"open_units": 999}, big,
                                     {"click_through": 0.50, "click_to_book": 0.50})[0]
        self.assertLess(low["Y"], high["Y"])     # 10 vs 250
        self.assertEqual(low["math"]["click_pct"], 10.0)

    def test_full_portfolio_recommends_nothing(self):
        self.assertEqual(cards.recommend_today(date(2026, 4, 27), {"open_units": 0},
                                               self._people(), A), [])

    def test_no_audience_campaign_is_skipped(self):
        # day 27 + only Quarantine members -> PAYDAY has no audience -> no recs
        q = [member(i, tier="Quarantine") for i in range(1, 10)]
        self.assertEqual(cards.recommend_today(date(2026, 4, 27), AVAIL, q, A), [])

    def test_statement_is_bilingual_and_names_no_unit(self):
        r = cards.recommend_today(date(2026, 4, 27), AVAIL, self._people(), A)[0]
        self.assertTrue(r["statement_ar"])
        self.assertTrue(r["statement_en"])
        self.assertIn("apartments", r["statement_en"])
        self.assertEqual(r["url"], "https://oujares.com/elite")


# --------------------------- send list CSV ---------------------------

class SendListCsv(unittest.TestCase):
    def test_columns_and_filtering(self):
        people = [member(1, first_name="Noura", phone="+966512345678"),
                  member(2, opted_out=1), member(3, recent_contact=1)]
        fn, text = cards.build_send_list_csv("HEATWAVE", people, "ar")
        self.assertTrue(fn.endswith(".csv"))
        rows = list(csv.reader(io.StringIO(text)))
        self.assertEqual(rows[0], cards.SEND_CSV_COLUMNS)
        self.assertEqual(rows[0], ["first_name", "phone", "tier", "campaign", "language"])
        body = rows[1:]
        self.assertEqual(len(body), 1)                       # opted-out + fatigued dropped
        self.assertEqual(body[0], ["Noura", "966512345678", "Silver", "HEATWAVE", "ar"])


# --------------------------- availability (gaps) ---------------------------

class OpenInventory(unittest.TestCase):
    def _grid(self):
        # Sun..Wed midweek, then Thu/Fri/Sat weekend.
        days = [{"date": "2026-06-28", "weekday": 6}, {"date": "2026-06-29", "weekday": 0},
                {"date": "2026-06-30", "weekday": 1}, {"date": "2026-07-01", "weekday": 2},
                {"date": "2026-07-02", "weekday": 3}, {"date": "2026-07-03", "weekday": 4}]
        def cell(s):
            return {"status": s, "price": 400}
        units = [
            {"lid": "A", "name": "A", "cells": [cell("empty"), cell("empty"), cell("booked"), cell("booked"), cell("empty"), cell("empty")]},
            {"lid": "B", "name": "B", "cells": [cell("booked"), cell("empty"), cell("empty"), cell("empty"), cell("empty"), cell("empty")]},
            {"lid": "C", "name": "C", "cells": [cell("booked"), cell("booked"), cell("booked"), cell("booked"), cell("booked"), cell("booked")]},
        ]
        return {"days": days, "units": units}

    def test_counts_distinct_apartments_and_nights_excluding_weekends(self):
        inv = gaps.open_midweek_inventory(self._grid(), horizon_days=6)
        self.assertEqual(inv["open_units"], 2)               # A and B have midweek empties; C none
        self.assertEqual(inv["open_unit_nights"], 5)         # A:2 (Sun,Mon) + B:3 (Mon,Tue,Wed)
        # the Thu/Fri empties (idx 4,5) are NEVER counted
        weekend = [s for s in inv["strip"] if s["weekend"]]
        self.assertTrue(all(s["weekday"] in (3, 4, 5) for s in weekend))


if __name__ == "__main__":
    unittest.main()
