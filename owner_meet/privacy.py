# -*- coding: utf-8 -*-
"""
owner_meet.privacy — PURE. The fail-closed check on any owner-facing HTML or PDF text (R1–R6).

`scan(text, forbidden)` -> [{kind, where}] — the KIND of leak and a short context, never the leaked
value itself (the result is shown in the presenter window and must not become a new leak).
The build runs it on the rendered presentation; «إرسال» (S5) runs it again and refuses on any hit.

No backslashes in this file (brief P3).
"""

import re

from .redact import bounded

AR = chr(0x0600) + "-" + chr(0x06FF)
WORD = "A-Za-z0-9" + AR

PATTERNS = (
    ("reservation_code", re.compile("HM[A-Z0-9]{8}")),
    ("phone", re.compile("(?<![0-9])(?:9665|05)[0-9]{8}(?![0-9])")),
    ("email", re.compile("[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+[.][A-Za-z]{2,}")),
    ("unit_count", re.compile("(?<![0-9])[0-9]+ ?(?:شقة|شقق|وحدة|وحدات|إعلاناً|إعلانات|listings)")),
    ("n_equals", re.compile("(?<![A-Za-z])n ?= ?[0-9]")),
    ("rank", re.compile("(?:الترتيب|المركز|رقم) ?[0-9]+ ?(?:من|/) ?[0-9]+")),
    ("sample", re.compile("مثال")),
)
# Ouja's own economics never reach an owner (R5): his fee % is fine, these are not.
INTERNAL_WORDS = ("هامش عوجا", "هامش الربح", "تكلفة التنظيف لكل", "تكلفة اشتراك التنظيف", "تكلفة الدورة",
                  "نسبة إدارة مالك", "رسوم الملاك الآخرين", "margin", "cost per turnover")

_STYLE = re.compile("<style[^>]*>.*?</style>", re.S)


def _bounded(term):
    return re.compile(bounded(term), re.I)


def scan(text, forbidden=None):
    """forbidden: {"other_units": [...], "other_owners": [...], "guest_full_names": [...],
    "staff": [...]} -> hits. <style> blocks are skipped (CSS numbers are not prose)."""
    src = _STYLE.sub(" ", text or "")
    hits = []

    def ctx(m):
        a, b = max(0, m.start() - 24), min(len(src), m.end() + 24)
        return src[a:m.start()] + "…" + src[m.end():b]

    for kind, rx in PATTERNS:
        m = rx.search(src)
        if m:
            hits.append({"kind": kind, "where": ctx(m) if kind not in ("phone", "email", "reservation_code") else ""})
    for w in INTERNAL_WORDS:
        if w.lower() in src.lower():
            hits.append({"kind": "internal_economics", "where": w})
    for kind, terms in sorted((forbidden or {}).items()):
        for t in terms or []:
            t = str(t or "").strip()
            if len(t) < 3:
                continue
            m = _bounded(t).search(src)
            if m:
                hits.append({"kind": kind, "where": ""})
                break
    return hits


LABELS = {"reservation_code": "كود حجز", "phone": "رقم جوال", "email": "بريد إلكتروني", "unit_count": "عدد شقق",
          "n_equals": "عدد عيّنة", "rank": "ترتيب", "sample": "كلمة «مثال»", "internal_economics": "أرقام داخلية لعوجا",
          "other_units": "اسم شقة لمالك آخر", "other_owners": "اسم مالك آخر", "guest_full_names": "اسم ضيف كامل",
          "staff": "اسم موظف", "staff_tokens": "اسم موظف", "guest_tokens": "اسم ضيف"}


def readiness_line(hits):
    kinds = []
    for h in hits:
        if h["kind"] not in kinds:
            kinds.append(h["kind"])
    return {"level": "red", "key": "privacy",
            "text_ar": "فحص الخصوصية وجد في صفحة المالك: " + "، ".join(LABELS.get(k, k) for k in kinds)
                       + " — لا يُرسل حتى يُصحّح", "kinds": kinds}
