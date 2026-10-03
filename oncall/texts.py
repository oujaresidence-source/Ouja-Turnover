# -*- coding: utf-8 -*-
"""
oncall.texts — every Arabic word «المناوبة» sends. Najdi, short, phone-first.
One place, so the Discord post, the DM and the dashboard can never drift apart.
"""

from .engine import hm

DAYS_AR = ["الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت"]

NOT_FOUND = "ما لقيت هالسؤال — يمكن انتهى."
NOT_YOURS = "هذي مو مناوبتك 🙂"
ALREADY = "مسجّل من قبل ✅"
THANKS = "تمام، مسجّل إنك موجود ✅"
LATE = "تأخرت عن العشر دقايق — انحسبت غياب. إذا عندك عذر كلّم اسيل."
NOT_ROSTER = "أنت مو من فريق المناوبة."
SWAP_SENT = "وصل طلبك لـ{who} — إذا وافق يتعدّل الجدول تلقائياً."
SWAP_GONE = "انتهى وقت التبديل — الجدول مقفل."
SWAP_CHANGED = "السلوت تغيّر صاحبه من بعد الطلب — الطلب لاغي."
RESOLVE_NOT_ALLOWED = "«انحلّت» لصاحب المشكلة أو اللي ساعده أو الأدمن بس."
RESOLVED = "تمام، انقفلت المشكلة ✅"


def day_label(d):
    from .engine import sun_weekday
    return "%s %s" % (DAYS_AR[sun_weekday(d)], d.strftime("%d/%m"))


def slot_label(s):
    return "%s – %s" % (hm(s["start_min"]), hm(s["end_min"]))


def schedule_text(d, slots, unavailable, locked):
    lines = ["🌙 **مناوبة ليلة %s** (٥ العصر – ١٢ الليل)" % day_label(d), ""]
    if not slots:
        lines.append("⚠️ ما فيه أحد متاح الليلة — اسيل بتتصرف.")
    for s in slots:
        mention = ("<@%s>" % s["employee_did"]) if s.get("employee_did") else s["employee"]
        lines.append("• %s ← %s" % (slot_label(s), mention))
    if unavailable:
        lines.append("")
        lines.append("مو موجودين: " + "، ".join("%s (%s)" % (u["name"], u["why"]) for u in unavailable))
    lines.append("")
    if locked:
        lines.append("🔒 الجدول مقفل — أي تغيير من اسيل.")
    else:
        lines.append("🔁 تبي تبدّل؟ اضغط على سلوت زميلك — التبديل لين ٣ العصر يوم المناوبة.")
    return "\n".join(lines)


def supervisor_roster_alert(d, unavailable, empty):
    head = ("⚠️ ليلة %s ما فيها أحد متاح للمناوبة!" % day_label(d)) if empty else \
           ("للعلم — جدول مناوبة %s نزل، وهذولي مو فيه:" % day_label(d))
    return "\n".join([head] + ["• %s — %s" % (u["name"], u["why"]) for u in unavailable])


def reminder(s):
    return "⏰ مناوبتك تبدأ %s وتخلص %s. أول سؤال «موجود؟» يوصلك أول ما تبدأ." % (
        hm(s["start_min"]), hm(s["end_min"]))


def check_text(due_label):
    return "✋ **موجود؟** (%s) — اضغط الزر خلال ١٠ دقايق." % due_label


def miss_dm(nth):
    if nth <= 1:
        return ("⚠️ ما ضغطت «موجود» خلال ١٠ دقايق. اسيل انبلغت وبتغطي لين ترجع. "
                "ترى المرة الثانية الليلة = إنذار رسمي.")
    if nth == 2:
        return "⚠️ ثاني غياب الليلة — انسجل عليك إنذار رسمي (التفاصيل والاعتراض في رسالة ثانية)."
    return "⚠️ ما ضغطت «موجود» مرة ثانية. اسيل انبلغت."


def supervisor_miss(employee, nth, slot):
    tail = " — وانسجل عليه إنذار رسمي." if nth == 2 else ""
    return "🚨 %s ما ردّ على «موجود؟» (مرة %d الليلة، سلوت %s). غطّي المناوبة لين يرجع%s" % (
        employee, nth, slot_label(slot), tail)


def warning_reason(date_label):
    return "غياب عن المناوبة مرتين ليلة %s (ما ضغط «موجود» خلال ١٠ دقايق)." % date_label


def warning_dm(date_label, pct, link):
    return "\n".join([
        "⚠️ انسجل إنذار — المناوبة (%s)" % date_label,
        "ما ضغطت «موجود» مرتين خلال مناوبتك.",
        "",
        "عمولتك لهذا الشهر صارت %s." % pct,
        "",
        "إذا تشوف إن الإنذار غلط، قدّم اعتراضك من هنا وبيوصل مباشرة للمسؤولين:",
        link])


def hr_line(employee, date_label, pct):
    return "\n".join(["⚠️ إنذار تلقائي — " + employee,
                      "المناوبة: " + date_label,
                      "السبب: غياب مرتين عن «موجود؟»",
                      "العمولة بعد الإنذار: " + pct])


def swap_ask(requester, target_slot, requester_slot, kind):
    if kind == "exchange":
        body = "%s يبي يبدّل معك: ياخذ سلوتك %s وتاخذ سلوته %s." % (
            requester, slot_label(target_slot), slot_label(requester_slot))
    else:
        body = "%s يبي ياخذ سلوتك %s (وأنت ترتاح)." % (requester, slot_label(target_slot))
    return "🔁 طلب تبديل مناوبة\n" + body + "\nموافق؟"


def swap_result(accepted, target, slot):
    if accepted:
        return "✅ %s وافق — السلوت %s صار لك." % (target, slot_label(slot))
    return "❌ %s رفض التبديل على %s." % (target, slot_label(slot))


def swap_fyi(requester, target, slot, kind):
    what = "بدّلوا" if kind == "exchange" else "أخذ السلوت"
    return "للعلم: %s و%s %s — %s." % (requester, target, what, slot_label(slot))


def swap_expired(slot):
    return "⌛ طلب التبديل على %s انتهى — الجدول تقفل الساعة ٣." % slot_label(slot)


def slot_edited_new(slot, by):
    return "📌 %s حطّتك في مناوبة الليلة %s." % (by, slot_label(slot))


def slot_edited_old(slot, by):
    return "📌 %s شالتك من مناوبة الليلة %s." % (by, slot_label(slot))


def issue_note(kind, owner_did, owner):
    who = ("<@%s>" % owner_did) if owner_did else owner
    if kind == "maint":
        return "🌙 متابع المناوبة: %s — التذكرة باسمه لين تتقفل." % who
    return ("🌙 المناوب المسؤول: %s — استلم خلال ١٠ دقايق (🙋 فوق)، وإذا خلصت اضغط ✅ انحلّت."
            % who)


def claim_overdue(issue):
    return "⏰ تصعيد «%s» عند %s ما انستلم من ١٠ دقايق — تابعيه." % (
        issue.get("title") or "—", issue["owner"])


def stale(issue):
    return "🕰️ مشكلة «%s» (صاحبها %s) ما تحدّثت من ٣٠ دقيقة وهو خلّص مناوبته — تابعيها." % (
        issue.get("title") or "—", issue["owner"])


def handover(slot, nxt, issues):
    who = ("<@%s>" % nxt["employee_did"]) if nxt.get("employee_did") else nxt["employee"]
    lines = ["🔄 تسليم %s: %s خلّص — دورك %s (%s)." % (
        hm(slot["end_min"]), slot["employee"], who, slot_label(nxt))]
    if issues:
        lines.append("مشاكل مفتوحة (تبقى باسم أصحابها):")
        lines += ["• %s — %s" % (i.get("title") or "—", i["owner"]) for i in issues]
    else:
        lines.append("ما فيه مشاكل مفتوحة 👌")
    return "\n".join(lines)


def night_summary(d, per, warnings, open_issues):
    lines = ["🌙 ملخص مناوبة %s" % day_label(d)]
    for p in per:
        lines.append("• %s: ردّ %d من %d%s" % (
            p["name"], p["answered"], p["total"],
            (" — غياب %d" % p["missed"]) if p["missed"] else ""))
    if warnings:
        lines.append("إنذارات: " + "، ".join(warnings))
    lines.append("مشاكل للحين مفتوحة: %d" % len(open_issues))
    return "\n".join(lines)
