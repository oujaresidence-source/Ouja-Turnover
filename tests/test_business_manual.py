# -*- coding: utf-8 -*-
"""
Tests for business.manual — the "what Hostaway can't know" loader.

Rule from superprompt §3: every entry requires value, as_of, source.
No as_of, no render. Fail loud in dev (strict), silent in prod.

Run:  python3 -m unittest tests.test_business_manual
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from business.manual import load_manual_metrics, ManualMetricError  # noqa: E402


class LoaderRules(unittest.TestCase):
    def test_valid_entry_passes_through(self):
        data = {"followers": {"value": "70,000+", "as_of": "2026-07-23", "source": "internal"}}
        out = load_manual_metrics(data=data, strict=True)
        self.assertEqual(out["followers"]["value"], "70,000+")

    def test_missing_as_of_is_dropped_when_not_strict(self):
        data = {
            "ok": {"value": "60+", "as_of": "2026-07-23", "source": "internal"},
            "bad": {"value": "100M+", "source": "internal"},  # no as_of
        }
        out = load_manual_metrics(data=data, strict=False)
        self.assertIn("ok", out)
        self.assertNotIn("bad", out)

    def test_missing_as_of_raises_when_strict(self):
        data = {"bad": {"value": "100M+", "source": "internal"}}
        with self.assertRaises(ManualMetricError) as ctx:
            load_manual_metrics(data=data, strict=True)
        self.assertIn("bad", str(ctx.exception))
        self.assertIn("as_of", str(ctx.exception))

    def test_missing_value_or_source_also_gated(self):
        self.assertNotIn(
            "a", load_manual_metrics(data={"a": {"as_of": "2026-07-23", "source": "internal"}}, strict=False)
        )
        self.assertNotIn(
            "b", load_manual_metrics(data={"b": {"value": "x", "as_of": "2026-07-23"}}, strict=False)
        )

    def test_empty_as_of_string_counts_as_missing(self):
        data = {"bad": {"value": "x", "as_of": "  ", "source": "internal"}}
        self.assertNotIn("bad", load_manual_metrics(data=data, strict=False))

    def test_list_value_is_allowed(self):
        data = {"compounds": {"value": ["Al Majdiah", "Dyar 20"], "as_of": "2026-07-23", "source": "internal"}}
        out = load_manual_metrics(data=data, strict=True)
        self.assertEqual(out["compounds"]["value"], ["Al Majdiah", "Dyar 20"])


class ShippedFile(unittest.TestCase):
    """The committed manual_metrics.json must itself pass the strict gate."""

    def test_shipped_manual_metrics_all_valid(self):
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "business", "manual_metrics.json",
        )
        out = load_manual_metrics(path=path, strict=True)
        # spot-check the anchors the page depends on
        for key in ("units_under_management", "commercial_registration", "followers"):
            self.assertIn(key, out)
            self.assertTrue(out[key].get("as_of"))
            self.assertTrue(out[key].get("source"))


if __name__ == "__main__":
    unittest.main()
