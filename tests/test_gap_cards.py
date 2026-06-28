# -*- coding: utf-8 -*-
"""Weekday-Gap decision engine — synthetic, no network, no DB.

Drives brain.cards.build_card with hand-built gaps + member rows and asserts the §4/§5 contract:
campaign selection by class, protected units are upgrade-only (never discounted), audience filter
+ tier→fit→recency ranking, the frequency/flag exclusions, per-guest reasons, the floor, and the
merged AR/EN message.
"""
import unittest

from brain import cards, playbook


def member(mid, name, tier, stays=3, score=70, days_since=20, weekday=1,
           preferred=None, nights=6, opted_out=0):
    return {"id": mid, "first_name": name, "phone": "+96650000%04d" % mid, "tier": tier,
            "stays_count": stays, "score": score, "days_since": days_since,
            "weekday_pattern": weekday, "preferred_unit": preferred, "nights_total": nights,
            "opted_out": opted_out}


def gap(unit="9B HTN", lid="9B", cls="MIDWEEK-2", prio=2, protected=False,
        labels=None, weekdays=None, prices=None, nights=2):
    return {"lid": lid, "unit": unit, "protected": protected, "gap_class": cls,
            "priority": prio, "priority_label": "P%d" % prio, "days_out": 1, "nights": nights,
            "gap_dates": ["2026-06-30", "2026-07-01"], "gap_labels": labels or ["Mon 30 Jun", "Tue 01 Jul"],
            "weekdays": weekdays or [0, 1], "prices": prices or [600, 600],
            "at_risk": sum(prices or [600, 600])}


class CampaignSelection(unittest.TestCase):
    def test_midweek2_picks_midweek2(self):
        c = cards.build_card(gap(), [member(1, "Sara", "Gold")])
        self.assertEqual(c["campaign"], "MIDWEEK-2")

    def test_protected_forces_upgrade_campaign(self):
        c = cards.build_card(gap(unit="F1", lid="F1", protected=True), [member(1, "Sara", "Gold")])
        self.assertEqual(c["campaign"], "UPGRADE-MIDWEEK")

    def test_full_pace_swaps_to_relationship(self):
        c = cards.build_card(gap(), [member(1, "Sara", "Gold", preferred="9B HTN")], pace_mode="full")
        self.assertEqual(c["campaign"], "YOUR-UNIT-FREE")
        self.assertEqual(c["offer"]["mode"], "relationship")


class ProtectedNeverDiscounted(unittest.TestCase):
    def test_f1_offer_is_upgrade_only_no_pct(self):
        c = cards.build_card(gap(unit="F1", lid="F1", protected=True), [member(1, "A", "Turaif")])
        self.assertEqual(c["offer"]["mode"], "upgrade")
        self.assertEqual(c["offer"]["max_pct"], 0)
        self.assertIsNone(c["offer"]["floor"])


class OfferAndFloor(unittest.TestCase):
    def test_value_add_caps_at_ceiling_and_respects_floor(self):
        c = cards.build_card(gap(), [member(1, "A", "Gold")],
                             cfg={"ceiling_pct": 13},
                             floor_fn=lambda lid: 660)
        self.assertEqual(c["offer"]["mode"], "value_add")
        self.assertEqual(c["offer"]["max_pct"], 13)
        self.assertEqual(c["offer"]["floor"], 660)

    def test_floor_falls_back_to_p5_times_pct_when_unset(self):
        c = cards.build_card(gap(prices=[600, 600]), [member(1, "A", "Gold")],
                             cfg={"deep_floor_pct": 55})
        self.assertEqual(c["offer"]["floor"], 330)            # 600 × 0.55

    def test_deep_allowed_only_on_p1_dead_night(self):
        tonight = gap(cls="TONIGHT", prio=1, nights=1, prices=[500])
        c = cards.build_card(tonight, [member(1, "A", "Silver")])
        self.assertTrue(c["offer"]["deep_allowed"])
        midweek = cards.build_card(gap(), [member(1, "A", "Gold")])
        self.assertFalse(midweek["offer"]["deep_allowed"])


class AudienceFilterAndRank(unittest.TestCase):
    def test_midweek2_requires_gold_and_weekday_pattern(self):
        people = [
            member(1, "GoldWk", "Gold", weekday=1),       # in
            member(2, "GoldNoWk", "Gold", weekday=0),     # out: not weekday regular
            member(3, "Silver", "Silver", weekday=1),     # out: below Gold
        ]
        c = cards.build_card(gap(), people)
        names = [t["name"] for t in c["targets"]]
        self.assertEqual(names, ["GoldWk"])

    def test_rank_prefers_tier_then_preferred_then_recency(self):
        people = [
            member(1, "GoldOld", "Gold", days_since=120, preferred=None),
            member(2, "GoldPref", "Gold", days_since=120, preferred="9B HTN"),
            member(3, "Turaif", "Turaif", days_since=200, preferred=None),
            member(4, "GoldRecent", "Gold", days_since=5, preferred=None),
        ]
        c = cards.build_card(gap(), people)
        order = [t["name"] for t in c["targets"]]
        self.assertEqual(order[0], "Turaif")               # tier wins
        self.assertEqual(order[1], "GoldPref")             # preferred unit beats plain Gold
        self.assertEqual(order.index("GoldRecent"), 2)     # recent beats old among plain Gold

    def test_target_cap_applies(self):
        people = [member(i, "G%d" % i, "Gold") for i in range(1, 40)]
        c = cards.build_card(gap(), people, cfg={"targets_per_card": 10})
        self.assertEqual(c["target_count"], 10)
        self.assertEqual(c["pool_eligible"], 39)


class Exclusions(unittest.TestCase):
    def test_contacted_within_7d_and_optout_and_risk_excluded(self):
        people = [
            member(1, "Fresh", "Gold"),
            member(2, "Recent7d", "Gold"),
            member(3, "OptedOut", "Gold", opted_out=1),
            member(4, "Risky", "Gold"),
        ]
        c = cards.build_card(gap(), people, contacted_7d={2}, risk_ids={4})
        names = sorted(t["name"] for t in c["targets"])
        self.assertEqual(names, ["Fresh"])

    def test_quarantine_never_targeted(self):
        c = cards.build_card(gap(), [member(1, "Q", "Quarantine")])
        self.assertEqual(c["target_count"], 0)


class WhyAndMessage(unittest.TestCase):
    def test_card_carries_why_and_per_guest_reasons(self):
        c = cards.build_card(gap(), [member(1, "Sara", "Gold", stays=4, days_since=21, preferred="9B HTN")])
        self.assertTrue(c["why_en"])
        self.assertTrue(c["why_ar"])
        t = c["targets"][0]
        self.assertIn("favourite unit", t["reason_en"])
        self.assertIn("last 21d ago", t["reason_en"])
        self.assertIn("Sun–Wed", t["reason_en"])

    def test_message_merges_unit_and_dates_keeps_name_token(self):
        c = cards.build_card(gap(), [member(1, "Sara", "Gold")])
        self.assertIn("9B HTN", c["message_en"])
        self.assertIn("Mon 30 Jun", c["message_en"])
        self.assertIn("{name}", c["message_en"])           # sender fills the name (Karzoum-style)
        self.assertIn("{name}", c["message_ar"])


class PlaybookSanity(unittest.TestCase):
    def test_every_campaign_has_both_languages(self):
        for code, c in playbook.CAMPAIGNS.items():
            for k in ("name_ar", "name_en", "why_ar", "why_en", "msg_ar", "msg_en"):
                self.assertTrue(c.get(k), "%s missing %s" % (code, k))
            self.assertIn(c["offer_mode"], ("relationship", "value_add", "deeper", "upgrade"))

    def test_every_class_primary_resolves_to_a_real_campaign(self):
        for cls, code in playbook.CLASS_PRIMARY.items():
            self.assertIn(code, playbook.CAMPAIGNS)


if __name__ == "__main__":
    unittest.main()
