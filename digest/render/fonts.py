# -*- coding: utf-8 -*-
"""digest.render.fonts — the Thmanyah faces the digest ships (brief §2.1), as
@font-face rules with file:// urls into fonts/ so a local Chromium subsets and embeds
them into the PDF (the cp/tools/build_pdf.py idiom; base64 inlining would add ~400 KB
to every preview). Five faces, the ones the design uses; Almarai then system-ui fall back.
The five files are byte-identical to monthly_public/static/fonts/ (md5-checked in
tests/test_digest_fonts.py)."""

import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FONT_DIR = os.path.join(ROOT, "fonts")

SERIF = "Thmanyah Serif Display"
SANS = "Thmanyah Sans"
FALLBACK = '"Almarai", system-ui, sans-serif'

# (family, weight, file)
FACES = (
    (SERIF, 700, "ThmanyahSerifDisplay-Bold.woff2"),
    (SERIF, 900, "ThmanyahSerifDisplay-Black.woff2"),
    (SANS, 400, "ThmanyahSans-Regular.woff2"),
    (SANS, 500, "ThmanyahSans-Medium.woff2"),
    (SANS, 700, "ThmanyahSans-Bold.woff2"),
)

# the monthly_public originals each file was copied from (route stem)
ORIGINS = {
    "ThmanyahSerifDisplay-Bold.woff2": "thmanyah-serif-display-bold.v20260827a.woff2",
    "ThmanyahSerifDisplay-Black.woff2": "thmanyah-serif-display-black.v20260827a.woff2",
    "ThmanyahSans-Regular.woff2": "thmanyah-sans-regular.v20260827a.woff2",
    "ThmanyahSans-Medium.woff2": "thmanyah-sans-medium.v20260827a.woff2",
    "ThmanyahSans-Bold.woff2": "thmanyah-sans-bold.v20260827a.woff2",
}


def path_for(filename):
    return os.path.join(FONT_DIR, filename)


def font_faces():
    out = []
    for fam, w, f in FACES:
        out.append('@font-face{font-family:"%s";font-weight:%d;font-style:normal;font-display:block;'
                   'src:url("file://%s") format("woff2")}' % (fam, w, path_for(f)))
    return "\n".join(out)


def stacks():
    return {"serif": '"%s", %s' % (SERIF, FALLBACK), "sans": '"%s", %s' % (SANS, FALLBACK)}
