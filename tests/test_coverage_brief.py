# -*- coding: utf-8 -*-
"""The «نزّل كل البيانات» export — one readable briefing + one complete JSON.

The whole point of this file is PROVENANCE. A number the owner typed by hand and a
number Hostaway returned look identical once they are both printed as "3" — and a
decision about hiring four people is exactly the kind of decision that must never be
built on a hand-typed placeholder mistaken for measured fact.

So every assertion here is about the export saying WHERE a number came from, and about
it staying honest when a source is missing: Hostaway down must read as "unavailable",
never as zero.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coverage_study import brief as B


# A study snapshot shaped exactly like coverage_study.routes._build returns.
def _study(**over):
    s = {
        "units": {
            "total": 3, "in_house": 1, "third_party": 1, "unassigned": 1,
            "located": 2, "missing_location": 1,
            "rows": [
                {"lid": 101, "name": "Ouja | Alpha", "district": "As Sahafah",
                 "bedrooms": 2, "lat": 24.8, "lng": 46.6, "coord_source": "listing",
                 "has_location": True, "map_link": "https://maps.app.goo.gl/x",
                 "guide_slug": "alpha", "team_id": "team-1", "team_name": "OujaCT",
                 "in_house": True, "oujact_flag": True, "active": True},
                {"lid": 102, "name": "Ouja | Beta", "district": "Al Malqa",
                 "bedrooms": 1, "lat": 24.9, "lng": 46.7, "coord_source": "guide",
                 "has_location": True, "map_link": "", "guide_slug": "beta",
                 "team_id": "team-9", "team_name": "Sparkle Co", "in_house": False,
                 "oujact_flag": False, "active": True},
                {"lid": 103, "name": "Ouja | Gamma", "district": "", "bedrooms": 3,
                 "lat": None, "lng": None, "coord_source": "", "has_location": False,
                 "map_link": "", "guide_slug": "", "team_id": "", "team_name": "",
                 "in_house": False, "oujact_flag": False, "active": True},
            ],
        },
        "clusters": {"total": 2, "multi": 1, "stacked_units": 2, "biggest": 2, "rows": []},
        "teams": [{"team_id": "team-1", "name": "OujaCT", "apartments": 1,
                   "located": 1, "in_house": True},
                  {"team_id": "team-9", "name": "Sparkle Co", "apartments": 1,
                   "located": 1, "in_house": False}],
        "oujact": {
            "started_on": "2026-06-01", "since": "2026-06-01", "days_worked": 40,
            "total_cleans": 520, "per_day_avg": 13.0, "active_people": 4,
            "daily": [{"date": "2026-08-01", "count": 14, "people": 3}],
            "people": [{"person": "reem", "days": 40, "cleans": 300, "counted": True,
                        "per_day": 7.5},
                       {"person": "faisalouja", "days": 10, "cleans": 20,
                        "counted": False, "per_day": 2.0}],
            "work_days": [{"date": "2026-08-01", "person": "reem", "count": 5,
                           "lids": [101, 102]}],
        },
        "cycle": {"median_min": 41, "n": 300, "p25_min": 30, "p75_min": 60},
        "throughput": {"median": 5, "mean": 4.8, "n": 40},
        "photo_time": {"median_min": 12, "n": 88, "warning": "photo not cleaning"},
        "capacity": {"demand_per_day": 19.4, "current_people": 3,
                     "demand_source": "hostaway_30d",
                     "demand_note": "582 checkouts in 30 days",
                     "headcount": {"demand_per_day": 19.4, "rate": 4.0,
                                   "current_people": 3, "peak_per_day": 26,
                                   "roster_factor": 1.167, "absence_factor": 0.0673,
                                   "on_shift_avg": 5, "payroll": 7, "on_shift_peak": 7,
                                   "gap": 4, "reason": ""}},
        "turns": {
            "rows": [{"lid": 101, "name": "Ouja | Alpha", "date": "2026-08-01",
                      "kind": "T0", "deadline": "2026-08-01T15:00",
                      "checkout": "2026-08-01T11:00",
                      "next_checkin": "2026-08-01T15:00"}],
            "by_date": {"2026-08-01": {"date": "2026-08-01", "T0": 1, "T1": 0,
                                       "T2": 0, "total": 1}},
            "skipped": [{"lid": 900, "reason": "الشقة غير مرتبطة بـ Hostaway"}],
            "counts": {"T0": 1, "T1": 0, "T2": 0},
            "window": {"start": "2026-06-06", "end": "2026-08-01", "weeks": 8},
            "checkouts_per_day": 19.4,
        },
        "week": {"days": [{"weekday": 6, "ar": "الأحد", "en": "Sun", "total": 18.0,
                           "T0": 6.0, "observed_days": 8}],
                 "mean_per_day": 19.4, "p70_per_day": 21, "observed_days": 56,
                 "busiest": {"weekday": 3, "ar": "الخميس", "en": "Thu", "total": 26.0,
                             "T0": 11.0, "observed_days": 8},
                 "peak_ratio": 1.34},
        "cleaner": {"own_units": 1, "cleaners": 3, "window_days": 56,
                    "own_checkouts": 300, "own_per_day": 5.4, "busiest_day": 12,
                    "per_cleaner_typical": 1.8, "per_cleaner_best": 4.0,
                    "likely_underused": True, "reason": ""},
        "vendors": {"rows": [{"lid": 102, "name": "Ouja | Beta", "bedrooms": 1,
                              "team_id": "team-9", "team_name": "Sparkle Co",
                              "monthly": 900.0, "cleans_per_month": 6.0,
                              "per_clean": 150.0}],
                    "total_monthly": 900.0, "missing_prices": ["Ouja | Gamma"],
                    "missing_count": 1, "priced_count": 1, "apartments": 2,
                    "by_team": [{"name": "Sparkle Co", "monthly": 900.0}]},
        "cost": {"demand_per_day": 19.4, "per_cleaner_day": 4.0, "cleaners_needed": 7,
                 "inhouse_monthly": 15100.0, "inhouse_per_clean": 26.0,
                 "vendor_monthly": 900.0, "vendor_per_clean": 1.5,
                 "current_monthly": 13800.0, "saving_monthly": -1300.0, "reason": ""},
        "reconcile": {"logged_per_day": 13.0, "checkouts_per_day": 19.4,
                      "unlogged_per_day": 6.4, "has_gap": True,
                      "crews": [{"team_id": "team-1", "name": "OujaCT", "units": 1,
                                 "cleans": 520, "implausible": True}],
                      "untagged_cleans": 3},
        "settings": {"non_cleaners": ["faisalouja", "route-link"], "cleaners_count": 3,
                     "supervisors_count": 1, "cleaner_cost_sar": 1300,
                     "supervisor_cost_sar": 6000, "days_per_week": 6,
                     "days_off_per_year": 21,
                     "apartment_price_sar": {"102": 900.0},
                     "roster_factor": 1.167, "absence_factor": 0.0673},
        "geo": {"have_key": False, "filled_from_cache": 0, "cached_total": 4,
                "pending": 1, "nothing_to_resolve": 0},
        "generated_at": "2026-08-05T14:00:00",
    }
    s.update(over)
    return s


def _no_hostaway():
    """Exactly what _build returns when the reservations call fails."""
    s = _study()
    for k in ("turns", "week", "cleaner", "vendors", "cost", "reconcile"):
        s[k] = None
    s["capacity"]["headcount"] = None
    s["capacity"]["demand_source"] = "estimated_from_log"
    s["capacity"]["demand_note"] = "Hostaway demand unavailable: timeout"
    return s


# ---------------------------------------------------------------- markdown

class TestMarkdown(unittest.TestCase):
    def test_renders_and_names_every_major_section(self):
        md = B.render_markdown(_study())
        for heading in ("القرار", "كتبناها بأيدينا", "Hostaway", "سجل العمليات",
                        "الحسابات", "الشقق", "الناقص"):
            self.assertIn(heading, md, "missing section: " + heading)

    def test_hand_typed_numbers_are_listed_as_hand_typed(self):
        md = B.render_markdown(_study())
        typed = md.split("## 3")[1].split("## 4")[0] if "## 3" in md else md
        # Rendered for a human to read, so 1300 prints as 1,300.
        for token in ("1,300", "6,000", "21"):
            self.assertIn(token, typed)

    def test_the_apartment_price_is_shown_against_its_apartment_name(self):
        md = B.render_markdown(_study())
        line = [l for l in md.split("\n") if "Ouja | Beta" in l and "900" in l]
        self.assertTrue(line, "the typed 900 SAR price is not shown next to Ouja | Beta")

    def test_an_apartment_with_no_typed_price_is_named_not_zeroed(self):
        md = B.render_markdown(_study())
        self.assertIn("Ouja | Gamma", md)
        self.assertNotIn("Ouja | Gamma | 0 ", md)

    def test_demand_carries_its_source(self):
        md = B.render_markdown(_study())
        self.assertIn("hostaway_30d", md)
        self.assertIn("582 checkouts in 30 days", md)

    def test_the_supervisor_caveat_is_always_stated(self):
        """The single most misleading thing in this data: the log records who pressed
        «تم» (a supervisor), not who cleaned. An export without it invites a wrong
        per-cleaner rate in the next session."""
        md = B.render_markdown(_study())
        self.assertIn("تم", md)
        self.assertIn("المشرف", md)

    def test_excluded_people_are_marked_not_silently_dropped(self):
        md = B.render_markdown(_study())
        self.assertIn("faisalouja", md)

    def test_skipped_reservations_are_reported(self):
        md = B.render_markdown(_study())
        self.assertIn("900", md)
        self.assertIn("غير مرتبطة", md)


class TestMarkdownWithoutHostaway(unittest.TestCase):
    """Hostaway down must read as 'we do not know', never as zero."""

    def test_renders_without_crashing(self):
        md = B.render_markdown(_no_hostaway())
        self.assertTrue(len(md) > 500)

    def test_says_unavailable_rather_than_printing_zero_turns(self):
        md = B.render_markdown(_no_hostaway())
        self.assertIn("غير متوفرة", md)

    def test_does_not_claim_a_head_count(self):
        md = B.render_markdown(_no_hostaway())
        self.assertNotIn("نوظّف 4", md)

    def test_survives_a_study_missing_whole_keys(self):
        md = B.render_markdown({"generated_at": "2026-08-05T14:00:00"})
        self.assertTrue(len(md) > 200)

    def test_survives_an_empty_dict(self):
        self.assertTrue(len(B.render_markdown({})) > 200)


# ---------------------------------------------------------------- json

class TestJson(unittest.TestCase):
    def test_is_serialisable_and_keeps_the_study_whole(self):
        payload = B.render_payload(_study())
        text = json.dumps(payload, ensure_ascii=False)
        back = json.loads(text)
        self.assertEqual(back["study"]["units"]["rows"][0]["lid"], 101)
        self.assertEqual(back["study"]["turns"]["counts"]["T0"], 1)

    def test_carries_a_provenance_map_covering_the_four_buckets(self):
        p = B.render_payload(_study())["provenance"]
        for bucket in ("typed_by_hand", "hostaway_api", "ops_log", "computed"):
            self.assertIn(bucket, p)
            self.assertTrue(p[bucket], "empty provenance bucket: " + bucket)

    def test_every_provenance_field_names_a_real_key_path(self):
        """A provenance map that points at keys the study does not have is worse than
        none — the next session would go looking for data that was never exported."""
        s = _study()
        p = B.render_payload(s)["provenance"]
        for bucket, fields in p.items():
            for f in fields:
                path = f["path"] if isinstance(f, dict) else f
                node, ok = s, True
                for part in path.split("."):
                    if isinstance(node, dict) and part in node:
                        node = node[part]
                    else:
                        ok = False
                        break
                self.assertTrue(ok, "provenance points at a missing path: " + path)

    def test_gaps_are_listed_explicitly(self):
        g = B.render_payload(_study())["gaps"]
        joined = " ".join(json.dumps(x, ensure_ascii=False) for x in g)
        self.assertIn("Gamma", joined)          # no price, no location, no team

    def test_no_hostaway_marks_the_missing_sources(self):
        p = B.render_payload(_no_hostaway())
        self.assertFalse(p["sources"]["hostaway_reservations"])
        self.assertTrue(p["sources"]["ops_log"])


class TestFilenames(unittest.TestCase):
    def test_names_are_dated_and_safe(self):
        self.assertEqual(B.filename("md", "2026-08-05"),
                         "ouja-coverage-brief-2026-08-05.md")
        self.assertEqual(B.filename("json", "2026-08-05"),
                         "ouja-coverage-data-2026-08-05.json")

    def test_a_junk_date_cannot_escape_the_filename(self):
        name = B.filename("md", "../../etc/passwd")
        self.assertNotIn("/", name)


if __name__ == "__main__":
    unittest.main()
