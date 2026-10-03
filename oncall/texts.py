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
LATE_NOTED = ("سجّلنا ضغطتك بعد العشر دقايق ✍️ — البوت يراجعها خلال دقيقة، وإذا كان متوقف "
              "وقت السؤال ما تنحسب عليك.")
WHY_EXTRA = "راحة الليلة (المتاحين أكثر من ٧ ساعات)"
AUTO_CLOSED = "تلقائي — مرّ يومين بدون إقفال"
LIST_CAP = 10
_AR = "٠١٢٣٤٥٦٧٨٩"


def ar(n):
    return "".join(_AR[int(c)] if c.isdigit() else c for c in str(n))


def capped(items, line):
    """At most LIST_CAP lines, then «… و١٥ غيرها» — a Discord message stops at 2,000
    characters and a handover that silently fails is worse than a short one."""
    out = [line(i) for i in items[:LIST_CAP]]
    if len(items) > LIST_CAP:
        out.append("… و%s غيرها في الداشبورد" % ar(len(items) - LIST_CAP))
    return out


def day_label(d):
    from .engine import sun_weekday
    return "%s %s" % (DAYS_AR[sun_weekday(d)], d.strftime("%d/%m"))


def slot_label(s):
    # Words, not a dash: «5:00 – 7:00» inside an Arabic line renders right-to-left as
    # «7:00 – 5:00». «من … لين …» keeps the order whatever the paragraph direction.
    return "من %s لين %s" % (hm(s["start_min"]), hm(s["end_min"]))


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


def slot_on_leave(s):
    return ("🚨 سلوت %s باسم %s بدون مناوب — الإجازة مسجّلة اليوم في التقويم. غطّي أو غيّري "
            "المناوب من الداشبورد." % (slot_label(s), s["employee"]))


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
    tail = " — وانسجل إنذار رسمي." if nth == 2 else ""
    return "🚨 ما وصلنا رد من %s على «موجود؟» (مرة %d الليلة، سلوت %s). غطّي المناوبة لين يوصلنا رد%s" % (
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
        body = "طلب من %s: سلوتك %s مقابل سلوت %s." % (
            requester, slot_label(target_slot), slot_label(requester_slot))
    else:
        body = "طلب من %s: تنتقل له مناوبتك %s وترتاح الليلة." % (requester, slot_label(target_slot))
    return "🔁 طلب تبديل مناوبة\n" + body + "\nموافق؟"


def swap_result(accepted, target, slot):
    if accepted:
        return "✅ تمت الموافقة من %s — السلوت %s صار لك." % (target, slot_label(slot))
    return "❌ ما تمت الموافقة من %s على التبديل (%s)." % (target, slot_label(slot))


def swap_fyi(requester, target, slot, kind):
    if kind == "exchange":
        return "للعلم: تبديل مناوبة بين %s و%s — %s." % (requester, target, slot_label(slot))
    return "للعلم: سلوت %s انتقل من %s إلى %s." % (slot_label(slot), target, requester)


def swap_expired(slot):
    return "⌛ طلب التبديل على %s انتهى — الجدول تقفل الساعة ٣." % slot_label(slot)


def slot_edited_new(slot, by):
    return "📌 تعديل من %s: عندك مناوبة الليلة %s." % (by, slot_label(slot))


def slot_edited_old(slot, by):
    return "📌 تعديل من %s: ما عاد عندك مناوبة الليلة %s." % (by, slot_label(slot))


def issue_note(kind, owner_did, owner):
    who = ("<@%s>" % owner_did) if owner_did else owner
    if kind == "maint":
        return "🌙 متابعة المناوبة: %s — التذكرة تبقى باسمك لين تتقفل." % who
    return ("🌙 مسؤولية المناوبة: %s — الاستلام خلال ١٠ دقايق (🙋 فوق)، وبعد الحل اضغط ✅ انحلّت."
            % who)


def claim_overdue(issue):
    return "⏰ تصعيد «%s» عند %s ما انستلم من ١٠ دقايق — تابعيه." % (
        issue.get("title") or "—", issue["owner"])


def stale(issue):
    return "🕰️ مشكلة «%s» (باسم %s) ما تحدّثت من ٣٠ دقيقة، ومناوبة %s انتهت — تابعيها." % (
        issue.get("title") or "—", issue["owner"], issue["owner"])


def handover(slot, nxt, issues):
    who = ("<@%s>" % nxt["employee_did"]) if nxt.get("employee_did") else nxt["employee"]
    lines = ["🔄 تسليم %s: انتهى سلوت %s — الدور على %s (%s)." % (
        hm(slot["end_min"]), slot["employee"], who, slot_label(nxt))]
    if issues:
        lines.append("مشاكل مفتوحة (تبقى باسم أصحابها):")
        lines += capped(issues, lambda i: "• %s — %s" % (i.get("title") or "—", i["owner"]))
    else:
        lines.append("ما فيه مشاكل مفتوحة 👌")
    return "\n".join(lines)


def night_summary(d, per, warnings, open_issues):
    lines = ["🌙 ملخص مناوبة %s" % day_label(d)]
    for p in per:
        lines.append("• %s — الردود: %d من %d%s" % (
            p["name"], p["answered"], p["total"],
            (" — غياب %d" % p["missed"]) if p["missed"] else ""))
    if warnings:
        lines.append("إنذارات: " + "، ".join(warnings))
    lines.append("مشاكل للحين مفتوحة: %d" % len(open_issues))
    lines += capped(open_issues, lambda i: "• %s — %s" % (i.get("title") or "—", i["owner"]))
    return "\n".join(lines)
