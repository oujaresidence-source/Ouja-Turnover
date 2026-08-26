# -*- coding: utf-8 -*-
"""
cp/tools/tokenise_source.py — turn the approved Arabic edition into a template.

WHY THIS EXISTS, and why the port is a script rather than a retype:

The brief's hardest rule is that the copy on /cp is the copy in ouja-cp-ar.html —
not a paraphrase of it, not a tidied version, not a translation of a translation.
The only way to prove that is to never type any of it. This script reads the
approved file and performs a fixed list of literal substitutions, each with the
number of hits it MUST make. A substitution that fires the wrong number of times
aborts the build, so the template can never drift from the document silently, and
a future edit to the source document is re-portable by rerunning this.

What becomes a placeholder: every figure that comes from cp_stats.json or
cp_market.json, every bar width derived from one, and every link or contact
detail that must come from configuration. Everything else — all the prose — is
carried across untouched.

Run:  python3 -m cp.tools.tokenise_source ~/Downloads/ouja-cp-ar.html
Out:  cp/templates/ar.html
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "templates", "ar.html")
ROUTES_OUT = os.path.join(os.path.dirname(HERE), "data", "cp_routes_ar.json")


class PortError(RuntimeError):
    pass


# (literal in the approved document, placeholder, exact number of occurrences)
# Ordered: longer / more specific literals first, so "74.0%" is consumed before
# anything could match a bare "74".
RULES = [
    # ---- figures shown as data displays -------------------------------------
    ("8,114", "__RESERVATIONS__", 3),
    ("13,093", "__NIGHTS__", 1),
    ("2,633", "__REVIEWS__", 2),
    ("152,177", "__MESSAGES__", 1),
    ("21,812", "__MKT_LISTINGS__", 2),
    ("21,000", "__MKT_LISTINGS_ROUND__", 3),
    ("23,000", "__MSG_NOW__", 1),
    ("2,900", "__MSG_START__", 1),
    ("66,000", "__LOC__", 1),
    ("1,000", "__MAINT__", 1),

    ("87.6%", "__PERFECT__%", 1),
    ("78.6%", "__CHURN_OCC__%", 1),
    ("76.9%", "__OCC__%", 5),

    ("9.77", "__CAT_COMM__", 1),
    ("9.74", "__CAT_CHECKIN__", 1),
    ("9.66", "__CAT_ACCURACY__", 1),
    ("9.64", "__CAT_LOCATION__", 1),
    ("9.57", "__CAT_CLEAN__", 2),
    ("9.38", "__CAT_VALUE__", 1),
    ("4.77", "__RATING__", 2),

    ("3.6×", "__X_REVPAR__×", 2),
    ("2.0×", "__X_OCC__×", 2),
    ("1.7×", "__X_ADR__×", 1),
    ("1.7 ضعف", "__X_ADR__ ضعف", 1),

    ("341", "__MKT_ADR__", 1),
    ("124", "__MKT_REVPAR__", 1),
    ("582", "__ADR__", 1),
    ("654", "__ADR90__", 1),
    ("451", "__REVPAR__", 1),
    ("485", "__REVPAR_ACTIVE__", 1),
    ("38%", "__MKT_OCC__%", 7),

    ("933", "__REPEAT_GUESTS__", 1),
    ("37% من كل الحجوزات", "__REPEAT_PCT__% من كل الحجوزات", 1),
    ("49 مرة", "__TOP_GUEST__ مرة", 1),
    ("94%", "__SAUDI__%", 1),
    ("42%", "__SAMEDAY__%", 2),
    ("35%", "__THUFRI__%", 1),
    ("22%", "__ADR_GROWTH__%", 1),
    ("6% من الحجوزات", "__LONGSTAY_BOOK__% من الحجوزات", 1),
    ("26% من الإيراد", "__LONGSTAY_REV__% من الإيراد", 1),
    ("2.3 دقيقة", "__RESPONSE__ دقيقة", 1),
    ("4.0 وحدات", "__PER_PERSON__ وحدات", 1),

    ("نُشغّل 74 وحدة", "نُشغّل __RESIDENCES__ وحدة", 1),
    ("74 وحدة مفروشة", "__RESIDENCES__ وحدة مفروشة", 1),
    ('<span class="v">74</span>', '<span class="v">__RESIDENCES__</span>', 1),
    ("لـ200 وحدة", "لـ__CAPACITY__ وحدة", 1),
    ("قرابة 200 وحدة", "قرابة __CAPACITY__ وحدة", 1),
    ("~200 · دون إدارة إضافية", "~__CAPACITY__ · دون إدارة إضافية", 1),
    ("خلال 5 أيام", "خلال __DAYS_FURN__ أيام", 1),
    ("خمسة أيام إن كان مفروشاً، و28 يوماً",
     "خمسة أيام إن كان مفروشاً، و__DAYS_UNFURN__ يوماً", 1),
    ("خلال 28 يوماً", "خلال __DAYS_UNFURN__ يوماً", 1),
    ("قرابة 28 يوماً", "قرابة __DAYS_UNFURN__ يوماً", 1),
    ("3.75 ريال للدولار", "__FX__ ريال للدولار", 1),

    # ---- bar widths, all derived from the figures above ---------------------
    ('style="width:47.5%"', 'style="width:__W_MKT_OCC__%"', 1),
    ('style="width:96%"', 'style="width:__W_OCC__%"', 1),
    ('style="width:48.5%"', 'style="width:__W_MKT_ADR__%"', 1),
    ('style="width:83%"', 'style="width:__W_ADR__%"', 1),
    ('style="width:24%"', 'style="width:__W_MKT_REVPAR__%"', 1),
    ('style="width:87%"', 'style="width:__W_REVPAR__%"', 1),
    ('style="width:97.7%"', 'style="width:__WC_COMM__%"', 1),
    ('style="width:97.4%"', 'style="width:__WC_CHECKIN__%"', 1),
    ('style="width:96.6%"', 'style="width:__WC_ACCURACY__%"', 1),
    ('style="width:96.4%"', 'style="width:__WC_LOCATION__%"', 1),
    ('style="width:95.7%"', 'style="width:__WC_CLEAN__%"', 1),
    ('style="width:93.8%"', 'style="width:__WC_VALUE__%"', 1),
    ('style="width:37%"', 'style="width:__W_CAPACITY__%"', 1),
    # 93.5% is the shared full-scale width of the ADR and RevPAR rows
    ('style="width:93.5%"', 'style="width:__W_FULL__%"', 2),

    # ---- dates and sources --------------------------------------------------
    ("حتى أغسطس 2026", "حتى __AS_OF_AR__", 2),
    ("الرياض، يوليو 2026", "الرياض، __MKT_DATE_AR__", 2),

    # ---- links, contacts, and the file-based navigation ---------------------
    ("Ouja-Residence-Company-Profile.pdf", "/cp.pdf", 2),
    ('hreflang="en" href="ouja-cp-en.html"', 'hreflang="en" href="__BASE__/cp/en"', 1),
    ('href="ouja-cp-en.html"', 'href="/cp/en"', 2),
    ('href="ouja-cp-ar.html"', 'href="__BASE__/cp/ar"', 1),
    ("https://tiktok.com/@oujares", "__TIKTOK__", 1),

    # Seeds §12 requires FIVE audience doors; the approved document has three.
    # The heading counts them, so it moves with them.
    ("<h2>ثلاثة أسباب لوجودك في هذه الصفحة</h2>", "<h2>__ROUTES_HEADING__</h2>", 1),
    ("</head>", "__HEAD_EXTRA__\n</head>", 1),

    # PORT FIX (not a copy change). In the approved document the skip link is
    # parked at left:-9999px. In a right-to-left page that is the inline-END
    # side, so the browser treats it as real content and the page gains 9999px
    # of horizontal scroll — measured in Chromium at both 380px and 1440px, and
    # it breaks the brief's "no horizontal scroll in either direction" floor.
    # Replaced with the clip technique /business already uses, and the focused
    # state uses a logical property so it lands on the correct side in RTL.
    (".skip{position:absolute;left:-9999px}",
     ".skip{position:absolute;width:1px;height:1px;padding:0;margin:-1px;"
     "overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0}", 1),
    # PORT FIX (not a copy change). `.cols-2` is auto-fit at minmax(285px), so
    # inside the 1120px measure it resolves to THREE tracks, not two: the four
    # "why now" blocks and the four governance blocks land 3+1 with one stranded
    # on its own row. Measured in Chromium at 1440 and 1024. Raising the track
    # minimum to 420px gives two columns on desktop and one below ~840px, which
    # is what the class name and the four-item sections intend.
    (".cols-2{grid-template-columns:repeat(auto-fit,minmax(285px,1fr))}",
     # min(420px,100%) matters: a bare 420px minimum is wider than a 380px
     # phone and pushes the track past the viewport — measured at 60px of
     # horizontal scroll before this was added.
     ".cols-2{grid-template-columns:repeat(auto-fit,minmax(min(420px,100%),1fr))}", 1),

    (".skip:focus{left:12px;top:12px;",
     ".skip:focus{width:auto;height:auto;margin:0;overflow:visible;clip:auto;"
     "inset-inline-start:12px;top:12px;", 1),

    # Contact details become configuration. Defect §8.1: the WhatsApp button on
    # /business opens email, and the address is a Gmail one — for an institutional
    # reader that single detail undoes the rest of the page.
    ('href="mailto:oujaresidence@gmail.com?subject=%D8%B7%D9%84%D8%A8%20%D8%A7%D8%AC%D8%AA%D9%85%D8%A7%D8%B9%20-%20%D8%B9%D9%88%D8%AC%D8%A7"',
     '__EMAIL_MEET_HREF__', 1),
    ('href="mailto:oujaresidence@gmail.com"', '__EMAIL_HREF__', 1),
    ('<a class="btn" style="border-color:var(--rule-dark);background:transparent;color:var(--on-dark)" href="https://wa.me/966500000000?text=%D8%A3%D8%B1%D8%BA%D8%A8%20%D8%A8%D8%AD%D8%AC%D8%B2%20%D8%A7%D8%AC%D8%AA%D9%85%D8%A7%D8%B9%20%D9%85%D8%B9%20%D8%B9%D9%88%D8%AC%D8%A7">واتساب</a>',
     "__WA_BUTTON_DARK__", 1),
    ('<p><a href="https://wa.me/966500000000">واتساب</a></p>', "__WA_FOOTER__", 1),
]

# Whole blocks the renderer rebuilds from data rather than from the document:
# the five audience tracks, the six review slots, the six residences, and the
# three «ask» fields. In the approved document the last three are deliberately
# left as coloured blanks — the document itself says nothing in that section is
# ours to write — so replacing them here loses no copy.
BLOCKS = [
    (r'<div class="routes">.*?\n    </div>', "__ROUTES__", 1),
    (r'<div class="voices">.*?\n    </div>', "__VOICES__", 1),
    (r'<p class="note" style="margin-top:22px">الحقول الملوّنة.*?</p>', "__VOICES_NOTE__", 1),
    (r'<div class="units">.*?\n    </div>', "__UNITS__", 1),
    (r'<div class="ask">.*?\n    </div>', "__ASK__", 1),
    # rebuilt from data so the "vs market" column is always the real ratio
    (r"<tbody>.*?</tbody>", "__OCC_TABLE__", 1),
    (r'<p class="asof">.*?</p>', "__SYNC_STAMP__", 1),
]


# Placeholders the renderer must fill even though no literal in the document
# produced them (they are inserted, not substituted).
INSERTED = ("__HEAD_EXTRA__", "__ROUTES__", "__VOICES__", "__UNITS__", "__ASK__",
            "__ROUTES_HEADING__", "__SYNC_STAMP__", "__OCC_TABLE__", "__VOICES_NOTE__")


_ROUTE_RX = re.compile(
    r'<div class="route"><h3>(?P<h3>.*?)</h3>\s*<p>(?P<p>.*?)</p>\s*'
    r'<a class="go" href="(?P<href>[^"]+)">(?P<cta>.*?)</a></div>', re.S)


def extract_routes(source_html):
    """Lift the audience cards out of the document verbatim.

    Seeds §12 needs five doors and the document has three. The three that exist
    are copy we may not rewrite, so they are extracted rather than retyped — the
    two that do not exist are added to the JSON afterwards and marked `authored`
    so they are visible as ours in review.
    """
    out = []
    for m in _ROUTE_RX.finditer(source_html):
        out.append({"h3": m.group("h3").strip(), "p": " ".join(m.group("p").split()),
                    "href": m.group("href"), "cta": m.group("cta").strip(),
                    "authored": False})
    if len(out) != 3:
        raise PortError("expected 3 audience cards in the document, found %d" % len(out))
    return out


def port(source_html):
    out = source_html
    report = []
    for literal, placeholder, expected in RULES:
        hits = out.count(literal)
        if hits != expected:
            raise PortError(
                "substitution %r expected %d occurrence(s) in the approved "
                "document, found %d. The source document changed — re-check this "
                "rule before porting, do not adjust the count to make it pass."
                % (literal, expected, hits))
        if expected:
            out = out.replace(literal, placeholder)
        report.append((literal, placeholder, hits))

    for pattern, placeholder, expected in BLOCKS:
        rx = re.compile(pattern, re.S)
        hits = len(rx.findall(out))
        if hits != expected:
            raise PortError(
                "block %r expected %d match(es), found %d — the source document's "
                "structure changed" % (pattern[:44], expected, hits))
        out = rx.sub(placeholder, out)
        report.append((pattern[:44], placeholder, hits))

    if "\\" in out:
        raise PortError("the ported template contains a backslash; the source "
                        "document is supposed to be free of them")
    return out, report


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    with open(os.path.expanduser(argv[1]), encoding="utf-8") as fh:
        src = fh.read()
    routes = extract_routes(src)
    if not os.path.exists(ROUTES_OUT):
        with open(ROUTES_OUT, "w", encoding="utf-8") as fh:
            json.dump(routes, fh, ensure_ascii=False, indent=2)
        print("extracted %d audience cards -> %s (two more must be added by hand)"
              % (len(routes), ROUTES_OUT))
    else:
        print("audience cards already extracted; leaving %s alone" % ROUTES_OUT)
    ported, report = port(src)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(ported)
    print("ported %d rules -> %s (%d bytes)" % (len(report), OUT, len(ported)))
    missing = [p for p in INSERTED if p not in ported]
    print("placeholders still to be inserted by the renderer: %s" % ", ".join(missing))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
