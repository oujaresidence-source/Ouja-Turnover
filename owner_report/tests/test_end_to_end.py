# -*- coding: utf-8 -*-
"""End-to-end: operator inputs -> model -> validate -> render -> layout audit.

Renderer-dependent (Playwright + Python 3.12+). Skips cleanly where the renderer can't
be imported, so the pure-logic suite still runs on older interpreters.
"""
import pathlib
import tempfile
import unittest

from owner_report.model import build_cfg
from owner_report.validate import validate
from owner_report.tests.fixtures import valid_inp, valid_meta

try:
    from owner_report import renderer_api
    # goes through the shim, which puts the renderer dir on sys.path and imports it
    # (also fails fast on <3.12 where the renderer's f-string syntax won't parse)
    _CAN_RENDER = renderer_api.verify_schema_matches()
except Exception:  # pragma: no cover - environment-dependent
    _CAN_RENDER = False


class TestSchemaSync(unittest.TestCase):
    @unittest.skipUnless(_CAN_RENDER, "renderer not importable on this interpreter")
    def test_shim_schema_matches_frozen_renderer(self):
        self.assertTrue(renderer_api.verify_schema_matches())


@unittest.skipUnless(_CAN_RENDER, "renderer not importable on this interpreter")
class TestFullRender(unittest.TestCase):
    def test_pipeline_renders_17_clean_pages(self):
        cfg, man, disc = build_cfg(valid_inp())
        meta = valid_meta()
        meta["reservation_revenue_total"] = sum(m[4] for m in cfg["MONTHS"])
        meta["acknowledged"] = list(disc)
        meta["disclosures"] = list(disc)
        validate(cfg, meta).raise_if_blocked()

        with tempfile.TemporaryDirectory() as tmp:
            pdf = renderer_api.render(cfg, pathlib.Path(tmp) / "e2e.pdf")
            self.assertTrue(pdf.exists())
            import fitz
            self.assertEqual(fitz.open(pdf).page_count, 17)
            html = renderer_api.html_for(pdf)
            renderer_api.assert_layout_clean(html)  # spec §4 hard gate

    def test_provenance_manifest_covers_all_tags(self):
        _, man, _ = build_cfg(valid_inp())
        tags = {e.tag for e in man}
        self.assertEqual(tags, {"H", "O", "M", "C"})


if __name__ == "__main__":
    unittest.main()
