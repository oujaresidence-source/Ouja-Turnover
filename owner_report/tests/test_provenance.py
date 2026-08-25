# -*- coding: utf-8 -*-
import unittest

from owner_report.provenance import (
    Fig,
    ProvenanceError,
    assert_fully_tagged,
    manifest,
    tag_counts,
    unwrap,
)


class TestFig(unittest.TestCase):
    def test_valid_tags(self):
        for t in ("H", "O", "M", "C"):
            self.assertEqual(Fig(1, t).tag, t)

    def test_bad_tag_raises(self):
        with self.assertRaises(ProvenanceError):
            Fig(1, "X")

    def test_bool_is_not_a_figure(self):
        # a bool must never be wrapped as a figure (delivered_furnished etc. are flags)
        with self.assertRaises(ProvenanceError):
            Fig(True, "O")

    def test_string_is_not_a_figure(self):
        with self.assertRaises(ProvenanceError):
            Fig("85000", "O")

    def test_is_estimate(self):
        self.assertTrue(Fig(640, "M").is_estimate)
        self.assertFalse(Fig(640, "H").is_estimate)


class TestTaggingEnforcement(unittest.TestCase):
    def test_fully_tagged_model_passes(self):
        model = {
            "ASSET": {"purchase_price": Fig(1_300_000, "O")},
            "MONTHS": [("Jan", Fig(31, "H"), Fig(24, "H"), Fig(15_840, "H"))],
            "UNIT": {"name": "Ouja | X", "furnished": True, "beds": Fig(2, "O")},
        }
        assert_fully_tagged(model)  # must not raise

    def test_raw_number_is_a_build_failure(self):
        model = {"ASSET": {"purchase_price": 1_300_000}}  # untagged!
        with self.assertRaises(ProvenanceError) as ctx:
            assert_fully_tagged(model)
        self.assertIn("ASSET.purchase_price", str(ctx.exception))

    def test_raw_number_inside_tuple_is_caught(self):
        model = {"MONTHS": [("Jan", Fig(31, "H"), 24, Fig(15_840, "H"))]}
        with self.assertRaises(ProvenanceError):
            assert_fully_tagged(model)

    def test_bool_flag_does_not_trip_enforcement(self):
        model = {"FURNISHING": {"delivered_furnished": True, "owner_funded": False}}
        assert_fully_tagged(model)  # bools are structural, not figures


class TestUnwrapAndManifest(unittest.TestCase):
    def setUp(self):
        self.model = {
            "ASSET": {"purchase_price": Fig(1_300_000, "O", "owner acquisition cost")},
            "COMP_SET": [("Comp A", Fig(640, "M"), Fig(0.68, "M"))],
            "MONTHS": [("Jan", Fig(31, "H"), Fig(24, "H"), Fig(15_840, "H"))],
        }

    def test_unwrap_produces_plain_values(self):
        cfg = unwrap(self.model)
        self.assertEqual(cfg["ASSET"]["purchase_price"], 1_300_000)
        self.assertEqual(cfg["COMP_SET"][0], ("Comp A", 640, 0.68))
        self.assertIsInstance(cfg["COMP_SET"][0], tuple)

    def test_manifest_lists_every_figure_with_path(self):
        m = manifest(self.model)
        paths = {e.path: e.tag for e in m}
        self.assertEqual(paths["ASSET.purchase_price"], "O")
        self.assertEqual(paths["COMP_SET[0][1]"], "M")
        self.assertEqual(paths["MONTHS[0][3]"], "H")

    def test_tag_counts(self):
        c = tag_counts(self.model)
        self.assertEqual(c["O"], 1)
        self.assertEqual(c["M"], 2)
        self.assertEqual(c["H"], 3)
        self.assertEqual(c["C"], 0)


if __name__ == "__main__":
    unittest.main()
