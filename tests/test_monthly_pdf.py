# -*- coding: utf-8 -*-
"""
S13 — the owner PDF. Renders here, on Python 3.9, which is the whole reason it
is a separate renderer from the frozen 3.12+ one: a broken PDF is found on this
machine rather than in an owner's inbox.

Run: python3 -m unittest tests.test_monthly_pdf
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monthly import engine, quote_render                # noqa: E402


def payload(**over):
    own = [{"adr": 620, "occ": 0.86, "months_old": 10, "nights": 26}]
    p = engine.price_unit(
        461328, "2026-10", own=own,
        district=[{"adr": 590, "occ": 0.83, "months_old": 10, "nights": 120}],
        attr_values=over.pop("attrs", {"design": 8, "majlis": True}),
        ejar_row=over.pop("ejar", None), today="2026-08-19")
    p["name"] = "Ouja | C2 NFL"
    p["district"] = "الملقا"
    p["bedrooms"] = 3
    p.update(over)
    return p


class FrozenRendererUntouchedTest(unittest.TestCase):
    def test_we_never_import_the_frozen_renderer(self):
        """Parsed, not grepped — for the second time. A text search matched this
        module's own docstring explaining that it does NOT use ouja_render."""
        import ast, inspect
        names = set()
        for node in ast.walk(ast.parse(inspect.getsource(quote_render))):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for a in node.names:
                    names.add(a.name.split(".")[-1])
                if isinstance(node, ast.ImportFrom) and node.module:
                    names.add(node.module.split(".")[-1])
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)
        self.assertNotIn("ouja_render", names)
        self.assertNotIn("render_report", names)

    def test_we_do_reuse_its_layout_gate_unchanged(self):
        import ast, inspect
        mods = set()
        for node in ast.walk(ast.parse(inspect.getsource(quote_render))):
            if isinstance(node, ast.ImportFrom) and node.module:
                mods.add(node.module)
        self.assertIn("audit_layout", mods)


class HtmlContractTest(unittest.TestCase):
    def test_four_pages_with_a_footer_each_and_a_cover(self):
        h = quote_render.build_html(payload())
        self.assertEqual(h.count('class="page'), 4)
        self.assertEqual(h.count('class="rf"'), 4)
        # class="page cover", not a bare "cover" — the CSS defines .cover and
        # .cover .rf, so the loose count was 3 and never meant what it said.
        self.assertEqual(h.count('class="page cover"'), 1)

    def test_the_word_is_estimate_not_price(self):
        h = quote_render.build_html(payload())
        self.assertIn("تقدير", h)
        self.assertIn("هذا تقدير، لا عرض سعر", h)

    def test_it_states_vat_is_excluded(self):
        self.assertIn("ضريبة القيمة المضافة", quote_render.build_html(payload()))

    def test_it_states_the_basis_of_the_number(self):
        h = quote_render.build_html(payload())
        self.assertIn("محسوب من حجوزات هذه الوحدة نفسها", h)

    def test_a_pool_priced_unit_says_so_in_the_pdf_too(self):
        p = engine.price_unit(1, "2026-10", own=[],
                              district=[{"adr": 500, "occ": 0.8, "months_old": 1}],
                              attr_values={})
        p["name"] = "x"
        self.assertIn("لا من سجل هذه الوحدة", quote_render.build_html(p))

    def test_an_unscored_unit_disowns_its_own_model_gate(self):
        p = payload(attrs={})
        self.assertIn("غير مفعّلة", quote_render.build_html(p))

    def test_a_scored_unit_does_not_carry_that_warning(self):
        self.assertNotIn("غير مفعّلة", quote_render.build_html(payload()))

    def test_fonts_are_embedded_not_linked(self):
        h = quote_render.build_html(payload())
        self.assertIn("data:font/woff2;base64,", h)
        self.assertNotIn("fonts.googleapis.com", h)

    def test_no_external_request_of_any_kind(self):
        h = quote_render.build_html(payload())
        for bad in ("http://", "https://"):
            self.assertNotIn(bad, h)

    def test_a_long_label_is_ellipsised_not_guillotined(self):
        self.assertTrue(quote_render._clip("a" * 80, 20).endswith("…"))
        self.assertEqual(quote_render._clip("short", 20), "short")


class RenderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ouja_pdf_test_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_it_renders_four_pages_and_passes_the_layout_gate(self):
        out = os.path.join(self.tmp, "q.pdf")
        pdf, html, violations = quote_render.render(payload(), out,
                                                    {"turnover_note": "140 ريال"})
        self.assertEqual(violations, [], "layout violations: %s" % violations)
        self.assertTrue(os.path.getsize(pdf) > 20000)
        self.assertTrue(os.path.exists(html), "the audited HTML must sit beside the PDF")
        try:
            import fitz
        except ImportError:
            return
        self.assertEqual(fitz.open(pdf).page_count, 4)

    def test_the_waterfall_in_the_pdf_sums_to_the_price_on_the_cover(self):
        """The document's whole claim is that the numbers add up."""
        p = payload()
        self.assertAlmostEqual(sum(c["sar"] for c in p["components"]), p["price"])


if __name__ == "__main__":
    unittest.main()


class CoverCannotContradictTheFileTest(unittest.TestCase):
    """The cover claimed «بمواصفاتها» while page 4 said «0 من 16» three pages
    later. That is the sentence an owner quotes back at you. Same discipline as
    the verdict/trust fix: one source, and a test that they cannot disagree."""

    import re as _re

    def _cover(self, p):
        import re
        m = re.search(r'<div class="c-bound">(.*?)</div>',
                      quote_render.build_html(p), re.S)
        return m.group(1)

    def _unscored(self):
        p = engine.price_unit(1, "2026-08", own=[],
                              district=[{"adr": 779.2, "occ": 0.516,
                                         "months_old": 1, "nights": 30}],
                              attr_values={})
        p["name"] = "MLQ 11"
        return p

    def test_an_unscored_unit_never_claims_its_specs_earned_the_number(self):
        p = self._unscored()
        self.assertEqual(p["bound_by"], "model")
        self.assertFalse(quote_render._measured(p))
        self.assertNotIn("بمواصفاتها", self._cover(p))
        self.assertIn("لم تُسجَّل بعد", self._cover(p))

    def test_a_scored_unit_may_claim_them(self):
        p = engine.price_unit(1, "2026-08", own=[],
                              district=[{"adr": 779.2, "occ": 0.516,
                                         "months_old": 1, "nights": 30}],
                              attr_values={"design": 8, "majlis": True})
        p["name"] = "x"
        self.assertTrue(quote_render._measured(p))
        self.assertIn("بمواصفاتها", self._cover(p))

    def test_the_cover_and_the_gate_share_one_definition(self):
        """If _measured ever disagrees with what page 2 draws, both move."""
        for attrs_v in ({}, {"design": 8}, {"design": 5}):
            p = engine.price_unit(1, "2026-08", own=[],
                                  district=[{"adr": 700, "occ": 0.6,
                                             "months_old": 1, "nights": 30}],
                                  attr_values=attrs_v)
            p["name"] = "x"
            html = quote_render.build_html(p)
            claims = "بمواصفاتها" in self._cover(p)
            gate_dead = "غير مفعّلة" in html
            self.assertNotEqual(claims, gate_dead,
                                "cover and gate disagree for %s" % attrs_v)

    def test_no_waterfall_step_says_specs_when_none_were_scored(self):
        p = self._unscored()
        for c in p["components"]:
            if abs((p.get("quality") or {}).get("mult", 1.0) - 1.0) < 1e-9:
                self.assertNotIn("مواصفات", c["label_ar"],
                                 "a waterfall step claims quality with none scored")

    def test_the_gross_row_states_its_occupancy(self):
        """Page 3's «30 nights» and page 2's ceiling both said '30 nights' and
        meant different things — which invited comparing them."""
        p = self._unscored()
        row = [c for c in p["components"] if c["key"] == "nightly_gross"][0]
        self.assertIn("إشغال", row["label_ar"])
        self.assertIn("52%", row["label_ar"])


class ZeroNightsOnTheCoverTest(unittest.TestCase):
    def test_a_unit_with_no_observed_nights_says_so_on_page_one(self):
        p = engine.price_unit(1, "2026-08", own=[],
                              district=[{"adr": 700, "occ": 0.6,
                                         "months_old": 1, "nights": 30}],
                              attr_values={})
        p["name"] = "x"
        self.assertIn("ولا ليلة مرصودة", quote_render.build_html(p))

    def test_a_unit_with_history_does_not_carry_that_line(self):
        p = engine.price_unit(1, "2026-08",
                              own=[{"adr": 700, "occ": 0.6, "months_old": 1,
                                    "nights": 26}],
                              district=[{"adr": 700, "occ": 0.6, "months_old": 1}],
                              attr_values={})
        p["name"] = "x"
        self.assertNotIn("ولا ليلة مرصودة", quote_render.build_html(p))


class DraftWatermarkTest(unittest.TestCase):
    def _p(self):
        p = engine.price_unit(1, "2026-08",
                              own=[{"adr": 700, "occ": 0.6, "months_old": 1,
                                    "nights": 26}],
                              district=[{"adr": 700, "occ": 0.6, "months_old": 1}],
                              attr_values={})
        p["name"] = "x"
        return p

    def test_a_placeholder_cleaning_cost_stamps_every_page(self):
        h = quote_render.build_html(self._p(), {"draft": True})
        self.assertEqual(h.count('class="wm"'), 4)

    def test_the_watermark_sits_inside_the_page_not_after_it(self):
        h = quote_render.build_html(self._p(), {"draft": True})
        self.assertIn('<div class="page cover"><div class="wm">', h)

    def test_it_disappears_by_itself_once_a_real_cost_is_set(self):
        self.assertNotIn('class="wm"', quote_render.build_html(self._p(), {}))

    def test_a_draft_still_passes_the_layout_gate(self):
        """A full-bleed overlay would fail the very gate it sits behind."""
        self.assertEqual(quote_render.audit(
            quote_render.build_html(self._p(), {"draft": True})), [])


class ChartLabelsFitTest(unittest.TestCase):
    def test_every_short_label_fits_without_an_ellipsis(self):
        for key, lbl in quote_render._SHORT_AR.items():
            self.assertLessEqual(len(lbl), quote_render.CHART_LABEL_MAX,
                                 "%s is too long for the chart column" % key)

    def test_every_component_key_the_engine_emits_has_a_short_form(self):
        seen = set()
        for attrs_v in ({}, {"design": 9, "sqm": 300}):
            for occ in (0.2, 0.6, 0.95):
                p = engine.price_unit(1, "2026-08",
                                      own=[{"adr": 700, "occ": occ,
                                            "months_old": 1, "nights": 30}],
                                      district=[{"adr": 700, "occ": occ,
                                                 "months_old": 1}],
                                      attr_values=attrs_v)
                for c in (p.get("components") or []):
                    seen.add(c["key"])
        missing = [k for k in seen
                   if k != "nightly_gross" and k not in quote_render._SHORT_AR]
        self.assertEqual(missing, [], "no short chart label for: %s" % missing)

    def test_no_label_in_a_rendered_chart_is_ellipsised(self):
        p = engine.price_unit(1, "2026-08",
                              own=[{"adr": 700, "occ": 0.6, "months_old": 1,
                                    "nights": 26}],
                              district=[{"adr": 700, "occ": 0.6, "months_old": 1}],
                              attr_values={"design": 9})
        p["name"] = "x"
        self.assertNotIn("…", quote_render._svg_waterfall(p))
