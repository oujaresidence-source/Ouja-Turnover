# -*- coding: utf-8 -*-
"""owner_meet.charts — deterministic SVG with the house rules (spec §10, gate G16).

Golden files live in tests/fixtures/owner_meet/golden/. To refresh them after an INTENDED visual
change: OWNER_MEET_GOLDEN_UPDATE=1 python3 -m unittest tests.test_owner_meet_charts — then look at
the diff before committing it.

Run: python3 -m unittest tests.test_owner_meet_charts
"""
import os
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from owner_meet import charts, texts  # noqa: E402

GOLDEN = ROOT / "tests" / "fixtures" / "owner_meet" / "golden"
ARABIC = re.compile("[؀-ۿ]")

MONTHS = [{"m": "2026-%02d" % i, "value": 1000.0 * i, "partial": i == 9} for i in range(1, 10)]
WF = [{"key": "income", "amount": 30000.0, "sign": 1}, {"key": "fee", "amount": 6000.0, "sign": -1},
      {"key": "cleaning", "amount": 900.0, "sign": -1}, {"key": "expenses", "amount": 0.0, "sign": -1},
      {"key": "net", "amount": 23100.0, "sign": 0}]
BAND = {"value": 34800.0, "p25": 9000.0, "p50": 13500.0, "p75": 18000.0, "pct10": 90, "tone": "top",
        "label": "x", "scope": "peers"}


def _bars():
    return charts.month_bars(MONTHS, "صافي المالك كل شهر", "وصف", shade={"2026-03": "رمضان"},
                             notes={"2026-09": "*"}, width=1180)


def _wf():
    return charts.waterfall(WF, "أين ذهب كل ريال", "وصف")


def _band():
    return charts.band(BAND, texts.money, "قيمة الحجوزات")


CASES = {"bars.svg": _bars, "waterfall.svg": _wf, "band.svg": _band, "band_key.svg": charts.band_key}


class Golden(unittest.TestCase):
    def test_same_input_same_bytes(self):
        for name, fn in CASES.items():
            self.assertEqual(fn(), fn(), name)

    def test_matches_the_golden_files(self):
        GOLDEN.mkdir(parents=True, exist_ok=True)
        for name, fn in CASES.items():
            path = GOLDEN / name
            if os.environ.get("OWNER_MEET_GOLDEN_UPDATE") == "1" or not path.exists():
                path.write_text(fn(), encoding="utf-8")
            self.assertEqual(fn(), path.read_text(encoding="utf-8"), "%s drifted from its golden file" % name)


class HouseRules(unittest.TestCase):
    def test_every_chart_is_an_image_with_title_and_desc(self):
        for name, fn in CASES.items():
            svg = fn()
            self.assertIn('role="img"', svg, name)
            self.assertRegex(svg, "<title>[^<]+</title>", name)
            self.assertRegex(svg, "<desc>[^<]+</desc>", name)

    def test_arabic_text_nodes_are_rtl(self):
        for name, fn in CASES.items():
            for attrs, body in re.findall(r"<text([^>]*)>([^<]*)</text>", fn()):
                if ARABIC.search(body):
                    self.assertIn('direction="rtl"', attrs, "%s: %s" % (name, body))

    def test_bars_are_zero_based_on_one_axis(self):
        svg = _bars()
        axes = re.findall(r'<line x1="10" x2="[0-9.]+" y1="([0-9.]+)" y2="[0-9.]+" stroke="#0B1A2E" stroke-width="1.5"/>', svg)
        self.assertEqual(len(axes), 1, "exactly one zero line — no dual axis")
        zero = axes[0]
        bars = re.findall(r'<path d="M[0-9.]+ ([0-9.]+)V', svg)
        self.assertEqual(len(bars), len(MONTHS))
        self.assertTrue(all(b == zero for b in bars), "every bar starts at the zero line")

    def test_time_runs_right_to_left(self):
        svg = _bars()
        xs = [float(x) for x in re.findall(r'<path d="M([0-9.]+) ', svg)]
        self.assertEqual(xs, sorted(xs, reverse=True), "the first month sits at the right edge")

    def test_negative_month_hangs_red_below_zero(self):
        svg = charts.month_bars([{"m": "2026-01", "value": -500.0}, {"m": "2026-02", "value": 800.0}], "t", "d")
        self.assertIn('fill="%s"' % charts.RED, svg)

    def test_waterfall_reads_from_income_on_the_right_to_net_on_the_left(self):
        svg = _wf()
        labels = re.findall(r'<text x="([0-9.]+)" y="[0-9.]+" class="lb"[^>]*>([^<]+)</text>', svg)
        pos = {t: float(x) for x, t in labels}
        self.assertGreater(pos["صافي الحجوزات"], pos["صافي المالك"])
        self.assertNotIn("−0", svg, "a zero deduction carries no minus sign")

    def test_band_draws_one_mark_whatever_the_group_size(self):
        """R1: a band never draws one mark per peer — its markup is the same size for 6 or 60 peers,
        because it is never handed the peers at all."""
        svg = _band()
        self.assertEqual(svg.count("<circle"), 1)
        self.assertEqual(svg.count("<rect"), 1)
        self.assertIsNone(re.search(r"(?<![a-z])n ?= ?[0-9]", svg), "no «n=» count anywhere")


if __name__ == "__main__":
    unittest.main()
