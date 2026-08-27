# -*- coding: utf-8 -*-
"""
cp/tools/build_pdf.py — the PDF profile, from the page's own material.

Six sections the owner asked for: who we are, the beginning, mission and
vision, who we serve, our reviews, the operating model.

Three rules carried over from the page, because a PDF that contradicts the
page is worse than no PDF:

  * FIGURES ARE TOKENS. Every number is __NAME__ filled from cp.stats at build
    time, so the document cannot drift from /cp/ar. Rebuild it and the numbers
    move with the page.
  * COPY IS VERBATIM where it exists. The audience doors, the reviews, the
    operating steps and the closing are lifted from the approved page and its
    drawers, not rewritten for print. What is authored (the «من نحن» framing
    and the mission/vision draft) lives in cp_pdf_ar.json where it can be
    reviewed in one place.
  * THE GUARD RUNS. The assembled HTML is scanned before a single page is
    rendered; a withheld figure aborts the build.

Design tokens, fonts and the palette come from templates/ar_v2.html itself, so
the PDF is the page in print, not a lookalike.

Run:  python3 -m cp.tools.build_pdf            (writes cp/assets/profile-ar.pdf)
"""
import html as _html
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
ROOT = os.path.dirname(PKG)
OUT_PDF = os.path.join(PKG, "assets", "profile-ar.pdf")
OUT_HTML = os.path.join(PKG, "templates", "pdf_ar.html")

sys.path.insert(0, ROOT)
from cp import guard, page_v2, stats  # noqa: E402


def _e(s):
    return _html.escape(str(s if s is not None else ""), quote=True)


def read_json(name):
    with open(os.path.join(PKG, "data", name), encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        return {k: v for k, v in data.items() if not k.startswith("_")}
    return data


def design_tokens():
    """The :root block from the live template — one source for the palette."""
    tpl = page_v2.TEMPLATE
    m = re.search(r":root\{(.*?)\}", tpl, re.S)
    return m.group(1).strip() if m else ""


def font_faces():
    """file:// urls so a local Chromium embeds the real faces into the PDF."""
    fonts = os.path.join(ROOT, "fonts")
    def url(name):
        return "file://" + os.path.join(fonts, name)
    out = []
    for w, f in ((400, "ThmanyahDisplay-400.woff2"), (500, "ThmanyahDisplay-500.woff2"),
                 (700, "ThmanyahDisplay-700.woff2")):
        out.append('@font-face{font-family:"Thmanyah Display";font-weight:%s;'
                   'src:url("%s") format("woff2")}' % (w if w != 500 else "500 600", url(f)))
    for w, f in ((300, "Almarai-300.woff2"), (400, "Almarai-400.woff2"),
                 (700, "Almarai-700.woff2")):
        out.append('@font-face{font-family:"Almarai";font-weight:%d;'
                   'src:url("%s") format("woff2")}' % (w, url(f)))
    return "\n".join(out)


CSS = """
*{box-sizing:border-box}
@page{size:A4;margin:0}
html,body{margin:0;padding:0;background:var(--white);color:var(--ink);
  font-family:var(--sans);font-size:11pt;line-height:1.85;direction:rtl}
h1,h2,h3{margin:0;font-family:var(--serif);font-weight:600;text-wrap:balance}
p{margin:0 0 10pt}
.num{font-variant-numeric:tabular-nums}
.page{width:210mm;min-height:297mm;padding:18mm 16mm;page-break-after:always;
  position:relative;background:var(--white)}
.page:last-child{page-break-after:auto}
.cover{background:var(--beige);display:flex;flex-direction:column;justify-content:center}
.cover .mark{width:34mm;margin-bottom:12mm}
.cover h1{font-size:34pt;line-height:1.25;letter-spacing:-.01em}
.cover .sub{font-family:var(--serif);font-size:15pt;color:var(--mute);margin-top:3mm}
.cover .line{font-size:12pt;line-height:1.9;color:var(--ink2);margin-top:12mm;max-width:135mm}
.cover .stamp{position:absolute;bottom:18mm;font-size:9pt;color:var(--mute)}
.eyebrow{font-size:9pt;letter-spacing:.06em;color:var(--mute);margin-bottom:3mm}
h2{font-size:21pt;line-height:1.4;margin-bottom:6mm}
.lede{font-size:12pt;line-height:1.9;color:var(--ink2);margin-bottom:7mm;max-width:150mm}
.rule{height:1px;background:var(--line);margin:7mm 0}
.figs{display:grid;grid-template-columns:repeat(4,1fr);gap:4mm;margin:6mm 0}
.fig{border:1px solid var(--line);border-radius:3mm;padding:4mm}
.fig .v{font-family:var(--serif);font-weight:700;font-size:17pt;line-height:1}
.fig .k{font-size:8.5pt;color:var(--mute);margin-top:2mm;line-height:1.5}
.two{display:grid;grid-template-columns:1fr 1fr;gap:6mm}
.card{border:1px solid var(--line);border-radius:3mm;padding:5mm;background:var(--white)}
.card b{font-family:var(--serif);font-size:12pt;font-weight:600;display:block;margin-bottom:2mm}
.card span{font-size:10pt;color:var(--ink2);line-height:1.8}
ol.steps{margin:0;padding:0;list-style:none;counter-reset:s}
ol.steps li{counter-increment:s;position:relative;padding-inline-start:11mm;margin-bottom:5mm}
ol.steps li::before{content:counter(s);position:absolute;inset-inline-start:0;top:0;
  width:7mm;height:7mm;border-radius:50%;background:var(--black);color:var(--white);
  font-size:9pt;display:flex;align-items:center;justify-content:center;font-family:var(--sans)}
ol.steps b{font-family:var(--serif);font-size:11.5pt;font-weight:600;display:block}
ol.steps span{font-size:10pt;color:var(--ink2)}
.q{border-inline-start:2px solid var(--black);padding-inline-start:5mm;margin-bottom:6mm}
.q p{font-family:var(--serif);font-size:11.5pt;line-height:1.75;margin:0 0 2mm}
.q .who{font-size:9pt;color:var(--mute)}
.q.crit{border-color:var(--ochre,#8a6a34)}
.dark{background:var(--black);color:var(--white)}
.dark h2{color:var(--white)}
.dark .lede{color:#BDB5A8}
.foot{position:absolute;bottom:12mm;inset-inline-start:16mm;inset-inline-end:16mm;
  font-size:8pt;color:var(--mute);border-top:1px solid var(--line);padding-top:3mm}
.dark .foot{color:#8F877A;border-color:var(--line-dark,#3A3631)}
.pill{display:inline-block;font-size:8.5pt;color:var(--mute);border:1px solid var(--line);
  border-radius:99px;padding:1mm 3mm;margin-inline-start:2mm}
"""


def build_html():
    copy = read_json("cp_pdf_ar.json")
    cells = stats.load(snapshot=None)
    reviews = read_json("cp_reviews.json")
    # The doors come from the SAME block the page renders, not the older v1
    # extraction — otherwise the printed profile and the live page disagree on
    # what the company offers, which is worse than having no PDF at all.
    doors = [{"h3": a, "p": b} for a, b in re.findall(
        r'<b>(.*?)</b><span>(.*?)</span>', page_v2.DEFAULT_BLOCKS["doors"], re.S)]

    def f(field):
        return stats.fmt(field, cells[field]["value"])

    tokens = {
        "__RESIDENCES__": f("residences_total"),
        "__RESERVATIONS__": f("reservations_total"),
        "__NIGHTS__": f("nights_total"),
        "__REVIEWS__": f("reviews_total"),
        "__RATING__": f("rating_avg"),
        "__PERFECT__": f("perfect_ten_pct"),
        "__OCC__": f("occupancy_pct"),
        "__SAUDI__": f("saudi_guest_pct"),
        "__SAMEDAY__": f("same_day_booking_pct"),
        "__REPEAT_GUESTS__": f("repeat_guests"),
        "__REPEAT_PCT__": f("repeat_booking_pct"),
        "__RESPONSE__": f("median_response_minutes"),
        "__CAPACITY__": f("designed_capacity_residences"),
        "__AS_OF_AR__": page_v2._ar_month_year(
            stats.sync_stamp(snapshot=None)["as_of"]),
    }

    def t(key):
        s = copy.get(key, "")
        for k, v in tokens.items():
            s = s.replace(k, str(v))
        return s

    logo = os.path.join(PKG, "assets", "logo-mark.png")
    if not os.path.exists(logo):
        logo = os.path.join(PKG, "assets", "logo.png")
    logo_tag = ('<img class="mark" src="file://%s" alt="">' % logo) \
        if os.path.exists(logo) else ""

    # cover
    pages = ['<div class="page cover">%s<h1>%s</h1><div class="sub">%s</div>'
             '<p class="line">%s</p><div class="stamp">%s</div></div>'
             % (logo_tag, _e(t("cover_title")), _e(t("cover_sub")),
                _e(t("cover_line")), _e(t("cover_stamp")))]

    # 1 who we are + 2 the beginning
    figs = '<div class="figs">' + "".join('<div class="fig"><div class="v num">%s</div><div class="k">%s</div></div>'
                   % (v, _e(k)) for v, k in (
                       (tokens["__RESERVATIONS__"], "حجزاً مكتملاً"),
                       (tokens["__NIGHTS__"], "ليلة ضيافة"),
                       (tokens["__RATING__"], "من 5 · عبر %s مراجعة" % tokens["__REVIEWS__"]),
                       (tokens["__SAUDI__"] + "%", "من ضيوفنا سعوديون"))) + "</div>"
    pages.append(
        '<div class="page"><p class="eyebrow">%s</p><h2>%s</h2>'
        '<p class="lede">%s</p><p>%s</p><p>%s</p>%s<div class="rule"></div>'
        '<p class="eyebrow">%s</p><h2>%s</h2><p>%s</p><p>%s</p><p>%s</p>'
        '<div class="foot">%s</div></div>'
        % (_e("الملف التعريفي"), _e(t("s1_title")), _e(t("s1_p1")), _e(t("s1_p2")),
           _e(t("s1_p3")), figs, _e("كيف بدأنا"), _e(t("s2_title")), _e(t("s2_p1")),
           _e(t("s2_p2")), _e(t("s2_p3")), _e(t("footer_note"))))

    # 3 mission and vision
    pages.append(
        '<div class="page"><p class="eyebrow">%s</p><h2>%s</h2>'
        '<div class="two"><div class="card"><b>%s</b><span>%s</span></div>'
        '<div class="card"><b>%s</b><span>%s</span></div></div>'
        '<div class="foot">%s</div></div>'
        % (_e("ما نعمل من أجله"), _e(t("s3_title")),
           _e(t("s3_mission_k")), _e(t("s3_mission")),
           _e(t("s3_vision_k")), _e(t("s3_vision")),
           _e(t("footer_note"))))

    pages.append(
        '<div class="page"><p class="eyebrow">%s</p><h2>%s</h2><p class="lede">%s</p>%s'
        '<div class="foot">%s</div></div>'
        % (_e("من نخدم"), _e(t("s4_title")), _e(t("s4_lede")),
           '<div class="two">' + "".join(
               '<div class="card"><b>%s</b><span>%s</span></div>'
               % (d.get("h3", ""), re.sub(r"__[A-Z_]+__",
                                          lambda m: str(tokens.get(m.group(0), "")),
                                          d.get("p", "")))
               for d in doors) + "</div>",
           _e(t("footer_note"))))

    # 5 reviews
    qs = []
    for r in reviews:
        if not (r.get("text_original") or "").strip():
            continue
        crit = " crit" if "العزل" in r["text_original"] else ""
        ltr = ' dir="ltr" style="text-align:left"' if r.get("language") == "en" else ""
        qs.append('<div class="q%s"><p%s>«%s»</p><div class="who">%s · %s · %s</div></div>'
                  % (crit, ltr, _e(r["text_original"]), _e(r.get("guest_name", "")),
                     _e(r.get("listing_name", "")), _e(r.get("date", ""))))
    pages.append(
        '<div class="page"><p class="eyebrow">%s</p><h2>%s</h2><p class="lede">%s</p>%s'
        '<p class="lede" style="font-size:10pt">%s</p><div class="foot">%s</div></div>'
        % (_e("بكلماتهم · منشورة كما كُتبت"), _e(t("s5_title")), _e(t("s5_lede")),
           "".join(qs), _e(t("s5_foot")), _e(t("footer_note"))))

    # 6 operating model — the stay steps, verbatim from the drawer
    steps = re.findall(r"<li><div><b>(.*?)</b><span>(.*?)</span></div></li>",
                       page_v2.MORE.get("stay", ""), re.S)
    steps_html = "".join('<li><b>%s</b><span>%s</span></li>'
                         % (a, re.sub(r"__[A-Z_]+__",
                                      lambda m: str(tokens.get(m.group(0), "")), b))
                         for a, b in steps)
    pages.append(
        '<div class="page"><p class="eyebrow">%s</p><h2>%s</h2><p class="lede">%s</p>'
        '<ol class="steps">%s</ol><p class="lede" style="font-size:10pt">%s</p>'
        '<div class="foot">%s</div></div>'
        % (_e("كيف نُشغّل"), _e(t("s6_title")), _e(t("s6_lede")), steps_html,
           _e(t("s6_foot")), _e(t("footer_note"))))

    # closing
    pages.append(
        '<div class="page dark"><p class="eyebrow" style="color:#8F877A">%s</p>'
        '<h2>%s</h2><p class="lede">%s</p></div>'
        % (_e("باتفاقية سرية"), _e(t("closing_title")), _e(t("closing_p"))))

    return ("<!doctype html>\n<html lang=\"ar\" dir=\"rtl\">\n<head>\n"
            "<meta charset=\"utf-8\">\n<title>عوجا للأملاك — الملف التعريفي</title>\n"
            "<style>\n:root{%s}\n%s\n%s\n</style>\n</head>\n<body>\n%s\n</body>\n</html>"
            % (design_tokens(), font_faces(), CSS, "\n".join(pages)))


def main():
    markup = build_html()
    guard.assert_clean(markup, label="cp PDF profile")
    with open(OUT_HTML, "w", encoding="utf-8") as fh:
        fh.write(markup)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("HTML written to %s — install playwright to render the PDF" % OUT_HTML)
        return 0
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        pg = br.new_page()
        pg.goto("file://" + OUT_HTML, wait_until="networkidle")
        pg.wait_for_timeout(1200)
        pg.pdf(path=OUT_PDF, format="A4", print_background=True,
               margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
        br.close()
    print("wrote %s (%d KB)" % (OUT_PDF, os.path.getsize(OUT_PDF) // 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
