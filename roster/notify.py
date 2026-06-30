"""
roster.notify — build the bilingual (AR/EN) Discord messages for a roster change, the
morning digest, and the gap escalation (build spec §8). Message TEXT is built here (pure,
testable); actual delivery is HOST.notify(payload) which bot.py wires to the Discord loop.
Roster never sends anything itself, so a missing/disabled notifier can never break a route.
"""

from .host import HOST

_WD_AR = {"sun": "الأحد", "mon": "الإثنين", "tue": "الثلاثاء", "wed": "الأربعاء",
          "thu": "الخميس", "fri": "الجمعة", "sat": "السبت"}
_WD_EN = {"sun": "Sunday", "mon": "Monday", "tue": "Tuesday", "wed": "Wednesday",
          "thu": "Thursday", "fri": "Friday", "sat": "Saturday"}


def _emp_text(date, wd, emp):
    """One custodian's bilingual responsibility card (Discord code-block friendly)."""
    own = emp.get("primary") or []
    cov = emp.get("covered") or []
    L = []
    L.append("مسؤوليتك اليوم — %s (%s)" % (date, _WD_AR.get(wd, wd)))
    L.append("ملكك (%d): %s" % (len(own), "، ".join(p["name"] for p in own) or "—"))
    if cov:
        L.append("تغطية (%d): %s" % (len(cov),
                  "، ".join("%s (بدل %s)" % (c["name"], c.get("orig_name") or "—") for c in cov)))
    L.append("الإجمالي: %d" % emp.get("load", len(own) + len(cov)))
    L.append("")
    L.append("Your units today — %s (%s)" % (date, _WD_EN.get(wd, wd)))
    L.append("Own (%d): %s" % (len(own), ", ".join(p["name"] for p in own) or "—"))
    if cov:
        L.append("Covering (%d): %s" % (len(cov),
                 ", ".join("%s (for %s)" % (c["name"], c.get("orig_name") or "—") for c in cov)))
    L.append("Total: %d" % emp.get("load", len(own) + len(cov)))
    return "\n".join(L)


def _channel_text(date, wd, enriched, reason):
    st = enriched["status"]
    absent = enriched.get("absent") or []
    out = []
    head = "تحديث التوزيع" if reason != "digest" else "توزيع اليوم"
    out.append("%s — %s (%s)" % (head, date, _WD_AR.get(wd, wd)))
    if reason and reason not in ("digest",):
        out.append("السبب: %s" % reason)
    if absent:
        out.append("غائب: " + "، ".join(
            "%s (%s)" % (a["name"], {"off": "يوم راحة", "leave": "إجازة"}.get(a["reason"], a["reason"]))
            for a in absent))
    covered_total = sum(len(e.get("covered") or []) for e in enriched["board"])
    out.append("أعيد توزيع %d شقة · التغطية %d/%d · فجوات: %d"
               % (covered_total, st["assigned"], st["total"], st["gaps"]))
    out.append("Coverage %d/%d · gaps %d" % (st["assigned"], st["total"], st["gaps"]))
    return "\n".join(out)


def _escalation_text(date, wd, enriched):
    gaps = enriched.get("gaps") or []
    if not gaps:
        return None
    out = ["🚨 تعذّرت التغطية — %s (%s)" % (date, _WD_AR.get(wd, wd)),
           "شقق بدون مسؤول (%d): %s" % (len(gaps), "، ".join(g["name"] for g in gaps)),
           "الخيارات: استدعاء موظف إضافي · توزيع جزئي يدوي · تأجيل تنظيف غير عاجل",
           "",
           "🚨 Coverage gap — %s. %d unit(s) unassigned: %s"
           % (date, len(gaps), ", ".join(g["name"] for g in gaps))]
    return "\n".join(out)


def build(date, wd, enriched, reason=None):
    """Return {per_employee:[{discord_id,name,text}], channel:str, escalation:str|None}."""
    per = []
    for emp in enriched["board"]:
        if not (emp.get("primary") or emp.get("covered")):
            continue
        per.append({"discord_id": emp.get("discord_id"), "name": emp["name"],
                    "text": _emp_text(date, wd, emp)})
    return {"per_employee": per,
            "channel": _channel_text(date, wd, enriched, reason),
            "escalation": _escalation_text(date, wd, enriched),
            "reason": reason, "date": date}


def fire(date, wd, enriched, reason=None):
    """Best-effort delivery via the host notifier. Never raises into a route handler."""
    try:
        notifier = getattr(HOST, "notify", None)
        if not notifier:
            return False
        notifier(build(date, wd, enriched, reason))
        return True
    except Exception as e:
        print("[roster] notify failed (non-fatal):", e)
        return False
