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
