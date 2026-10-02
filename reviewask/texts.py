# -*- coding: utf-8 -*-
"""
reviewask.texts — every Arabic word of «رفع التقييم» (PURE: no I/O, no discord).

R2: button LABELS carry text only, never an emoji — meaning comes from the label + the colour.
Embeds, board lines and room messages may keep emoji. No money figure ever appears here
(fees, revenue and nightly rates stay out of every staff room). No template text either: the
guest message and the call script are the owner's, stored in rv_settings (R4, R8).
"""

from . import engine

NL = chr(10)

BUTTON_LABELS = {
    "wa": "فتح واتساب",
    "airbnb": "رسالة Airbnb",
    "sent": "أرسلت الرسالة",
    "replied": "الضيف رد",
    "no_phone": "ما فيه رقم",
    "rated": "قيّم",
    "promise": "وعد يقيّم",
    "noanswer": "ما رد",
    "later": "كلمني بعدين",
    "complaint": "عنده ملاحظة",
    "decline": "ما يبي يقيّم",
    "wrong": "الرقم غلط",
    "satisfied": "راضي",
    # the «الضيف رد» choice (an ephemeral follow-up, not on the card)
    "replied_will": "بيقيّم",
    "replied_complaint": "عنده ملاحظة",
    "replied_no": "ما يبي",
    "replied_quiet": "رد بس ما قال شي",
    # the complaint step
    "complaint_write": "اكتب كلام الضيف",
    # template editor opener (/review-message prefix fallback has no modal)
    "open_editor": "فتح المحرر",
}

# discord.ButtonStyle names; bot.py maps them. Link buttons are always style link.
BUTTON_STYLE = {
    "sent": "success", "replied": "primary", "no_phone": "secondary",
    "rated": "success", "promise": "success", "noanswer": "secondary", "later": "secondary",
    "complaint": "danger", "decline": "secondary", "wrong": "secondary", "satisfied": "success",
    "replied_will": "success", "replied_complaint": "danger", "replied_no": "secondary",
    "replied_quiet": "secondary", "complaint_write": "danger", "open_editor": "primary",
}

STATE_AR = {
    engine.WAITING: "⏳ ننتظر يوم الخروج",
    engine.WA_DUE: "📱 لازم تنرسل رسالة الواتساب",
    engine.WA_SENT: "✉️ انرسلت الرسالة — ننتظر التقييم",
    engine.CALL_DUE: "📞 لازم مكالمة الليلة",
    engine.CALL_RETRY: "🔁 نعيد الاتصال بكرة",
    engine.CARE_DUE: "🤝 مكالمة اطمئنان",
    engine.PROMISED: "🙏 وعد يقيّم — ننتظر يوصل التقييم",
    engine.REVIEWED: "⭐ وصل التقييم",
    engine.PROMISED_EXPIRED: "⌛ وعد وما وصل تقييم",
    engine.DECLINED: "🚫 ما يبي يقيّم",
    engine.WRONG_NUMBER: "☎️ الرقم غلط",
    engine.NO_ANSWER_FINAL: "📵 ما رد مرتين",
    engine.COMPLAINT: "🛠️ عنده ملاحظة — انفتحت تذكرة صيانة",
    engine.EXPIRED: "⌛ انتهت مهلة Airbnb (١٤ يوم)",
    engine.CANCELLED: "❌ الحجز انلغى أو تغيّر",
    engine.VOID: "— ملغية",
}

MODE_AR = {"review": "رفع تقييم", "care": "اطمئنان (كان عنده بلاغ)"}

CARE_WARNING = ("الضيف كان عنده بلاغ صيانة أثناء الإقامة: اتصل اطمئنان أول، "
                "لا تطلب تقييم قبل ما تتأكد إنه راضي")

FOOTER = ("لا تتصل بعد ١٠ مساءً · التقييم في Airbnb يوصلنا بعد ما نقيّم الضيف أو بعد ١٤ يوم — "
          "إذا قال الضيف إنه قيّم اضغط «قيّم»")

NOT_FOUND = "ما لقينا هذي التذكرة."
ADMIN_ONLY = "🚫 هذا الأمر للإدارة فقط."
LEAD_ONLY = "🚫 هذا الأمر للإدارة أو مسؤولي التشغيل."
DISABLED = "رفع التقييم مو شغال في هذا السيرفر."


def hm(d):
    d = engine.parse_dt(d)
    return d.strftime("%H:%M") if d else "—"


def hm12(d):
    d = engine.parse_dt(d)
    if not d:
        return "—"
    h = d.hour % 12 or 12
    return "%d:%02d %s" % (h, d.minute, "AM" if d.hour < 12 else "PM")


def mention(did):
    did = str(did or "")
    if did.startswith("role:"):
        return "<@&%s>" % did[5:]
    return "<@%s>" % did if did.isdigit() else ""


def who(row):
    return mention(row.get("responsible_did")) or row.get("responsible") or "المسؤول"


def stars(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "—"
    return ("%.1f" % f).rstrip("0").rstrip(".") + "★"


def rating_line(row):
    avg = row.get("avg_at_open")
    n = row.get("n_at_open")
    need = row.get("needed_at_open")
    if not n:
        return "ما لها تقييمات كفاية بعد — كل تقييم يفرق (ناقص %s)" % (need or 3)
    return "%s من %s تقييم · ناقص %s تقييم ٥ نجوم عشان تتعدى ٤.٧٥" % (
        stars(avg), n, need or 0)


def state_line(row):
    s = STATE_AR.get(row.get("state"), row.get("state") or "—")
    if row.get("state_by") and row.get("state") not in (engine.WAITING,):
        s += " — %s" % row["state_by"]
    if row.get("wa_note") == "no_phone":
        s += " · ما فيه رقم"
    if row.get("review_stars"):
        s += " · %s" % stars(row["review_stars"])
    return s


def card(row):
    """The room's card, a plain dict in Discord's embed shape (bot.py draws it)."""
    fields = [
        {"name": "🏠 الشقة", "value": engine.unit_short(row.get("unit")) or "—", "inline": True},
        {"name": "👤 الضيف", "value": row.get("guest") or "—", "inline": True},
        {"name": "🧳 الخروج", "value": str(row.get("day") or "—"), "inline": True},
        {"name": "🙋 المسؤول", "value": row.get("responsible") or "—", "inline": True},
        {"name": "⭐ تقييم الشقة الحالي", "value": rating_line(row), "inline": False},
        {"name": "🧭 الوضع", "value": MODE_AR.get(row.get("mode"), "—"), "inline": True},
        {"name": "📌 الحالة", "value": state_line(row), "inline": False},
    ]
    if row.get("mode") == "care":
        fields.append({"name": "⚠️ تنبيه", "value": CARE_WARNING, "inline": False})
    color = 0xB88935
    if row.get("state") in (engine.REVIEWED,):
        color = 0x2E7D4F
    elif row.get("state") in (engine.COMPLAINT, engine.NO_ANSWER_FINAL, engine.WRONG_NUMBER):
        color = 0xB3261E
    elif row.get("state") in engine.TERMINAL:
        color = 0x8A8A8A
    return {"title": "⭐ رفع التقييم — %s" % (engine.unit_short(row.get("unit")) or "—"),
            "color": color, "fields": fields, "footer": {"text": FOOTER}}


# ------------------------------------------------------------------ room messages

def stage_ping(row, call_time_hhmm=""):
    st = row.get("state")
    if st == engine.WA_DUE:
        return ("%s 📱 وقت رسالة الواتساب للضيف %s — اضغط «فتح واتساب» (الرسالة مكتوبة باسمك)، "
                "وبعد ما ترسلها اضغط «أرسلت الرسالة»." % (who(row), row.get("guest") or ""))
    if st == engine.CARE_DUE:
        return ("%s 🤝 اتصل على الضيف %s اطمئنان — كان عنده بلاغ صيانة. لا تطلب تقييم إلا إذا "
                "كان راضي. لا تتصل بعد ١٠ مساءً." % (who(row), row.get("guest") or ""))
    if st == engine.CALL_DUE:
        n = int(row.get("calls_used") or 0) + 1
        return ("%s 📞 مكالمة الليلة (المحاولة %d) — ما وصلنا تقييم من %s. اتبع النص تحت، "
                "واضغط النتيجة. لا تتصل بعد ١٠ مساءً." % (who(row), n, row.get("guest") or ""))
    return "%s" % who(row)


def remind(row, n):
    if row.get("state") == engine.WA_DUE:
        return "%s ⏰ تذكير %d: رسالة الواتساب لسا ما انرسلت." % (who(row), n)
    return "%s ⏰ تذكير %d: المكالمة لسا ما صارت — قبل ١٠ مساءً." % (who(row), n)


def miss_line(row):
    if row.get("state") == engine.WA_DUE:
        return "🔴 فات وقت رسالة الواتساب اليوم — انحسبت على %s. المكالمة بكرة." % (
            row.get("responsible") or "المسؤول")
    return "🔴 فات وقت المكالمة الليلة — انحسبت على %s، ونفس المحاولة تنعاد بكرة." % (
        row.get("responsible") or "المسؤول")


def reviewed_post(stars_value):
    low = ""
    try:
        if float(stars_value) < 5:
            low = " · تقييم أقل من ٥"
    except (TypeError, ValueError):
        pass
    return "⭐ وصل تقييم الضيف: %s%s — انقفلت التذكرة. شكراً للفريق 🙏" % (stars(stars_value), low)


def close_post(state):
    return "🔒 انقفلت التذكرة: %s" % STATE_AR.get(state, state)


def press_saved(kind, row):
    base = {
        "sent": "✅ انحفظ: أرسلت الرسالة.",
        "no_phone": "✅ انحفظ: ما فيه رقم — استخدم رسالة Airbnb، والمكالمة بكرة.",
        "replied_will": "✅ انحفظ: الضيف بيقيّم.",
        "replied_no": "✅ انحفظ: الضيف ما يبي يقيّم.",
        "replied_quiet": "✅ انحفظ: رد بس ما قال شي — المكالمة بكرة.",
        "rated": "✅ انحفظ: قال إنه قيّم — تنقفل لما يوصل التقييم.",
        "promise": "✅ انحفظ: وعد يقيّم.",
        "noanswer": "✅ انحفظ: ما رد.",
        "later": "✅ انحفظ: نتصل عليه بكرة.",
        "decline": "✅ انحفظ: ما يبي يقيّم.",
        "wrong": "✅ انحفظ: الرقم غلط.",
        "satisfied": "✅ انحفظ: راضي — الحين أرسل له رسالة الواتساب.",
        "complaint": "✅ انحفظ: عنده ملاحظة — انفتحت تذكرة صيانة.",
    }.get(kind, "✅ انحفظ.")
    if kind == "noanswer" and row.get("state") == engine.NO_ANSWER_FINAL:
        base = "✅ انحفظ: ما رد للمرة الثانية — انقفلت التذكرة."
    elif kind == "noanswer":
        base += " نعيد الاتصال بكرة."
    return base


def press_line(kind, by):
    words = {
        "sent": "📱 أرسل الرسالة", "no_phone": "📵 ما فيه رقم", "replied_will": "💬 الضيف رد: بيقيّم",
        "replied_no": "💬 الضيف رد: ما يبي", "replied_quiet": "💬 الضيف رد بس ما قال شي",
        "rated": "⭐ الضيف قال إنه قيّم", "promise": "🙏 وعد يقيّم", "noanswer": "📵 ما رد",
        "later": "🔁 قال كلمني بعدين", "decline": "🚫 ما يبي يقيّم", "wrong": "☎️ الرقم غلط",
        "satisfied": "🤝 راضي", "complaint": "🛠️ عنده ملاحظة",
    }
    return "%s — %s" % (words.get(kind, kind), by or "—")


def taken(row):
    return "انحفظت قبلك من %s (%s)." % (row.get("state_by") or "النظام",
                                        STATE_AR.get(row.get("state"), row.get("state")))


AIRBNB_LINE = "ما عندنا رقم الضيف — راسله من Airbnb:"
COMPLAINT_ASK = "وش مستوى الاستعجال؟ اختر، بعدها اضغط «اكتب كلام الضيف»."
REPLIED_ASK = "وش قال الضيف؟"


def complaint_room_reply(maint_channel_id):
    return "🛠️ انفتحت تذكرة صيانة من المكالمة: <#%s>" % maint_channel_id


def maint_summary(unit, guest):
    return ("من مكالمة تقييم — %s — %s" % (engine.unit_short(unit) or "—",
                                          engine.guest_first(guest) or "ضيف"))[:120]


def maint_details(words, presser, res_id, day):
    return NL.join([str(words or "").strip(), "", "اتصل: %s" % (presser or "—"),
                    "رقم الحجز: %s" % (res_id or "—"), "تاريخ الخروج: %s" % (day or "—")])


# ------------------------------------------------------------------ commands

def open_summary(rep, day, dry):
    lines = []
    head = "🗓️ تقييمات %s" % day
    if dry:
        head += " — تجربة (ما انفتح شي، النظام موقف)"
    lines.append(head)
    if dry:
        lines.append("بتنفتح %d غرفة:" % len(rep.get("would_open") or []))
        for it in rep.get("would_open") or []:
            lines.append("• %s — %s (%s)" % (engine.unit_short(it.get("unit")), it.get("guest") or "—",
                                            MODE_AR.get(it.get("mode"), "")))
    else:
        lines.append("انفتحت %d غرفة · موجودة من قبل %d" % (len(rep.get("opened") or []),
                                                       len(rep.get("existing") or [])))
        for it in rep.get("opened") or []:
            lines.append("• %s — %s" % (engine.unit_short(it.get("unit")), it.get("guest") or "—"))
    skipped = rep.get("skipped") or []
    if skipped:
        lines.append("")
        lines.append("ما انفتحت (%d):" % len(skipped))
        for it in skipped:
            lines.append("• %s — %s" % (engine.unit_short(it.get("unit")) or "—",
                                       engine.SKIP_AR.get(it.get("reason"), it.get("reason"))))
    if rep.get("error"):
        lines.append("")
        lines.append("⚠️ %s" % rep["error"])
    return NL.join(lines)


START_REPLY = "▶️ اشتغل رفع التقييم — الغرف تنفتح الساعة ١٢:٠٥ كل ليلة، والرسائل تبدأ ٥ العصر."
STOP_REPLY = "⏸️ وقف رفع التقييم (الأزرار تظل تسجل)."
TEMPLATE_SAVED = "✅ انحفظ النص — من الحين كل رسالة واتساب تطلع بالنص الجديد."


# ------------------------------------------------------------------ board + report

BOARD_SECTIONS = (
    ("wa", "📱 اليوم: واتساب لازم ينرسل"),
    ("call", "📞 مكالمات الليلة"),
    ("wait", "🙏 بانتظار التقييم"),
    ("closed", "🔒 انقفلت اليوم"),
    ("low", "⚠️ تقييمات أقل من ٥"),
    ("weak", "🏠 الشقق تحت ٤.٧٥"),
)
BOARD_EMPTY = "ما فيه شي اليوم."


def board_header(now):
    return "**⭐ متابعة التقييمات — %s** (آخر تحديث %s)" % (now.date().isoformat(), hm12(now))


def board_line(row):
    bits = [engine.unit_short(row.get("unit")) or "—", row.get("guest") or "—"]
    if row.get("responsible"):
        bits.append(row["responsible"])
    if row.get("review_stars"):
        bits.append(stars(row["review_stars"]))
    elif row.get("state") in engine.TERMINAL:
        bits.append(STATE_AR.get(row.get("state"), row.get("state")))
    return " · ".join(str(b) for b in bits)


def weak_line(st, name):
    avg = stars(st.get("avg")) if st.get("avg") is not None else "بدون تقييم"
    s = "%s — %s · ناقص %s" % (engine.unit_short(name), avg, st.get("needed") or 0)
    if st.get("open_tickets"):
        s += " · تكتات مفتوحة %d" % st["open_tickets"]
    if st.get("pinned"):
        s += " · مثبتة يدوي"
    return s


def summary(day, s):
    lines = ["**📊 ملخص رفع التقييم — %s**" % day,
             "⭐ تقييمات وصلت اليوم: %d%s" % (s["reviews"], (" (%s)" % "، ".join(stars(x) for x in s["stars"]))
                                              if s["stars"] else ""),
             "📱 رسائل الواتساب: %d من %d" % (s["wa_done"], s["wa_due"]),
             "📞 المكالمات: %d من %d" % (s["calls_done"], s["calls_due"]),
             "🔴 فوات على الفريق: %d" % s["misses"],
             "🛠️ ملاحظات انفتح لها صيانة: %d" % s["complaints"]]
    return NL.join(lines)


def monitor_header(now):
    return "**⭐ رفع التقييم — %s**" % hm12(now)


def monitor_line(row, minutes, what):
    return "• %s — %s — %s · متأخر %d دقيقة" % (
        row.get("responsible") or "بدون مسؤول", engine.unit_short(row.get("unit")), what, minutes)


def report(people, apartments, title):
    lines = ["**%s**" % title, ""]
    if not people:
        lines.append("ما فيه نشاط في هذي الفترة.")
    for p in people:
        lines.append("👤 **%s** — رسائل %s · مكالمات %s · تقييمات جت %d (متوسط %s) · فوات %d" % (
            p["name"], _rate(p["wa_done"], p["wa_due"]), _rate(p["calls_done"], p["calls_due"]),
            p["reviews"], stars(p["avg_stars"]) if p["avg_stars"] else "—", p["misses"]))
    if apartments:
        lines += ["", "**🏠 الشقق**"]
        for a in apartments:
            lines.append("• %s — كانت %s، الحين %s · ناقص %s" % (
                engine.unit_short(a["unit"]), stars(a["then"]) if a["then"] else "—",
                stars(a["now"]) if a["now"] else "—", a["needed"]))
    return NL.join(lines)


def _rate(done, due):
    if not due:
        return "—"
    return "%d/%d (%d٪)" % (done, due, round(100.0 * done / due))
