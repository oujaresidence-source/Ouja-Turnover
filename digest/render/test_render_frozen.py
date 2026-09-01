# -*- coding: utf-8 -*-
"""The look, locked. Renders reference_payload.json and compares a three-part
fingerprint per page against golden_fingerprint.json:

  text_md5    md5 of the page's extracted text (PyMuPDF)      — exact
  layout_md5  md5 of the browser-measured element geometry     — exact (locks the design)
  pixel_md5   md5 of the 72-dpi pixmap                          — exact, OR a mean absolute
              pixel delta <= 3/255 against golden/page-N.png (sub-pixel antialiasing
              drift between Chromium builds; the golden records its Chromium version)

owner_report's pixel-only golden is environment-locked and therefore not in CI; this
one is strict AND portable. If it fails, someone changed the look: revert, do not
regenerate. `--write-golden` refuses to overwrite an existing golden unless
`--i-have-owner-approval` is also passed.

Run:  python3 -m digest.render.test_render_frozen
      python3 -m digest.render.test_render_frozen --write-golden [--i-have-owner-approval]"""

import hashlib
import io
import json
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).parent
GOLDEN_JSON = HERE / "golden_fingerprint.json"
GOLDEN_DIR = HERE / "golden"
PIXEL_TOLERANCE = 3.0       # mean absolute delta, 0..255


def _md5(b):
    return hashlib.md5(b).hexdigest()


def fingerprint(pdf_path, layout):
    import fitz
    doc = fitz.open(str(pdf_path))
    pages = []
    layout_json = json.dumps(layout, ensure_ascii=False, separators=(",", ":"))
    for i in range(doc.page_count):
        pg = doc[i]
        png = pg.get_pixmap(dpi=72).tobytes("png")
        pages.append({
            "n": i + 1,
            "text_md5": _md5(pg.get_text().encode("utf-8")),
            "pixel_md5": _md5(png),
            "_png": png,
        })
    return {"page_count": doc.page_count, "layout_md5": _md5(layout_json.encode("utf-8")), "pages": pages}


def mean_delta(png_a, png_b):
    from PIL import Image, ImageChops, ImageStat
    a = Image.open(io.BytesIO(png_a)).convert("RGB")
    b = Image.open(io.BytesIO(png_b)).convert("RGB")
    if a.size != b.size:
        return 255.0
    st = ImageStat.Stat(ImageChops.difference(a, b))
    return sum(st.mean) / 3.0


def compare(cand, golden, golden_dir=GOLDEN_DIR):
    fails = []
    if cand["page_count"] != golden["page_count"]:
        fails.append("page count %d != golden %d" % (cand["page_count"], golden["page_count"]))
    if cand["layout_md5"] != golden["layout_md5"]:
        fails.append("LAYOUT CHANGED (element geometry differs from the golden)")
    for g in golden["pages"]:
        i = g["n"] - 1
        if i >= cand["page_count"]:
            break
        c = cand["pages"][i]
        if c["text_md5"] != g["text_md5"]:
            fails.append("page %d: text changed" % g["n"])
        if c["pixel_md5"] != g["pixel_md5"]:
            gp = golden_dir / ("page-%d.png" % g["n"])
            if not gp.exists():
                fails.append("page %d: VISUAL CHANGED and no golden PNG to measure against" % g["n"])
                continue
            d = mean_delta(c["_png"], gp.read_bytes())
            if d > PIXEL_TOLERANCE:
                fails.append("page %d: VISUAL CHANGED (mean pixel delta %.2f/255 > %.1f)" % (g["n"], d, PIXEL_TOLERANCE))
    return fails


def render_reference(tmp):
    from . import build
    res = build.render(build.reference_payload(), {}, tmp, "ref", run_audit=True)
    return res


def write_golden(fp, chromium):
    GOLDEN_DIR.mkdir(exist_ok=True)
    for p in fp["pages"]:
        (GOLDEN_DIR / ("page-%d.png" % p["n"])).write_bytes(p["_png"])
    data = {"chromium": chromium, "page_count": fp["page_count"], "layout_md5": fp["layout_md5"],
            "pages": [{k: v for k, v in p.items() if not k.startswith("_")} for p in fp["pages"]]}
    GOLDEN_JSON.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    write = "--write-golden" in argv
    approved = "--i-have-owner-approval" in argv
    with tempfile.TemporaryDirectory() as tmp:
        res = render_reference(tmp)
        fp = fingerprint(res["pdf"], res["layout"])
        if write:
            if GOLDEN_JSON.exists() and not approved:
                print("✗ a golden already exists. The look is FROZEN; regenerate only with the owner's word:")
                print("    python3 -m digest.render.test_render_frozen --write-golden --i-have-owner-approval")
                return 2
            write_golden(fp, res.get("chromium", ""))
            print("✓ golden written: %d pages, layout %s, chromium %s" % (fp["page_count"], fp["layout_md5"][:12], res.get("chromium", "")))
            return 0
        if not GOLDEN_JSON.exists():
            print("✗ no golden yet — run with --write-golden after the owner approves the look")
            return 2
        golden = json.loads(GOLDEN_JSON.read_text(encoding="utf-8"))
        fails = compare(fp, golden)
        if fails:
            print("✗ VISUAL REGRESSION")
            for f in fails:
                print("   " + f)
            print(chr(10) + "The look is FROZEN. Revert your change to digest/render/; do not regenerate the golden.")
            return 1
        print("✓ %d/%d pages match the approved design (golden chromium %s, this %s)"
              % (fp["page_count"], fp["page_count"], golden.get("chromium", "?"), res.get("chromium", "?")))
        return 0


if __name__ == "__main__":
    sys.exit(main())
