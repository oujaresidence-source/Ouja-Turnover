# -*- coding: utf-8 -*-
"""§1 RFM re-tiering — synthetic, no network, no DB.

Drives brain.retier.retier() with hand-built per-phone aggregates and asserts the tier ladder,
the percentile-ranked score, the cancellation penalty, the weekday_pattern flag, days_since, and
the quarantine override.
"""
import unittest

from brain import retier


def agg(phone, stays, spend, last_stay, cancels=0, weekday_share=0.0, nights=None):
    return {"phone": phone, "name": phone, "stays": stays, "spend": spend,
            "last_stay": last_stay, "cancels": cancels, "weekday_share": weekday_share,
            "nights": nights if nights is not None else stays * 2, "median_adr": 400}


class Stats(unittest.TestCase):
    def test_pct_rank_bounds(self):
        s = [1, 2, 3, 4, 5]
        self.assertEqual(retier.pct_rank(5, s), 1.0)
        self.assertEqual(retier.pct_rank(1, s), 0.2)
        self.assertEqual(retier.pct_rank(0, s), 0.0)
        self.assertEqual(retier.pct_rank(3, []), 0.5)

    def test_percentile_interpolates(self):
        self.assertEqual(retier.percentile([10, 20, 30, 40], 75), 32.5)
        self.assertEqual(retier.percentile([], 90), 0.0)
        self.assertEqual(retier.percentile([7], 90), 7.0)


class TierLadder(unittest.TestCase):
    def setUp(self):
        # today fixed; last_stay strings chosen to make days_since explicit.
        self.today = "2026-06-29"
        self.rows = [
            agg("+9665000000001", stays=6, spend=30000, last_stay="2026-06-01", weekday_share=0.8),  # Turaif (recent, 5+)
            agg("+9665000000002", stays=6, spend=30000, last_stay="2024-06-01"),                      # 5+ but stale -> Gold
            agg("+9665000000003", stays=3, spend=2000,  last_stay="2026-05-01"),                      # >=3 -> Gold
            agg("+9665000000004", stays=2, spend=50000, last_stay="2026-05-01"),                      # 2 + high spend -> Gold via sp75
            agg("+9665000000005", stays=2, spend=300,   last_stay="2026-05-01"),                      # 2 + low spend -> Silver
            agg("+9665000000006", stays=1, spend=900,   last_stay="2026-05-01"),                      # single -> Prospect
            agg("+9665000000007", stays=25, spend=99999, last_stay="2026-06-01"),                     # internal -> Quarantine
        ]
        self.out = retier.retier(self.rows, today=self.today, quarantine_min=20)
        self.by = {r["phone"]: r for r in self.out["rows"]}

    def test_turaif_recent(self):
        self.assertEqual(self.by["+9665000000001"]["tier"], "Turaif")

    def test_turaif_stale_demotes_to_gold(self):
        self.assertEqual(self.by["+9665000000002"]["tier"], "Gold")

    def test_three_stays_is_gold(self):
        self.assertEqual(self.by["+9665000000003"]["tier"], "Gold")

    def test_two_stays_high_spend_is_gold(self):
        self.assertEqual(self.by["+9665000000004"]["tier"], "Gold")

    def test_two_stays_low_spend_is_silver(self):
        self.assertEqual(self.by["+9665000000005"]["tier"], "Silver")

    def test_single_stay_is_prospect(self):
        self.assertEqual(self.by["+9665000000006"]["tier"], "Prospect")

    def test_over_quarantine_is_quarantine(self):
        self.assertEqual(self.by["+9665000000007"]["tier"], "Quarantine")

    def test_days_since_computed(self):
        self.assertEqual(self.by["+9665000000003"]["days_since"], 59)  # 2026-06-29 - 2026-05-01

    def test_weekday_pattern_flag(self):
        self.assertEqual(self.by["+9665000000001"]["weekday_pattern"], 1)   # 0.8 share
        self.assertEqual(self.by["+9665000000003"]["weekday_pattern"], 0)   # 0.0 share

    def test_scores_in_range_and_top_member_highest(self):
        for r in self.out["rows"]:
            self.assertGreaterEqual(r["score"], 0.0)
            self.assertLessEqual(r["score"], 100.0)
        # The frequent, high-spend, recent member should outscore the single-stay prospect.
        self.assertGreater(self.by["+9665000000001"]["score"], self.by["+9665000000006"]["score"])


class CancellationPenalty(unittest.TestCase):
    def test_cancellations_dock_score_capped_at_five(self):
        base = agg("+9665000000010", stays=4, spend=8000, last_stay="2026-06-20", cancels=0)
        many = agg("+9665000000011", stays=4, spend=8000, last_stay="2026-06-20", cancels=9)
        out = retier.retier([base, many], today="2026-06-29")
        by = {r["phone"]: r for r in out["rows"]}
        # identical RFM inputs, so the only difference is the -3×min(cancels,5)=15 penalty.
        self.assertAlmostEqual(by["+9665000000010"]["score"] - by["+9665000000011"]["score"], 15.0, delta=0.1)

    def test_no_last_stay_is_worst_recency_not_a_crash(self):
        out = retier.retier([agg("+9665000000012", stays=2, spend=500, last_stay=None)],
                            today="2026-06-29")
        self.assertIsNone(out["rows"][0]["days_since"])


if __name__ == "__main__":
    unittest.main()
