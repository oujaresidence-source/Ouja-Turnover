# -*- coding: utf-8 -*-
"""
schedule.notify — optional morning ops-channel summary of the day's coverage (Ouja extension;
the spec is a calendar page, this is a small useful add-on). schedule_employees has no Discord
id, so we post ONE ops-channel summary rather than per-employee DMs. Pure text builder here;
delivery is HOST.notify(payload), wired in bot.py and DRY-RUN by default.
"""

from .host import HOST


def build_summary(day_result):
    L = ["توزيع اليوم — %s (%s)" % (day_result.get("date", ""), day_result.get("weekday_ar", ""))]
    for w in sorted(day_result["working"], key=lambda x: x.get("sort_order", 0)):
        own = len(w["own"])
        cov = len(w["coverage"])
        line = "• %s: %d (أصلي %d" % (w["name"], w["load"], own)
        if cov:
            line += " + تغطية %d" % cov
        line += ")"
        L.append(line)
    for o in day_result["off"]:
        tag = "إجازة" if o.get("reason") == "leave" else "يوم راحة"
        L.append("• %s: %s" % (o["name"], tag))
    L.append("الإجمالي: %d شقة" % day_result["total"])
    return "\n".join(L)


def fire(day_result):
    try:
        notifier = getattr(HOST, "notify", None)
        if not notifier:
            return False
        notifier({"channel": build_summary(day_result), "date": day_result.get("date")})
        return True
    except Exception as e:
        print("[schedule] notify failed (non-fatal):", e)
        return False
