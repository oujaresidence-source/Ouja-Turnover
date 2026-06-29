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
           preferred=None, nights=6, opted_out=0, lastmin=0, preferred_area=None, full_name=None,
           phone_plus=None):
    return {"id": mid, "first_name": name, "full_name": full_name,
            "phone": phone_plus or ("+96650000%04d" % mid),
            "tier": tier, "stays_count": stays, "score": score, "days_since": days_since,
            "weekday_pattern": weekday, "lastmin": lastmin, "preferred_unit": preferred,
            "preferred_area": preferred_area, "nights_total": nights, "opted_out": opted_out}


def gap(unit="9B HTN", lid="9B", cls="MIDWEEK-2", prio=2, protected=False,
        labels=None, weekdays=None, prices=None, nights=2, area=None, days_out=1):
    return {"lid": lid, "unit": unit, "protected": protected, "gap_class": cls,
            "priority": prio, "priority_label": "P%d" % prio, "days_out": days_out, "nights": nights,
            "area": area, "gap_dates": ["2026-06-30", "2026-07-01"],
            "gap_labels": labels or ["Mon 30 Jun", "Tue 01 Jul"],
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
    def test_midweek2_includes_a_tier_mix_not_all_turaif(self):
        # The bug being fixed: cards used to be 100% Turaif. A normal MIDWEEK-2 must mix tiers.
        people = [
            member(1, "Sara", "Gold", weekday=1, preferred="9B HTN"),
            member(2, "Noor", "Silver", weekday=1),
            member(3, "Turki", "Turaif", weekday=0, preferred="F1"),
            member(4, "Hala", "Silver", weekday=0),
        ]
        c = cards.build_card(gap(), people)
        tiers = set(t["tier"] for t in c["targets"])
        self.assertIn("Silver", tiers)
        self.assertIn("Gold", tiers)
        self.assertGreaterEqual(len(tiers), 2, "a normal MIDWEEK-2 card must show a tier MIX")

    def test_rank_is_fit_first_tier_only_breaks_ties(self):
        # A fitting Gold (favourite unit + weekday regular) must outrank a no-fit Turaif.
        people = [
            member(1, "GoldFit", "Gold", weekday=1, preferred="9B HTN", days_since=120),
            member(2, "TuraifNoFit", "Turaif", weekday=0, preferred="F1", days_since=200),
            member(3, "SilverFit", "Silver", weekday=1, preferred="9B HTN", days_since=30),
        ]
        c = cards.build_card(gap(), people)
        order = [t["name"] for t in c["targets"]]
        self.assertEqual(order[0], "GoldFit")              # fit (+3 unit +2 weekday) beats Turaif's tier
        # GoldFit and SilverFit tie on fit (both +5); tier breaks it -> Gold above Silver
        self.assertLess(order.index("GoldFit"), order.index("SilverFit"))
        self.assertEqual(order[-1], "TuraifNoFit")         # highest tier, but no fit -> last

    def test_lastmin_fit_boost_on_p1_dead_night(self):
        tonight = gap(cls="TONIGHT", prio=1, nights=1, prices=[500])
        people = [
            member(1, "FastTuraif", "Turaif", weekday=0, lastmin=1, days_since=40),
            member(2, "SlowTuraif", "Turaif", weekday=0, lastmin=0, days_since=10),
        ]
        c = cards.build_card(tonight, people)
        self.assertEqual(c["targets"][0]["name"], "FastTuraif")   # +2 last-minute fit wins

    def test_area_fit_boost(self):
        g = gap(area="Hittin")
        people = [
            member(1, "SameArea", "Silver", weekday=0, preferred="Other Unit", preferred_area="Hittin"),
            member(2, "NoArea", "Silver", weekday=0, preferred="Far Unit", preferred_area="Olaya"),
        ]
        c = cards.build_card(g, people)
        self.assertEqual(c["targets"][0]["name"], "SameArea")     # +1 area fit

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


class FullNames(unittest.TestCase):
    def test_display_uses_full_name_not_first_only(self):
        c = cards.build_card(gap(), [member(1, "Mohammed", "Gold", full_name="Mohammed Al-Qahtani")])
        t = c["targets"][0]
        self.assertEqual(t["name"], "Mohammed Al-Qahtani")     # full name displayed
        self.assertEqual(t["first"], "Mohammed")               # first name kept for {name} merge

    def test_single_letter_first_name_falls_back_gracefully(self):
        # full_name present even when first_name is a stray single letter -> show the full name
        c = cards.build_card(gap(), [member(1, "A", "Gold", full_name="Abdullah Nasser")])
        self.assertEqual(c["targets"][0]["name"], "Abdullah Nasser")


class WhyAndMessage(unittest.TestCase):
    def test_card_carries_why_and_per_guest_reasons(self):
        c = cards.build_card(gap(), [member(1, "Sara", "Gold", stays=4, days_since=21, preferred="9B HTN")])
        self.assertTrue(c["why_en"])
        self.assertTrue(c["why_ar"])
        t = c["targets"][0]
        self.assertIn("favourite unit", t["reason_en"])
        self.assertIn("last 21d ago", t["reason_en"])
        self.assertIn("Sun–Wed", t["reason_en"])

    def test_message_merges_unit_keeps_name_token(self):
        c = cards.build_card(gap(), [member(1, "Sara", "Gold")])
        self.assertIn("9B HTN", c["message_en"])           # {unit} merged
        self.assertIn("{name}", c["message_en"])           # sender fills the name (Karzoum-style)
        self.assertIn("{name}", c["message_ar"])

    def test_dated_campaign_merges_the_date(self):
        # TOMORROW v2 copy uses {date} -> must be merged to the gap's date label
        c = cards.build_card(gap(cls="TOMORROW", prio=1, nights=1, labels=["Mon 29 Jun"]),
                             [member(1, "Sara", "Gold")])
        self.assertIn("Mon 29 Jun", c["message_en"])


class CsvExport(unittest.TestCase):
    def _payload(self):
        # two cards: a P2 MIDWEEK-2 and a P1 TONIGHT (today) — the P1 must export first.
        c_p2 = cards.build_card(gap(cls="MIDWEEK-2", prio=2),
                                [member(1, "Sara", "Gold", full_name="Sara Ali", preferred="9B HTN")])
        c_p1 = cards.build_card(gap(unit="F2 GO", lid="F2", cls="TONIGHT", prio=1, nights=1,
                                    days_out=0, prices=[500], labels=["Sun 28 Jun"]),
                                [member(2, "Omar", "Silver", full_name="Omar Khan", phone_plus="+966512345678")])
        return {"cards": [c_p2, c_p1]}    # deliberately P2 before P1 to prove the sort

    def test_columns_exact_order(self):
        import csv as _csv
        import io
        fn, text = cards.build_today_csv(self._payload())
        self.assertEqual(fn, "ouja_gaps_today.csv")
        rows = list(_csv.reader(io.StringIO(text)))
        self.assertEqual(rows[0], cards.CSV_COLUMNS)         # bilingual headers, exact order
        self.assertEqual(rows[0][0], "متى نرسل · When")
        self.assertEqual(rows[0][6], "Message (English)")

    def test_today_first_sort_name_merge_and_phone(self):
        import csv as _csv
        import io
        fn, text = cards.build_today_csv(self._payload())
        rows = list(_csv.reader(io.StringIO(text)))[1:]      # drop header
        self.assertEqual(rows[0][0], "اليوم · Today")        # days_out 0 -> Today
        self.assertEqual(rows[0][1], "TONIGHT")              # P1 card exported first
        self.assertEqual(rows[0][2], "Omar Khan")            # full name in the Name column
        self.assertEqual(rows[0][3], "966512345678")         # phone without the leading +
        self.assertEqual(rows[0][4], "Silver")               # Tag = tier
        self.assertNotIn("{name}", rows[0][5])               # {name} merged (AR)
        self.assertIn("Omar", rows[0][6])                    # first name merged (EN)
        self.assertEqual(rows[1][1], "MIDWEEK-2")            # P2 card second


class PlaybookSanity(unittest.TestCase):
    def test_every_campaign_has_both_languages(self):
        for code, c in playbook.CAMPAIGNS.items():
            for k in ("name_ar", "name_en", "why_ar", "why_en", "msg_ar", "msg_en"):
                self.assertTrue(c.get(k), "%s missing %s" % (code, k))
            self.assertIn(c["offer_mode"], ("relationship", "value_add", "deeper", "upgrade"))

    def test_every_class_primary_resolves_to_a_real_campaign(self):
        for cls, code in playbook.CLASS_PRIMARY.items():
            self.assertIn(code, playbook.CAMPAIGNS)

    def test_v2_copy_merged_with_principle_and_tier_focus(self):
        from brain import playbook_v2
        for code, c in playbook.CAMPAIGNS.items():
            self.assertTrue(c.get("principle"), "%s missing principle" % code)
            self.assertTrue(c.get("tier_focus"), "%s missing tier_focus" % code)
            # the message body came from the v2 file, not the old draft
            self.assertEqual(c["msg_en"], playbook_v2.CAMPAIGNS[code]["en"])
            self.assertEqual(c["msg_ar"], playbook_v2.CAMPAIGNS[code]["ar"])
        # structural fields the engine reads must survive the swap
        self.assertEqual(playbook.CAMPAIGNS["TURAIF-MIDWEEK"]["filter"], {"tier_only": "Turaif"})
        self.assertEqual(playbook.CAMPAIGNS["UPGRADE-MIDWEEK"]["offer_mode"], "upgrade")

    def test_v2_date_tokens_merge_clean_no_leftover_braces(self):
        # LONG-GAP copy uses {date_in}/{date_out}; make sure they merge (no raw tokens leak)
        g = gap(cls="LONG-GAP", nights=3, labels=["Sun 28 Jun", "Mon 29 Jun", "Tue 30 Jun"])
        c = cards.build_card(g, [member(1, "Sara", "Gold", nights=9)])
        self.assertNotIn("{date", c["message_en"])
        self.assertNotIn("{date", c["message_ar"])


if __name__ == "__main__":
    unittest.main()
