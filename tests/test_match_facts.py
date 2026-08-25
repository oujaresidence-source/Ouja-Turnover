"""match/facts.py — the owner-declared apartment facts list. Pure, no I/O."""
import unittest

from match import facts


class TestKeysAndLabels(unittest.TestCase):
    def test_keys_returns_every_fact_key(self):
        ks = facts.keys()
        self.assertEqual(len(ks), len(facts.FACTS))
        self.assertIn("parking", ks)
        self.assertIn("view", ks)

    def test_label_ar_known_key(self):
        self.assertEqual(facts.label_ar("parking"), "موقف خاص")

    def test_label_ar_unknown_key_is_none(self):
        self.assertIsNone(facts.label_ar("not_a_real_fact"))

    def test_label_en_known_key(self):
        self.assertEqual(facts.label_en("parking"), "Private parking")

    def test_label_en_unknown_key_is_none(self):
        self.assertIsNone(facts.label_en("not_a_real_fact"))

    def test_by_group_covers_every_fact_exactly_once(self):
        grouped = facts.by_group()
        seen = []
        for gkey, gar, rows in grouped:
            for k, ar, en in rows:
                seen.append(k)
        self.assertEqual(sorted(seen), sorted(facts.keys()))
        self.assertEqual(len(seen), len(set(seen)))   # no duplicates

    def test_by_group_matches_declared_groups(self):
        grouped = facts.by_group()
        self.assertEqual([g[0] for g in grouped], [g[0] for g in facts.GROUPS])


class TestNormalize(unittest.TestCase):
    def test_drops_unknown_keys(self):
        out = facts.normalize({"parking": True, "not_a_real_fact": True})
        self.assertEqual(out, {"parking": True})

    def test_rejects_non_boolean_values(self):
        out = facts.normalize({"parking": 1, "elevator": "true", "pool": None,
                                "washer": [], "view": {}})
        self.assertEqual(out, {})

    def test_preserves_true_and_false(self):
        out = facts.normalize({"parking": True, "elevator": False})
        self.assertEqual(out, {"parking": True, "elevator": False})

    def test_missing_key_stays_missing(self):
        out = facts.normalize({"parking": True})
        self.assertNotIn("elevator", out)

    def test_non_dict_input_returns_empty(self):
        for bad in (None, [], "junk", 5, ("a", "b")):
            self.assertEqual(facts.normalize(bad), {})

    def test_empty_dict_returns_empty(self):
        self.assertEqual(facts.normalize({}), {})

    def test_int_true_false_are_rejected_despite_bool_subclassing(self):
        """`isinstance(1, bool)` is False in Python — 1/0 must NOT be laundered
        into True/False. Only an actual bool counts as an answer."""
        out = facts.normalize({"parking": 1, "elevator": 0})
        self.assertEqual(out, {})


if __name__ == "__main__":
    unittest.main()
