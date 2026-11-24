# -*- coding: utf-8 -*-
"""
contracting.ownerpdf — «ملف المالك»: one A4 PDF per project, in the Ouja look
(docs/brand/OUJA_LOOK.md, templates/report-a4.html). For the PROPERTY owner, so:
  - no staff names, no Discord, no internal escalations — what was done, when, and proof;
  - delays are shown with their reason (honest, and the owner asked for it);
  - dates are Arabic words (an ISO date inside Arabic text is reordered by bidi).

Sent to #مقاولات-الإدارة every Thursday, once at handover, and on demand (the card's button,
the dashboard). Faisal forwards it on WhatsApp — the bot never sends it to the owner itself.

Printing reuses the shared Chromium (owner_report.renderer.ouja_render: _pw_pool/_pw_lock),
the same way owner_meet.pdf does; a private launch is the local fallback. Never raises.
"""

import datetime as dt
import html
import os
import re
import tempfile
import traceback

from . import db, engine, photos

FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts")
PDF_TIMEOUT_S = int(os.environ.get("CONTRACTING_PDF_TIMEOUT_S", "150"))
PER_LINE = 4                 # photos per finished line in the file
PROGRESS_MAX = 6             # newest work-in-progress photos
RIYADH = dt.timedelta(hours=3)

FACES = [("Thmanyah Serif", 700, "ThmanyahSerifDisplay-Bold.woff2"),
         ("Thmanyah Serif", 900, "ThmanyahSerifDisplay-Black.woff2"),
         ("Thmanyah Sans", 400, "ThmanyahSans-Regular.woff2"),
         ("Thmanyah Sans", 500, "ThmanyahSans-Medium.woff2"),
         ("Thmanyah Sans", 700, "ThmanyahSans-Bold.woff2")]

E = html.escape


def _fonts_css():
    out = []
    for fam, w, fn in FACES:
        p = os.path.join(FONT_DIR, fn)
        if os.path.isfile(p):
            out.append("@font-face{font-family:'%s';font-weight:%d;font-style:normal;"
                       "src:url('file://%s') format('woff2')}" % (fam, w, p))
    return "".join(out)


def _local_day(iso_utc):
    try:
        return (dt.datetime.fromisoformat(str(iso_utc)[:19]) + RIYADH).date().isoformat()
    except (TypeError, ValueError):
        return ""


def _money(v):
    try:
        return "{:,.2f}".format(float(v)).replace(".00", "")
    except (TypeError, ValueError):
        return "—"


def _status(it, today):
    st = it.get("status")
    if st == "done":
        return "خلص", "ok"
    if st == "awaiting_photos":
        return "خلص، يتوثّق", "ok"
    if st == "blocked":
        return "واقف", "warn"
    d = engine._d(it.get("due"))
    if d and d < today:
        return "متأخر", "warn"
    return "جاي", ""


CSS = """
@page{size:A4;margin:20mm 18mm 20mm 18mm;
  @bottom-left{content:counter(page);font-family:"Thmanyah Sans";font-size:8.5pt;color:#6B5F52}
  @bottom-right{content:"عوجا ريزيدنس · OUJA RESIDENCE";font-family:"Thmanyah Sans";font-size:8pt;color:#6B5F52}}
@page cover{margin:0;@bottom-left{content:none}@bottom-right{content:none}}
@page end{margin:0;@bottom-left{content:none}@bottom-right{content:none}}
:root{--paper:#F4EFE7;--paper2:#ECE5D9;--card:#FBF8F3;--ink:#1D1813;--ink2:#463C33;--mut:#6B5F52;--line:#DCD2C3;--line2:#E8E1D5;--gold:#A57A2C;--night:#15110D;--ok:#2E6A49;--warn:#8A4B2A;
  --f-d:"Thmanyah Serif","Thmanyah Sans",Georgia,serif;--f-t:"Thmanyah Sans",system-ui,sans-serif}
*{box-sizing:border-box}
html{-webkit-print-color-adjust:exact;print-color-adjust:exact}
body{margin:0;font-family:var(--f-t);font-size:10.5pt;line-height:1.75;color:var(--ink);background:#fff}
h1,h2{font-family:var(--f-d);font-weight:700;margin:0;text-wrap:balance}
h1{font-size:24pt;line-height:1.25;margin-bottom:4mm}
h2{font-size:17pt;line-height:1.25;margin:9mm 0 3mm;break-after:avoid}
h3{font-size:12pt;font-weight:700;line-height:1.4;margin:0;break-after:avoid}
p{margin:0 0 3mm;color:var(--ink2);max-width:150mm}
.num{font-variant-numeric:tabular-nums;unicode-bidi:isolate}
.eyebrow{display:flex;align-items:center;gap:3mm;font-size:9pt;font-weight:500;color:var(--mut);margin:0 0 3mm}
.eyebrow:before{content:"";width:6mm;height:.6mm;background:var(--gold)}
.small{font-size:8.5pt;color:var(--mut);line-height:1.6}
.cover{page:cover;height:297mm;padding:24mm 22mm;background:var(--paper);display:flex;flex-direction:column;break-after:page}
.brand{display:flex;align-items:baseline;gap:3mm}
.brand .ar{font-family:var(--f-d);font-weight:900;font-size:22pt;line-height:1}
.brand .en{font-size:7pt;font-weight:700;letter-spacing:.22em;color:var(--mut)}
.cover .t{margin-top:auto}
.cover h1{font-size:36pt;font-weight:900;line-height:1.18;max-width:13ch;margin:0}
.cover .sub{font-size:12.5pt;color:var(--ink2);margin-top:5mm;max-width:130mm}
.big{display:flex;align-items:baseline;gap:4mm;margin-top:14mm}
.big .v{font-family:var(--f-d);font-weight:900;font-size:64pt;line-height:1;color:var(--ink)}
.big .of{font-family:var(--f-d);font-weight:700;font-size:22pt;color:var(--gold)}
.big .k{font-size:11pt;color:var(--ink2)}
.cover .meta{display:flex;gap:10mm;margin-top:14mm;padding-top:5mm;border-top:.3mm solid var(--line);font-size:9pt;color:var(--mut)}
.cover .meta b{display:block;color:var(--ink);font-weight:700;font-size:10.5pt}
.figs{display:grid;grid-template-columns:repeat(4,1fr);border-top:.3mm solid var(--line);margin:6mm 0 8mm;break-inside:avoid}
.figs div{padding:4mm 4mm 0 0;border-inline-start:.3mm solid var(--line2)}
.figs div:first-child{border:0;padding-inline-start:0}
.figs .v{font-family:var(--f-d);font-weight:700;font-size:20pt;line-height:1.1}
.figs .k{font-size:8.5pt;color:var(--mut);margin-top:2mm;line-height:1.45}
table{width:100%;border-collapse:collapse;margin:3mm 0 6mm;font-size:9.5pt}
th{text-align:start;font-weight:700;font-size:8.5pt;color:var(--mut);padding:2.3mm 2mm;border-bottom:.4mm solid var(--ink)}
td{padding:2.3mm 2mm;border-bottom:.25mm solid var(--line2);color:var(--ink2);vertical-align:top}
td.n{width:8mm;color:var(--mut);font-variant-numeric:tabular-nums}
td b{color:var(--ink);font-weight:500}
tr{break-inside:avoid}
.st{font-weight:700;white-space:nowrap}
.st.ok{color:var(--ok)}
.st.warn{color:var(--warn)}
.delay{display:grid;grid-template-columns:1fr auto;gap:2mm 6mm;padding:3mm 0;border-bottom:.25mm solid var(--line2);break-inside:avoid}
.delay .why{grid-column:1/-1;color:var(--ink2);font-size:9.5pt}
.line{margin:7mm 0 0;break-inside:avoid}
.line .hd{display:flex;justify-content:space-between;align-items:baseline;gap:4mm;padding-bottom:2mm;border-bottom:.3mm solid var(--line);margin-bottom:3mm}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:3mm}
.grid img{width:100%;height:58mm;object-fit:cover;border-radius:2.5mm;display:block;background:var(--paper2)}
.end{page:end;height:297mm;padding:24mm 22mm;background:var(--night);color:var(--paper);display:flex;flex-direction:column;justify-content:space-between;break-before:page}
.end .brand .en{color:rgba(244,239,231,.6)}
.end p{color:rgba(244,239,231,.78);margin:0 0 2mm}
"""


def build_html(p, reason, today, delays=None, progress=None):
    """Pure: the project dict (with items) → the page's HTML. Images by local file path."""
    from .notify import fmt_date                      # one Arabic date format everywhere
    its = sorted(p.get("items") or [], key=lambda i: i.get("pos", 0))
    h = engine.health(its, today)
    final = reason == "final" or h["state"] == "done"
    eyebrow = "ملف التسليم" if final else "تقرير سير العمل"
    hand = next((i for i in its if i.get("is_handover")), its[-1] if its else None)
    hand_day = fmt_date(hand.get("due")) if hand else "—"
    lede = {"ok": "الشغل ماشي على الخطة.",
            "late": "فيه بنود عدّى موعدها، وتحت أسباب التأخير.",
            "blocked": "فيه بند واقف ننتظر حله، وتحت التفاصيل.",
            "done": "خلص المشروع، وهذا ملف التسليم بالصور."}[h["state"]]
    delays = delays or []
    names = {i["id"]: i["name"] for i in its}

    rows = []
    for i in its:
        label, cls = _status(i, today)
        when = fmt_date(_local_day(i["done_at"])) if i.get("status") == "done" and i.get("done_at") \
            else fmt_date(i.get("due"))
        rows.append("<tr><td class='n num'>%d</td><td><b>%s</b></td><td class='num'>%s</td>"
                    "<td><span class='st %s'>%s</span></td></tr>"
                    % (i["pos"], E(i["name"]), E(when), cls, E(label)))

    dl = []
    for ev in delays:
        dl.append("<div class='delay'><b>%s</b><span class='small num'>من %s إلى %s</span>"
                  "<div class='why'>السبب: %s</div></div>"
                  % (E(names.get(ev.get("item_id"), "بند")), E(fmt_date(ev.get("old_due"))),
                     E(fmt_date(ev.get("new_due"))), E(ev.get("text") or "—")))

    gal = []
    for i in its:
        files = [photos.path_of(x.get("file")) for x in (i.get("photos") or [])]
        files = [f for f in files if f][:PER_LINE]
        if not files:
            continue
        done_day = fmt_date(_local_day(i.get("done_at"))) if i.get("done_at") else ""
        gal.append("<div class='line'><div class='hd'><h3>%d. %s</h3><span class='small'>%s</span></div>"
                   "<div class='grid'>%s</div></div>"
                   % (i["pos"], E(i["name"]), E(("خلص " + done_day) if done_day else "خلص، يتوثّق"),
                      "".join("<img src='file://%s'>" % E(f) for f in files)))
    prog = [photos.path_of(x.get("file")) for x in (progress or [])]
    prog = [f for f in prog if f][-PROGRESS_MAX:]
    if prog:
        gal.append("<div class='line'><div class='hd'><h3>من الموقع — شغل جاري</h3></div>"
                   "<div class='grid'>%s</div></div>"
                   % "".join("<img src='file://%s'>" % E(f) for f in prog))

    unit = (p.get("unit") or "").strip()
    sub = " · ".join(x for x in ["الوحدة: " + unit if unit else "",
                                  "المالك: " + p["owner"] if p.get("owner") else ""] if x)
    parts = [
        "<!doctype html><html lang='ar' dir='rtl'><head><meta charset='utf-8'><title>%s</title>"
        "<style>%s%s</style></head><body>" % (E(p.get("title") or ""), _fonts_css(), CSS),
        "<section class='cover'><div class='brand'><span class='ar'>عوجا</span>"
        "<span class='en'>OUJA RESIDENCE</span></div><div class='t'>"
        "<p class='eyebrow'>%s</p><h1>%s</h1>%s"
        "<div class='big'><span class='v num'>%d</span><span class='of'>من %d</span>"
        "<span class='k'>بنود خلصت</span></div>"
        "<div class='meta'><div>التاريخ<b class='num'>%s</b></div>"
        "<div>المبلغ المعتمد<b class='num'>%s ر.س</b></div><div>التسليم%s<b class='num'>%s</b></div></div>"
        "</div></section>"
        % (E(eyebrow), E(p.get("title") or ""), ("<p class='sub'>%s</p>" % E(sub)) if sub else "",
           h["done"], h["total"], E(fmt_date(today.isoformat())), E(_money(p.get("total_sar"))),
           "" if final else " المتوقع", E(hand_day)),
        "<main><p class='eyebrow'>وين وصلنا</p><h1>%s</h1>" % E(lede),
        "<div class='figs'><div><div class='v num'>%d</div><div class='k'>خلصت</div></div>"
        "<div><div class='v num'>%d</div><div class='k'>باقي</div></div>"
        "<div><div class='v num'>%d</div><div class='k'>مرات تأجيل موعد</div></div>"
        "<div><div class='v num'>%s</div><div class='k'>التسليم%s</div></div></div>"
        % (h["done"], h["total"] - h["done"], len(delays), E(" ".join(hand_day.split(" ")[1:]) or hand_day),
           "" if final else " المتوقع"),
        "<h2>البنود</h2><table><thead><tr><th>#</th><th>البند</th><th>التاريخ</th><th>الحالة</th>"
        "</tr></thead><tbody>%s</tbody></table>" % "".join(rows),
        "<p class='small'>التاريخ للبند الخالص = يوم خلاصه، وللباقي = موعده.</p>",
    ]
    if dl:
        parts.append("<h2>التأخيرات</h2>%s" % "".join(dl))
    if gal:
        parts.append("<h2>الصور</h2>%s" % "".join(gal))
    parts.append("</main><section class='end'><div class='brand'><span class='ar'>عوجا</span>"
                 "<span class='en'>OUJA RESIDENCE · RIYADH</span></div><div>"
                 "<p>الصور من الموقع وقت التنفيذ.</p><p>oujares.com</p></div></section></body></html>")
    return "".join(parts)


def project_html(project_id, reason, today):
    p = db.project(project_id)
    if not p:
        return None, None
    delays = [e for e in reversed(db.events(project_id, 500)) if e.get("kind") == "delay"]
    progress = []
    for b in db.batches(project_id, "progress"):
        progress += b["photos"]
    return p, build_html(p, reason, today, delays, progress)


def file_name(p, today):
    tag = re.sub(r"[^0-9A-Za-z]+", "-", str(p.get("title") or "")).strip("-")
    return "Ouja-%s%s.pdf" % ((tag + "-") if tag else "", today.isoformat())


# ---------------------------------------------------------------- printing

def _print_with(browser, html_path, pdf_path):
    pg = browser.new_page()
    try:
        pg.goto("file://" + os.path.abspath(html_path))
        pg.wait_for_timeout(900)
        pg.pdf(path=pdf_path, format="A4", print_background=True, prefer_css_page_size=True)
    finally:
        try:
            pg.close()
        except Exception:
            pass


def _shared_print(html_path, pdf_path):
    from owner_report.renderer import ouja_render as r
    with r._pw_lock:
        _print_with(r._pw_browser(), html_path, pdf_path)


def _local_print(html_path, pdf_path):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch(args=["--disable-dev-shm-usage"])
        try:
            _print_with(b, html_path, pdf_path)
        finally:
            b.close()


def render(project_id, reason, today):
    """→ (pdf_path, file_name, project) or ('', '', project) on failure. Never raises.
    The caller deletes the file's folder after sending it."""
    p = None
    try:
        p, page = project_html(project_id, reason, today)
        if not p:
            return "", "", None
        folder = tempfile.mkdtemp(prefix="ctr_pdf_")
        html_path = os.path.join(folder, "file.html")
        pdf_path = os.path.join(folder, file_name(p, today))
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(page)
        try:
            from owner_report.renderer import ouja_render as r
            r._pw_pool.submit(_shared_print, html_path, pdf_path).result(timeout=PDF_TIMEOUT_S)
        except (ImportError, SyntaxError):
            _local_print(html_path, pdf_path)
        if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
            return pdf_path, os.path.basename(pdf_path), p
    except Exception:
        traceback.print_exc()
    return "", "", p
