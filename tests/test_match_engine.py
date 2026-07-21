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
        # neighborhood + amenities must ALSO miss for "every soft signal
        # fails" to be true now that proximity/amenities are real scoring
        # dimensions (Tasks 5-6) — the default fixture (al_malqa, Wifi) is
        # coincidentally near the Boulevard and has Wifi, which used to be
        # inert before those weights were wired in.
        answers = dict(BASE, party_size=2, purpose="boulevard", budget_max=100)
        u = unit(1, est_avg=5000, rating=3.0, reviews=2,
                 neighborhood="manfuhah", amenities=["Kitchen"])
        out = engine.score(answers, [u])
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


class TestProximity(unittest.TestCase):
    def test_closer_unit_to_the_boulevard_outranks_farther(self):
        from match import poi as _poi
        blvd = (_poi.POIS["boulevard"][2], _poi.POIS["boulevard"][3])
        near = (blvd[0] + 0.01, blvd[1])
        far = (blvd[0] + 0.30, blvd[1])
        answers = dict(BASE, purpose="boulevard")
        out = engine.score(answers, [unit(1), unit(2)], geo={1: far, 2: near})
        self.assertEqual(out["top"][0]["id"], 2)

    def test_close_unit_gets_a_minutes_reason(self):
        from match import poi as _poi
        blvd = (_poi.POIS["boulevard"][2], _poi.POIS["boulevard"][3])
        answers = dict(BASE, purpose="boulevard")
        out = engine.score(answers, [unit(1)], geo={1: (blvd[0] + 0.01, blvd[1])})
        joined = " ".join(out["top"][0]["reasons"])
        self.assertIn("دقيقة", joined)

    def test_missing_coords_fall_back_to_centroid_not_null(self):
        answers = dict(BASE, purpose="boulevard")
        out = engine.score(answers, [unit(1, neighborhood="al_malqa")], geo={})
        self.assertEqual(len(out["top"]), 1)
        self.assertGreater(out["top"][0]["match_score"], 0)

    def test_purpose_without_a_poi_scores_neutral_for_everyone(self):
        answers = dict(BASE, purpose="rest")
        out = engine.score(answers, [unit(1, neighborhood="al_malqa"),
                                     unit(2, neighborhood="al_malaz")], geo={})
        self.assertEqual(out["top"][0]["match_score"], out["top"][1]["match_score"])

    def test_unlocatable_unit_is_not_eliminated(self):
        u = unit(1, neighborhood="")
        answers = dict(BASE, purpose="boulevard")
        out = engine.score(answers, [u], geo={})
        self.assertEqual(len(out["top"]), 1)

    def test_far_unit_gets_a_distance_tradeoff(self):
        from match import poi as _poi
        blvd = (_poi.POIS["boulevard"][2], _poi.POIS["boulevard"][3])
        answers = dict(BASE, purpose="boulevard")
        out = engine.score(answers, [unit(1)], geo={1: (blvd[0] + 0.40, blvd[1])})
        self.assertIsNotNone(out["top"][0]["tradeoff"])


class TestBudget(unittest.TestCase):
    def test_within_budget_outranks_over_budget(self):
        answers = dict(BASE, budget_max=800)
        out = engine.score(answers, [unit(1, est_avg=1400), unit(2, est_avg=700)])
        self.assertEqual(out["top"][0]["id"], 2)

    def test_over_budget_unit_still_appears_with_a_tradeoff(self):
        answers = dict(BASE, budget_max=500)
        out = engine.score(answers, [unit(1, est_avg=900)])
        self.assertEqual(len(out["top"]), 1)
        self.assertIsNotNone(out["top"][0]["tradeoff"])

    def test_tradeoff_states_the_real_gap(self):
        # Tests _score_budget directly rather than through the full engine:
        # once tradeoffs are picked by largest actual points-lost (Fix 3),
        # a *different* dimension's tradeoff can legitimately outrank
        # budget's in the top-level `score()` output for a given fixture —
        # this test only needs to prove budget's OWN tradeoff text is right.
        fit, reason, tradeoff = engine._score_budget({"est_avg": 650}, {"budget_max": 500})
        self.assertIn("150", tradeoff)

    def test_no_budget_answer_scores_neutral_for_everyone(self):
        answers = dict(BASE, budget_max=None)
        out = engine.score(answers, [unit(1, est_avg=300), unit(2, est_avg=3000)])
        self.assertEqual(out["top"][0]["match_score"], out["top"][1]["match_score"])

    def test_unpriced_unit_is_not_eliminated(self):
        u = unit(1); u["est_avg"] = None; u["price_base"] = None
        out = engine.score(dict(BASE, budget_max=500), [u])
        self.assertEqual(len(out["top"]), 1)

    def test_malformed_budget_max_scores_neutral_not_raise(self):
        """`budget_max` might not be cleaned yet when this is called directly —
        a non-numeric string must not raise inside `int(budget)`."""
        answers = dict(BASE, budget_max="abc")
        out = engine.score(answers, [unit(1, est_avg=900)])
        self.assertEqual(len(out["top"]), 1)


class TestPurposeAmenities(unittest.TestCase):
    def test_workspace_helps_a_work_trip(self):
        answers = dict(BASE, purpose="work")
        withws = unit(1, amenities=["Wifi", "Dedicated workspace", "Kitchen"])
        without = unit(2, amenities=["Kitchen"])
        out = engine.score(answers, [withws, without], geo={})
        self.assertEqual(out["top"][0]["id"], 1)

    def test_washer_helps_a_family_trip(self):
        answers = dict(BASE, purpose="family")
        withw = unit(1, amenities=["Kitchen", "Washer"])
        without = unit(2, amenities=["Wifi"])
        out = engine.score(answers, [withw, without], geo={})
        self.assertEqual(out["top"][0]["id"], 1)

    def test_missing_amenities_list_does_not_crash(self):
        u = unit(1); u["amenities"] = None
        out = engine.score(dict(BASE, purpose="work"), [u])
        self.assertEqual(len(out["top"]), 1)


class TestAmenityExclusions(unittest.TestCase):
    """Fix 1: real Hostaway/Airbnb amenity strings that contain a keyword as a
    substring but mean something else entirely must NOT be credited — that
    would tell a guest they have an amenity the unit does not actually have,
    the worst failure mode this feature has."""

    def test_dishwasher_does_not_satisfy_washer(self):
        answers = dict(BASE, purpose="family")
        u = unit(1, amenities=["Kitchen", "Dishwasher"])
        fit, reason, tradeoff = engine._score_amenities(u, answers)
        self.assertNotIn("غسالة", reason or "")

    def test_pool_table_does_not_satisfy_pool(self):
        answers = dict(BASE, purpose="rest")
        u = unit(1, amenities=["Pool table"])
        fit, reason, tradeoff = engine._score_amenities(u, answers)
        self.assertIsNone(reason)
        self.assertIsNotNone(tradeoff)

    def test_pool_cue_does_not_satisfy_pool(self):
        answers = dict(BASE, purpose="rest")
        u = unit(1, amenities=["Pool cue rack"])
        fit, reason, tradeoff = engine._score_amenities(u, answers)
        self.assertIsNone(reason)

    def test_paid_parking_off_premises_does_not_satisfy_parking(self):
        answers = dict(BASE, purpose="medical")
        u = unit(1, amenities=["Paid parking off premises"])
        fit, reason, tradeoff = engine._score_amenities(u, answers)
        self.assertNotIn("موقف", reason or "")

    def test_street_parking_does_not_satisfy_parking(self):
        answers = dict(BASE, purpose="boulevard")
        u = unit(1, amenities=["Street parking"])
        fit, reason, tradeoff = engine._score_amenities(u, answers)
        self.assertNotIn("موقف", reason or "")

    def test_real_washer_is_credited(self):
        answers = dict(BASE, purpose="family")
        u = unit(1, amenities=["Washer", "Kitchen"])
        fit, reason, tradeoff = engine._score_amenities(u, answers)
        self.assertIn("غسالة", reason)

    def test_real_pool_is_credited(self):
        answers = dict(BASE, purpose="rest")
        u = unit(1, amenities=["Pool"])
        fit, reason, tradeoff = engine._score_amenities(u, answers)
        self.assertIn("مسبح", reason)

    def test_free_parking_on_premises_is_credited(self):
        answers = dict(BASE, purpose="boulevard")
        u = unit(1, amenities=["Free parking on premises"])
        fit, reason, tradeoff = engine._score_amenities(u, answers)
        self.assertIn("موقف", reason)

    def test_exclusions_do_not_leak_across_separate_amenity_strings(self):
        """"washer" must still be credited from a genuine "Washer" entry even
        when a *different* amenity string in the same list is "Dishwasher" —
        matching per-string (not one joined blob) keeps the exclusion scoped
        to only the string it actually appears in."""
        answers = dict(BASE, purpose="family")
        u = unit(1, amenities=["Dishwasher", "Washer", "Kitchen"])
        fit, reason, tradeoff = engine._score_amenities(u, answers)
        self.assertIn("غسالة", reason)


class TestAmenityAndQualityTradeoffs(unittest.TestCase):
    """Fix 2: amenities and quality must be able to produce a tradeoff, not
    just a reason-or-nothing — otherwise a unit that loses real points on
    both (e.g. no relevant amenities + a genuinely low rating) presents as
    flawless, which reads as machine-generated once guests compare cards."""

    def test_no_relevant_amenities_produces_a_tradeoff(self):
        answers = dict(BASE, purpose="work")
        u = unit(1, amenities=["Ethernet only", "Fireplace"])
        fit, reason, tradeoff = engine._score_amenities(u, answers)
        self.assertIsNone(reason)
        self.assertIsNotNone(tradeoff)
        self.assertIn("ما ذكروا", tradeoff)

    def test_work_tradeoff_names_workspace_not_wifi(self):
        """Wifi is a near-universal basic — Hostaway amenity lists are
        frequently incomplete, so a missing wifi match only means the
        LISTING didn't mention it, not that the unit lacks it. Naming it as
        missing would be a false-negative claim (the mirror of the
        false-positive bug this table was already fixed for), so wifi must
        never appear in this tradeoff even though it's in PURPOSE_AMENITIES
        for "work"."""
        answers = dict(BASE, purpose="work")
        u = unit(1, amenities=["Ethernet only", "Fireplace"])
        fit, reason, tradeoff = engine._score_amenities(u, answers)
        self.assertIn("مكتب", tradeoff)
        self.assertNotIn("واي فاي", tradeoff)

    def test_family_missing_amenities_tradeoff_names_real_labels(self):
        answers = dict(BASE, purpose="family")
        u = unit(1, amenities=["Fireplace"])
        fit, reason, tradeoff = engine._score_amenities(u, answers)
        self.assertIsNotNone(tradeoff)
        self.assertTrue(any(lbl in tradeoff for lbl in ("غسالة", "سرير أطفال")))
        self.assertNotIn("مطبخ كامل", tradeoff)   # kitchen is a near-universal basic

    def test_only_wifi_or_kitchen_missing_produces_no_amenity_tradeoff(self):
        """If every unmatched amenity for a purpose is a near-universal basic
        (wifi/kitchen-class, tradeoff-ineligible), there is nothing honest
        left to name — no amenity tradeoff should be emitted at all, rather
        than falsely implying the unit lacks something distinctive."""
        wifi_and_kitchen_only = [("wifi", (), "واي فاي", False),
                                  ("kitchen", (), "مطبخ كامل", False)]
        self.assertIsNone(engine._missing_amenities_tradeoff(wifi_and_kitchen_only))

    def test_boulevard_tradeoff_names_parking_not_wifi(self):
        answers = dict(BASE, purpose="boulevard")
        u = unit(1, amenities=["Fireplace"])
        fit, reason, tradeoff = engine._score_amenities(u, answers)
        self.assertIn("موقف", tradeoff)
        self.assertNotIn("واي فاي", tradeoff)

    def test_low_rating_with_enough_reviews_gets_a_tradeoff(self):
        fit, reason, tradeoff = engine._score_quality({"rating": 3.2, "reviews_count": 50})
        self.assertIsNone(reason)
        self.assertIsNotNone(tradeoff)
        self.assertIn("3.2", tradeoff)

    def test_unrated_unit_gets_no_quality_tradeoff(self):
        fit, reason, tradeoff = engine._score_quality({"rating": None, "reviews_count": 0})
        self.assertIsNone(tradeoff)

    def test_thinly_reviewed_low_rating_gets_no_quality_tradeoff(self):
        """A low rating from only a handful of reviews is noise, not a proven
        fault — must not be held against new inventory."""
        fit, reason, tradeoff = engine._score_quality({"rating": 3.0, "reviews_count": 3})
        self.assertIsNone(tradeoff)

    def test_a_weak_unit_no_longer_presents_as_flawless(self):
        """Reproduces the proof case exactly: amenities=['Ethernet only',
        'Fireplace'] + rating 3.2/50 reviews on a boulevard journey used to
        score 78 with tradeoff: None. It must now surface a tradeoff."""
        from match import poi as _poi
        blvd = (_poi.POIS["boulevard"][2], _poi.POIS["boulevard"][3])
        answers = dict(BASE, purpose="boulevard")
        u = unit(1, amenities=["Ethernet only", "Fireplace"], rating=3.2, reviews=50)
        out = engine.score(answers, [u], geo={1: (blvd[0] + 0.005, blvd[1])})
        self.assertIsNotNone(out["top"][0]["tradeoff"])


class TestImpactBasedSelection(unittest.TestCase):
    """Fix 3: reasons/tradeoffs must be picked by actual point impact
    (fit * weight gained, (1 - fit) * weight lost), not by which scoring
    block happened to run first."""

    def test_tradeoff_picks_the_larger_actual_loss_distance_over_bedrooms(self):
        """A unit one bedroom short loses 18.9 pts (30 * (1 - 0.37)); a unit
        129 minutes from the requested Boulevard loses 22.5 pts
        (25 * (1 - 0.1)) — the bigger loss. Insertion order would have shown
        the bedroom shortfall first and hidden the distance entirely."""
        from match import poi as _poi
        blvd = (_poi.POIS["boulevard"][2], _poi.POIS["boulevard"][3])
        far = (blvd[0] + 2.0, blvd[1])   # comfortably past the far threshold
        answers = dict(BASE, party_size=4, sleep_pref="pairs", purpose="boulevard")
        u = unit(1, beds=1, capacity=6)   # needs 2 bedrooms, has 1 -> short by 1
        out = engine.score(answers, [u], geo={1: far})
        self.assertIn("بوليفارد", out["top"][0]["tradeoff"])
        self.assertNotIn("غرفة", out["top"][0]["tradeoff"])

    def test_reasons_are_ordered_by_actual_points_not_by_scoring_order(self):
        """A near-perfect proximity match (25 pts) must lead the reasons list
        ahead of a merely-adequate, heavily-over-provisioned bedroom fit
        (floored at 18 pts) even though bedrooms is scored first."""
        from match import poi as _poi
        blvd = (_poi.POIS["boulevard"][2], _poi.POIS["boulevard"][3])
        answers = dict(BASE, party_size=2, purpose="boulevard")   # needs 1 bedroom
        u = unit(1, beds=6, capacity=10)   # way over-provisioned -> floor fit
        out = engine.score(answers, [u], geo={1: (blvd[0] + 0.01, blvd[1])})
        self.assertIn("دقيقة", out["top"][0]["reasons"][0])

class TestBudgetContinuousDecay(unittest.TestCase):
    """Fix 4: past the 25%-over tier, budget fit must decay continuously
    instead of a flat 0.15 — otherwise a unit 26% over budget and one 1000%
    over score identically, losing ranking resolution among over-budget
    units even though the tradeoff text already states the real gap."""

    def test_over_budget_units_stay_distinguishable_past_the_flat_tier(self):
        answers = dict(BASE, budget_max=500)
        slightly_over = unit(1, est_avg=700)    # 40% over
        way_over = unit(2, est_avg=5500)        # 1000% over
        out = engine.score(answers, [slightly_over, way_over])
        self.assertEqual(out["top"][0]["id"], 1)
        self.assertGreater(out["top"][0]["match_score"], out["top"][1]["match_score"])

    def test_decay_never_reaches_zero(self):
        fit, reason, tradeoff = engine._score_budget(
            {"est_avg": 100000}, {"budget_max": 100})
        self.assertGreater(fit, 0.0)

    def test_decay_is_continuous_at_the_25_percent_boundary(self):
        just_under, _, _ = engine._score_budget({"est_avg": 624}, {"budget_max": 500})  # 24.8% over
        just_over, _, _ = engine._score_budget({"est_avg": 626}, {"budget_max": 500})   # 25.2% over
        self.assertLess(abs(just_under - just_over), 0.05)


class TestConfidenceReachable(unittest.TestCase):
    def test_weights_sum_to_one_hundred(self):
        self.assertEqual(sum(engine.WEIGHTS.values()), 100)

    def test_a_strong_match_clears_the_confidence_floor(self):
        """Regression guard: CONFIDENCE_FLOOR assumes every weight is wired.
        If a future change unwires one, the honest-fallback copy would fire for
        every guest, including perfect matches."""
        from match import poi as _poi
        blvd = (_poi.POIS["boulevard"][2], _poi.POIS["boulevard"][3])
        answers = dict(BASE, party_size=4, sleep_pref="pairs",
                       purpose="boulevard", budget_max=1000)
        u = unit(1, beds=2, capacity=6, rating=4.9, reviews=80,
                 amenities=["Wifi", "Free parking"], est_avg=800)
        out = engine.score(answers, [u], geo={1: (blvd[0] + 0.005, blvd[1])})
        self.assertTrue(out["confident"],
                        f"score {out['top'][0]['match_score']} < {engine.CONFIDENCE_FLOOR}")


if __name__ == "__main__":
    unittest.main()
