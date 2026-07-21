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


class TestTopAndNearSplit(unittest.TestCase):
    def test_top_capped_at_three_rest_goes_to_near(self):
        out = engine.score(BASE, [unit(i) for i in range(1, 8)])
        self.assertEqual(len(out["top"]), 3)
        self.assertEqual(len(out["near"]), 4)

    def test_scores_are_descending_across_top_then_near(self):
        out = engine.score(BASE, [unit(i, beds=i) for i in range(1, 7)])
        scores = [u["match_score"] for u in out["top"] + out["near"]]
        self.assertEqual(scores, sorted(scores, reverse=True))


if __name__ == "__main__":
    unittest.main()
