# -*- coding: utf-8 -*-
"""
VISUAL REGRESSION TEST — run this in CI. It must always pass.

It renders the frozen renderer against the reference data and compares the result,
PIXEL BY PIXEL, to the approved design (golden_fingerprint.json).

If this test fails, someone changed the look of the report. That is almost never
intended. Do not "update the golden" to make it pass — find what changed and revert it.

    python3 test_render_frozen.py
"""
import hashlib, json, pathlib, sys, tempfile

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))

import fitz
import reference_data as R
from ouja_render import render_report, REPORT_SCHEMA


def main() -> int:
    golden = json.loads((HERE / "golden_fingerprint.json").read_text())
    cfg = {k: getattr(R, k) for k in REPORT_SCHEMA}

    with tempfile.TemporaryDirectory() as tmp:
        pdf = render_report(cfg, pathlib.Path(tmp) / "candidate.pdf")
        doc = fitz.open(pdf)

        fails = []
        if doc.page_count != golden["page_count"]:
            fails.append(f"page count {doc.page_count} != golden {golden['page_count']}")

        for g in golden["pages"]:
            i = g["n"] - 1
            if i >= doc.page_count:
                break
            px = hashlib.md5(doc[i].get_pixmap(dpi=72).tobytes("png")).hexdigest()
            tx = hashlib.md5(doc[i].get_text().encode()).hexdigest()
            if px != g["pixel_md5"]:
                fails.append(f"page {g['n']}: VISUAL CHANGED (pixel hash differs)")
            elif tx != g["text_md5"]:
                fails.append(f"page {g['n']}: text content changed")

    if fails:
        print("✗ VISUAL REGRESSION — the report no longer matches the approved design:")
        for f in fails:
            print("   ", f)
        print("\nThe renderer is FROZEN. Revert your change to ouja_render.py.")
        return 1

    print(f"✓ {golden['page_count']}/{golden['page_count']} pages pixel-identical to the approved design")
    return 0


if __name__ == "__main__":
    sys.exit(main())
