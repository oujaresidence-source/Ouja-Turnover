# -*- coding: utf-8 -*-
"""Open Location Code decoder, checked against the published reference values.

If these fail, apartments get pinned to the wrong place on the coverage map — worse
than leaving them blank, because a wrong pin looks like knowledge.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from coverage_study import pluscode as P

RIYADH = (24.7136, 46.6753)


class TestDecodeFull(unittest.TestCase):
    """Reference values from the Open Location Code spec's own test data."""

    def test_spec_example_8fvc2222(self):
        lat, lng = P.decode("8FVC2222+22")
        self.assertAlmostEqual(lat, 47.0000625, places=5)
        self.assertAlmostEqual(lng, 8.0000625, places=5)

    def test_spec_example_8fvc(self):
        lat, lng = P.decode("8FVC0000+")
        self.assertAlmostEqual(lat, 47.5, places=4)
        self.assertAlmostEqual(lng, 8.5, places=4)

    def test_spec_example_zero_zero(self):
        lat, lng = P.decode("6FG22222+22")
        self.assertTrue(-1 < lat < 1, lat)
        self.assertTrue(-1 < lng < 1, lng)

    def test_rubbish_returns_none(self):
        self.assertIsNone(P.decode("not-a-code"))
        self.assertIsNone(P.decode(""))
        self.assertIsNone(P.decode("AAAA+AA"))      # A is not in the alphabet


class TestEncodeRoundTrip(unittest.TestCase):
    def test_encode_then_decode_lands_back(self):
        for lat, lng in ((24.7136, 46.6753), (24.8289, 46.7362), (-33.857, 151.215)):
            code = P.encode(lat, lng)
            got = P.decode(code)
            self.assertAlmostEqual(got[0], lat, places=2)
            self.assertAlmostEqual(got[1], lng, places=2)

    def test_encode_has_the_separator_in_the_right_place(self):
        self.assertEqual(P.encode(24.7136, 46.6753).index("+"), 8)


class TestShortCodeRecovery(unittest.TestCase):
    """The form actually present in Ouja's Hostaway addresses: 'QJVM+4MM'."""

    def test_recovered_code_is_near_the_reference(self):
        got = P.recover("QJVM+4MM", RIYADH[0], RIYADH[1])
        self.assertIsNotNone(got)
        self.assertTrue(24.0 < got[0] < 25.5, got)     # inside greater Riyadh
        self.assertTrue(46.0 < got[1] < 47.5, got)

    def test_matches_decoding_the_equivalent_full_code(self):
        full = P.encode(24.7136, 46.6753)
        short = full[4:]                                # drop 4 leading chars
        a = P.recover(short, RIYADH[0], RIYADH[1])
        b = P.decode(full)
        self.assertAlmostEqual(a[0], b[0], places=4)
        self.assertAlmostEqual(a[1], b[1], places=4)

    def test_full_code_passes_straight_through(self):
        self.assertEqual(P.recover("8FVC2222+22", 47.0, 8.0), P.decode("8FVC2222+22"))

    def test_missing_separator_refuses(self):
        self.assertIsNone(P.recover("QJVM4MM", RIYADH[0], RIYADH[1]))


class TestFindInAddress(unittest.TestCase):
    """Real address strings copied off the owner's live dashboard."""

    def test_finds_the_code_in_a_real_address(self):
        self.assertEqual(P.find_in("QJVM+4MM, King Fahd Rd, As Sahafah, Riyadh 133"),
                         "QJVM+4MM")
        self.assertEqual(P.find_in("QMCR+7V3, At Taawun, Riyadh 12475"), "QMCR+7V3")
        self.assertEqual(P.find_in("QJF5+GHV Hittin, Riyadh"), "QJF5+GHV")

    def test_saudi_short_address_is_not_mistaken_for_a_plus_code(self):
        # RRHC3169 / RHGA7576 are Saudi national addresses — no '+' and NOT decodable.
        self.assertIsNone(P.find_in("RRHC3169, 3169 Prince Faisal Ibn Abdulrahman"))
        self.assertIsNone(P.find_in("RHGA7576, 7576 Tamir"))

    def test_no_code_returns_none(self):
        self.assertIsNone(P.find_in("Al Malqa, Riyadh"))
        self.assertIsNone(P.find_in(""))

    def test_from_address_end_to_end(self):
        got = P.from_address("QJF5+GHV Hittin, Riyadh", RIYADH[0], RIYADH[1])
        self.assertIsNotNone(got)
        self.assertTrue(24.0 < got[0] < 25.5 and 46.0 < got[1] < 47.5, got)


if __name__ == "__main__":
    unittest.main()
