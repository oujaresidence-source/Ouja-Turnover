# -*- coding: utf-8 -*-
"""
mot.report — the evidence file: one closed, fully-inspected round as a printable A4 page.

HTML is built with plain string concatenation from escaped values (no template engine,
no backslashes in any embedded CSS). PDF is Chromium via Playwright's SYNC api pinned to a
one-worker pool (the owner_report lesson: sync Playwright is greenlet-bound). When Chromium
is absent the caller serves the HTML itself — never a broken button.
"""
import base64
import html as _h
import os
import pathlib
import tempfile
from concurrent.futures import ThreadPoolExecutor

from . import catalogue as C
from . import engine

_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ouja-mot-pdf")
_chromium = {"v": None}

STATE_AR = {"available": "متوفر", "missing": "غير متوفر", "unchecked": "لم يُفحص"}
KIND_AR = {"product": "منتج", "works": "أعمال", "document": "مستند", "structural": "إنشائي"}


def chromium_available():
    if _chromium["v"] is not None:
        return _chromium["v"]
    try:
        from digest.render.build import chromium_available as _ca
        _chromium["v"] = bool(_ca())
    except Exception:
        _chromium["v"] = False
    return _chromium["v"]


def e(s):
    return _h.escape(str(s if s is not None else ""), quote=True)


def _img_data(state_dir, rel):
    try:
        p = os.path.join(state_dir, rel)
        with open(p, "rb") as f:
            return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode("ascii")
    except Exception:
        return ""


CSS = """
@page { size: A4; margin: 14mm 12mm; }
body { font-family: 'IBM Plex Sans Arabic','Tajawal','Segoe UI',sans-serif; direction: rtl; color:#292925;
       background:#fff; margin:0; font-size:12px; }
h1 { font-size:20px; margin:0 0 2px; } h2 { font-size:14px; margin:18px 0 6px; color:#8B3748; }
.sub { color:#6f6a60; font-size:11px; }
.kpis { display:flex; gap:10px; margin:12px 0; }
.kpi { flex:1; border:1px solid #E7DFD1; border-radius:10px; padding:8px 10px; background:#FAF7F1; }
.kpi b { display:block; font-size:22px; font-family: Inter, sans-serif; color:#1c1c1c; }
.kpi span { color:#6f6a60; font-size:10px; }
table { width:100%; border-collapse:collapse; page-break-inside:auto; }
th { background:#1c1c1c; color:#fff; font-weight:600; padding:6px 7px; text-align:right; font-size:11px; }
td { padding:5px 7px; border-bottom:1px solid #EEE7DA; vertical-align:top; }
tr { page-break-inside:avoid; }
.ok { color:#4A7C59; font-weight:700; } .no { color:#8B3748; font-weight:700; }
.blk { background:#F3E2E4; border:1px solid #e3c5ca; border-radius:8px; padding:8px 10px; margin:10px 0; }
.ph { display:flex; flex-wrap:wrap; gap:6px; margin-top:4px; }
.ph img { width:120px; height:90px; object-fit:cover; border-radius:6px; border:1px solid #E7DFD1; }
.sig { display:flex; justify-content:space-between; margin-top:26px; }
.sig div { width:45%; border-top:1px solid #292925; padding-top:6px; font-size:11px; }
.foot { margin-top:14px; color:#9C958A; font-size:10px; }
.num { font-family: Inter, sans-serif; }
"""


def html_for(rnd, results, photo_rows, meta, prices, state_dir="/data"):
    has_pool = bool(rnd["has_pool"])
    ver = rnd.get("catalogue_version")
    comps = engine.components_for(has_pool, ver)
    sc = engine.score(results, has_pool, ver)
    q = engine.quote_lines(results, prices, meta, has_pool, version=ver)
    by_key = {}
    for p in photo_rows or []:
        by_key.setdefault(p["comp_key"], []).append(p["url"])
    name = rnd.get("apartment_name") or ("#%s" % rnd["listing_id"])
    parts = ["<!doctype html><html lang='ar' dir='rtl'><head><meta charset='utf-8'>",
             "<title>", e("سجل مطابقة — " + name), "</title><style>", CSS, "</style></head><body>",
             "<h1>سجل مطابقة معايير وزارة السياحة</h1>",
             "<div class='sub'>", e(name), " · جولة رقم ", e(rnd["id"]),
             " · أُغلقت ", e(str(rnd.get("closed_at") or "")[:16].replace("T", " ")),
             " · المفتش: ", e(rnd.get("inspector") or rnd.get("opened_by") or "—"),
             " · نسخة المعايير ", e(rnd.get("catalogue_version")), "</div>",
             "<div class='kpis'>",
             "<div class='kpi'><b class='num'>", e(sc["compliance_pct"]), "٪</b><span>نسبة المطابقة (متوفر ÷ ما فُحص)</span></div>",
             "<div class='kpi'><b class='num'>", e(sc["inspected_pct"]), "٪</b><span>نسبة الفحص (", e(sc["available"] + sc["missing"]),
             " من ", e(sc["denominator"]), " مكوّن)</span></div>",
             "<div class='kpi'><b class='num'>", e(sc["missing"]), "</b><span>غير متوفر</span></div>",
             "<div class='kpi'><b class='num'>", e(len(q["blocked"])), "</b><span>معايير إنشائية غير مطابقة</span></div>",
             "</div>"]
    parts.append("<div class='sub'>المعايير المحسوبة: %d معيارًا / %d مكوّنًا%s · المالك: %s</div>" % (
        C.criteria_count(has_pool, ver), sc["denominator"],
        " (شقة بمسبح)" if has_pool else " (بدون مسبح)", e(meta.get("owner") or "—")))
    if q["blocked"]:
        parts.append("<div class='blk'><b>الوحدة غير مطابقة — تحتاج قرار:</b> ")
        parts.append("، ".join(e("%d. %s" % (b["criterion_no"], b["label_ar"])) for b in q["blocked"]))
        parts.append("</div>")
    for skey, slabel in C.SECTIONS:
        rows = [c for c in comps if c["section"] == skey]
        if not rows:
            continue
        parts.append("<h2>%s</h2><table><thead><tr><th style='width:34px'>#</th><th>المعيار</th><th>المكوّن</th>"
                     "<th style='width:70px'>الحالة</th><th style='width:44px'>النوع</th><th>ملاحظة / صور</th></tr></thead><tbody>" % e(slabel))
        for c in rows:
            r = results.get(c["key"]) or {}
            st = r.get("state") or "unchecked"
            imgs = "".join("<img src='%s'>" % _img_data(state_dir, u) for u in by_key.get(c["key"], [])[:3])
            desc = C.DESCRIPTION_AR.get(c["criterion_no"], "")
            parts.append("<tr><td class='num'>%d</td><td>%s%s</td><td>%s</td><td class='%s'>%s</td><td>%s</td><td>%s%s</td></tr>" % (
                c["criterion_no"], e(c["criterion_ar"]),
                ("<div class='sub'>%s</div>" % e(desc)) if desc else "",
                e(c["label_ar"]), "ok" if st == "available" else ("no" if st == "missing" else ""),
                e(STATE_AR.get(st, st)), e(KIND_AR.get(c["kind"], c["kind"])),
                e(r.get("note") or "") + (" <span class='sub'>(المصدر: اشتراكات النت)</span>" if r.get("source") == "wifi" else ""),
                ("<div class='ph'>%s</div>" % imgs) if imgs else ""))
        parts.append("</tbody></table>")
    parts.append("<div class='sig'><div>توقيع المفتش: %s</div><div>توقيع المالك / الممثل</div></div>" % e(rnd.get("inspector") or ""))
    parts.append("<div class='foot'>Ouja Residence · عوجا للإقامة · سجل مؤرّخ لا يُعدَّل بعد الإغلاق؛ أي تصحيح يكون بجولة جديدة.</div>")
    parts.append("</body></html>")
    return "".join(parts)


def _print(html_path, pdf_path):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch(args=["--disable-dev-shm-usage"])
        try:
            pg = b.new_page()
            pg.goto(pathlib.Path(html_path).as_uri())
            pg.evaluate("() => document.fonts.ready")
            pg.wait_for_timeout(300)
            pg.pdf(path=pdf_path, format="A4", print_background=True, prefer_css_page_size=True)
        finally:
            b.close()


def pdf_bytes(html):
    """Blocking. Call through HOST.web_thread."""
    d = tempfile.mkdtemp(prefix="motpdf_")
    hp, pp = os.path.join(d, "r.html"), os.path.join(d, "r.pdf")
    with open(hp, "w", encoding="utf-8") as f:
        f.write(html)
    _pool.submit(_print, hp, pp).result(timeout=90)
    with open(pp, "rb") as f:
        data = f.read()
    for p in (hp, pp):
        try:
            os.remove(p)
        except OSError:
            pass
    try:
        os.rmdir(d)
    except OSError:
        pass
    return data
