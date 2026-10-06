# -*- coding: utf-8 -*-
"""owner_meet.engine / periods / money — the PURE rules, TDD-locked (spec §5, §6, §8, §14).

R1 is the reason most of these exist: a comparison may leave the engine only as a band, its
percentile rounded to 10 and spoken only from 60 up, with no peer count anywhere in it.

Run: python3 -m unittest tests.test_owner_meet_engine
"""
import datetime
import json
import os
import sys
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from owner_meet import airbnb_import, engine, money, periods  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "owner_meet" / "host_opportunity_2026-10-04.tsv"
# The plan PDF (docs/owner_meet/airbnb-plan-2026-10.pdf p.11), group A by opportunity rank — typed
# from the PDF page, NOT produced by the code under test.
PDF_GROUP_A_RANKS = [1, 2, 4, 5, 6, 12, 15, 16, 18, 19, 23, 24, 26, 28, 29, 36, 37, 38, 41, 42, 43]


class Percentiles(unittest.TestCase):
    def test_ties_count_half(self):
        self.assertEqual(engine.percentile(5, [1, 5, 9, 10]), 37.5)

    def test_empty_or_missing_is_none(self):
        self.assertIsNone(engine.percentile(5, []))
        self.assertIsNone(engine.percentile(None, [1, 2]))

    def test_round10_halves_up(self):
        self.assertEqual(engine.round10(55), 60)
        self.assertEqual(engine.round10(54.9), 50)
        self.assertEqual(engine.round10(4), 0)
        self.assertEqual(engine.round10(100), 100)

    def test_labels_never_speak_a_number_below_60(self):
        tone, lab = engine.percentile_label(60)
        self.assertEqual(tone, "top")
        self.assertIn("60", lab)
        tone, lab = engine.percentile_label(50)
        self.assertEqual(tone, "mid")
        self.assertFalse(any(ch.isdigit() for ch in lab), lab)
        tone, lab = engine.percentile_label(30)
        self.assertEqual(tone, "low")
        self.assertEqual(lab, "أقل من أغلب الشقق المشابهة")
        self.assertFalse(any(ch.isdigit() for ch in lab), lab)

    def test_top_label_caps_at_90(self):
        self.assertIn("90", engine.percentile_label(100)[1])
        self.assertNotIn("100", engine.percentile_label(100)[1])

    def test_portfolio_scope_wording_has_no_number(self):
        _t, lab = engine.percentile_label(20, scope="portfolio")
        self.assertEqual(lab, "أقل من أغلب شققنا")

    def test_quartiles_interpolate(self):
        self.assertEqual(engine.quartiles([1, 2, 3, 4, 5]), (2, 3, 4))
        self.assertEqual(engine.quartiles([10, 20]), (12.5, 15.0, 17.5))


class Bands(unittest.TestCase):
    VALS = {1: 100.0, 2: 10.0, 3: 20.0, 4: 30.0, 5: 40.0, 6: 50.0, 7: 60.0, 8: 70.0, 9: 5.0}

    def test_band_from_same_bedroom_peers(self):
        band, inn = engine.peer_bands(self.VALS, 1, [1, 2, 3, 4, 5, 6, 7], list(self.VALS))
        self.assertEqual(band["scope"], "peers")
        self.assertEqual(band["value"], 100.0)
        self.assertEqual((band["p25"], band["p50"], band["p75"]), (22.5, 35.0, 47.5))
        self.assertEqual(band["pct10"], 100)
        self.assertEqual(band["tone"], "top")
        self.assertEqual(inn["n"], 6, "the unit itself is never its own peer")

    def test_band_carries_no_count_anywhere(self):
        band, _inn = engine.peer_bands(self.VALS, 1, [1, 2, 3, 4, 5, 6, 7], list(self.VALS))
        self.assertEqual(set(band), {"value", "p25", "p50", "p75", "pct10", "tone", "label", "scope"})
        self.assertNotIn("6", band["label"])

    def test_fewer_than_six_peers_falls_back_to_portfolio(self):
        band, inn = engine.peer_bands(self.VALS, 1, [1, 2, 3], list(self.VALS))
        self.assertEqual(band["scope"], "portfolio")
        self.assertIn("شققنا", band["label"])
        self.assertEqual(inn["scope"], "portfolio")

    def test_too_few_even_in_portfolio_gives_no_band(self):
        band, inn = engine.peer_bands({1: 5.0, 2: 6.0, 3: 7.0}, 1, [2, 3], [1, 2, 3])
        self.assertIsNone(band)
        self.assertEqual(inn["reason"], "too_few")

    def test_mid_band_hides_the_percentile(self):
        vals = {i: float(i) for i in range(1, 12)}
        band, _ = engine.peer_bands(vals, 6, list(vals), list(vals))
        self.assertEqual(band["tone"], "mid")
        self.assertIsNone(band["pct10"])

    def test_fair_share_index(self):
        self.assertEqual(engine.fair_share_index(120.0, 100.0), 120)
        self.assertEqual(engine.fair_share_index(99.5, 100.0), 100)
        self.assertIsNone(engine.fair_share_index(50.0, 0))
        self.assertIsNone(engine.fair_share_index(None, 100.0))


class Ratings(unittest.TestCase):
    def test_zero_and_empty_scores_are_not_reviews(self):
        rv = [{"listing_id": 7, "rating_raw": 10}, {"listing_id": 7, "rating_raw": 0},
              {"listing_id": 7, "rating_raw": ""}, {"listing_id": 7, "rating_raw": None}]
        n, R = engine.rating_stats(rv)[7]
        self.assertEqual((n, R), (1, 10))
        self.assertEqual(engine.rating5(n, R), 5.0)

    def test_exact_475(self):
        rv = [{"listing_id": 1, "rating_raw": x} for x in (10, 10, 9, 9)]
        n, R = engine.rating_stats(rv)[1]
        self.assertEqual(engine.rating5(n, R), 4.75)


class PromoSplit(unittest.TestCase):
    """Faisal 2026-10-06: group A is computed from the report by the plan's own method — and must
    reproduce the plan PDF's 21 listings exactly."""

    @classmethod
    def setUpClass(cls):
        cls.parsed = airbnb_import.parse(FIXTURE.read_bytes(), FIXTURE.name)
        cls.a, cls.b = engine.promo_split(cls.parsed["rows"])
        cls.by_id = {r["airbnb_id"]: r for r in cls.parsed["rows"]}

    def test_group_a_equals_the_plan_pdf(self):
        self.assertEqual(sorted(self.by_id[i]["rank"] for i in self.a), PDF_GROUP_A_RANKS)

    def test_21_and_21_disjoint_and_complete(self):
        self.assertEqual((len(self.a), len(self.b)), (21, 21))
        self.assertFalse(set(self.a) & set(self.b))
        self.assertEqual(set(self.a) | set(self.b), set(self.by_id))

    def test_each_bedroom_group_is_split_evenly(self):
        for br in {r["bedrooms"] for r in self.parsed["rows"]}:
            ids = [r["airbnb_id"] for r in self.parsed["rows"] if r["bedrooms"] == br]
            na = sum(1 for i in ids if i in self.a)
            self.assertLessEqual(abs(na - (len(ids) - na)), 1, br)

    def test_the_seed_carries_this_exact_list_confirmed_by_faisal(self):
        """Faisal confirmed the list on 2026-10-06 («اتأكد»), before the 5 November start."""
        seed = json.loads((ROOT / "owner_meet" / "rules.seed.json").read_text(encoding="utf-8"))
        g = seed["promo_test_group_a"]
        self.assertEqual(g["airbnb_ids"], self.a)
        self.assertEqual((g["confirmed_by"], g["confirmed_at"]), ("Faisal", "2026-10-06"))
        self.assertTrue(engine.promo_confirmed(seed))

    def test_an_unconfirmed_list_keeps_the_test_action_silent(self):
        seed = {"promo_test_group_a": {"airbnb_ids": list(self.a), "confirmed_by": None, "confirmed_at": None}}
        self.assertFalse(engine.promo_confirmed(seed))
        seed["promo_test_group_a"]["confirmed_by"] = "Faisal"
        self.assertFalse(engine.promo_confirmed(seed), "a confirmation needs who AND when")

    def test_rows_without_bedrooms_or_id_are_left_out(self):
        a, b = engine.promo_split([{"airbnb_id": None, "bedrooms": 2, "gbv_usd": 9},
                                   {"airbnb_id": "1", "bedrooms": None, "gbv_usd": 9},
                                   {"airbnb_id": "2", "bedrooms": 1, "gbv_usd": 1}])
        self.assertEqual((a, b), (["2"], []))


class Periods(unittest.TestCase):
    TODAY = datetime.date(2026, 10, 6)

    def test_quarter_is_three_complete_months(self):
        p = periods.resolve("quarter", self.TODAY)
        self.assertEqual(p["months"], ["2026-07", "2026-08", "2026-09"])
        self.assertEqual((p["start"], p["end"]), ("2026-07-01", "2026-09-30"))
        self.assertIsNone(p["partial"])

    def test_this_month_is_partial_to_today(self):
        p = periods.resolve("this_month", self.TODAY)
        self.assertEqual((p["months"], p["end"], p["partial"]), (["2026-10"], "2026-10-06", "2026-10"))

    def test_ytd_and_last_month(self):
        self.assertEqual(len(periods.resolve("ytd", self.TODAY)["months"]), 10)
        self.assertEqual(periods.resolve("last_month", self.TODAY)["months"], ["2026-09"])

    def test_since_last_meeting_starts_the_day_after(self):
        p = periods.resolve("since_last", self.TODAY, last_end="2026-08-15")
        self.assertEqual(p["start"], "2026-08-16")
        self.assertEqual(p["months"], ["2026-08", "2026-09", "2026-10"])
        with self.assertRaises(ValueError):
            periods.resolve("since_last", self.TODAY)

    def test_custom_clips_at_today_and_refuses_reversed(self):
        p = periods.resolve("custom", self.TODAY, first_mkey="2025-11", last_mkey="2026-12")
        self.assertEqual(p["months"][-1], "2026-10")
        self.assertEqual(len(p["months"]), 12)
        with self.assertRaises(ValueError):
            periods.resolve("custom", self.TODAY, first_mkey="2026-05", last_mkey="2026-04")

    def test_window_days_in_month(self):
        self.assertEqual(periods.window_days_in_month("2026-08", "2026-08-16", "2026-10-06"), 16)


class MoneyPure(unittest.TestCase):
    def _tot(self, **kw):
        base = {f: Decimal(0) for f in money.FIELDS}
        base.update({k: Decimal(str(v)) for k, v in kw.items()})
        return base

    def test_waterfall_reconciles_and_per_100_sums_to_100(self):
        wf = money.waterfall(self._tot(total_income=3300, ouja_fee=660, cleaning=300, expenses=0, owner_net=2340))
        self.assertTrue(wf["reconciled"])
        self.assertEqual([r["key"] for r in wf["rows"]], ["income", "fee", "cleaning", "expenses", "net"])
        p = money.per_100(wf)
        self.assertEqual(sum(p.values()), 100)
        self.assertEqual(p, {"fee": 20, "cleaning": 9, "expenses": 0, "owner": 71})

    def test_unreconciled_waterfall_draws_nothing(self):
        wf = money.waterfall(self._tot(total_income=1000, ouja_fee=200, owner_net=900))
        self.assertFalse(wf["reconciled"])
        self.assertIsNone(money.per_100(wf))

    def test_adjustment_row_appears_and_blocks_per_100(self):
        wf = money.waterfall(self._tot(total_income=1000, ouja_fee=200, adjustments=50, owner_net=850))
        self.assertTrue(wf["reconciled"])
        self.assertIn("adjustments", [r["key"] for r in wf["rows"]])
        self.assertIsNone(money.per_100(wf))

    def test_degraded_or_red_blocks_send(self):
        self.assertFalse(money.can_send({"meta": {"degraded": True}})[0])
        self.assertFalse(money.can_send({"meta": {}, "presenter": {"readiness": [{"level": "red", "text_ar": "x"}]}})[0])
        self.assertTrue(money.can_send({"meta": {}, "presenter": {"readiness": [{"level": "yellow"}]}})[0])


class RulesFile(unittest.TestCase):
    """The owner-editable rules: $STATE_DIR file wins key-by-key; a broken edit keeps the last good copy."""

    def setUp(self):
        import tempfile
        from owner_meet import config, host
        self.config, self.host = config, host
        self.tmp = tempfile.mkdtemp()
        self._sd = host.HOST.state_dir
        host.HOST.state_dir = self.tmp
        config._cache.update(key=None, rules=None)

    def tearDown(self):
        self.host.HOST.state_dir = self._sd
        self.config._cache.update(key=None, rules=None)

    def _write(self, text):
        p = os.path.join(self.tmp, self.config.STATE_NAME)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        st = os.stat(p)
        os.utime(p, (st.st_atime, st.st_mtime + 5))        # a fresh mtime even on a fast filesystem

    def test_seed_alone(self):
        self.assertEqual(self.config.rules()["peer_min"], 6)

    def test_override_wins_key_by_key(self):
        self._write(json.dumps({"peer_min": 8}))
        r = self.config.rules()
        self.assertEqual(r["peer_min"], 8)
        self.assertEqual(r["fx_sar_per_usd"], 3.75, "keys not overridden keep the seed value")

    def test_broken_edit_keeps_the_last_good_copy(self):
        self._write(json.dumps({"peer_min": 9}))
        self.assertEqual(self.config.rules()["peer_min"], 9)
        self._write("{ not json")
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(self.config.rules()["peer_min"], 9)
        self.assertIn("last good copy", out.getvalue())

    def test_callers_cannot_mutate_the_cache(self):
        self.config.rules()["peer_min"] = 99
        self.assertEqual(self.config.rules()["peer_min"], 6)


if __name__ == "__main__":
    unittest.main()
