# -*- coding: utf-8 -*-
import unittest

from owner_report.model import build_cfg, build_model, VAT_RATE
from owner_report.provenance import assert_fully_tagged, tag_counts
from owner_report.validate import (
    validate, W_EJAR_SINGLE, W_EJAR_UNFURNISHED,
)
from owner_report.tests.fixtures import valid_inp, valid_meta, valid_cfg


class TestReferenceParity(unittest.TestCase):
    def test_build_cfg_reproduces_reference_numbers(self):
        cfg, man, disc = build_cfg(valid_inp())
        ref = valid_cfg()
        self.assertEqual(cfg["MONTHS"], ref["MONTHS"])
        self.assertEqual(cfg["ASSET"]["purchase_price"], 1_300_000)
        self.assertEqual(cfg["EJAR"]["annual_rent"], 85_000)
        self.assertEqual(cfg["COMP_SET"], ref["COMP_SET"])
        self.assertEqual(disc, [])

    def test_all_schema_keys_present(self):
        from owner_report.renderer_api import REPORT_SCHEMA_KEYS
        cfg, _, _ = build_cfg(valid_inp())
        for k in REPORT_SCHEMA_KEYS:
            self.assertIn(k, cfg)

    def test_every_figure_tagged(self):
        model = build_model(valid_inp())
        model.pop("_disclosures")
        assert_fully_tagged(model)  # no raw numbers
        c = tag_counts(model)
        for t in ("H", "O", "M", "C"):
            self.assertGreater(c[t], 0, f"no {t}-tagged figures")

    def test_cfg_passes_validation(self):
        cfg, man, disc = build_cfg(valid_inp())
        m = valid_meta()
        m["reservation_revenue_total"] = sum(x[4] for x in cfg["MONTHS"])
        m["acknowledged"] = list(disc); m["disclosures"] = list(disc)
        res = validate(cfg, m)
        self.assertTrue(res.ok, msg=res.hard)


class TestVAT(unittest.TestCase):
    def test_inclusive_basis_divides_out_vat(self):
        inp = valid_inp(); inp["vat_basis"] = "inclusive"
        cfg, _, _ = build_cfg(inp)
        # Jan raw 15840 incl VAT -> net = round(15840/1.15)
        self.assertEqual(cfg["MONTHS"][0][4], round(15_840 / (1 + VAT_RATE)))

    def test_net_basis_leaves_revenue_untouched(self):
        cfg, _, _ = build_cfg(valid_inp())
        self.assertEqual(cfg["MONTHS"][0][4], 15_840)


class TestOwnerBlockedNights(unittest.TestCase):
    def test_exclude_reduces_available(self):
        inp = valid_inp(); inp["blocked_by_month"] = [5, 0, 0, 0, 0, 0]
        inp["owner_blocked_treatment"] = "exclude"
        cfg, _, _ = build_cfg(inp)
        self.assertEqual(cfg["MONTHS"][0][2], 31 - 5)

    def test_vacant_keeps_available(self):
        inp = valid_inp(); inp["blocked_by_month"] = [5, 0, 0, 0, 0, 0]
        inp["owner_blocked_treatment"] = "vacant"
        cfg, _, _ = build_cfg(inp)
        self.assertEqual(cfg["MONTHS"][0][2], 31)


class TestFurnishedUplift(unittest.TestCase):
    def test_unfurnished_with_uplift_adjusts_rent_and_notes_it(self):
        inp = valid_inp()
        inp["ejar"]["comparable_furnished"] = False
        inp["ejar"]["furnished_uplift_pct"] = 0.20
        cfg, _, disc = build_cfg(inp)
        self.assertEqual(cfg["EJAR"]["annual_rent"], round(85_000 * 1.20))
        self.assertIn("uplift", cfg["EJAR"]["ref"].lower())
        self.assertNotIn(W_EJAR_UNFURNISHED, disc)

    def test_unfurnished_no_uplift_flags_and_caveats(self):
        inp = valid_inp()
        inp["ejar"]["comparable_furnished"] = False
        inp["ejar"]["furnished_uplift_pct"] = 0.0
        cfg, _, disc = build_cfg(inp)
        self.assertEqual(cfg["EJAR"]["annual_rent"], 85_000)  # unchanged
        self.assertIn(W_EJAR_UNFURNISHED, disc)
        self.assertIn("narrower", cfg["EJAR"]["ref"].lower())


class TestSingleContractBaseline(unittest.TestCase):
    def test_single_contract_labelled_baseline_not_benchmark(self):
        inp = valid_inp(); inp["ejar_is_single_contract"] = True
        cfg, _, disc = build_cfg(inp)
        self.assertIn(W_EJAR_SINGLE, disc)
        self.assertIn("baseline", cfg["EJAR"]["ref"].lower())
        self.assertIn("not a benchmark", cfg["EJAR"]["ref"].lower())


class TestFurnishing(unittest.TestCase):
    def test_delivered_furnished_zero_capex(self):
        cfg, _, _ = build_cfg(valid_inp())
        self.assertEqual(cfg["FURNISHING"]["capex"], 0)
        self.assertFalse(cfg["FURNISHING"]["owner_funded"])

    def test_owner_funded_retains_capex(self):
        inp = valid_inp()
        inp["furnishing"] = {"delivered_furnished": False, "capex": 90_000,
                             "amort_years": 5, "owner_funded": True}
        cfg, _, _ = build_cfg(inp)
        self.assertEqual(cfg["FURNISHING"]["capex"], 90_000)
        self.assertTrue(cfg["FURNISHING"]["owner_funded"])


class TestDisclosureWovenIntoSources(unittest.TestCase):
    def test_comp_stale_appended_to_a_printed_sources_row(self):
        inp = valid_inp(); inp["comp_stale"] = True
        cfg, _, disc = build_cfg(inp)
        from owner_report.validate import W_COMP_STALE
        self.assertIn(W_COMP_STALE, disc)
        self.assertTrue(any("90" in r[2] for r in cfg["SOURCES"]))


if __name__ == "__main__":
    unittest.main()
