# -*- coding: utf-8 -*-
"""Wraps digest/render/test_render_frozen.py into the suite. Skips when Chromium cannot
launch or when no golden exists yet (before the owner has approved the look); once the
golden is committed this is the lock — a failure here means the design changed."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from digest.render import build, test_render_frozen as frozen


class Compare(unittest.TestCase):
    """The comparison logic itself, exercised without a browser."""

    def _fp(self, layout="L", texts=("a", "b"), pixels=("p1", "p2")):
        return {"page_count": len(texts), "layout_md5": layout,
                "pages": [{"n": i + 1, "text_md5": t, "pixel_md5": p, "_png": b""} for i, (t, p) in enumerate(zip(texts, pixels))]}

    def test_identical_passes(self):
        g = self._fp()
        self.assertEqual(frozen.compare(self._fp(), g), [])

    def test_layout_change_fails(self):
        self.assertTrue(any("LAYOUT" in f for f in frozen.compare(self._fp(layout="X"), self._fp())))

    def test_text_change_fails(self):
        self.assertTrue(any("text" in f for f in frozen.compare(self._fp(texts=("a", "c")), self._fp())))

    def test_page_count_change_fails(self):
        self.assertTrue(frozen.compare(self._fp(texts=("a",), pixels=("p1",)), self._fp()))

    def test_pixel_change_without_golden_png_fails(self):
        import tempfile, pathlib
        with tempfile.TemporaryDirectory() as d:
            fails = frozen.compare(self._fp(pixels=("z1", "p2")), self._fp(), golden_dir=pathlib.Path(d))
        self.assertTrue(any("VISUAL" in f for f in fails))

    def test_pixel_tolerance(self):
        from PIL import Image
        import io
        def png(v):
            im = Image.new("RGB", (4, 4), (v, v, v)); b = io.BytesIO(); im.save(b, "PNG"); return b.getvalue()
        self.assertLessEqual(frozen.mean_delta(png(100), png(102)), 3.0)
        self.assertGreater(frozen.mean_delta(png(100), png(120)), 3.0)


@unittest.skipUnless(build.chromium_available(), "Chromium not available")
@unittest.skipUnless(frozen.GOLDEN_JSON.exists(), "no golden yet — written after the owner approves the look")
class Frozen(unittest.TestCase):
    def test_reference_render_matches_the_golden(self):
        self.assertEqual(frozen.main([]), 0)


if __name__ == "__main__":
    unittest.main()
