# -*- coding: utf-8 -*-
import unittest

from owner_report.validate import (
    validate, validate_field_limits, W_EJAR_SINGLE, W_EJAR_UNFURNISHED,
    W_COMP_STALE, W_ADR_BAND,
)
from owner_report.errors import ValidationError
from owner_report.tests.fixtures import valid_cfg, valid_meta


class TestCleanPasses(unittest.TestCase):
    def test_reference_unit_passes_every_gate(self):
        res = validate(valid_cfg(), valid_meta())
        self.assertTrue(res.ok, msg=f"unexpected hard gates: {res.hard}")
        self.assertEqual(res.soft, [])

    def test_golden_counts_are_allowed(self):
        # 9 FACTORS + 6 RISKS (the approved golden) must NOT trip field limits.
        self.assertEqual(validate_field_limits(valid_cfg()), [])


class TestHardGates(unittest.TestCase):
    def _hard(self, cfg=None, **meta_over):
        m = valid_meta(); m.update(meta_over)
        return validate(cfg or valid_cfg(), m).hard

    def test_occupancy_over_100_blocks(self):
        cfg = valid_cfg()
        cfg["MONTHS"][0] = ("يناير", "Jan", 31, 40, 15_840)  # booked > available
        self.assertTrue(any("nights_booked" in h for h in self._hard(cfg)))

    def test_revenue_reconciliation_to_the_riyal(self):
        self.assertTrue(any("reconcile" in h for h in self._hard(reservation_revenue_total=95_286)))

    def test_missing_reservation_total_blocks(self):
        m = valid_meta(); m.pop("reservation_revenue_total")
        self.assertTrue(any("reconciliation cannot run" in h for h in validate(valid_cfg(), m).hard))

    def test_cancelled_in_revenue_blocks(self):
        self.assertTrue(any("cancelled" in h for h in self._hard(cancelled_in_revenue=2)))

    def test_vat_unresolved_blocks(self):
        self.assertTrue(any("VAT" in h for h in self._hard(vat_resolved=False)))

    def test_unsigned_reconciliation_blocks(self):
        self.assertTrue(any("unsigned reconciliation" in h for h in self._hard(reconciliation_signed=False)))

    def test_missing_purchase_price_blocks_when_lease_enabled(self):
        cfg = valid_cfg(); cfg["ASSET"]["purchase_price"] = 0
        self.assertTrue(any("purchase_price" in h for h in self._hard(cfg)))

    def test_missing_ejar_blocks_when_lease_enabled(self):
        cfg = valid_cfg(); cfg["EJAR"]["annual_rent"] = 0
        self.assertTrue(any("annual_rent" in h for h in self._hard(cfg)))

    def test_unconfirmed_fields_block(self):
        self.assertTrue(any("re-confirmed" in h for h in self._hard(required_fields_confirmed=False)))

    def test_raise_if_blocked(self):
        m = valid_meta(); m["vat_resolved"] = False
        with self.assertRaises(ValidationError):
            validate(valid_cfg(), m).raise_if_blocked()


class TestFieldLimits(unittest.TestCase):
    def test_long_name_blocks(self):
        cfg = valid_cfg()
        cfg["UNIT"]["listing_name_en"] = "Ouja | " + "X" * 40
        self.assertTrue(any("listing_name_en" in v for v in validate_field_limits(cfg)))

    def test_comp_set_must_be_five(self):
        cfg = valid_cfg(); cfg["COMP_SET"] = cfg["COMP_SET"][:4]
        self.assertTrue(any("COMP_SET" in v for v in validate_field_limits(cfg)))

    def test_months_must_be_6_or_12(self):
        cfg = valid_cfg(); cfg["MONTHS"] = cfg["MONTHS"][:5]
        self.assertTrue(any("MONTHS" in v for v in validate_field_limits(cfg)))

    def test_opex_max_three(self):
        cfg = valid_cfg(); cfg["COSTS"]["opex"] = cfg["COSTS"]["opex"] + [("x", "x", 10)]
        self.assertTrue(any("opex" in v for v in validate_field_limits(cfg)))

    def test_sar_column_width(self):
        cfg = valid_cfg(); cfg["ASSET"]["purchase_price"] = 12_000_000
        self.assertTrue(any("column width" in v for v in validate_field_limits(cfg)))

    def test_note_length(self):
        cfg = valid_cfg(); cfg["MARKET_YIELD"]["note_en"] = "x" * 300
        self.assertTrue(any("note is" in v for v in validate_field_limits(cfg)))

    def test_ten_factors_blocks(self):
        cfg = valid_cfg(); cfg["FACTORS"] = cfg["FACTORS"] + [("up", "ي", "Tenth", "x", "y")]
        self.assertTrue(any("FACTORS" in v for v in validate_field_limits(cfg)))


class TestSoftWarnings(unittest.TestCase):
    def test_single_contract_warning_must_be_acknowledged_and_disclosed(self):
        m = valid_meta(); m["ejar_is_single_contract"] = True
        res = validate(valid_cfg(), m)
        self.assertIn(W_EJAR_SINGLE, [c for c, _ in res.soft])
        # unacknowledged -> promoted to hard
        self.assertTrue(any(W_EJAR_SINGLE in h for h in res.hard))
        # acknowledged but not disclosed -> still hard
        m["acknowledged"] = [W_EJAR_SINGLE]
        self.assertTrue(any("no disclosure line" in h for h in validate(valid_cfg(), m).hard))
        # acknowledged AND disclosed -> clean
        m["disclosures"] = [W_EJAR_SINGLE]
        self.assertTrue(validate(valid_cfg(), m).ok)

    def test_unfurnished_no_uplift_warning(self):
        m = valid_meta(); m["ejar_unfurnished_no_uplift"] = True
        m["acknowledged"] = [W_EJAR_UNFURNISHED]; m["disclosures"] = [W_EJAR_UNFURNISHED]
        res = validate(valid_cfg(), m)
        self.assertIn(W_EJAR_UNFURNISHED, [c for c, _ in res.soft])
        self.assertTrue(res.ok)

    def test_comp_stale_warning(self):
        m = valid_meta(); m["comp_stale"] = True
        m["acknowledged"] = [W_COMP_STALE]; m["disclosures"] = [W_COMP_STALE]
        self.assertIn(W_COMP_STALE, [c for c, _ in validate(valid_cfg(), m).soft])

    def test_adr_out_of_band_warns(self):
        cfg = valid_cfg()
        # crush revenue so ADR < 100
        cfg["MONTHS"] = [(a, b, na, nb, 100) for (a, b, na, nb, g) in cfg["MONTHS"]]
        m = valid_meta(); m["reservation_revenue_total"] = 600
        m["acknowledged"] = [W_ADR_BAND]; m["disclosures"] = [W_ADR_BAND]
        self.assertIn(W_ADR_BAND, [c for c, _ in validate(cfg, m).soft])


if __name__ == "__main__":
    unittest.main()
