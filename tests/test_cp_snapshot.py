# -*- coding: utf-8 -*-
"""
cp.snapshot — the nightly refresher for cp_stats.json.

Scope is deliberate: v1 refreshes ONLY the figures whose methodology is
unambiguous from reservation and review rows — counts, nights, repeat rates,
weekday shares, review scores. Occupancy, ADR and RevPAR are NOT refreshed:
their published values follow the owner's export methodology, and printing a
number computed a different way — on a page that invites a reviewer to check —
is worse than an honest «as of August» stamp. They stay seeds-valued until
that computation is built and reconciled against 76.9 / 582 / 451.

Every refreshed field passes a sanity band before it may overlay: totals are
monotonic (the dataset only grows), shares stay inside wide-but-real bounds.
A failed fetch, an empty computation, or an out-of-band value keeps the seeds
value — the /business lesson, held here by construction.

Synthetic-data logic test per CLAUDE.md: fake reservations in, asserted
figures out.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cp import snapshot  # noqa: E402


def _res(arrival, departure, guest="g1", status="new"):
    return {"arrival": arrival, "departure": departure,
            "guest_key": guest, "status": status}


def _rev(rating10=10, date="2026-05-01", cats=None):
    return {"rating10": rating10, "date": date, "public": True,
            "categories": cats or {}}


RAW = {
    "as_of": "2026-09-01",
    "reservations": [
        # g1 books twice (a repeat guest), g2..g4 once each -> 5 bookings
        _res("2026-08-06", "2026-08-07", "g1"),   # Thursday arrival
        _res("2026-08-07", "2026-08-08", "g1"),   # Friday arrival
        _res("2026-08-10", "2026-08-12", "g2"),   # Monday, 2 nights
        _res("2026-08-11", "2026-08-12", "g3"),
        _res("2026-08-12", "2026-08-16", "g4"),   # 4 nights
    ],
    "reviews": [
        _rev(10, cats={"communication": 10, "cleanliness": 9}),
        _rev(10, cats={"communication": 9}),
        _rev(8),
        _rev(9),
    ],
}


class ComputeFromSynthetic(unittest.TestCase):
    def setUp(self):
        self.out = snapshot.compute(RAW)

    def test_counts_and_nights(self):
        self.assertEqual(self.out["reservations_total"], 5)
        self.assertEqual(self.out["nights_total"], 9)   # 1+1+2+1+4

    def test_stay_shape(self):
        self.assertEqual(self.out["avg_stay_nights"], 1.8)
        self.assertEqual(self.out["one_night_booking_pct"], 60)   # 3 of 5

    def test_repeat_metrics(self):
        self.assertEqual(self.out["repeat_guests"], 1)            # g1
        self.assertEqual(self.out["repeat_booking_pct"], 40)      # 2 of 5

    def test_weekend_arrivals(self):
        self.assertEqual(self.out["thu_fri_arrival_pct"], 40)     # 2 of 5

    def test_reviews(self):
        self.assertEqual(self.out["reviews_total"], 4)
        self.assertEqual(self.out["rating_avg"], 4.63)            # 37/4/2
        self.assertEqual(self.out["perfect_ten_pct"], 50.0)
        self.assertEqual(self.out["category_scores"]["communication"], 9.5)

    def test_no_forbidden_fields_are_computed(self):
        """Occupancy/ADR/RevPAR must NOT appear — their methodology is not
        replicated here, and a half-right number is worse than a dated one."""
        for banned in ("occupancy_pct", "adr_sar", "revpar_sar",
                       "residences_total", "saudi_guest_pct"):
            self.assertNotIn(banned, self.out)

    def test_computed_at_stamped(self):
        self.assertTrue(self.out["computed_at"].startswith("2026-09-01"))

    def test_cancelled_rows_do_not_count(self):
        raw = dict(RAW)
        raw["reservations"] = RAW["reservations"] + [
            _res("2026-08-20", "2026-08-21", "g9", status="cancelled")]
        self.assertEqual(snapshot.compute(raw)["reservations_total"], 5)


class SanityBands(unittest.TestCase):
    def test_shrinking_totals_are_rejected(self):
        """The dataset only grows. 100 reservations computed against a seeds
        floor of 8,114 means the fetch was partial — never overlay it."""
        gated = snapshot.apply_sanity({"reservations_total": 100,
                                       "nights_total": 50})
        self.assertNotIn("reservations_total", gated)
        self.assertNotIn("nights_total", gated)

    def test_grown_totals_pass(self):
        gated = snapshot.apply_sanity({"reservations_total": 8300,
                                       "nights_total": 13400})
        self.assertEqual(gated["reservations_total"], 8300)

    def test_out_of_band_shares_are_rejected(self):
        self.assertNotIn("repeat_booking_pct",
                         snapshot.apply_sanity({"repeat_booking_pct": 3}))
        self.assertNotIn("rating_avg",
                         snapshot.apply_sanity({"rating_avg": 3.9}))

    def test_in_band_shares_pass(self):
        gated = snapshot.apply_sanity({"repeat_booking_pct": 38,
                                       "rating_avg": 4.78})
        self.assertEqual(gated["repeat_booking_pct"], 38)

    def test_unknown_fields_never_pass(self):
        """Only fields this job owns may reach cp_stats.json — a stray key
        cannot smuggle a figure onto the page."""
        self.assertEqual(snapshot.apply_sanity({"occupancy_pct": 80}), {})


class BuildAndWrite(unittest.TestCase):
    def test_happy_path_writes_gated_fields(self):
        saved = {}
        res = snapshot.build_and_write(
            fetch=lambda: RAW,
            save_json=lambda name, obj: saved.update({name: obj}) or True,
            seeds={"reservations_total": 4, "nights_total": 8,
                   "reviews_total": 3})
        self.assertTrue(res["ok"])
        snap = saved["cp_stats.json"]
        self.assertEqual(snap["reservations_total"], 5)
        self.assertIn("computed_at", snap)

    def test_a_failed_fetch_writes_nothing(self):
        saved = {}
        def boom():
            raise RuntimeError("hostaway down")
        res = snapshot.build_and_write(
            fetch=boom, save_json=lambda n, o: saved.update({n: o}) or True)
        self.assertFalse(res["ok"])
        self.assertEqual(saved, {})

    def test_all_fields_gated_out_writes_nothing(self):
        """If nothing survives sanity, do not write an empty snapshot over a
        good one."""
        saved = {}
        res = snapshot.build_and_write(
            fetch=lambda: {"as_of": "2026-09-01",
                           "reservations": [], "reviews": []},
            save_json=lambda n, o: saved.update({n: o}) or True)
        self.assertFalse(res["ok"])
        self.assertEqual(saved, {})


if __name__ == "__main__":
    unittest.main()
