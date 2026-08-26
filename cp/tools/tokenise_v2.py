# -*- coding: utf-8 -*-
"""
cp/tools/tokenise_v2.py — the approved v6 mock becomes the v2 template set.

Same philosophy as v1's tokenise_source: the design and the Arabic are settled,
so nothing is retyped — every transformation is a counted literal substitution
that ABORTS if it matches a different number of times than recorded against the
approved file. Three rule classes, labelled: figure/link tokens, PORT FIX
(behavior the production page needs that a static mock cannot carry), and
copy-key extraction (the strings the dashboard may edit).

Outputs:
  cp/templates/ar_v2.html        — the page, tokenised
  cp/templates/more/<key>.html   — the seven drawer bodies, extracted verbatim
                                   (they become /cp/ar/more/<key> AND stay
                                   inlined in the page for the JS drawer)
  cp/data/cp_copy_v2_ar.json     — key → default string, extracted verbatim;
                                   the dashboard's «النصوص» tab edits against
                                   these keys and the renderer swaps
                                   default → override at render time

Run:  python3 -m cp.tools.tokenise_v2 docs/cp/v6-mock.html
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
OUT_PAGE = os.path.join(PKG, "templates", "ar_v2.html")
OUT_MORE = os.path.join(PKG, "templates", "more")
OUT_COPY = os.path.join(PKG, "data", "cp_copy_v2_ar.json")

DRAWER_KEYS = ("compare", "system", "stay", "guests", "units", "owners", "gov")


class PortError(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# figure / link tokens — (literal, replacement, exact count in the mock)
# Order matters: longer literals run before their substrings (3.75 before 3.7).
# --------------------------------------------------------------------------- #
RULES = [
    # market (AirDNA) — from cp_market.json / benchmarks config
    ("21,812", "__MKT_LISTINGS__", 3),
    ("21,000", "__MKT_ROUND__", 2),
    ("38%", "__MKT_OCC__%", 12),
    ("341", "__MKT_ADR__", 1),
    ("124", "__MKT_REVPAR__", 1),
    ("3.75", "__FX__", 1),
    ("24.1%", "__YOY_OCC__%", 1),
    ("11.8%", "__YOY_ADR__%", 1),
    ("−8%", "−__YOY_SUPPLY__%", 1),

    # official benchmarks — MoT + Knight Frank (benchmarks config)
    ("59.3%", "__MOT_OCC__%", 2),
    ("63.4%", "__KF_OCC__%", 2),
    ("478", "__KF_REVPAR__", 2),
    ("754", "__KF_ADR__", 1),
    ("206", "__MOT_ADR__", 1),

    # ouja — the figure layer (hostaway/seeds/manual provenance, v1 unchanged)
    ("8,114", "__RESERVATIONS__", 3),
    ("13,093", "__NIGHTS__", 1),
    ("2,633", "__REVIEWS__", 4),
    ("4.77", "__RATING__", 3),
    ("76.9%", "__OCC__%", 7),
    ("87.6%", "__PERFECT__%", 1),
    ("582", "__ADR__", 3),
    ("654", "__ADR90__", 2),
    ("451", "__REVPAR__", 4),
    ("485", "__REVPAR_ACT__", 2),
    ("94%", "__SAUDI__%", 2),
    ("42%", "__SAMEDAY__%", 2),
    ("67%", "__WITHIN24__%", 1),
    ("35%", "__THUFRI__%", 1),
    ("644 · 554", "__WKND_HIGH__ · __WKND_LOW__", 1),
    ("933", "__REPEAT_GUESTS__", 2),
    ("37%", "__REPEAT_PCT__%", 1),
    ("<b>49</b>", "<b>__TOP_GUEST__</b>", 1),
    ("58% · 28%", "__SOLO__% · __COUPLE__%", 1),
    ("9.77", "__CAT_COMM__", 1),
    ("9.74", "__CAT_CHECKIN__", 1),
    ("9.66", "__CAT_ACCURACY__", 1),
    ("9.64", "__CAT_LOCATION__", 1),
    ("9.57", "__CAT_CLEAN__", 1),
    ("9.38", "__CAT_VALUE__", 1),
    ("2.3", "__RESPONSE__", 3),
    ("4.0", "__PER_PERSON__", 2),
    ("66,000", "__LOC__", 1),
    ("152,177", "__MESSAGES__", 1),
    ("~1,000", "~__MAINT__", 1),
    ("2,900", "__MSG_START__", 1),
    ("23,000", "__MSG_NOW__", 1),
    ("53.8%", "__OCC_LOW__%", 1),
    ("82.6%", "__OCC_HIGH__%", 1),
    ("78.6%", "__CHURN_OCC__%", 1),
    # bar widths derived from figures — computed at render, never stale
    ('style="--w:49%"', 'style="--w:__W_OCC_M__%"', 1),
    ('style="--w:59%"', 'style="--w:__W_ADR_M__%"', 1),
    ('style="--w:27%"', 'style="--w:__W_REVPAR_M__%"', 1),
    ('style="--w:97.7%"', 'style="--w:__WC_COMM__%"', 1),
    ('style="--w:97.4%"', 'style="--w:__WC_CHECKIN__%"', 1),
    ('style="--w:96.6%"', 'style="--w:__WC_ACCURACY__%"', 1),
    ('style="--w:96.4%"', 'style="--w:__WC_LOCATION__%"', 1),
    ('style="--w:95.7%"', 'style="--w:__WC_CLEAN__%"', 1),
    ('style="--w:93.8%"', 'style="--w:__WC_VALUE__%"', 1),
    ("5 <small>", "__DAYS_FURN__ <small>", 1),
    ("28 <small>", "__DAYS_UNFURN__ <small>", 1),
    # the animated instrument card reads its figures from data- attributes
    ('<div class="card inst" id="inst" aria-live="polite">',
     '<div class="card inst" id="inst" aria-live="polite" data-occ="__OCC__" '
     'data-mkt="__MKT_OCC__" data-asof="__ASOF_LINE__">', 1),
    # the success text becomes a copy slot the JS composes onto
    ('<p id="okText">نؤكد الموعد على جوالك خلال يوم عمل. وإن كان عاجلاً، فالواتساب يصل إلى الفريق مباشرة.</p>',
     '<p id="okText" data-tpl="__RESV_OK__">__RESV_OK__</p>', 1),

    ("نُشغّل 74", "نُشغّل __RESIDENCES__", 1),
    ("74 وحدة", "__RESIDENCES__ وحدة", 4),   # the 5th is consumed by the نُشغّل rule above

    # contacts — from the admin overlay (never hardcoded again)
    ('href="https://wa.me/966533779297?text=%D8%A3%D8%B1%D8%BA%D8%A8%20%D8%A8%D8%AD%D8%AC%D8%B2%20%D8%A7%D8%AC%D8%AA%D9%85%D8%A7%D8%B9%20%D9%85%D8%B9%20%D8%B9%D9%88%D8%AC%D8%A7"',
     'href="__WA_HREF__"', 1),
    ('href="https://wa.me/966533779297"', 'href="__WA_PLAIN__"', 1),
    ('href="mailto:Info@oujares.com?subject=%D8%AD%D8%AC%D8%B2%20%D8%A7%D8%AC%D8%AA%D9%85%D8%A7%D8%B9"',
     'href="__MAIL_HREF__"', 1),
    ('href="mailto:Info@oujares.com"', 'href="__MAIL_PLAIN__"', 1),
    (">Info@oujares.com</a>", ">__EMAIL_TEXT__</a>", 1),

    # PORT FIX — the production head: fonts become self-hosted (§2.4) and the
    # page gains canonical/OG/JSON-LD via a token before the stylesheet.
    ('<link rel="preconnect" href="https://fonts.googleapis.com">\n'
     '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Naskh+Arabic:wght@500;600;700&family=Amiri:wght@400;700&family=Almarai:wght@300;400;700&family=Readex+Pro:wght@300;400;500;600&family=IBM+Plex+Sans+Arabic:wght@300;400;500;600&family=Noto+Sans+Arabic:wght@300;400;500;600&display=swap">',
     "__HEAD_EXTRA__", 1),

    # PORT FIX — the review-only font switcher must not ship (§2.4): its CSS
    # hooks go too, so no dead selectors ride to production.
    ('[data-font="b"]{--serif:"Noto Naskh Arabic",serif;--sans:"Readex Pro",Tahoma,sans-serif}\n'
     '[data-font="c"]{--serif:"Noto Naskh Arabic",serif;--sans:"IBM Plex Sans Arabic",Tahoma,sans-serif}\n'
     '[data-font="d"]{--serif:"Amiri",serif;--sans:"Noto Sans Arabic",Tahoma,sans-serif}\n',
     "", 1),


    # PORT FIX — the font stacks use the self-hosted faces with metric-matched
    # local fallbacks (§2.4); Amiri/Readex never shipped, they were switcher
    # options.
    ('--serif:"Noto Naskh Arabic","Amiri",serif; --sans:"Almarai","Readex Pro",Tahoma,sans-serif;',
     '--serif:"Noto Naskh Arabic","Naskh Fallback",serif; --sans:"Almarai","Almarai Fallback",Tahoma,sans-serif;', 1),

    # PORT FIX — the page must be a document. The mock has NO <html> element at
    # all (it was authored to sit inside a preview wrapper), so the live page
    # had no lang and no dir — Lighthouse a11y 92, and a screen reader with no
    # language to announce. Same shell v1 ships.
    ("<title>عوجا للأملاك</title>",
     '<!doctype html>\n<html lang="ar" dir="rtl">\n<head>\n'
     "<title>عوجا للأملاك</title>", 1),
    ("</style>\n", "</style>\n</head>\n<body>\n", 1),

    # PORT FIX — contrast. --mute #7A7267 on the beige ground measures 3.92:1
    # at 13px (door lines, eyebrows, review attributions) and --mkt #8F877A
    # measures 3.55:1 on white — both under the 4.5 floor the brief sets. Same
    # hue, darkened to the first passing step: 5.13:1 and 5.51:1. This is the
    # correction the v1 seeds file already made for its own faint neutral, not
    # a reinterpretation of the design.
    ("--mute:#7A7267;", "--mute:#676057;", 1),
    ("--mkt:#8F877A;", "--mkt:#6F685D;", 1),
    # --faint does double duty: correct as light-on-dark inside the dark band,
    # but 2.27:1 where the footer puts it on beige. The dark-band usage keeps
    # the token; the two light-ground usages move to --mute (5.13:1).
    ("footer h4{font-size:12px;letter-spacing:.04em;color:var(--faint);",
     "footer h4{font-size:12px;letter-spacing:.04em;color:var(--mute);", 1),
    ('<span style="color:var(--faint)">النسخة الإنجليزية — قريباً</span>',
     '<span style="color:var(--mute)">النسخة الإنجليزية — قريباً</span>', 1),
    ("gap:10px;font-size:13px;color:var(--faint)}",
     "gap:10px;font-size:13px;color:var(--mute)}", 1),

    # PORT FIX — a real <img> inside .ph is unconstrained in the mock (it only
    # ever holds a placeholder span), so a 1024px photo overflowed a 390px
    # phone. Measured before/after.
    ('.unit .b{', '.unit .ph img{display:block;width:100%;height:100%;'
                  'object-fit:cover}\n.unit .b{', 1),

    # PORT FIX — a skip link (§2.7); the mock has none.
    ('<header class="top">',
     '<a class="skip" href="#main">تخطَّ إلى المحتوى</a>\n<header class="top">', 1),
    (':focus-visible{outline:2px solid var(--black);outline-offset:4px}',
     ':focus-visible{outline:2px solid var(--black);outline-offset:4px}\n'
     '.skip{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0}\n'
     '.skip:focus{width:auto;height:auto;margin:0;overflow:visible;clip:auto;inset-inline-start:12px;top:12px;z-index:99;background:var(--black);color:var(--white);padding:10px 16px}', 1),

    # PORT FIX — the form posts for real; success text slot; booking button slot
    ('<form id="lead" novalidate>',
     '<form id="lead" method="post" action="/api/cp/lead" novalidate>', 1),
    ('<div class="fa"><button class="btn" type="submit">احجز اللقاء</button>',
     '__BOOKING_BUTTON__<div class="fa"><button class="btn" type="submit">احجز اللقاء</button>', 1),
]

# PORT FIX — the mock's «اعرف المزيد» controls are <button>s; production needs
# real crawlable routes (§2.2), so each becomes an <a> to /cp/ar/more/<key> with
# JS intercepting the click. The WHOLE element is rewritten, close tag included:
# an earlier version swapped only the opening tag and left </button> behind, so
# the anchor never closed and swallowed the rest of the document — the form's
# submit button ended up inside it and a real click did nothing. Caught by
# driving a browser, invisible to every unit test.
MORE_LINK_RX = re.compile(
    r'<button class="more" data-drawer="(?P<k>[a-z]+)">(?P<inner>.*?)</button>', re.S)
MORE_LINK_EXPECTED = 7


# --------------------------------------------------------------------------- #
# blocks rebuilt from data at render time
# --------------------------------------------------------------------------- #
BLOCKS = [
    (r'<div class="doors">.*?\n    </div>', "__DOORS__", 1),
    (r'<div class="quotes">.*?\n    </div>', "__PAGE_QUOTES__", 1),
    (r'<div class="units">.*?\n    </div>', "__UNITS_GRID__", 1),
    (r'<div class="shots">.*?\n    </div>', "__SHOTS__", 1),
    (r'<div class="bench reveal">.*?\n    </div>', "__BENCH__", 1),
    # the occupancy-by-type rows inside the compare drawer: the vs-column is
    # computed, never typed (same rule as v1's table)
    (r'<div class="kv"><span>غرفة نوم واحدة</span>.*?إجمالي المحفظة</span><span class="pair"><span class="g num">__MKT_OCC__%</span><b>__OCC__%</b></span></div>',
     "__OCC_TYPES__", 1),
    # the six drawer reviews — chosen in the dashboard, verbatim from the store
    (r'<h4>ست مراجعات، كما كُتبت</h4>.*?<p>ننشر المجموعة كاملة',
     "__DRAWER_REVIEWS__\n      <p>ننشر المجموعة كاملة", 1),
    # the six drawer unit rows — from the showcase config
    (r'(<div class="dsec" data-d="units"[^>]*>.*?</p>)\s*<ol>.*?</ol>',
     r"\1\n      __DRAWER_UNITS__", 1),
    # the whole mock script (fake submit + font switcher) is replaced by the
    # production script, kept as its own FILE so no Python string ever holds JS
    (r'<script>.*?</script>', "__SCRIPT__\n</body>\n</html>", 1),
    # the switcher panel itself, and its now-orphaned CSS rules
    (r'<div class="fontsw"[^>]*>.*?</div>', "", 1),
    (r'\.fontsw\{[^}]*\}\n\.fontsw b\{[^}]*\}\n\.fontsw button\{[^}]*\}\n\.fontsw button\.on\{[^}]*\}\n', "", 1),
]

# --------------------------------------------------------------------------- #
# copy keys — the strings the dashboard edits. Extracted verbatim: the port
# records key → the exact default string found in the mock (count must be ≥1;
# the FIRST occurrence context defines it). The renderer swaps default →
# override when the overlay carries the key.
# --------------------------------------------------------------------------- #
COPY_KEYS = [
    ("hero_h1_tail", "وحداتنا لا."),
    ("hero_sub", "نُشغّل __RESIDENCES__ وحدة مفروشة في الرياض على نظام بنيناه بأنفسنا — لأن ما يُباع في السوق لم يُصنع لهذا العمل."),
    ("trust_1", "تصريح سياحي لكل وحدة"),
    ("trust_2", "رابحة ومموّلة ذاتياً منذ 2024"),
    ("trust_3", "__REPEAT_GUESTS__ ضيفاً عادوا إلينا"),
    ("trust_4", "كل رقم هنا له مصدر وتاريخ"),
    ("doors_h2", "أنت هنا لأنك…"),
    ("compare_h2", "المؤشر نفسه. رقمان."),
    ("compare_lede", "سوق الرياض بحسب AirDNA (يوليو 2026، على __MKT_LISTINGS__ وحدة)، وعوجا بحسب نظامنا (حتى أغسطس 2026، على كامل المحفظة)."),
    ("proof_h2", "نظام نديره كل صباح، وضيوف يقيّمونه كل ليلة."),
    ("stay_h2", "إقامة كاملة، بلا مكالمة واحدة."),
    ("guests_lede_eyebrow", "بكلماتهم · منشورة كما كُتبت"),
    ("residences_lede", "من الاستوديو إلى أربع غرف، داخل مجمعات مُدارة في شمال الرياض. كل صورة هي للوحدة نفسها."),
    ("owners_h2", "من مفتاحك إلى أول حجز"),
    ("owners_lede", "حصة من الإيراد، بلا دفعة مقدمة، وبلا رسوم على الليالي الفارغة. عقد سنة، إشعار شهر، وتستعيد عقارك."),
    ("gov_h2", "أين نقف، وأين لا نقف"),
    ("meet_h2", "أفضل الأرقام ليست هنا."),
    ("meet_lede", "ننشر الأداء العام لأنك تستطيع التحقق منه. أما الأتعاب والتكاليف وصافي عائد المالك، فنفتحها معك في غرفة البيانات خلال 45 دقيقة."),
    ("resv_h3", "احجز اللقاء."),
    ("resv_p", "خمس وأربعون دقيقة. اختر الطريقة والوقت، ونؤكد الموعد على جوالك."),
    ("footer_about_numbers", "أرقام التشغيل حتى أغسطس 2026 من نظامنا على كامل المحفظة. مقارنات السوق من AirDNA الرياض، يوليو 2026. التقييمات متوسط المراجعات المنشورة، بما فيها المنخفضة."),
    ("footer_tagline", "كل رقم في هذه الصفحة له مصدر وتاريخ."),
]


# tokens whose replaced block is saved verbatim as the render-time DEFAULT —
# the page stays pixel-identical to the mock until the dashboard configures
# that block, and no default markup is ever authored by hand.
DEFAULTED = {"__DOORS__": "doors", "__PAGE_QUOTES__": "page_quotes",
             "__UNITS_GRID__": "units_grid", "__SHOTS__": "shots",
             "__BENCH__": "bench", "__OCC_TYPES__": "occ_types",
             "__DRAWER_REVIEWS__": "drawer_reviews",
             "__DRAWER_UNITS__": "drawer_units"}


def port(src, defaults_out=None):
    out = src
    for lit, repl, expected in RULES:
        hits = out.count(lit)
        if hits != expected:
            raise PortError("rule %r expected %d, found %d — the mock changed; "
                            "re-verify before adjusting" % (lit[:70], expected, hits))
        if expected:
            out = out.replace(lit, repl)

    hits = len(MORE_LINK_RX.findall(out))
    if hits != MORE_LINK_EXPECTED:
        raise PortError("«اعرف المزيد» controls: expected %d, found %d"
                        % (MORE_LINK_EXPECTED, hits))
    out = MORE_LINK_RX.sub(
        lambda m: '<a class="more" href="/cp/ar/more/%s" data-drawer="%s">%s</a>'
        % (m.group("k"), m.group("k"), m.group("inner")), out)

    for pattern, repl, expected in BLOCKS:
        rx = re.compile(pattern, re.S)
        found = rx.findall(out)
        if len(found) != expected:
            raise PortError("block %r expected %d, found %d" % (pattern[:60],
                                                                expected, len(found)))
        token = next((t for t in DEFAULTED if t in repl), "")
        if defaults_out is not None and token and found:
            m = rx.search(out)
            markup = m.group(0)
            if m.groups():          # a kept prefix (\1) is not part of the default
                markup = markup[len(m.group(1)):].lstrip()
            defaults_out[DEFAULTED[token]] = markup
        out = rx.sub(repl, out)
    return out


def extract_drawers(src_after_rules):
    """Each .dsec body, verbatim, AFTER figure tokenisation so /more pages get
    the same live figures as the page."""
    out = {}
    for key in DRAWER_KEYS:
        m = re.search(r'<div class="dsec" data-d="%s" data-title="([^"]*)">(.*?)\n    </div>'
                      % key, src_after_rules, re.S)
        if not m:
            raise PortError("drawer %r not found" % key)
        out[key] = {"title": m.group(1), "body": m.group(2)}
    return out


def extract_copy(tokenised):
    reg = {}
    for key, default in COPY_KEYS:
        if tokenised.count(default) < 1:
            raise PortError("copy key %r: default string not found — the mock "
                            "changed" % key)
        reg[key] = default
    return reg


def main(argv):
    src_path = argv[1] if len(argv) > 1 else os.path.join(
        os.path.dirname(os.path.dirname(PKG)), "docs", "cp", "v6-mock.html")
    with open(src_path, encoding="utf-8") as fh:
        src = fh.read()

    # figures first, then drawer extraction from the FIGURE-tokenised source
    # (before block replacement removes the drawer internals we extract)
    inter = src
    for lit, repl, expected in RULES:
        if inter.count(lit) != expected:
            raise PortError("rule %r expected %d, found %d" % (lit[:70], expected,
                                                               inter.count(lit)))
        inter = inter.replace(lit, repl)
    inter = MORE_LINK_RX.sub(
        lambda m: '<a class="more" href="/cp/ar/more/%s" data-drawer="%s">%s</a>'
        % (m.group("k"), m.group("k"), m.group("inner")), inter)
    drawers = extract_drawers(inter)

    defaults = {}
    tokenised = port(src, defaults_out=defaults)
    copy_reg = extract_copy(tokenised)

    os.makedirs(OUT_MORE, exist_ok=True)
    defaults_dir = os.path.join(PKG, "templates", "defaults")
    os.makedirs(defaults_dir, exist_ok=True)
    for name, markup in defaults.items():
        with open(os.path.join(defaults_dir, name + ".html"), "w",
                  encoding="utf-8") as fh:
            fh.write(markup)
    with open(OUT_PAGE, "w", encoding="utf-8") as fh:
        fh.write(tokenised)
    for key, d in drawers.items():
        with open(os.path.join(OUT_MORE, key + ".html"), "w", encoding="utf-8") as fh:
            fh.write("<!-- title: %s -->\n%s" % (d["title"], d["body"]))
    with open(OUT_COPY, "w", encoding="utf-8") as fh:
        json.dump({"_note": "key -> DEFAULT string, extracted verbatim from the "
                            "approved v6 mock by tokenise_v2. The dashboard edits "
                            "overrides against these keys; the renderer swaps "
                            "default -> override. Never edit defaults here — they "
                            "must keep matching the template.", **copy_reg},
                  fh, ensure_ascii=False, indent=2)
    print("ported: %s (%d bytes), %d drawers, %d copy keys, %d block defaults"
          % (OUT_PAGE, len(tokenised), len(drawers), len(copy_reg), len(defaults)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
