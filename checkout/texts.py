# -*- coding: utf-8 -*-
"""
checkout.texts — EVERY word «متابعة الخروج» says, and nothing else. PURE.

Rules for this file (the tests read them back):
  * Team messages: short, casual Najdi. No money figures, no criticism of the platform, no
    remarks on a named person's performance. A factual line such as «أكده ناصر 12:40» is fine.
  * Guest messages (Airbnb chat, WhatsApp): NO DIGITS at all — the outbound firewall's R1
    treats a run of digits near a door word as a leaked code — and no readiness words.
  * Newlines are built with NL, never typed as an escape inside a longer literal.
"""

import urllib.parse

from . import engine

NL = "\n"
GOLD, GREEN, RED, AMBER, GREY = 0xC8A24B, 0x0E9E5F, 0xC44343, 0xF0A431, 0x8A8378

# ------------------------------------------------------------------ small helpers


def hm(d):
    d = engine.parse_dt(d)
    return d.strftime("%H:%M") if d else "—"


def mention(did):
    did = str(did or "")
    if did.startswith("role:"):
        return "<@&%s>" % did[5:]
    return ("<@%s>" % did) if did.isdigit() else ""


def who(row):
    """The person to address: a mention when we can reach them, the name otherwise."""
    return mention(row.get("responsible_did")) or (row.get("responsible") or "المسؤول")


def _strip_digits(s):
    return "".join(c for c in str(s or "") if not c.isdigit())


def guest_first(guest):
    """First name only, and never a digit (guest names sometimes carry a booking number)."""
    words = [w for w in _strip_digits(guest).replace("|", " ").split() if w.strip()]
    return words[0] if words else ""


# ------------------------------------------------------------------ labels

REASONS_AR = {
    "late_ok": "عنده تأخير خروج موافق عليه",
    "late_ask": "يطلب تأخير خروج الحين",
    "packing": "يجهز أغراضه — شوي ويطلع",
    "unaware": "ما كان يدري بوقت الخروج",
    "refuse": "رافض يطلع / فيه مشكلة",
    "other": "سبب ثاني",
    "surprise": "الفريق وصل ولقاه داخل",
}

EXPECT_AR = {"30m": "30 دقيقة", "1h": "ساعة", "2h": "ساعتين", "3h": "3 ساعات",
             "custom": "وقت ثاني"}

EXPECT_ERRORS = {
    "format": "اكتب الوقت بصيغة 24 ساعة، مثل 14:30.",
    "past": "الوقت لازم يكون بعد الحين.",
    "tomorrow": "الوقت لازم يكون اليوم — قبل 12 بالليل.",
    "choice": "اختر وقت الخروج المتوقع.",
}

BUTTON_LABELS = {
    "yes": "✅ طلع",
    "noanswer": "📵 ما رد",
    "no": "⛔ ما طلع",
    "wa": "📱 واتساب الضيف",
    "surprise": "🚨 وصلنا والضيف داخل",
    "demo_ff": "⏩ قدّم الوقت 30 دقيقة",
}


# ------------------------------------------------------------------ §5a playbook + cap


def playbook(row, deadline):
    code = row.get("reason_code") or ""
    latest = engine.latest_ok_exit(row.get("checkin_at"), deadline, row.get("clean_minutes"))
    if code == "late_ok":
        return "تأكد إن وقت التأخير مسجل. نسأل تلقائي وقت خروجه الجديد."
    if code == "late_ask":
        if row.get("checkin_at"):
            return "فيه دخول اليوم %s — أقصى تأخير نقدر نعطيه %s." % (hm(row["checkin_at"]), hm(latest))
        return "ما فيه دخول اليوم — أقصى تأخير لين %s." % hm(latest)
    if code == "packing":
        return "نسأله تلقائي بعد الوقت اللي حددته."
    if code == "unaware":
        return "أرسل له واتساب بوقت الخروج — ونسأله تلقائي بعد الوقت اللي حددته."
    if code == "refuse":
        return ("تواصل معه بهدوء ووثق كل شي هنا بالقناة. "
                + ("فيه دخول اليوم %s — جهز خطة للضيف الجاي." % hm(row["checkin_at"])
                   if row.get("checkin_at") else "ما فيه دخول اليوم."))
    if code == "other":
        return (row.get("reason_text") or "").strip()
    if code == "surprise":
        return "كلمه الحين وتأكد متى يطلع — واضغط ✅ أول ما يطلع."
    return ""


def cap_line(row, deadline):
    if not engine.red_cap(row.get("expected_out_at"), row.get("checkin_at"), deadline,
                          row.get("clean_minutes")):
        return ""
    anchor = engine.cap_anchor(row.get("checkin_at"), deadline)
    latest = engine.latest_ok_exit(row.get("checkin_at"), deadline, row.get("clean_minutes"))
    return "🔴 لو طلع %s ما نلحق ننظف قبل %s — أقصى وقت نقدر نعطيه %s" % (
        hm(row.get("expected_out_at")), hm(anchor), hm(latest))


# ------------------------------------------------------------------ state lines


def state_line(row, card=False):
    st = row.get("state")
    by, at = row.get("state_by") or "", hm(row.get("state_at"))
    if st == engine.WAITING:
        return "⏳ ننتظر وقت الخروج"
    if st == engine.ASKING:
        return "⏰ ننتظر الرد — طلع الضيف؟" if row.get("pinged_at") else "⏳ ننتظر وقت الخروج"
    if st == engine.OUT:
        if card:
            return "✅ الضيف طلع — أكده %s %s · الشقة جاهزة للتنظيف 🧹" % (by, at)
        return "✅ طلع — أكده %s %s" % (by, at)
    if st == engine.NO_ANSWER:
        return "📵 الضيف ما رد — سجله %s %s" % (by, at)
    if st == engine.INSIDE:
        reason = REASONS_AR.get(row.get("reason_code") or "", "")
        exp = row.get("expected_out_at")
        tail = (" · متوقع يطلع %s" % hm(exp)) if exp else ""
        return "⛔ الضيف داخل — %s%s (سجله %s %s)" % (reason or "ما طلع", tail, by, at)
    if st == engine.CLEANED:
        return "🧹 انرسل تقرير التنظيف — بانتظار الاعتماد"
    if st == engine.APPROVED:
        return "✔️ التنظيف معتمد"
    return "—"


def _color(row):
    st = row.get("state")
    if st in (engine.OUT, engine.APPROVED):
        return GREEN
    if st in (engine.INSIDE, engine.NO_ANSWER):
        return RED
    if st == engine.CLEANED:
        return AMBER
    return GOLD


# ------------------------------------------------------------------ the Checkout Card


def card(row, deadline, hint=False):
    """{title, description, color} — the ONE card, edited in place on every change."""
    demo = bool(row.get("demo"))
    title = ("🎬 تجربة · " if demo else "") + "🚪 متابعة الخروج — %s" % (row.get("unit") or "")
    lines = ["**الضيف:** %s" % (row.get("guest") or "ضيف")]
    ln = "**الخروج:** %s" % hm(row.get("checkout_at"))
    if row.get("checkin_at"):
        ln += " · 🔴 دخول اليوم %s" % hm(row.get("checkin_at"))
    lines.append(ln)
    lines.append("**المسؤول:** %s" % (row.get("responsible") or "—"))
    lines.append("**الحالة:** %s" % state_line(row, card=True))
    if row.get("state") == engine.INSIDE:
        pb = playbook(row, deadline)
        if pb:
            lines.append("📋 " + pb)
        cap = cap_line(row, deadline)
        if cap:
            lines.append(cap)
    if hint and row.get("state") in engine.OPEN:
        lines.append("💡 الضيف كتب في الشات إنه طلع — تأكد واضغط ✅")
    if row.get("airbnb_note"):
        lines.append(row["airbnb_note"])
    if row.get("state") in engine.OPEN or row.get("state") == engine.OUT:
        lines.append("")
        lines.append("_اضغط الزر المناسب — اسمك ينحفظ مع الجواب._")
    return {"title": title[:250], "description": NL.join(lines)[:3900], "color": _color(row)}


# ------------------------------------------------------------------ channel messages


def ping(row):
    return "%s 🚪 وقت خروج **%s** من **%s** (%s). طلع الضيف؟" % (
        who(row), row.get("guest") or "الضيف", row.get("unit") or "", hm(row.get("checkout_at")))


def remind(row, n, minutes):
    if row.get("state") == engine.NO_ANSWER:
        return ("⏰ %s %s: الضيف ما رد من %d دقيقة. جربت الواتساب والاتصال؟ طلع الضيف؟"
                % (who(row), row.get("unit") or "", minutes))
    if row.get("state") == engine.INSIDE:
        return ("⏰ %s %s: الفريق لقى الضيف داخل من %d دقيقة. طلع الحين؟"
                % (who(row), row.get("unit") or "", minutes))
    return ("⏰ %s %s: ما جاوب أحد من %d دقيقة. طلع الضيف؟"
            % (who(row), row.get("unit") or "", minutes))


def reask(row):
    return "%s 🔁 **%s**: قلتوا الضيف بيطلع %s. طلع؟" % (
        who(row), row.get("unit") or "", hm(row.get("expected_out_at")))


def reask_now(row):
    return "%s 🔁 **%s**: طلع الضيف الحين؟" % (who(row), row.get("unit") or "")


YES_POST = "🧹 تقدرون تدخلون — الضيف طلع"
BEFORE_OUT = "⚠️ انتبهوا: ما تأكدنا إن الضيف طلع قبل الدخول"


def surprise_post(row):
    return "🚨 الفريق وصل والضيف داخل — %s تواصل معه الحين" % who(row)


def reply_saved(kind, row):
    if kind == "yes":
        return "✅ انحفظ: الضيف طلع — باسمك. بلغنا الفريق يدخلون."
    if kind == "noanswer":
        return "📵 انحفظ: الضيف ما رد. بنذكرك كل 30 دقيقة لين يتأكد."
    if kind == "no":
        return "⛔ انحفظ: الضيف داخل — متوقع يطلع %s. بنسألك وقتها." % hm(row.get("expected_out_at"))
    if kind == "surprise":
        return "🚨 انحفظ. بلغنا المسؤول وحطينا تنبيه للفريق."
    return "تم ✅"


def reply_taken(row):
    return "انحفظت قبلك من %s (%s)." % (row.get("state_by") or "زميلك", state_line(row))


REPLY_NOT_FOUND = "ما لقينا هذي الشقة في المتابعة."
REPLY_NOANSWER_AGAIN = "مسجل من قبل إن الضيف ما يرد — كمل المحاولة واضغط ✅ أو ⛔ أول ما يرد."


# ------------------------------------------------------------------ guest messages (NO DIGITS)


def airbnb_body(guest, second=False):
    """The second message must differ from the first: send_guest_message de-duplicates on the
    raw body, so an identical follow-up would be silently suppressed."""
    g = guest_first(guest)
    if second:
        ar = ("مرحبا %s 👋 " % g if g else "مرحبا 👋 ") + \
            "نعيد نسأل: طلعت من الشقة؟ فريق التنظيف ينتظر ردك 🙏"
        en = ("Hi %s, " % g if g else "Hi, ") + \
            "following up — have you checked out? Our cleaning team is waiting on your reply 🙏"
        return _strip_digits(ar + NL + en)
    ar = ("مرحبا %s 👋 " % g if g else "مرحبا 👋 ") + \
        "نبي نتأكد إذا طلعت من الشقة، لأن فريق التنظيف في الطريق. طمنّا بكلمة 🙏"
    en = ("Hi %s, " % g if g else "Hi, ") + \
        "just checking whether you've checked out — our cleaning team is on the way. " \
        "A quick reply helps 🙏"
    return _strip_digits(ar + NL + en)


def wa_text(guest, presser_name):
    g = guest_first(guest)
    p = _strip_digits(presser_name).strip() or "فريق عوجا"
    ar = ("مرحبا %s 👋 " % g if g else "مرحبا 👋 ") + \
        "معك %s من عوجا. حبيت أتأكد: هل طلعت من الشقة؟ لأن فريق التنظيف متجه لك الحين 🙏" % p
    en = ("Hi %s, " % g if g else "Hi, ") + \
        "this is %s from Ouja. Just checking — have you checked out? " \
        "Our cleaning team is heading over now 🙏" % p
    return _strip_digits(ar + NL + en)


def wa_link(number, text):
    """number = 'wa.me/<intl>' (bot.py's _wa_from_phone) or '' → the contact picker."""
    enc = urllib.parse.quote(text, safe="")
    if number:
        return "https://%s?text=%s" % (number, enc)
    return "https://wa.me/?text=%s" % enc


WA_REPLY = "📱 رسالة جاهزة باسمك — اضغط الزر وتفتح المحادثة:"
WA_NO_PHONE = "ما عندنا رقم الضيف"
WA_DEMO = "🎬 تجربة — الرابط يفتح قائمة الأسماء بدون رقم، عشان ما تنرسل لأحد حقيقي."


def airbnb_failed(reason):
    return "⚠️ ما انرسلت رسالة Airbnb (%s)" % (reason or "خطأ")


def airbnb_sent_line(n):
    return "💬 انرسلت رسالة للضيف في Airbnb (%s)" % ("الأولى" if n == 1 else "الثانية")


def demo_airbnb_preview(body):
    return "🎬 تجربة — كان بينرسل للضيف: «%s»" % body.replace(NL, " / ")


# ------------------------------------------------------------------ board (§10)

BOARD_SECTIONS = (
    ("act", "🔴 يحتاج تصرف"),
    ("wait", "⏳ ننتظر وقت الخروج"),
    ("out", "✅ طلع — ننظف"),
    ("review", "🧹 بانتظار الاعتماد"),
    ("done", "✔️ معتمدة"),
)


def board_line(row):
    s = "%s · %s · خروج %s" % (row.get("unit") or "", row.get("guest") or "ضيف",
                               hm(row.get("checkout_at")))
    if row.get("checkin_at"):
        s += " · 🔴 دخول %s" % hm(row.get("checkin_at"))
    s += " · %s" % state_line(row)
    if row.get("channel_id"):
        s += " · <#%s>" % row["channel_id"]
    return s


def board_header(now):
    return "📋 **متابعة الخروج** — آخر تحديث %s · الهدف: كل الشقق معتمدة قبل ٥ العصر" % hm(now)


BOARD_EMPTY = "ما فيه خروج اليوم في المتابعة."


def summary(n, on_time, late_units):
    s = "📊 **ملخص الساعة ٥** — اليوم %d خروج · معتمدة قبل ٥: %d" % (n, on_time)
    s += " · متأخرة: %s" % ("، ".join(late_units) if late_units else "ولا وحدة 👏")
    return s


# ------------------------------------------------------------------ risk (§8.3)

RISK_ICON = {"red": "🔴", "orange": "🟠", "green": "🟢", "done": "✅"}

RISK_REASON = {
    "inside_checkin": ("الضيف داخل وفيه دخول اليوم", "كلمه الحين واتفق على وقت خروج قبل %(latest)s"),
    "noanswer_checkin": ("الضيف ما يرد وفيه دخول اليوم", "جرب الواتساب والاتصال الحين"),
    "slack_negative": ("ما يمدينا ننظف قبل الدخول", "جهز فريق إضافي أو خطة للضيف الجاي"),
    "surprise": ("الفريق لقى الضيف داخل اليوم", "تأكد إنه طلع قبل يرجع الفريق"),
    "past_deadline": ("عدت ٥ العصر وما انعتمدت", "خلصوا التنظيف واعتمدوا التقرير"),
    "unconfirmed_checkin": ("ما تأكدنا إنه طلع وفيه دخول اليوم", "اضغط ✅ أو ⛔ في قناة الشقة"),
    "slack_low": ("الوقت ضيق — أقل من ساعة فراغ", "ابدأوا التنظيف أول ما يطلع"),
    "early_checkin": ("فيه دخول مبكر معتمد", "رتبوا التنظيف قبل وقت الدخول المبكر"),
    "ok": ("ماشي تمام", "—"),
    "done": ("خلصت", "—"),
}


def risk_header(n, with_ci, counts):
    return ("🧭 **خطر اليوم** — اليوم %d خروج · %d منها فيها دخول اليوم · 🔴 %d · 🟠 %d · 🟢 %d · ✅ %d"
            % (n, with_ci, counts.get("red", 0), counts.get("orange", 0),
               counts.get("green", 0), counts.get("done", 0)))


def risk_line(row, level, code, deadline):
    latest = engine.latest_ok_exit(row.get("checkin_at"), deadline, row.get("clean_minutes"))
    reason, step = RISK_REASON.get(code, ("—", "—"))
    step = step % {"latest": hm(latest)} if "%(" in step else step
    arrow = " → دخول %s" % hm(row.get("checkin_at")) if row.get("checkin_at") else " → بدون دخول"
    return ("%s **%s** · %s · خروج %s%s · %s · %s" % (
        RISK_ICON.get(level, ""), row.get("unit") or "", row.get("guest") or "ضيف",
        hm(row.get("checkout_at")), arrow, state_line(row), row.get("responsible") or "—")
        + NL + "   السبب: %s · الخطوة: %s" % (reason, step))


def risk_rest(level, units):
    return "%s %s" % (RISK_ICON.get(level, ""), "، ".join(units))


# ------------------------------------------------------------------ report (§8.6, ephemeral)


def report(rows, title):
    lines = ["📈 **%s** — للإدارة فقط" % title]
    if not rows:
        lines.append("ما فيه بيانات للفترة.")
        return NL.join(lines)
    for r in rows:
        med = "—" if r["median_answer_min"] is None else "%d د" % r["median_answer_min"]
        pct = "—" if r["on_time_pct"] is None else "%d٪" % r["on_time_pct"]
        lines.append("**%s** — خروج: %d · أول جواب بعد الخروج (وسيط): %s · ما رد: %d · "
                     "تذكيرات: %d · مفاجآت بعد ✅ حقه: %d · معتمدة قبل ٥: %s"
                     % (r["name"], r["turnovers"], med, r["noanswer"], r["reminders"],
                        r["surprises"], pct))
    return NL.join(lines)


# ------------------------------------------------------------------ commands


def start_summary(n, m, k, no_channel):
    s = "✅ اشتغل. حولت %d قناة · منها %d وقت خروجها عدى وانسألت الحين · %d منظفة وتخطيتها" % (n, m, k)
    s += " · بدون قناة: %s" % ("، ".join(no_channel) if no_channel else "ولا وحدة")
    return s


STOP_REPLY = "⏸️ وقفت المتابعة"
ADMIN_ONLY = "🚫 هذا الأمر للإدارة فقط."
DEMO_ENDED = "🧹 مسحت قنوات التجربة وبياناتها (%d قناة · %d شقة تجريبية)."
DEMO_READY = "🎬 جهزت التجربة: %s"


# ------------------------------------------------------------------ demo (§9)

DEMO_GUEST = "ضيف تجريبي"
DEMO_BADGE = "🎬 تجربة"

DEMO_CHANNELS = (
    ("تجربة-1-طلع", "yes"),
    ("تجربة-2-ما-رد", "noanswer"),
    ("تجربة-3-ما-طلع", "no"),
    ("تجربة-4-مفاجأة", "surprise"),
    ("تجربة-5-خطر-اليوم", "risk"),
)

DEMO_STEPS = {
    "yes": [
        "١. هذي قناة الشقة. أول ما يجي وقت الخروج البوت يمنشن المسؤول.",
        "٢. اضغط ⏩ قدّم الوقت — كأن وقت الخروج جا، وبيطلع لك سؤال «طلع الضيف؟».",
        "٣. اضغط ✅ طلع إذا تأكدت إن الضيف طلع — اسمك ينحفظ.",
        "٤. شوف الكرت تغير لحاله، والبوت كتب «تقدرون تدخلون» للفريق.",
    ],
    "noanswer": [
        "١. اضغط ⏩ قدّم الوقت — جا وقت الخروج.",
        "٢. الضيف ما يرد؟ اضغط 📵 ما رد.",
        "٣. البوت يكتب رسالة Airbnb للضيف (هنا بس معاينة — ما تنرسل).",
        "٤. اضغط ⏩ مرة ثانية — كل مرة كأنها ٣٠ دقيقة، ويجيك تذكير.",
        "٥. أول ما يرد الضيف اضغط ✅ أو ⛔ ويوقف التذكير.",
    ],
    "no": [
        "١. اضغط ⏩ قدّم الوقت — جا وقت الخروج.",
        "٢. الضيف لسه داخل؟ اضغط ⛔ ما طلع.",
        "٣. اختر السبب «يطلب تأخير خروج الحين» واختر متى بيطلع، واضغط حفظ.",
        "٤. شوف الكرت: فيه دخول اليوم — ولو الوقت متأخر يطلع لك سطر أحمر بأقصى وقت نقدر نعطيه.",
        "٥. اضغط ⏩ — البوت يرجع يسألك في الوقت اللي حددته.",
    ],
    "surprise": [
        "١. اضغط ⏩ قدّم الوقت، بعدها اضغط ✅ طلع.",
        "٢. تخيل الفريق وصل الباب ولقى الضيف داخل — اضغط 🚨 وصلنا والضيف داخل.",
        "٣. البوت ينبه المسؤول على طول ويرجع يسأل، وينحفظ مين ضغط ✅ قبلها.",
        "٤. 📱 واتساب الضيف يعطيك رسالة جاهزة باسمك.",
    ],
    "risk": [
        "١. هذي القناة تعرض تحليل خطر اليوم على شقق التجربة.",
        "٢. العب بالأزرار في القنوات ١ إلى ٤، بعدها اكتب /checkout-risk هنا.",
        "٣. داخل هذي القناة الأمر يحسب على شقق التجربة بس — برا يحسب على الشقق الحقيقية.",
        "٤. 🔴 أول، بعدها 🟠 — كل وحدة معها السبب والخطوة الجاية.",
    ],
}


def demo_steps(scenario):
    return {"title": "📖 خطوات الفيديو", "description": NL.join(DEMO_STEPS.get(scenario, [])),
            "color": GOLD}


def demo_sample_turnover(unit):
    return {"title": "🎬 تجربة · 🧹 Turnover — Ready to Clean",
            "description": NL.join(["**Unit:** %s" % unit, "**Guest:** %s" % DEMO_GUEST,
                                    "_هذا مثال على كرت التنظيف اللي ينفتح لكل شقة._"]),
            "color": GREY}
