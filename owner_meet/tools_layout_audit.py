# -*- coding: utf-8 -*-
"""
owner_meet.tools_layout_audit — gates G18 / G19, in a REAL Chromium (playwright).

    python3 owner_meet/tools_layout_audit.py --fixture tests/fixtures/owner_meet/snapshot_full.json
        every chapter at 1280×720: no element spills past its slide; the owner link at 390 px: no
        horizontal page scroll. Prints «LAYOUT_OK chapters=N overflow=0 phone_hscroll=0».
    python3 owner_meet/tools_layout_audit.py --pdf --fixture …
        the PDF: one 16:9 page per chapter, no ISO date in the text, the privacy scan clean.
        Prints «PDF_OK pages=N chapters=N ratio=1.78 iso_dates=0 privacy=0».

The fixture is test data. To cover every chapter the audit adds a previous-meeting promise list and
an «agreed» record to its in-memory copy (never written anywhere). No backslashes (brief P3).
"""

import copy
import json
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from owner_meet import pdf, privacy, render  # noqa: E402

FONTS = "file://" + os.path.join(ROOT, "fonts") + "/"
ISO = re.compile("20[0-9]{2}-[0-9]{2}-[0-9]{2}")

OVERFLOW_JS = """() => {
  const s = document.querySelector('.slide.on .in'); const r = s.getBoundingClientRect(); const bad = [];
  s.querySelectorAll('*').forEach(e => { const q = e.getBoundingClientRect();
    if (q.width && q.height && (q.bottom > r.bottom + 1 || q.right > r.right + 1 || q.left < r.left - 1))
      bad.push(e.tagName + '.' + (e.className && e.className.baseVal !== undefined ? e.className.baseVal : e.className)); });
  return bad.slice(0, 5); }"""


def full_coverage(snap):
    s = copy.deepcopy(snap)
    s["owner"]["promises"] = {"meeting_date": "2026-07-05", "items": [
        {"side": "ouja", "text": "تصوير احترافي جديد للشقة", "status": "done", "status_ar": "تم", "due": "2026-07-20",
         "evidence": "أُغلقت التذكرة المرتبطة بتاريخ 18 يوليو 2026"},
        {"side": "owner", "text": "إرسال صورة تصريح وزارة السياحة", "status": "not_done", "status_ar": "لم يتم",
         "due": "2026-08-01", "evidence": ""},
        {"side": "ouja", "text": "استبدال مرتبة غرفة النوم الرئيسية", "status": "in_progress", "status_ar": "قيد التنفيذ",
         "due": "2026-10-20", "evidence": ""}]}
    s["owner"]["agreed"] = {"decisions": [{"text": "وافق المالك على تصوير جديد", "amount_sar": 900}],
                            "commitments": [{"side": "ouja", "text": "مراجعة السعر أسبوعياً حتى نهاية أكتوبر", "due": "2026-10-31"},
                                            {"side": "owner", "text": "إرسال مستندات تجديد التصريح", "due": "2026-10-20"}]}
    return s


def layout(snap):
    from playwright.sync_api import sync_playwright
    tmp = tempfile.mkdtemp(prefix="meet-audit-")
    deck = os.path.join(tmp, "deck.html")
    owner = os.path.join(tmp, "owner.html")
    with open(deck, "w", encoding="utf-8") as f:
        f.write(render.presentation_html(snap, 1, font_base=FONTS))
    with open(owner, "w", encoding="utf-8") as f:
        f.write(render.owner_page_html(snap, "audit", "rt", font_base=FONTS))
    problems, n = [], 0
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1280, "height": 720})
        pg.goto("file://" + deck)
        pg.wait_for_timeout(500)
        n = pg.evaluate("document.querySelectorAll('.slide').length")
        for i in range(n):
            pg.evaluate("i => { document.querySelectorAll('.slide').forEach((s,k)=>s.classList.toggle('on', k===i)); }", i)
            pg.wait_for_timeout(40)
            bad = pg.evaluate(OVERFLOW_JS)
            if bad:
                key = pg.evaluate("i => document.querySelectorAll('.slide')[i].dataset.key", i)
                problems.append(("slide %d (%s)" % (i + 1, key), bad))
        ph = b.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, device_scale_factor=2)
        ph.goto("file://" + owner)
        ph.wait_for_timeout(500)
        hs = ph.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        b.close()
    for where, bad in problems:
        print("OVERFLOW", where, bad)
    if hs > 0:
        print("PHONE_HSCROLL", hs)
    return n, len(problems), 1 if hs > 0 else 0


def pdf_check(snap):
    import fitz
    tmp = tempfile.mkdtemp(prefix="meet-pdf-")
    path = os.path.join(tmp, "meeting.pdf")
    ok, chapters = pdf.to_pdf(snap, path)
    if not ok:
        print("PDF_FAILED")
        return None
    doc = fitz.open(path)
    pages = doc.page_count
    r = doc[0].rect
    text = "".join(pg.get_text() for pg in doc)
    iso = len(ISO.findall(text))
    hits = privacy.scan(text, (snap.get("presenter") or {}).get("forbidden") or {})
    for h in hits:
        print("PRIVACY", h["kind"])
    return pages, chapters, round(r.width / r.height, 2), iso, len(hits)


def main(argv):
    fx = argv[argv.index("--fixture") + 1] if "--fixture" in argv else os.path.join(ROOT, "tests", "fixtures", "owner_meet", "snapshot_full.json")
    with open(fx, encoding="utf-8") as f:
        snap = full_coverage(json.load(f))
    if "--pdf" in argv:
        res = pdf_check(snap)
        if not res:
            return 1
        pages, chapters, ratio, iso, priv = res
        line = "PDF_OK pages=%d chapters=%d ratio=%.2f iso_dates=%d privacy=%d" % (pages, chapters, ratio, iso, priv)
        print(line if (pages == chapters and ratio == 1.78 and iso == 0 and priv == 0) else "PDF_BAD " + line[7:])
        return 0 if (pages == chapters and ratio == 1.78 and iso == 0 and priv == 0) else 1
    n, overflow, hscroll = layout(snap)
    line = "chapters=%d overflow=%d phone_hscroll=%d" % (n, overflow, hscroll)
    print(("LAYOUT_OK " if not (overflow or hscroll) else "LAYOUT_BAD ") + line)
    return 0 if not (overflow or hscroll) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
