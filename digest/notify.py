# -*- coding: utf-8 -*-
"""digest.notify — PURE text builder for the Wednesday Discord post (copy of the
studio/notify.py pattern). Delivery + DRY-RUN gating live in bot.py. No network, no
host, no imports beyond the standard library. ZERO backslashes in this file."""

NL = chr(10)
SECTION_LINE = {"events": "🎨 فعاليات", "cinema": "🎬 سينما", "fixtures": "⚽ مباريات", "worth": "📍 يستاهل"}


def _items_line(section):
    key = section.get("key")
    items = section.get("items") or []
    if not items:
        return ""
    if key == "fixtures":
        parts = ["%s × %s (%s)" % (it.get("home", ""), it.get("away", ""), it.get("when", "")) for it in items]
    else:
        parts = [it.get("ttl", "") for it in items]
    return "%s: %s" % (SECTION_LINE.get(key, key), " · ".join(p for p in parts if p))


def build_message(payload, issue_no, dropped=None, base_url=""):
    """One Discord post: the four sections as lines, what was dropped and why, the
    sources, and where to open the preview. Returns '' when there is nothing to say."""
    payload = payload or {}
    sections = payload.get("sections") or []
    lines = [l for l in (_items_line(s) for s in sections) if l]
    if not lines:
        return ""
    L = ["**وش صاير بالرياض · العدد %s · %s**" % (payload.get("issue", issue_no), payload.get("dateLabel", ""))]
    L += lines
    drops = [d for d in (dropped if dropped is not None else payload.get("dropped") or []) if d.get("ttl")]
    if drops:
        L += ["", "حذفنا:"]
        L += ["• %s — %s" % (d.get("ttl", ""), d.get("reason", "")) for d in drops[:8]]
    srcs = []
    for s in sections:
        for it in s.get("items") or []:
            n = (it.get("source") or {}).get("name")
            if n and n not in srcs:
                srcs.append(n)
    if srcs:
        L += ["", "المصادر: " + " · ".join(srcs)]
    L += ["", "كل رابط تحققنا منه مرتين. اعتمد، أو بدّل عنصر، أو احذف — الأزرار تحت."]
    if base_url:
        L += ["المعاينة الكاملة 👉 %s/digest" % base_url.rstrip("/")]
    return NL.join(L)


def status_line(issue):
    """A one-liner for the /api/digest/status card and the edited Discord message."""
    if not issue:
        return "ما فيه عدد بعد"
    st = issue.get("status", "")
    ar = {"building": "قيد البناء", "preview": "جاهز للاعتماد", "approved": "معتمد", "published": "منشور", "failed": "فشل"}.get(st, st)
    return "العدد %s · %s · %s" % (issue.get("issue_no", ""), issue.get("week_of", ""), ar)
