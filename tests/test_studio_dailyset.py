# -*- coding: utf-8 -*-
"""TDD lock for the daily-set diversity fix (2026-07-24, spec S5).

The old set reused a few signals (1-day lead → 2 cards) and was almost all
owner-facing. These pin the cure: never two cards on one grounding fact, spread
across shape, and at least one escape-the-niche card when a broad one exists.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from studio import engine, plan  # noqa: E402


def _card(title, sid="", audience="niche", family="internal", trigger="curiosity",
          shape="cold_number", strength=50):
    c = {"id": abs(hash(title + sid)) % 100000, "visual_title": title, "angle": title,
         "signal_sid": sid, "audience": audience, "signal_family": family,
         "trigger_kind": trigger, "shape": shape, "strength": strength}
    c["nkey"] = engine.novelty_key(title)
    return c


class TestNoDuplicateSid(unittest.TestCase):
    def test_two_cards_on_the_same_fact_never_coexist(self):
        pool = [_card("زاوية أولى للحجز اللحظي", sid="AAA", strength=90),
                _card("زاوية ثانية للحجز اللحظي", sid="AAA", strength=88),
                _card("تسعير الويكند يرتفع", sid="BBB", strength=70)]
        got = plan.choose(pool, [], n=3, today="2026-07-24")
        sids = [c["signal_sid"] for c in got]
        self.assertEqual(len(sids), len(set(sids)), "a set must not reuse a grounding sid")

    def test_prefers_a_new_fact_over_a_stronger_duplicate(self):
        pool = [_card("الحجز اللحظي", sid="AAA", strength=95),
                _card("نفس الحجز بصياغة", sid="AAA", strength=93),
                _card("موضوع مختلف تماماً", sid="BBB", strength=40)]
        got = plan.choose(pool, [], n=2, today="2026-07-24")
        self.assertEqual({c["signal_sid"] for c in got}, {"AAA", "BBB"})


class TestShapeSpread(unittest.TestCase):
    def test_spread_prefers_a_different_shape(self):
        pool = [_card("فكرة رقمية", sid="A", shape="cold_number", strength=80),
                _card("فكرة رقمية ثانية", sid="B", shape="cold_number", strength=79),
                _card("فكرة بقصة", sid="C", shape="quote_reaction", strength=70)]
        got = plan.choose(pool, [], n=2, today="2026-07-24")
        shapes_used = {c["shape"] for c in got}
        self.assertIn("quote_reaction", shapes_used,
                      "the set should reach for a second shape, not two cold_numbers")


class TestEscapeGuarantee(unittest.TestCase):
    def test_includes_an_escape_card_when_one_exists(self):
        pool = [_card("للملّاك ١", sid="A", audience="niche", strength=95),
                _card("للملّاك ٢", sid="B", audience="niche", strength=90),
                _card("للملّاك ٣", sid="C", audience="niche", strength=85),
                _card("للجمهور العام", sid="D", audience="escape", strength=40)]
        got = plan.choose(pool, [], n=3, today="2026-07-24")
        self.assertTrue(any(c["audience"] == "escape" for c in got),
                        "a broad card exists — the set must include it")

    def test_no_escape_available_is_fine(self):
        pool = [_card("للملّاك ١", sid="A", audience="niche", strength=90),
                _card("للملّاك ٢", sid="B", audience="niche", strength=80)]
        got = plan.choose(pool, [], n=3, today="2026-07-24")
        self.assertTrue(got)   # doesn't force an escape that isn't there

    def test_escape_swap_keeps_sids_unique(self):
        pool = [_card("للملّاك ١", sid="A", audience="niche", strength=95),
                _card("للملّاك ٢", sid="B", audience="niche", strength=90),
                _card("عام على نفس فكرة A", sid="A", audience="escape", strength=88)]
        got = plan.choose(pool, [], n=2, today="2026-07-24")
        sids = [c["signal_sid"] for c in got]
        self.assertEqual(len(sids), len(set(sids)))


if __name__ == "__main__":
    unittest.main()
