#!/usr/bin/env python3
"""Render an HTML file in the «لوك عوجا» look to a PDF with the Thmanyah fonts embedded.

    python3 docs/brand/templates/build_pdf.py input.html output.pdf

It injects @font-face rules pointing at LOCAL font files (never a URL), then prints with
Chromium through Playwright. Chromium embeds a subset of each face in the PDF, which the
Thmanyah licence allows ("embed the Font Software in documents ... you create").

Font search order: $OUJA_FONTS_DIR, then <repo>/monthly_public/static/fonts and <repo>/fonts
(this repo, then $OUJA_REPO, default ~/Ouja-Turnover), then origin/main of that repo through git,
then fonts installed on this machine (download them from thmanyah.com — never copy the files
to anyone). Check the result with:  pdffonts output.pdf   (should list Thmanyah faces).
"""
import os
import subprocess
import sys
import pathlib
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent.parent
# When this script runs from a copy outside the repo (the ouja-look skill), fonts come from here:
OUJA_REPO = pathlib.Path(os.environ.get("OUJA_REPO", str(pathlib.Path.home() / "Ouja-Turnover")))

FACES = [
    ("Thmanyah Serif", 700, ["thmanyah-serif-display-bold.v20260827a.woff2", "ThmanyahSerifDisplay-Bold.woff2"]),
    ("Thmanyah Serif", 900, ["thmanyah-serif-display-black.v20260827a.woff2", "ThmanyahSerifDisplay-Black.woff2"]),
    ("Thmanyah Sans", 400, ["thmanyah-sans-regular.v20260827a.woff2", "ThmanyahSans-Regular.woff2"]),
    ("Thmanyah Sans", 500, ["thmanyah-sans-medium.v20260827a.woff2", "ThmanyahSans-Medium.woff2"]),
    ("Thmanyah Sans", 700, ["thmanyah-sans-bold.v20260827a.woff2", "ThmanyahSans-Bold.woff2"]),
]


def _fonts_from_git():
    """The checkout may be parked on an old branch without the font files. Read them from
    origin/main into a private temp folder for this one build (local use, never shared)."""
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="ouja-fonts-"))
    for _family, _weight, names in FACES:
        rel = "monthly_public/static/fonts/" + names[0]
        try:
            data = subprocess.run(["git", "-C", str(OUJA_REPO), "show", "origin/main:" + rel],
                                  check=True, capture_output=True).stdout
        except (OSError, subprocess.CalledProcessError):
            continue
        (tmp / names[0]).write_bytes(data)
    return tmp


def font_dirs():
    dirs = []
    if os.environ.get("OUJA_FONTS_DIR"):
        dirs.append(pathlib.Path(os.environ["OUJA_FONTS_DIR"]))
    for root in (REPO, OUJA_REPO):
        dirs += [root / "monthly_public" / "static" / "fonts", root / "fonts"]
    dirs = [d for d in dirs if d.is_dir()]
    if not any((d / FACES[0][2][0]).is_file() or (d / FACES[0][2][1]).is_file() for d in dirs):
        dirs.append(_fonts_from_git())
    return dirs


def font_faces():
    rules, missing = [], []
    dirs = font_dirs()
    for family, weight, names in FACES:
        path = next((d / n for d in dirs for n in names if (d / n).is_file()), None)
        if path is None:
            missing.append("%s %d" % (family, weight))
            continue
        rules.append('@font-face{font-family:"%s";font-weight:%d;font-style:normal;'
                     'src:url("%s") format("woff2")}' % (family, weight, path.as_uri()))
    return "\n".join(rules), missing


def build(src, out):
    from playwright.sync_api import sync_playwright
    src = pathlib.Path(src).resolve()
    html = src.read_text(encoding="utf-8")
    faces, missing = font_faces()
    if missing:
        print("warning: no local file for %s — falling back to installed fonts" % ", ".join(missing))
    html = html.replace("<head>", "<head>\n<style>%s</style>" % faces, 1)
    tmp = src.with_name("._ouja_print_" + src.name)
    tmp.write_text(html, encoding="utf-8")
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.goto(tmp.as_uri(), wait_until="networkidle")
            page.evaluate("document.fonts.ready")
            page.pdf(path=str(out), format="A4", print_background=True, prefer_css_page_size=True)
            browser.close()
    finally:
        tmp.unlink(missing_ok=True)
    print("wrote %s" % out)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    build(sys.argv[1], sys.argv[2])
