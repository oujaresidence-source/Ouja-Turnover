import unittest
from match import engine


def unit(uid, beds=2, capacity=4, rating=4.7, reviews=40,
         neighborhood="al_malqa", amenities=None, est_avg=700):
    """Fabricated public-listing dict, shaped like _gw_listing_public output."""
    return {
        "id": uid, "slug": f"unit-{uid}", "name_ar": f"عوجا | وحدة {uid}",
        "beds": beds, "baths": 2, "capacity": capacity,
        "neighborhood": neighborhood, "area": "الملقا",
        "amenities": amenities if amenities is not None else ["Wifi", "Kitchen"],
        "rating": rating, "reviews_count": reviews,
        "est_avg": est_avg, "available": True,
    }


BASE = {"party_size": 2, "sleep_pref": None, "purpose": "rest",
        "budget_max": None, "check_in": None, "check_out": None}


class TestNeverZero(unittest.TestCase):
    def test_returns_results_when_inventory_exists(self):
        out = engine.score(BASE, [unit(1), unit(2), unit(3)])
        self.assertGreater(len(out["top"]), 0)

    def test_returns_results_even_when_every_soft_signal_fails(self):
        answers = dict(BASE, party_size=2, purpose="boulevard", budget_max=100)
        out = engine.score(answers, [unit(1, est_avg=5000, rating=3.0, reviews=2)])
        self.assertEqual(len(out["top"]), 1)
        self.assertFalse(out["confident"])

    def test_empty_inventory_returns_empty_not_crash(self):
        out = engine.score(BASE, [])
        self.assertEqual(out["top"], [])
        self.assertFalse(out["impossible"])


class TestCapacityGate(unittest.TestCase):
    def test_never_recommends_a_unit_that_cannot_fit(self):
        answers = dict(BASE, party_size=6)
        out = engine.score(answers, [unit(1, capacity=4), unit(2, capacity=8)])
        ids = [u["id"] for u in out["top"] + out["near"]]
        self.assertNotIn(1, ids)
        self.assertIn(2, ids)

    def test_physically_impossible_party_is_flagged_honestly(self):
        answers = dict(BASE, party_size=20)
        out = engine.score(answers, [unit(1, capacity=4), unit(2, capacity=8)])
        self.assertEqual(out["top"], [])
        self.assertTrue(out["impossible"])
        self.assertEqual(out["max_capacity"], 8)

    def test_unit_with_unknown_capacity_is_not_gated_out(self):
        u = unit(1)
        u["capacity"] = None
        out = engine.score(dict(BASE, party_size=6), [u])
        self.assertEqual(len(out["top"]), 1)


class TestAvailabilityGate(unittest.TestCase):
    def test_unavailable_units_are_excluded_when_dates_given(self):
        a = unit(1); a["available"] = False
        b = unit(2); b["available"] = True
        answers = dict(BASE, check_in="2026-08-01", check_out="2026-08-04")
        out = engine.score(answers, [a, b])
        ids = [u["id"] for u in out["top"] + out["near"]]
        self.assertEqual(ids, [2])

    def test_availability_ignored_when_no_dates(self):
        a = unit(1); a["available"] = False
        out = engine.score(BASE, [a])
        self.assertEqual(len(out["top"]), 1)

    def test_booked_dates_are_not_reported_as_too_small(self):
        """A couple looking at a fully-booked weekend must NOT be told no unit
        is big enough for them."""
        a = unit(1, capacity=4); a["available"] = False
        b = unit(2, capacity=6); b["available"] = False
        answers = dict(BASE, party_size=2,
                       check_in="2026-08-01", check_out="2026-08-04")
        out = engine.score(answers, [a, b])
        self.assertEqual(out["top"], [])
        self.assertFalse(out["impossible"])

    def test_too_large_party_is_still_impossible_even_with_dates(self):
        answers = dict(BASE, party_size=20,
                       check_in="2026-08-01", check_out="2026-08-04")
        out = engine.score(answers, [unit(1, capacity=4), unit(2, capacity=8)])
        self.assertTrue(out["impossible"])
        self.assertEqual(out["max_capacity"], 8)


class TestDeterminism(unittest.TestCase):
    def test_identical_input_gives_identical_order(self):
        units = [unit(i) for i in (5, 3, 9, 1)]
        first = [u["id"] for u in engine.score(BASE, units)["top"]]
        second = [u["id"] for u in engine.score(BASE, list(units))["top"]]
        self.assertEqual(first, second)

    def test_ties_break_on_id_ascending(self):
        units = [unit(9), unit(2), unit(7)]
        out = engine.score(BASE, units)
        ids = [u["id"] for u in out["top"]]
        self.assertEqual(ids, sorted(ids))

    def test_does_not_mutate_the_caller_list(self):
        units = [unit(3), unit(1)]
        engine.score(BASE, units)
        self.assertEqual([u["id"] for u in units], [3, 1])

    def test_mixed_id_types_do_not_crash_the_sort(self):
        units = [unit(1), unit("2"), unit(None)]
        out = engine.score(BASE, list(units))
        again = engine.score(BASE, list(units))
        ids = [u["id"] for u in out["top"] + out["near"]]
        ids_again = [u["id"] for u in again["top"] + again["near"]]
        self.assertEqual(ids, ids_again)
        self.assertEqual(len(ids), 3)


class TestPartySizeCoercion(unittest.TestCase):
    def test_malformed_party_size_does_not_fail_open(self):
        """A garbage party_size must not silently disable the capacity gate
        (the old bug: int("abc") raised, was swallowed, and the unit was
        admitted no matter its capacity)."""
        units = [unit(1, capacity=1), unit(2, capacity=4)]
        malformed = engine.score(dict(BASE, party_size="abc"), [dict(u) for u in units])
        explicit_one = engine.score(dict(BASE, party_size=1), [dict(u) for u in units])
        got = sorted(u["id"] for u in malformed["top"] + malformed["near"])
        want = sorted(u["id"] for u in explicit_one["top"] + explicit_one["near"])
        self.assertEqual(got, want)

    def test_none_party_size_defaults_to_one(self):
        out = engine.score(dict(BASE, party_size=None), [unit(1, capacity=1)])
        self.assertEqual(len(out["top"]), 1)


class TestReturnedItemsAreCopies(unittest.TestCase):
    def test_mutating_a_returned_items_nested_list_does_not_touch_the_input(self):
        u = unit(1, amenities=["Wifi", "Kitchen"])
        out = engine.score(BASE, [u])
        out["top"][0]["amenities"].append("Pool")
        self.assertEqual(u["amenities"], ["Wifi", "Kitchen"])


class TestTopAndNearSplit(unittest.TestCase):
    def test_top_capped_at_three_rest_goes_to_near(self):
        out = engine.score(BASE, [unit(i) for i in range(1, 8)])
        self.assertEqual(len(out["top"]), 3)
        self.assertEqual(len(out["near"]), 4)

    def test_scores_are_descending_across_top_then_near(self):
        out = engine.score(BASE, [unit(i, beds=i) for i in range(1, 7)])
        scores = [u["match_score"] for u in out["top"] + out["near"]]
        self.assertEqual(scores, sorted(scores, reverse=True))


class TestRequiredBedrooms(unittest.TestCase):
    def test_solo_and_couple_need_one(self):
        self.assertEqual(engine.required_bedrooms(1, None), 1)
        self.assertEqual(engine.required_bedrooms(2, None), 1)

    def test_together_means_one_room(self):
        self.assertEqual(engine.required_bedrooms(5, "together"), 1)

    def test_each_means_one_room_per_person(self):
        self.assertEqual(engine.required_bedrooms(4, "each"), 4)

    def test_pairs_rounds_up(self):
        self.assertEqual(engine.required_bedrooms(5, "pairs"), 3)
        self.assertEqual(engine.required_bedrooms(4, "pairs"), 2)


class TestBedroomFit(unittest.TestCase):
    def test_exact_match_outranks_over_provisioned(self):
        answers = dict(BASE, party_size=4, sleep_pref="pairs")   # needs 2
        out = engine.score(answers, [unit(1, beds=5, capacity=10),
                                     unit(2, beds=2, capacity=6)])
        self.assertEqual(out["top"][0]["id"], 2)

    def test_under_provisioned_still_appears_with_a_tradeoff(self):
        answers = dict(BASE, party_size=6, sleep_pref="each")    # needs 6
        out = engine.score(answers, [unit(1, beds=2, capacity=8)])
        self.assertEqual(len(out["top"]), 1)
        self.assertIsNotNone(out["top"][0]["tradeoff"])

    def test_exact_match_produces_a_reason(self):
        answers = dict(BASE, party_size=4, sleep_pref="pairs")
        out = engine.score(answers, [unit(1, beds=2, capacity=6)])
        self.assertTrue(out["top"][0]["reasons"])

    def test_every_returned_unit_has_at_least_one_reason(self):
        answers = dict(BASE, party_size=2)
        out = engine.score(answers, [unit(i) for i in range(1, 6)])
        for u in out["top"] + out["near"]:
            self.assertTrue(u["reasons"], f"unit {u['id']} has no reason")

    def test_reason_contains_the_real_bedroom_number(self):
        """Locks the exact rendered string, not a loose digit-substring check
        (a weak "2" in reasons would falsely pass even after Fix 1's dual
        form "غرفتين نوم" — which contains no digit at all)."""
        answers = dict(BASE, party_size=4, sleep_pref="pairs")
        out = engine.score(answers, [unit(1, beds=2, capacity=6)])
        self.assertIn("غرفتين نوم — بالضبط اللي طلبته", out["top"][0]["reasons"])

    def test_malformed_party_size_does_not_raise_during_scoring(self):
        """`_score_one` must use the already-cleaned party_size, not re-derive
        it from raw `answers` (which can be a non-numeric string)."""
        answers = dict(BASE, party_size="abc", sleep_pref="pairs")
        out = engine.score(answers, [unit(1, beds=2, capacity=6)])
        self.assertEqual(len(out["top"]), 1)


class TestQualitySmoothing(unittest.TestCase):
    def test_perfect_rating_with_few_reviews_loses_to_strong_rating_with_many(self):
        out = engine.score(BASE, [unit(1, rating=5.0, reviews=3),
                                  unit(2, rating=4.8, reviews=90)])
        self.assertEqual(out["top"][0]["id"], 2)

    def test_unrated_unit_is_not_eliminated(self):
        u = unit(1, rating=None, reviews=0)
        out = engine.score(BASE, [u])
        self.assertEqual(len(out["top"]), 1)

    def test_high_rating_produces_a_reason_with_the_number(self):
        out = engine.score(BASE, [unit(1, rating=4.9, reviews=67)])
        joined = " ".join(out["top"][0]["reasons"])
        self.assertIn("4.9", joined)
        self.assertIn("67", joined)

    def test_reason_guarantee_holds_for_unknown_data_units(self):
        u = unit(1, rating=None, reviews=0)
        u["beds"] = None
        out = engine.score(BASE, [u])
        self.assertTrue(out["top"][0]["reasons"])

    def test_barely_reviewed_near_perfect_unit_can_beat_a_proven_strong_unit(self):
        """Intentional, not a bug: PRIOR_RATING=4.6 encodes "an Ouja unit is
        expected to perform around 4.6". A unit proven at 4.5 across 200
        reviews is a well-established below-prior performer; a unit with a
        single 5.0 review is pulled toward the prior and lands above it.
        Locked here so nobody "fixes" this later — see the comment on
        PRIOR_RATING in match/engine.py."""
        out = engine.score(BASE, [unit(1, rating=4.5, reviews=200),
                                  unit(2, rating=5.0, reviews=1)])
        self.assertEqual(out["top"][0]["id"], 2)


class TestArabicNumberAgreement(unittest.TestCase):
    """Fix 1: Arabic requires singular for 1, dual for 2, plural for 3-10,
    singular again for 11+. Getting this wrong on guest-facing copy reads as
    machine translation."""

    def test_bedroom_agreement_forms(self):
        forms = ('غرفة نوم وحدة', 'غرفتين نوم', 'غرف نوم', 'غرفة نوم')
        self.assertEqual(engine._ar_count(1, *forms), 'غرفة نوم وحدة')
        self.assertEqual(engine._ar_count(2, *forms), 'غرفتين نوم')
        self.assertEqual(engine._ar_count(3, *forms), '3 غرف نوم')
        self.assertEqual(engine._ar_count(10, *forms), '10 غرف نوم')
        self.assertEqual(engine._ar_count(11, *forms), '11 غرفة نوم')

    def test_guest_agreement_forms(self):
        forms = ('ضيف واحد', 'ضيفين', 'ضيوف', 'ضيف')
        self.assertEqual(engine._ar_count(1, *forms), 'ضيف واحد')
        self.assertEqual(engine._ar_count(2, *forms), 'ضيفين')
        self.assertEqual(engine._ar_count(3, *forms), '3 ضيوف')
        self.assertEqual(engine._ar_count(10, *forms), '10 ضيوف')
        self.assertEqual(engine._ar_count(11, *forms), '11 ضيف')

    def test_dual_form_appears_in_a_real_reason_and_the_broken_form_never_does(self):
        answers = dict(BASE, party_size=4, sleep_pref="pairs")   # needs 2
        out = engine.score(answers, [unit(1, beds=2, capacity=6)])
        reason = out["top"][0]["reasons"][0]
        self.assertIn("غرفتين", reason)
        self.assertNotIn("2 غرف", reason)

    def test_capacity_fallback_uses_correct_guest_agreement(self):
        u = unit(1, rating=None, reviews=0, capacity=2)
        u["beds"] = None
        out = engine.score(BASE, [u])
        self.assertIn("تستوعب ضيفين", out["top"][0]["reasons"])


class TestStudioVsUnknownBeds(unittest.TestCase):
    """Fix 2: `beds` missing/non-numeric is genuinely unknown (neutral,
    untouched); `beds == 0` is a real Hostaway studio and must be scored
    honestly, not laundered into "unknown"."""

    def test_missing_beds_is_neutral_with_no_claim(self):
        fit, reason, tradeoff = engine._score_bedrooms({"beds": None}, 2, None)
        self.assertEqual(fit, 0.5)
        self.assertIsNone(reason)
        self.assertIsNone(tradeoff)

    def test_non_numeric_beds_is_treated_as_unknown_not_studio(self):
        fit, reason, tradeoff = engine._score_bedrooms({"beds": "n/a"}, 2, None)
        self.assertEqual(fit, 0.5)
        self.assertIsNone(reason)
        self.assertIsNone(tradeoff)

    def test_studio_is_scored_honestly_not_as_unknown(self):
        fit, reason, tradeoff = engine._score_bedrooms({"beds": 0}, 2, None)
        self.assertNotEqual(fit, 0.5)
        self.assertIsNotNone(tradeoff)
        self.assertIn("استوديو", tradeoff)

    def test_studio_never_outscores_a_real_one_bedroom_at_the_same_need(self):
        cases = [(2, None), (4, "pairs"), (6, "pairs")]
        for party_size, sleep_pref in cases:
            studio_fit, _, _ = engine._score_bedrooms({"beds": 0}, party_size, sleep_pref)
            one_bed_fit, _, _ = engine._score_bedrooms({"beds": 1}, party_size, sleep_pref)
            self.assertLessEqual(studio_fit, one_bed_fit)

    def test_studio_does_not_hide_behind_the_neutral_unknown_score(self):
        """A studio used to be laundered as 'unknown data' (0.5), which beat
        a real one-room-short apartment (0.37). That was backwards."""
        studio_fit, _, _ = engine._score_bedrooms({"beds": 0}, 2, None)
        self.assertLess(studio_fit, 0.5)


class TestHonestAvailabilityFallback(unittest.TestCase):
    """Fix 3: the reason-guarantee fallback must never claim availability
    that was never checked. Availability is only verified when the guest
    gave real dates (mirrors bot.py's `_gw_search` browse-mode behaviour)."""

    def _unclaimed_unit(self):
        u = unit(1, rating=None, reviews=0)
        u["beds"] = None
        u["capacity"] = None
        return u

    def test_no_dates_makes_no_availability_claim(self):
        out = engine.score(BASE, [self._unclaimed_unit()])
        reasons = out["top"][0]["reasons"]
        self.assertIn("من وحدات عوجا المختارة", reasons)
        self.assertNotIn("متاحة للحجز", reasons)
        self.assertNotIn("متاحة بتواريخك", reasons)

    def test_dates_given_allows_the_availability_claim(self):
        answers = dict(BASE, check_in="2026-08-01", check_out="2026-08-04")
        out = engine.score(answers, [self._unclaimed_unit()])
        self.assertIn("متاحة بتواريخك", out["top"][0]["reasons"])


if __name__ == "__main__":
    unittest.main()
