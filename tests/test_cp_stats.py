# -*- coding: utf-8 -*-
"""
cp.stats — the figure layer (seeds §2, superprompt §6).

The contract this file defends:
  1. EVERY field has a fallback taken from the seeds file. A failed nightly job
     shows correct-but-stale figures — never zeros, never blank, never a crash.
  2. A figure carries its PROVENANCE. "Refreshed nightly" is a claim, and it is
     only true of the fields the job actually recomputes. The four figures with
     no data source in the system (response time, message volume, maintenance
     in SLA, headcount) travel as `manual` and must carry a source and a date,
     or they are not reported at all.
  3. Rounding is fixed per field, matching the source documents exactly:
     76.9%, not 76.87%.
  4. 74 residences everywhere (owner decision, 2026-08-26, resolving seeds §2).
"""
import json
import os
import unittest

from cp import stats


SEEDS = {   # seeds §2, transcribed for the test to check the fallback against
    "reservations_total": 8114, "nights_total": 13093,
    "occupancy_pct": 76.9, "occupancy_active_pct": 76.0,
    "adr_sar": 582, "adr_90d_sar": 654, "revpar_sar": 451, "revpar_active_sar": 485,
    "rating_avg": 4.77, "reviews_total": 2633, "perfect_ten_pct": 87.6,
    "repeat_booking_pct": 37, "repeat_guests": 933, "repeat_guest_share_pct": 17,
    "top_guest_stays": 49, "saudi_guest_pct": 94, "gcc_guest_pct": 3.2,
    "solo_guest_pct": 58, "couple_guest_pct": 28,
    "same_day_booking_pct": 42, "within_24h_pct": 67, "median_lead_time_days": 1,
    "avg_stay_nights": 1.62, "one_night_booking_pct": 73,
    "long_stay_booking_pct": 6, "long_stay_revenue_pct": 26,
    "thu_fri_arrival_pct": 35, "weekend_adr_premium_pct": 16,
    "direct_stay_nights": 3.68, "residences_total": 74,
    "median_response_minutes": 2.3, "messages_total": 152177,
    "messages_monthly_start": 2900, "messages_monthly_now": 23000,
    "maintenance_closed_in_sla": 1000,
    "residences_per_person_per_day": 4.0, "residences_per_custodian": 12,
    "team_headcount": 22, "designed_capacity_residences": 200,
    "platform_lines_of_code": 66000,
    "days_to_live_furnished": 5, "days_to_live_unfurnished": 28,
}


class FallbackIsComplete(unittest.TestCase):
    def test_every_seeds_field_has_a_fallback(self):
        fb = stats.FALLBACK
        for key in SEEDS:
            with self.subTest(field=key):
                self.assertIn(key, fb, "no fallback for %r — a failed job would blank it" % key)

    def test_fallback_values_match_the_seeds_file(self):
        for key, want in SEEDS.items():
            with self.subTest(field=key):
                self.assertEqual(stats.FALLBACK[key], want)

    def test_category_scores_match(self):
        self.assertEqual(stats.FALLBACK["category_scores"], {
            "communication": 9.77, "check_in": 9.74, "accuracy": 9.66,
            "location": 9.64, "cleanliness": 9.57, "value": 9.38})

    def test_occupancy_by_type_matches(self):
        self.assertEqual(stats.FALLBACK["occupancy_by_type"], {
            "1br": 80.9, "2br": 74.0, "3br": 70.9, "4br_plus": 78.0, "portfolio": 76.9})

    def test_no_field_is_zero_or_none(self):
        for key, val in stats.FALLBACK.items():
            if key in ("computed_at",):
                continue
            with self.subTest(field=key):
                self.assertNotIn(val, (0, None, "", {}, []),
                                 "%r falls back to an empty value" % key)

    def test_every_field_declares_a_provenance(self):
        for key in stats.FALLBACK:
            if key == "computed_at":
                continue
            with self.subTest(field=key):
                self.assertIn(stats.PROVENANCE.get(key),
                              ("hostaway", "manual", "seeds"),
                              "%r has no declared provenance" % key)


class ResidenceCountIsSettled(unittest.TestCase):
    """Seeds §2 flagged 74-vs-72. Owner resolved it to 74 on 2026-08-26."""

    def test_seventy_four(self):
        self.assertEqual(stats.FALLBACK["residences_total"], 74)

    def test_seventy_two_appears_nowhere_in_the_data_files(self):
        for name in ("cp_stats_fallback.json", "cp_manual.json"):
            path = os.path.join(stats.DATA_DIR, name)
            with open(path, encoding="utf-8") as fh:
                blob = json.load(fh)
            with self.subTest(file=name):
                self.assertNotIn(72, _numbers_in(blob))


def _numbers_in(obj):
    out = []
    if isinstance(obj, dict):
        for v in obj.values():
            out += _numbers_in(v)
    elif isinstance(obj, list):
        for v in obj:
            out += _numbers_in(v)
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        out.append(obj)
    return out


class ManualFiguresNeedASource(unittest.TestCase):
    """Seeds §8 financial control: a manual figure needs a value, a date and a
    source, or it is not reported. The four unbacked figures live here."""

    UNBACKED = ("median_response_minutes", "messages_total",
                "maintenance_closed_in_sla", "team_headcount")

    def test_the_four_unbacked_figures_are_manual(self):
        for key in self.UNBACKED:
            with self.subTest(field=key):
                self.assertEqual(stats.PROVENANCE[key], "manual")

    def test_each_manual_entry_carries_value_date_and_source(self):
        for key, entry in stats.MANUAL.items():
            with self.subTest(field=key):
                for req in ("value", "as_of", "source"):
                    self.assertTrue(str(entry.get(req) or "").strip(),
                                    "manual figure %r is missing %r" % (key, req))

    def test_an_unsourced_manual_entry_is_dropped(self):
        kept = stats.valid_manual({"good": {"value": 1, "as_of": "2026-08-26", "source": "internal"},
                                   "bad": {"value": 2, "as_of": "", "source": "internal"}})
        self.assertIn("good", kept)
        self.assertNotIn("bad", kept)

    def test_nothing_computable_is_hiding_in_the_manual_layer(self):
        """Anything Hostaway can answer must be `hostaway`, not hand-typed."""
        for key in ("reservations_total", "nights_total", "rating_avg",
                    "reviews_total", "adr_sar", "revpar_sar", "occupancy_pct",
                    "residences_total"):
            with self.subTest(field=key):
                self.assertEqual(stats.PROVENANCE[key], "hostaway")


class LoadNeverDegrades(unittest.TestCase):
    """The lesson already learned on /business: a failed fetch computes zeros,
    and persisting zeros silently replaces a good page with a broken one."""

    def test_no_snapshot_returns_the_full_fallback(self):
        got = stats.load(snapshot=None)
        self.assertEqual(got["reservations_total"]["value"], 8114)
        self.assertEqual(got["reservations_total"]["source"], "seeds")

    def test_empty_snapshot_is_ignored(self):
        got = stats.load(snapshot={})
        self.assertEqual(got["nights_total"]["value"], 13093)

    def test_zero_valued_fields_are_ignored(self):
        got = stats.load(snapshot={"reservations_total": 0, "nights_total": 0})
        self.assertEqual(got["reservations_total"]["value"], 8114)

    def test_a_live_field_overlays_and_is_labelled_hostaway(self):
        got = stats.load(snapshot={"reservations_total": 8290,
                                   "computed_at": "2026-08-27T03:00:00Z"})
        self.assertEqual(got["reservations_total"]["value"], 8290)
        self.assertEqual(got["reservations_total"]["source"], "hostaway")
        self.assertEqual(got["reservations_total"]["as_of"], "2026-08-27T03:00:00Z")

    def test_a_snapshot_cannot_overwrite_a_manual_field(self):
        """The nightly job has no way to know these; if it ever emits one, the
        hand-sourced value still wins and stays labelled."""
        got = stats.load(snapshot={"team_headcount": 999,
                                   "reservations_total": 8290})
        self.assertEqual(got["team_headcount"]["value"], 22)
        self.assertEqual(got["team_headcount"]["source"], "manual")

    def test_every_returned_field_carries_value_source_and_as_of(self):
        for key, cell in stats.load(snapshot=None).items():
            with self.subTest(field=key):
                self.assertIn("value", cell)
                self.assertIn("source", cell)
                self.assertIn("as_of", cell)


class RoundingMatchesTheSourceDocuments(unittest.TestCase):
    def test_occupancy_is_one_decimal(self):
        self.assertEqual(stats.fmt("occupancy_pct", 76.8734), "76.9")

    def test_rating_is_two_decimals(self):
        self.assertEqual(stats.fmt("rating_avg", 4.7712), "4.77")

    def test_whole_percentages_stay_whole(self):
        self.assertEqual(stats.fmt("repeat_booking_pct", 36.6), "37")
        self.assertEqual(stats.fmt("saudi_guest_pct", 93.8), "94")

    def test_counts_get_thousands_separators(self):
        self.assertEqual(stats.fmt("reservations_total", 8114), "8,114")
        self.assertEqual(stats.fmt("messages_total", 152177), "152,177")

    def test_western_numerals_in_both_editions(self):
        """Seeds §10: Western numerals, standard in Saudi business documents."""
        self.assertEqual(stats.fmt("reservations_total", 8114, lang="ar"), "8,114")

    def test_a_trailing_zero_decimal_is_kept_where_the_seeds_keep_it(self):
        self.assertEqual(stats.fmt("residences_per_person_per_day", 4.0), "4.0")
        self.assertEqual(stats.fmt("occupancy_active_pct", 76.0), "76.0")


class MarketConfigIsStaticAndSourced(unittest.TestCase):
    """Seeds §4 — AirDNA figures are config, not live, and carry a visible source."""

    def test_market_values(self):
        m = stats.MARKET
        self.assertEqual(m["occupancy_pct"], 38)
        self.assertEqual(m["adr_sar"], 341)
        self.assertEqual(m["revpar_sar"], 124)
        self.assertEqual(m["active_listings"], 21812)

    def test_source_and_date_are_present(self):
        self.assertEqual(stats.MARKET["source"], "AirDNA Riyadh market snapshot")
        self.assertEqual(stats.MARKET["source_date"], "July 2026")

    def test_the_revenue_multiple_is_not_in_the_config(self):
        """Seeds §4: publishing 7.6x lets a reader reverse-engineer per-residence
        revenue. It must not even be present to be accidentally rendered."""
        self.assertNotIn("annual_revenue_multiple", stats.MARKET.get("multiples", {}))
        for v in stats.MARKET.get("multiples", {}).values():
            self.assertNotIn("7.6", str(v))


if __name__ == "__main__":
    unittest.main()
