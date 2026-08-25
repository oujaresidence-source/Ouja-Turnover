# -*- coding: utf-8 -*-
"""
monthly.quote_render — the 4-page owner PDF for «التسعير الشهري».

A NEW RENDERER, NOT THE FROZEN ONE. owner_report/renderer/ouja_render.py is
pixel-frozen, CI-gated, and renders a 17-page half-year performance report — a
different document from a one-unit monthly-price justification. We copy its
APPROACH (base64 fonts embedded at render time, Playwright to PDF, A4 geometry,
inline SVG only) and never its file.

Written in Python 3.9-compatible syntax ON PURPOSE. The frozen renderer uses
3.12+ f-strings and cannot even be compiled on this machine, so it can only be
tested where it is deployed. This one renders and layout-audits locally, which is
the difference between finding a broken PDF here and finding it in an owner's
inbox.

Arabic is shaped by Chromium natively. Do NOT reach for arabic-reshaper or
python-bidi here — those belong to the fpdf2 path elsewhere in this repo, and
mixing them double-shapes the text and reverses it.

Every chart is inline SVG. No image files, no chart library, no external request:
the PDF must render identically offline.

THE LAYOUT CONTRACT: .page wrappers, a .rf footer on each, .cover on page 1.
owner_report's audit_layout.assert_clean is reused UNCHANGED against that markup,
so real data cannot quietly push content past the footer.
"""

import base64
import os
import pathlib

_FONT_DIR = pathlib.Path(__file__).resolve().parent.parent / "owner_report" / "renderer" / "fonts"

_FONTS = [
    ("IBM Plex Sans Arabic", "IBMPlexSansArabic-Regular.woff2", 400),
    ("IBM Plex Sans Arabic", "IBMPlexSansArabic-Medium.woff2", 500),
    ("IBM Plex Sans Arabic", "IBMPlexSansArabic-SemiBold.woff2", 600),
    ("IBM Plex Sans Arabic", "IBMPlexSansArabic-Bold.woff2", 700),
    ("IBM Plex Sans", "IBMPlexSans-Regular.woff2", 400),
    ("IBM Plex Sans", "IBMPlexSans-SemiBold.woff2", 600),
    ("IBM Plex Sans", "IBMPlexSans-Bold.woff2", 700),
]


def _font_css():
    out = []
    for family, fname, weight in _FONTS:
        p = _FONT_DIR / fname
        if not p.exists():
            continue
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        out.append(
            "@font-face{font-family:'%s';font-style:normal;font-weight:%d;"
            "font-display:block;src:url(data:font/woff2;base64,%s) format('woff2')}"
            % (family, weight, b64))
    return "".join(out)


def _e(s):
    return (str("" if s is None else s).replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def _sar(v):
    if v is None:
        return "—"
    return "{:,}".format(int(round(float(v))))


_MONTHS_AR = {1: "يناير", 2: "فبراير", 3: "مارس", 4: "أبريل", 5: "مايو", 6: "يونيو",
              7: "يوليو", 8: "أغسطس", 9: "سبتمبر", 10: "أكتوبر", 11: "نوفمبر",
              12: "ديسمبر"}


def _month_ar(key):
    try:
        y, m = str(key).split("-")
        return "%s %s" % (_MONTHS_AR.get(int(m), key), y)
    except (ValueError, AttributeError):
        return str(key)


def _measured(p):
    """Did the quality model actually measure anything? ONE definition, used by
    the cover sentence, by page 2's gate state, and by page 4 — so they cannot
    disagree. The cover claiming «بمواصفاتها» while page 4 says «0 من 16» is the
    sentence an owner quotes back at you."""
    return abs(((p.get("quality") or {}).get("mult") or 1.0) - 1.0) > 1e-9


def _bound_sentence(p):
    b = p.get("bound_by")
    if b == "floor":
        return "هذا أقل سعر يغطي تكلفة تشغيل الوحدة مقارنة بالتأجير اليومي"
    if b == "ceiling":
        return ("أقل من تكلفة حجز 30 ليلة منفصلة — وهذا ما يجعل العرض الشهري "
                "منطقياً للضيف")
    if b == "model":
        if _measured(p):
            return "هذا ما تستحقه الوحدة بمواصفاتها وأداء الحي"
        # No attributes scored: the model gate IS the comparable-units average.
        return ("هذا ما تحققه الوحدات المماثلة في نفس الحي — مواصفات هذه الوحدة "
                "لم تُسجَّل بعد")
    return ""

_BASIS_AR = {
    "own_history": "محسوب من حجوزات هذه الوحدة نفسها في نفس الشهر من السنوات السابقة",
    "district_pool": "محسوب من متوسط وحدات الحي — لا من سجل هذه الوحدة",
    "bedroom_pool": "محسوب من متوسط الوحدات المماثلة في الحجم — لا من سجل هذه الوحدة",
    "insufficient": "لا توجد بيانات كافية",
}

_CONF_AR = {"high": "عالية", "medium": "متوسطة", "low": "منخفضة",
            "insufficient": "غير كافية"}


# ─────────────────────────────── the charts ───────────────────────────────

# A chart label that needs an ellipsis is too long for its space. These are the
# SHORT forms for the PDF's narrow label column; the screen keeps the full text.
# A test asserts every one of them fits without clipping.
CHART_LABEL_MAX = 38

_SHORT_AR = {
    "turnover_cost": "تنظيف بين الحجوزات",
    "channel_fee": "عمولة المنصات",
    "monthly_cost": "تشغيل شهري: كهرباء، نت، تنظيفة",
    "margin": "الحد الأدنى لهامشنا",
    "quality_uplift": "فرق مواصفات الوحدة",
    "pool_above_floor": "فرق الوحدات المماثلة عن الأرضية",
    "ceiling_cap": "وقف عند السقف",
    "rounding": "تقريب لأقرب 50 ريال",
    "nightly_net_zero": "اليومي ما يغطي تكلفته",
    "model_base": "سعر الوحدة حسب حيّها",
}


def chart_label(component):
    """The short form when there is one, otherwise the full label."""
    return _SHORT_AR.get(component.get("key")) or (component.get("label_ar") or "")


def _clip(txt, n):
    t = str(txt or "")
    return t if len(t) <= n else (t[:n - 1].rstrip() + "…")


def _svg_gates(p):
    """The three gates, and which one bound. Inline SVG, no library."""
    g = p.get("gates") or {}
    rows = [("الأرضية", g.get("floor"), "floor"),
            ("المواصفات", g.get("model"), "model"),
            ("السقف", g.get("ceiling"), "ceiling")]
    vals = [v for (_l, v, _k) in rows if v]
    if not vals:
        return ""
    mx = max(vals) * 1.08
    measured = abs(((p.get("quality") or {}).get("mult") or 1.0) - 1.0) > 1e-9
    bar_h, gap, pad_r = 30, 16, 132
    h = len(rows) * (bar_h + gap) + 8
    out = ['<svg class="chart" viewBox="0 0 640 %d" width="100%%" height="%d" '
           'role="img" aria-label="البوابات الثلاث">' % (h, h)]
    y = 4
    for label, val, key in rows:
        w = int(round((val or 0) / mx * (640 - pad_r - 96))) if val else 0
        dead = (key == "model" and not measured)
        fill = "#DFD8C8" if dead else ("#8B6320" if key == p.get("bound_by") else "#E9E4D7")
        out.append('<text x="636" y="%d" text-anchor="end" class="sl">%s</text>'
                   % (y + 20, label))
        out.append('<rect x="%d" y="%d" width="%d" height="%d" rx="6" fill="%s"/>'
                   % (540 - w, y, max(w, 2), bar_h, fill))
        out.append('<text x="96" y="%d" text-anchor="start" class="sv%s">%s</text>'
                   % (y + 20, " dead" if dead else "", _sar(val)))
        y += bar_h + gap
    out.append("</svg>")
    return "".join(out)


def _svg_waterfall(p):
    """The steps, ending exactly on the number at the top of page 1."""
    comps = p.get("components") or []
    if not comps:
        return ""
    price = p.get("price") or 0
    running, pts = 0.0, []
    for c in comps:
        start = running
        running += c.get("sar") or 0
        pts.append((c, start, running))
    mx = max([abs(v) for (_c, _s, v) in pts] + [abs(price), 1.0]) * 1.05
    row_h, h = 38, len(pts) * 38 + 52
    out = ['<svg class="chart" viewBox="0 0 640 %d" width="100%%" height="%d" '
           'role="img" aria-label="من أين جاء الرقم">' % (h, h)]
    y = 2
    for c, start, end in pts:
        lo, hi = (min(start, end), max(start, end))
        x1 = 372 - int(round(hi / mx * 268))
        x2 = 372 - int(round(lo / mx * 268))
        neg = (c.get("sar") or 0) < 0
        out.append('<text x="636" y="%d" text-anchor="end" class="wl">%s</text>'
                   % (y + 23, _e(_clip(chart_label(c), CHART_LABEL_MAX))))
        out.append('<rect x="%d" y="%d" width="%d" height="19" rx="4" fill="%s"/>'
                   % (x1, y + 9, max(x2 - x1, 2), "#B3382A" if neg else "#8B6320"))
        out.append('<text x="8" y="%d" text-anchor="start" class="wv%s">%s</text>'
                   % (y + 23, " neg" if neg else "", _sar(c.get("sar"))))
        y += row_h
    out.append('<line x1="8" y1="%d" x2="632" y2="%d" stroke="#C8BFA9" stroke-width="1"/>'
               % (y + 6, y + 6))
    out.append('<text x="636" y="%d" text-anchor="end" class="wt">التقدير الشهري</text>'
               % (y + 32))
    out.append('<text x="8" y="%d" text-anchor="start" class="wt">%s</text>'
               % (y + 32, _sar(price)))
    out.append("</svg>")
    return "".join(out)


# ─────────────────────────────── the pages ───────────────────────────────

def _footer(n, unit_name, month_key):
    return ('<div class="rf"><span>%s · %s</span><span>عوجا · صفحة %d من 4</span></div>'
            % (_e(unit_name), _e(_month_ar(month_key)), n))


def _page1(p, cfg):
    price = p.get("price")
    return (
        '<div class="page cover">'
        '<div class="mark">عوجا</div>'
        '<div class="c-mid">'
        '<div class="c-unit">%s</div>'
        '<div class="c-meta">%s%s</div>'
        '<div class="c-month">تقدير الإيجار الشهري · %s</div>'
        '<div class="c-price">%s <span>ريال / شهر</span></div>'
        '<div class="c-tag">%s</div>'
        '<div class="c-bound">%s</div>'
        '%s</div>%s</div>'
        % (_e(p.get("name") or ""),
           _e(p.get("public_name") or p.get("district") or ""),
           (" · %s" % _e(p.get("district"))) if p.get("public_name") and p.get("district") else "",
           _e(_month_ar(p.get("month"))),
           _sar(price),
           _e(p.get("label_ar") or "تقدير"),
           _e(_bound_sentence(p)),
           _cover_zero_nights(p),
           _footer(1, p.get("name") or "", p.get("month"))))


def _cover_zero_nights(p):
    """Zero of our own nights, with a confident number above it, is the first
    thing an owner should read — not row two of a table on page 4."""
    d = p.get("data") or {}
    if (d.get("own_obs") or 0) > 0:
        return ""
    basis = p.get("basis")
    where = ("متوسط وحدات الحي" if basis == "district_pool"
             else "متوسط الوحدات المماثلة في الحجم" if basis == "bedroom_pool"
             else "وحدات مماثلة")
    return ('<div class="c-zero">ما عندنا ولا ليلة مرصودة لهالوحدة بهذا الشهر — '
            'الرقم من %s.</div>' % _e(where))


def _page2(p, cfg):
    measured = abs(((p.get("quality") or {}).get("mult") or 1.0) - 1.0) > 1e-9
    note = ""
    if not measured:
        note = ('<div class="warn">بوابة «المواصفات» غير مفعّلة لهذه الوحدة: لم '
                'تُسجَّل مواصفاتها بعد، فيتطابق حسابها مع دخل التأجير اليومي ولا '
                'يمثل تقييماً مستقلاً.</div>')
    return (
        '<div class="page">'
        '<h2>ما الذي حدّد الرقم</h2>'
        '<p class="lede">السعر الشهري يقع بين ثلاثة حدود. الرقم المعروض هو الحد '
        'الذي فرض نفسه، لا متوسطاً بينها.</p>'
        '%s'
        '<div class="legend">'
        '<div><b>الأرضية</b>ما يغطي تكلفة التشغيل مقارنة بالتأجير اليومي. تحتها خسارة.</div>'
        '<div><b>المواصفات</b>ما تستحقه الوحدة بمواصفاتها وأداء حيّها.</div>'
        '<div><b>السقف</b>أقل من تكلفة حجز 30 ليلة منفصلة، وإلا فلا سبب لاختيار الشهري.</div>'
        '</div>'
        '%s%s%s</div>'
        % (note, _svg_gates(p), _gap_band(p),
           _footer(2, p.get("name") or "", p.get("month"))))


def _gap_band(p):
    """What the distance between the gates means in riyals — the half of page 2
    that was empty, and the question an owner asks next."""
    g = p.get("gates") or {}
    price, fl, ce = p.get("price"), g.get("floor"), g.get("ceiling")
    if price is None:
        return ""
    bits = []
    if fl:
        bits.append('<div><b>%s ريال</b><span>فوق الأرضية — هامش الأمان قبل أن '
                    'يصبح التأجير الشهري أسوأ من اليومي</span></div>'
                    % _sar(price - fl))
    if ce:
        bits.append('<div><b>%s ريال</b><span>تحت السقف — ما يوفّره الضيف مقابل '
                    'الالتزام بشهر كامل بدلاً من 30 ليلة منفصلة</span></div>'
                    % _sar(ce - price))
    if not bits:
        return ""
    return '<div class="gapband">%s</div>' % "".join(bits)


def _page3(p, cfg):
    return (
        '<div class="page">'
        '<h2>من أين جاء الرقم</h2>'
        '<p class="lede">كل خطوة بالريال. المجموع يساوي الرقم المكتوب على الغلاف '
        'تماماً — لا تقريب ولا بند مخفي.</p>'
        '%s'
        '<div class="note3">السطران بالأحمر هما ما يدفعه التأجير <b>اليومي</b> '
        'ولا يدفعه الشهري: تنظيف متكرر بين كل حجز وحجز، وعمولة منصات الحجز. '
        'التأجير الشهري يدفع تنظيفة واحدة ولا يدفع عمولة عند التأجير المباشر — '
        'وهذا هو الفرق الذي يسمح بسعر أقل للضيف دون أن نخسر.</div>'
        '%s</div>'
        % (_svg_waterfall(p), _footer(3, p.get("name") or "", p.get("month"))))


def _page4(p, cfg):
    d = p.get("data") or {}
    q = p.get("quality") or {}
    mc = p.get("market_context") or {}
    be = p.get("breakeven") or {}
    rows = [
        ("أساس الحساب", _BASIS_AR.get(p.get("basis"), "—")),
        ("ليالي حجوزاتنا المرصودة لهذه الوحدة", str(d.get("own_obs") or 0)),
        ("متوسط سعر الليلة المتوقع", _sar(d.get("adr")) + " ريال"),
        ("نسبة الإشغال المتوقعة", ("%d%%" % round((d.get("occ") or 0) * 100))),
        ("درجة الثقة", _CONF_AR.get(p.get("confidence"), "—")),
        ("صفات الوحدة غير المسجّلة", "%d من 16" % (q.get("unanswered") or 0)),
        ("تكلفة التنظيفة المستخدمة", _e(cfg.get("turnover_note") or "—")),
    ]
    if be.get("months_let"):
        rows.append(("عدد الأشهر المؤجَّرة شهرياً لمعادلة سنة تأجير يومي",
                     "%.1f شهر" % be["months_let"]))
    if mc.get("available"):
        rows.append(("الإيجار السنوي المسجّل في الحي (للمقارنة فقط)",
                     _sar(mc.get("annual_rent")) + " ريال · أي " +
                     _sar(mc.get("annual_equivalent_month")) + " شهرياً"))
    body = "".join('<tr><td>%s</td><td class="v">%s</td></tr>' % (_e(a), _e(b))
                   for a, b in rows)
    return (
        '<div class="page">'
        '<h2>الافتراضات والمصادر</h2>'
        '<p class="lede">كل رقم في هذا الملف مبني على ما يلي. ما لا نعرفه مكتوب '
        'كما هو، لا مُقدَّراً.</p>'
        '<table class="assump"><tbody>%s</tbody></table>'
        '<div class="disclaim">'
        '<b>هذا تقدير، لا عرض سعر.</b> محسوب من حجوزات عوجا نفسها، ولم يُختبر بعد '
        'مقابل حجوزات شهرية فعلية بعدد كافٍ. الأرقام لا تشمل ضريبة القيمة المضافة. '
        'ما يغيّره: تسجيل مواصفات الوحدة، وتراكم حجوزات شهرية حقيقية يُقاس عليها.'
        '</div>%s</div>'
        % (body, _footer(4, p.get("name") or "", p.get("month"))))


def _watermark(cfg):
    """Stamped on every page while the cleaning cost is still the placeholder.
    A file that admits on page 4 that its inputs are provisional should not be
    sendable without saying so on every page. It disappears by itself the moment
    a real per-clean cost is set — nobody has to remember to remove it."""
    if not cfg.get("draft"):
        return ""
    return '<div class="wm">مسودة — أرقام غير نهائية</div>'


def build_html(p, cfg=None):
    """The assembled 4-page document. cfg carries render-time notes only."""
    cfg = cfg or {}
    return (
        '<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">'
        '<title>%s · %s</title><style>%s%s</style></head><body>%s%s%s%s</body></html>'
        % (_e(p.get("name") or ""), _e(_month_ar(p.get("month"))),
           _font_css(), _CSS,
           _stamp(_page1(p, cfg), cfg, '<div class="page cover">'),
           _stamp(_page2(p, cfg), cfg, '<div class="page">'),
           _stamp(_page3(p, cfg), cfg, '<div class="page">'),
           _stamp(_page4(p, cfg), cfg, '<div class="page">')))


def _stamp(page_html, cfg, opener):
    """Put the watermark INSIDE the page div — appended after it, position:absolute
    would resolve against the body and land on page 1 only."""
    wm = _watermark(cfg)
    if not wm:
        return page_html
    return page_html.replace(opener, opener + wm, 1)


_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#fff;color:#17150F;font-family:'IBM Plex Sans Arabic',sans-serif;
  -webkit-print-color-adjust:exact;print-color-adjust:exact}
.page{position:relative;width:210mm;height:297mm;padding:20mm 18mm 18mm;
  background:#FAF8F2;overflow:hidden;page-break-after:always}
.page:last-child{page-break-after:auto}
.rf{position:absolute;bottom:11mm;left:18mm;right:18mm;display:flex;
  justify-content:space-between;font-size:8.5pt;color:#736C5C;
  border-top:1px solid #DFD8C8;padding-top:6px}
h2{font-size:20pt;font-weight:700;letter-spacing:-.4px;margin-bottom:5mm}
.lede{font-size:11pt;color:#4A4339;line-height:1.7;max-width:150mm;margin-bottom:8mm}
.cover{background:#17150F;color:#FAF8F2}
.cover .rf{color:#8B8272;border-top-color:#3A362C}
.mark{font-size:13pt;font-weight:700;color:#C9A227;letter-spacing:2px}
.c-mid{position:absolute;top:52%;transform:translateY(-50%);right:18mm;left:18mm}
.c-unit{font-size:22pt;font-weight:600;line-height:1.3}
.c-meta{font-size:11pt;color:#A79E8C;margin-top:2mm}
.c-month{font-size:11pt;color:#C9A227;margin-top:12mm;font-weight:600}
.c-price{font-family:'IBM Plex Sans',sans-serif;font-size:58pt;font-weight:700;
  letter-spacing:-3px;line-height:1.05;margin-top:2mm;direction:ltr;text-align:right}
.c-price span{font-family:'IBM Plex Sans Arabic',sans-serif;font-size:13pt;
  font-weight:500;color:#A79E8C;letter-spacing:0}
.c-tag{display:inline-block;margin-top:4mm;padding:2mm 5mm;border:1px solid #C9A227;
  color:#C9A227;border-radius:99px;font-size:10pt;font-weight:600}
.c-bound{font-size:12pt;color:#D8D2C4;margin-top:8mm;max-width:135mm;line-height:1.7}
.c-zero{margin-top:6mm;padding:4mm 5mm;border-radius:8px;background:#3A2A24;
  border:1px solid #6B4A3E;color:#F0C9BE;font-size:10.5pt;line-height:1.6;
  max-width:135mm}
/* Height stops well above the footer ON PURPOSE: audit_layout flags any direct
   child of .page whose bottom passes the footer line, and a full-bleed overlay
   would fail the gate it exists to sit behind. */
.wm{position:absolute;top:0;left:0;right:0;height:250mm;pointer-events:none;
  display:flex;align-items:center;justify-content:center}
.wm::before{content:"مسودة — أرقام غير نهائية";font-size:34pt;font-weight:700;
  color:rgba(179,56,42,.13);transform:rotate(-24deg);white-space:nowrap;
  letter-spacing:2px}
.legend{display:grid;gap:3mm;margin-bottom:8mm}
.legend div{font-size:10pt;color:#4A4339;line-height:1.6;
  border-inline-start:3px solid #DFD8C8;padding-inline-start:4mm}
.legend b{display:block;font-size:11pt;color:#17150F;margin-bottom:1mm}
.warn{background:#FBE7E3;border:1px solid #E8BDB5;color:#B3382A;border-radius:8px;
  padding:4mm 5mm;font-size:10pt;line-height:1.6;margin-bottom:7mm}
/* direction:ltr on the SVG makes text-anchor PHYSICAL. Inside dir="rtl" the
   start/end anchors are LOGICAL and flip, so a label anchored "end" at x=636
   extends rightward past the viewBox instead of leftward — 19 clipped labels
   on the first render, caught by owner_report's own layout gate. The Arabic
   text runs still shape and order correctly: bidi handles that inside the run,
   independently of the element's direction. */
.chart{display:block;margin:0 auto;direction:ltr}
.sl{font-family:'IBM Plex Sans Arabic',sans-serif;font-size:12px;fill:#17150F;font-weight:600}
.sv{font-family:'IBM Plex Sans',sans-serif;font-size:13px;fill:#17150F;font-weight:700}
.sv.dead{fill:#736C5C;text-decoration:line-through}
.wl{font-family:'IBM Plex Sans Arabic',sans-serif;font-size:11px;fill:#4A4339}
.wv{font-family:'IBM Plex Sans',sans-serif;font-size:12px;fill:#17150F;font-weight:600}
.wv.neg{fill:#B3382A}
.wt{font-family:'IBM Plex Sans',sans-serif;font-size:14px;fill:#17150F;font-weight:700}
.gapband{display:grid;grid-template-columns:1fr 1fr;gap:5mm;margin-top:10mm}
.gapband div{background:#F3F0E8;border:1px solid #DFD8C8;border-radius:9px;
  padding:5mm 6mm}
.gapband b{display:block;font-family:'IBM Plex Sans',sans-serif;font-size:17pt;
  font-weight:700;color:#6F4F18;direction:ltr;text-align:right;margin-bottom:2mm}
.gapband span{display:block;font-size:9.5pt;color:#4A4339;line-height:1.65}
.note3{margin-top:9mm;background:#F3F0E8;border-inline-start:3px solid #8B6320;
  border-radius:0 9px 9px 0;padding:5mm 6mm;font-size:10pt;line-height:1.75;color:#4A4339}
.note3 b{color:#17150F}
table.assump{width:100%;border-collapse:collapse;font-size:10.5pt}
table.assump td{padding:3.4mm 2mm;border-bottom:1px solid #DFD8C8;color:#4A4339;
  vertical-align:top}
table.assump td.v{text-align:left;font-family:'IBM Plex Sans',sans-serif;
  color:#17150F;font-weight:600;direction:ltr;white-space:nowrap}
.disclaim{margin-top:9mm;background:#F5ECD8;border:1px solid #E3D3AC;border-radius:9px;
  padding:5mm 6mm;font-size:10pt;line-height:1.75;color:#4A4339}
.disclaim b{color:#6F4F18}
"""


def render(payload, out_pdf, cfg=None):
    """Render to PDF and return (pdf_path, html_path, violations).

    The HTML is written beside the PDF — the same side-effect contract the frozen
    renderer uses — so audit_layout runs on the EXACT markup that was printed,
    not on a re-render that might differ.
    """
    html = build_html(payload, cfg)
    out_pdf = str(out_pdf)
    html_path = os.path.splitext(out_pdf)[0] + "_quote.html"
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(html)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page()
        pg.set_content(html, wait_until="networkidle")
        pg.pdf(path=out_pdf, format="A4", print_background=True,
               margin={"top": "0", "right": "0", "bottom": "0", "left": "0"})
        b.close()

    violations = audit(html)
    return out_pdf, html_path, violations


def audit(html):
    """owner_report's layout gate, reused UNCHANGED. Zero violations or the PDF
    does not reach an owner."""
    import sys
    d = str((pathlib.Path(__file__).resolve().parent.parent /
             "owner_report" / "renderer"))
    if d not in sys.path:
        sys.path.insert(0, d)
    from audit_layout import audit_html
    return audit_html(html)
