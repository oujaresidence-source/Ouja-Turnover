# -*- coding: utf-8 -*-
"""Pure pricing math for /monthly (عوجا بالشهر). Synthetic, no network.

Locks the before/after engine BEFORE it ever touches live Hostaway prices:
- visible default discount drives the shown "after"
- promo lifts the visible default only when bigger
- pct never exceeds the advertised ceiling
- calendar-month date arithmetic clamps day-of-month and rolls the year
"""
import datetime
import unittest

import bot


def cfg(default=0.15, ceiling=0.30, promo_on=False, promo_pct=0.0):
    return {"default_pct": default, "ceiling_pct": ceiling,
            "promo": {"on": promo_on, "pct": promo_pct, "label_ar": "", "label_en": ""}}


class Pricing(unittest.TestCase):
    def test_default_15_one_month(self):
        p = bot.monthly_pricing(30000, 1, cfg())
        self.assertEqual(p["pct"], 0.15)
        self.assertEqual(p["before"], 30000)
        self.assertEqual(p["after"], 25500)
        self.assertEqual(p["saved"], 4500)
        self.assertEqual(p["per_month_before"], 30000)
        self.assertEqual(p["per_month_after"], 25500)
        self.assertEqual(p["ceiling"], 0.30)

    def test_promo_bigger_than_default_wins(self):
        p = bot.monthly_pricing(30000, 1, cfg(promo_on=True, promo_pct=0.20))
        self.assertEqual(p["pct"], 0.20)
        self.assertEqual(p["after"], 24000)
        self.assertEqual(p["saved"], 6000)
        self.assertTrue(p["promo"])

    def test_promo_smaller_than_default_ignored(self):
        p = bot.monthly_pricing(30000, 1, cfg(promo_on=True, promo_pct=0.10))
        self.assertEqual(p["pct"], 0.15)
        self.assertEqual(p["after"], 25500)

    def test_pct_never_exceeds_ceiling(self):
        p = bot.monthly_pricing(30000, 1, cfg(default=0.40))
        self.assertEqual(p["pct"], 0.30)
        self.assertEqual(p["after"], 21000)

    def test_promo_capped_at_ceiling(self):
        p = bot.monthly_pricing(30000, 1, cfg(promo_on=True, promo_pct=0.50))
        self.assertEqual(p["pct"], 0.30)

    def test_per_month_three_months(self):
        p = bot.monthly_pricing(90000, 3, cfg())
        self.assertEqual(p["per_month_before"], 30000)
        self.assertEqual(p["per_month_after"], round(p["after"] / 3))
        self.assertEqual(p["after"], 76500)

    def test_zero_before_is_safe(self):
        p = bot.monthly_pricing(0, 1, cfg())
        self.assertEqual(p["before"], 0)
        self.assertEqual(p["after"], 0)
        self.assertEqual(p["saved"], 0)


class AddMonths(unittest.TestCase):
    def test_clamp_day_end_of_month(self):
        self.assertEqual(bot._add_months(datetime.date(2026, 1, 31), 1),
                         datetime.date(2026, 2, 28))

    def test_simple_three_months(self):
        self.assertEqual(bot._add_months(datetime.date(2026, 6, 15), 3),
                         datetime.date(2026, 9, 15))

    def test_year_rollover(self):
        self.assertEqual(bot._add_months(datetime.date(2026, 12, 5), 1),
                         datetime.date(2027, 1, 5))

    def test_clamp_across_year(self):
        self.assertEqual(bot._add_months(datetime.date(2026, 11, 30), 3),
                         datetime.date(2027, 2, 28))


if __name__ == "__main__":
    unittest.main()
