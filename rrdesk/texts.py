# -*- coding: utf-8 -*-
"""
rrdesk.texts — every word «طلبات سام» sends. Staff: Najdi, casual, short. Sam: plain English.

House rules enforced by keeping all wording here (and by tests/test_rrdesk_structure.py):
  * no company money figures (fees, revenue, nightly rates) in any staff-room line
  * no per-person numbers in shared rooms — names + numbers go to DMs / غرفة-المراقبة only
  * no lines that comment on platform faults
Zero backslashes: newlines are NL = chr(10).
"""

from . import engine

NL = chr(10)
MARK = engine.INVISIBLE_MARK

ASK_EN = {"photos": "photos", "video": "a video", "invoice": "the invoice",
          "quote": "a quote", "guest_chat": "the guest chat", "airbnb_screens": "Airbnb screenshots",
          "ops_report": "an ops report", "receipt": "the receipt", "info": "information",
          "action": "an action", "other": "something"}
ASK_AR = {"photos": "صور", "video": "فيديو", "invoice": "الفاتورة", "quote": "عرض سعر",
          "guest_chat": "محادثة الضيف", "airbnb_screens": "سكرينات من Airbnb",
          "ops_report": "تقرير العمليات", "receipt": "الإيصال", "info": "معلومة",
          "action": "إجراء", "other": "طلب"}

STATE_EN = {"open": "Waiting", "acknowledged": "On it", "delivered": "Delivered",
            "confirmed": "Confirmed", "confirmed_auto": "Confirmed (auto)",
            "cancelled": "Cancelled", "closed_with_ticket": "Closed with ticket"}
STATE_AR = {"open": "ينتظر", "acknowledged": "قيد التنفيذ", "delivered": "تم التسليم",
            "confirmed": "تأكد ✓", "confirmed_auto": "تأكد تلقائياً",
            "cancelled": "ملغي", "closed_with_ticket": "انقفل مع التذكرة"}
STATE_EMOJI = {"open": "🟠", "acknowledged": "🔵", "delivered": "🟢", "confirmed": "✅",
               "confirmed_auto": "✅", "cancelled": "⚪", "closed_with_ticket": "🔒"}

FOOTER_AR2EN = "Auto-translation · AR→EN"
FOOTER_EN2AR = "ترجمة تلقائية · EN→AR"
CARD_FOOTER = "RR Desk · طلبات سام"
OUR_FOOTERS = (FOOTER_AR2EN, FOOTER_EN2AR, CARD_FOOTER)

# Button labels (text only — R2 house rule) and their static custom ids.
BTN = {
    "ack": ("استلمت · On it", "rd:ack"),
    "deliver": ("سلّمت · Delivered", "rd:deliver"),
    "got_it": ("Got it ✓", "rd:gotit"),
    "not_what": ("Not what I asked", "rd:notwhat"),
    "cancel": ("Cancel", "rd:cancel"),
    "reassign": ("Reassign", "rd:reassign"),
    "q_yes": ("Is this a request? Yes", "rd:qyes"),
    "q_no": ("No", "rd:qno"),
    "image": ("Translate image text", "rd:img"),
    "excuse": ("عذر · Excuse", "rd:excuse"),
}


def asks_en(asks):
    return ", ".join(ASK_EN.get(a, a) for a in (asks or ["other"]))


def asks_ar(asks):
    return "، ".join(ASK_AR.get(a, a) for a in (asks or ["other"]))


def mention(did):
    d = str(did or "")
    return ("<@%s>" % d) if d.isdigit() else ""


# ------------------------------------------------------------------ in-room replies

VOICE_REPLY = "سام ما يقدر يسمع الفويس — اكتبها نص الله يعافيك 🙏" + MARK

REFUSE = {
    "not_owner": "هذا الزر لصاحب الطلب أو للفريق.",
    "not_sam": "This button is for Sam or an admin.",
    "not_lead": "هذا الزر لقائد العمليات أو الإدارة.",
    "need_file": ("ما شفت أي ملف أو صورة بالروم بعد طلب سام — ارفع المطلوب أول، بعدين اضغط «سلّمت»."),
    "already": "انحفظت قبلك من {who}.",
    "closed": "الطلب انقفل — ما يحتاج شي.",
    "gone": "ما لقيت هذا الطلب.",
    "excuse_late": "فات وقت العذر (٤٨ ساعة). الإنذار — لو صار — يُراجع من رابط الاعتراض.",
    "excuse_short": "اكتب سبب واضح (١٠ أحرف على الأقل).",
    "off": "النظام موقف الحين.",
}


def done_line(event, who_name):
    return {
        "ack": "🔵 %s استلم الطلب." % who_name,
        "deliver": "🟢 %s سلّم المطلوب — Sam, please confirm." % who_name,
        "got_it": "✅ Sam confirmed. شكراً %s." % who_name,
        "not_what": "↩️ Sam: not what he asked — رجع الطلب للتنفيذ.",
        "cancel": "⚪ Cancelled by %s." % who_name,
        "reassign": "🔁 الطلب انتقل.",
    }.get(event, "تم.") + MARK


# ------------------------------------------------------------------ the request card

def card(req, now):
    """(content, embed dict). The content carries the owner mention (so it actually pings);
    the embed is the readable card. No money, no per-person numbers."""
    rdue, ddue = engine._dt(req.get("resp_due")), engine._dt(req.get("deliv_due"))
    st = req.get("state") or "open"
    owner = mention(req.get("owner_did")) or (req.get("owner_name") or "—")
    lines_en = [req.get("summary_en") or (req.get("text") or "")[:300]]
    lines_ar = [req.get("summary_ar") or ""]
    fields = [
        {"name": "Owner · المسؤول", "value": owner + (" · ⚠️ unowned" if req.get("unowned") else ""),
         "inline": True},
        {"name": "Status · الحالة",
         "value": "%s %s · %s" % (STATE_EMOJI.get(st, ""), STATE_EN.get(st, st), STATE_AR.get(st, st)),
         "inline": True},
        {"name": "Asks · المطلوب", "value": "%s · %s" % (asks_en(req.get("asks")), asks_ar(req.get("asks"))),
         "inline": False},
    ]
    if rdue and st == "open":
        fields.append({"name": "Response due · الرد قبل",
                       "value": "%s · %s" % (engine.fmt_due_en(rdue, now), engine.fmt_due_ar(rdue, now)),
                       "inline": True})
    if ddue and st in ("open", "acknowledged"):
        fields.append({"name": "Delivery due · التسليم قبل",
                       "value": "%s · %s" % (engine.fmt_due_en(ddue, now), engine.fmt_due_ar(ddue, now)),
                       "inline": True})
    if req.get("urgent"):
        fields.append({"name": "⚡ Urgent · مستعجل", "value": urgent_why(req.get("urgent_why")),
                       "inline": False})
    title = "📌 Sam's request #%s" % req.get("id")
    if req.get("ticket_seq"):
        title += " · RR #%s" % req.get("ticket_seq")
    embed = {"title": title,
             "description": (NL.join([x for x in lines_en if x]) + NL + NL +
                             NL.join([x for x in lines_ar if x])).strip()[:3900],
             "fields": fields, "footer": CARD_FOOTER, "color": 0xC9A227}
    content = "%s طلب جديد من سام%s" % (owner, MARK) if st == "open" else MARK
    return content, embed


def urgent_why(code):
    return {"flag": "Sam marked it urgent · سام حدده مستعجل",
            "aircover": "AirCover deadline ≤ 3 days · مهلة AirCover قربت"}.get(code or "", "—")


def card_buttons(state):
    if state in ("open", "acknowledged"):
        keys = (["ack"] if state == "open" else []) + ["deliver", "cancel", "reassign"]
    elif state == "delivered":
        keys = ["got_it", "not_what", "reassign"]
    else:
        keys = []
    return [{"label": BTN[k][0], "custom_id": BTN[k][1],
             "style": "success" if k in ("ack", "deliver", "got_it") else
             ("danger" if k in ("not_what", "cancel") else "secondary")} for k in keys]


# ------------------------------------------------------------------ the ladder

def ladder_room(step, req):
    who = mention(req.get("owner_did")) or (req.get("owner_name") or "")
    what = asks_ar(req.get("asks"))
    seq = req.get("ticket_seq") or "?"
    lines = {
        "R1": "%s سام ينتظر ردك على طلبه (%s) — RR #%s 🙏",
        "R2": "%s فات وقت الرد على طلب سام (%s) — RR #%s. رد عليه الحين الله يعافيك.",
        "D1": "%s باقي وقت قليل على تسليم طلب سام (%s) — RR #%s.",
        "D2": "%s فات موعد تسليم طلب سام (%s) — RR #%s. سلّمه واضغط «سلّمت».",
        "MISS": "%s طلب سام (%s) — RR #%s ما انسلّم بوقته. انسجّل تأخير.",
    }
    return (lines[step] % (who, what, seq)) + MARK


def ladder_dm(step, req, link):
    what = asks_ar(req.get("asks"))
    seq = req.get("ticket_seq") or "?"
    if step == "R2":
        return ("⏰ طلب سام في RR #%s (%s) ينتظر ردك من فترة. اضغط «استلمت» أو رد عليه: %s"
                % (seq, what, link))
    return ("🔴 طلب سام في RR #%s (%s) فات وقته مرتين وانسجّل عليك تأخير. لو عندك عذر كلم أصيل. %s"
            % (seq, what, link))


def watchdog_d2(req, link):
    return ("🟠 RR #%s — طلب سام (%s) فات موعد تسليمه · المسؤول: %s · %s"
            % (req.get("ticket_seq") or "?", asks_ar(req.get("asks")),
               req.get("owner_name") or req.get("owner_did") or "—", link)) + MARK


def watchdog_miss(req, link, eligible):
    tail = "" if eligible else " · (ما ينحسب: " + ("بدون مسؤول" if req.get("unowned") else "إداري/إجازة") + ")"
    return ("🔴 تأخير: RR #%s — طلب سام (%s) · المسؤول: %s%s · %s"
            % (req.get("ticket_seq") or "?", asks_ar(req.get("asks")),
               req.get("owner_name") or req.get("owner_did") or "—", tail, link)) + MARK


def lead_miss_dm(req, link):
    return ("🔴 تأخير على طلب سام — RR #%s (%s) · المسؤول: %s. تقدر تعطيه عذر خلال ٤٨ ساعة "
            "من زر «عذر» في غرفة المراقبة. %s"
            % (req.get("ticket_seq") or "?", asks_ar(req.get("asks")),
               req.get("owner_name") or "—", link))


# ------------------------------------------------------------------ the judge

def notice_dm(week):
    return ("تنبيه — تأخرت على طلب من سام هالأسبوع (%s). ما ينحسب إنذار هالمرة، "
            "بس التأخير الثاني بنفس الأسبوع ينحسب إنذار رسمي. 🙏" % week)


def warning_reason(reqs):
    parts = ["RR #%s (%s)" % (r.get("ticket_seq") or "?", asks_ar(r.get("asks"))) for r in reqs]
    return "تأخير مرتين على طلبات سام بنفس الأسبوع: " + "، ".join(parts)


def warning_dm(reason, pct, link):
    return ("⚠️ إنذار رسمي من نظام الالتزام — %s." % reason + NL +
            "نسبة عمولتك هالشهر صارت %s." % pct + NL +
            "لو عندك اعتراض: %s" % link)


def hr_line(employee, week, pct):
    return "⚠️ إنذار RR — %s · أسبوع %s · العمولة %s" % (employee, week, pct)


def dry_warning_detail(employee, week, pct):
    return ("would have issued an RR warning to %s for %s; commission would become %s"
            % (employee, week, pct))


# ------------------------------------------------------------------ digests

def sam_digest(rows, now, link):
    if not rows:
        return "Good afternoon Sam — no open requests right now. ✅"
    out = ["Good afternoon Sam — your open requests (%d):" % len(rows)]
    for r in rows[:15]:
        late = " ⚠️ overdue" if r.get("_late") else ""
        out.append("• RR #%s — %s · owner %s · %s old · %s%s"
                   % (r.get("ticket_seq") or "?", asks_en(r.get("asks")),
                      r.get("owner_name") or "—", engine.fmt_age(r.get("_age_min")),
                      STATE_EN.get(r.get("state"), r.get("state")), late))
    if link:
        out.append(link)
    return NL.join(out)


def watchdog_daily(day_label, people):
    if not people:
        return "📋 طلبات سام أمس (%s): ما فيه طلبات." % day_label
    out = ["📋 طلبات سام أمس (%s):" % day_label]
    for p in people:
        out.append("• %s — %d طلب · رد بوقته %s · سلّم بوقته %s · تأخير %d"
                   % (p["name"], p["owned"], _pct(p.get("resp_on_time")),
                      _pct(p.get("deliv_on_time")), p.get("misses", 0)))
    return NL.join(out)


def weekly_dm(name, k, week):
    if k.get("insufficient"):
        return ("📋 أرقامك على طلبات سام — أسبوع %s: %d طلب · %s (أقل من ٣ طلبات)."
                % (week, k.get("owned", 0), engine.INSUFFICIENT_AR))
    return NL.join([
        "📋 أرقامك على طلبات سام — أسبوع %s" % week,
        "• الطلبات: %d" % k.get("owned", 0),
        "• رد بوقته: %s (الهدف ٩٠٪)" % _pct(k.get("resp_on_time")),
        "• سلّم بوقته: %s (الهدف ٨٥٪)" % _pct(k.get("deliv_on_time")),
        "• إعادة شغل: %s (الهدف ١٠٪ أو أقل)" % _pct(k.get("rework_rate")),
        "• تأخيرات: %d · فويس بدل كتابة: %d" % (k.get("misses", 0), k.get("voice", 0)),
    ])


def _pct(v):
    return "—" if v is None else "%d٪" % int(round(v * 100))


def board(rows, now):
    """The «متابعة-طلبات-سام» board: ticket, ask, owner mention, age. No per-person stats."""
    if not rows:
        return "📋 **طلبات سام المفتوحة** · Sam's open requests" + NL + "ما فيه شي مفتوح ✅" + MARK
    out = ["📋 **طلبات سام المفتوحة** · Sam's open requests (%d)" % len(rows)]
    for r in rows[:40]:
        out.append("%s RR #%s — %s · %s · %s"
                   % (STATE_EMOJI.get(r.get("state"), ""), r.get("ticket_seq") or "?",
                      asks_ar(r.get("asks")), mention(r.get("owner_did")) or (r.get("owner_name") or "—"),
                      engine.fmt_age(r.get("_age_min"))))
    out.append("آخر تحديث %s" % engine.fmt_time(now))
    return NL.join(out)[:1990] + MARK


def cap_hit_line(cap):
    return ("⏸️ الترجمة التلقائية في غرف RR وقفت لين نص الليل — وصلت الحد اليومي (%d). "
            "تتبع طلبات سام شغال عادي." % cap) + MARK


# ------------------------------------------------------------------ slash replies

SWITCH_NAMES = {"translate": "الترجمة", "requests": "تتبع الطلبات", "ladder": "التذكيرات",
                "warn_live": "الإنذارات الفعلية", "force_off": "الإيقاف الكامل"}
WARN_ON_CONFIRM = "تشغيل"
WARN_ON_PROMPT = ("هذا يخلّي تأخيرات طلبات سام تنحسب إنذارات فعلية وتنقص العمولة. "
                  "اكتب «تشغيل» في خانة التأكيد عشان تشغّله.")
