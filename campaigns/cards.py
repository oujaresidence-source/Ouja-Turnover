# -*- coding: utf-8 -*-
"""
campaigns.cards — PURE. An alert row (db.alert) → a Discord card as plain data:

    {"embed": {title, description, color, fields[{name, value, inline}], footer{text}},
     "buttons": [(action, label, style)], "links": [(label, url)]}

bot.py turns it into a discord.Embed + a CampaignCardView; nothing here imports discord.
The same function paints a card when it is posted and every time a button changes it, so
the card on screen always says what happened, who did it and when.

Actions (bot.py maps each to a fixed custom_id «camp_<action>»):
    send      send the prepared reply (Airbnb thread or WhatsApp) — one press, no copying
    decline   the code word does not apply → send the polite «not this date» reply
    claim     «أنا عليه»: write the presser's name on the card (no message to anyone)
    called    owner: called, interested            (done)
    noanswer  owner: no answer → WhatsApp «حاولت أتصل عليك»   (waiting)
    notint    owner: not interested                (done, grey)
    done      «خلصت — رديت بنفسي»                   (done)
"""
import datetime

from . import config

GOLD, OK, MUT, WARN = 0xA57A2C, 0x2E6A49, 0x6B5F52, 0x8A4B2A
GREEN, GREY, RED, BLUE = "success", "secondary", "danger", "primary"

WEEKDAY_AR = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
MONTH_AR = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر",
            "أكتوبر", "نوفمبر", "ديسمبر"]

ACTION_AR = {
    "send": "انرسل الرد", "decline": "انرسل الاعتذار", "called": "اتصل — المالك مهتم",
    "noanswer": "ما رد — انرسلت له رسالة", "notint": "المالك مو مهتم", "done": "خلص",
}


# ---------------------------------------------------------------- small helpers
def day_ar(iso):
    """«الأحد 29 نوفمبر» from an ISO date; the input back when it is not a date."""
    try:
        d = datetime.date.fromisoformat(str(iso)[:10])
    except (TypeError, ValueError):
        return str(iso or "—")
    return "%s %d %s" % (WEEKDAY_AR[d.weekday()], d.day, MONTH_AR[d.month - 1])


def day_short(iso):
    try:
        d = datetime.date.fromisoformat(str(iso)[:10])
    except (TypeError, ValueError):
        return str(iso or "—")
    return "%d %s" % (d.day, MONTH_AR[d.month - 1])


def sar(v):
    try:
        return "{:,} ريال".format(int(v))
    except (TypeError, ValueError):
        return "—"


def first_name(name):
    parts = str(name or "").strip().split()
    return parts[0] if parts else ""


def clock(iso_utc):
    """«8:05 م» Riyadh from a naive-UTC ISO stamp (db.now_iso)."""
    try:
        t = datetime.datetime.fromisoformat(str(iso_utc)) + datetime.timedelta(hours=3)
    except (TypeError, ValueError):
        return ""
    h = t.hour % 12 or 12
    return "%d:%02d %s" % (h, t.minute, "ص" if t.hour < 12 else "م")


def _cut(text, n):
    text = str(text or "")
    return text if len(text) <= n else text[: n - 1] + "…"


def _quote(text, n=1000):
    return "\n".join("> " + ln if ln.strip() else ">" for ln in _cut(text, n).split("\n"))


def template_title(t):
    return config.TEMPLATE_TITLES.get(t or "", "") or "رسالة الحملة"


# ---------------------------------------------------------------- the guest replies
def codeword_reply(ctx):
    """What «أرسلت العرض — بلّغ الضيف» sends in the Airbnb thread, or "" when there is no
    offer to announce (no date, no price, not eligible)."""
    o = ctx.get("offer") or {}
    if not (o.get("eligible") and o.get("total")):
        return ""
    hi = "هلا %s 👋" % ctx["first"] if ctx.get("first") else "هلا فيك 👋"
    if ctx.get("booked"):
        return ("%s أرسلنا لك تعديل على حجزك يضيف ليلة %s بنص السعر (%s) 🎁\n"
                "وافق عليه من Airbnb ويثبت." % (hi, day_ar(o.get("night2")), sar(o.get("night2_price"))))
    return ("%s أرسلنا لك عرض خاص: ليلتين (%s و%s) بـ %s، والليلة الثانية بنص السعر 🎁\n"
            "اضغط «قبول» في Airbnb ويثبت حجزك." % (
                hi, day_short(o.get("offer_checkin")), day_short(o.get("night2")), sar(o.get("total"))))


def codeword_decline(ctx):
    """(label, text) for the second button: ask the date when we could not read it, else the
    polite «this date is not in the offer»."""
    o = ctx.get("offer") or {}
    hi = "هلا %s 👋" % ctx["first"] if ctx.get("first") else "هلا فيك 👋"
    if not o.get("night1"):
        return ("❔ اسأله عن التاريخ",
                "%s حياك! وش التاريخ اللي تبيه؟ العرض يكون على ليالي الأحد إلى الأربعاء." % hi)
    if o.get("eligible"):
        return ("", "")
    return ("ما ينطبق — أرسل اعتذار",
            "%s للأسف العرض ما ينطبق على هالتاريخ: يكون على ليالي الأحد إلى الأربعاء، والليلة "
            "الثانية لازم تكون فاضية.\nتبي نشوف لك تاريخ ثاني بين الأحد والأربعاء؟" % hi)


# ---------------------------------------------------------------- footer: what happened
def _status(a):
    """(color_override, footer_text) for the card's current state."""
    st = a.get("state") or "open"
    bits = []
    color = None
    if st in ("done", "dismissed"):
        color = OK if st == "done" else MUT
        bits.append("✅ %s — %s · %s" % (ACTION_AR.get(a.get("action") or "", "خلص"),
                                          a.get("actor") or "—", clock(a.get("acted_at"))))
    elif st == "waiting":
        color = WARN
        bits.append("⏳ %s — %s · %s" % (ACTION_AR.get(a.get("action") or "", ""),
                                          a.get("actor") or "—", clock(a.get("acted_at"))))
    elif a.get("claimed_by"):
        bits.append("🙋 %s ماسكه" % a["claimed_by"])
    if a.get("note") and st not in ("done", "dismissed"):
        bits.append("⚠️ " + a["note"])
    return color, "\n".join(bits)


def _open(a):
    return (a.get("state") or "open") in ("open", "busy")


# ---------------------------------------------------------------- the cards
def _codeword(a):
    c = a["ctx"]
    o = c.get("offer") or {}
    title = "🎯 %s يبي «%s»" % (c.get("guest") or "ضيف", c.get("title") or "عرض")
    desc = "%s · كتب «%s»" % ("حاجز أصلاً" if c.get("booked") else
                              ("استفسار في Airbnb · ما حجز للحين" if c.get("res_status") else "رسالة"),
                              c.get("phrase") or "")
    f = [{"name": "الشقة", "value": _cut(c.get("unit") or "—", 100), "inline": True}]
    if o.get("night1"):
        ok1 = o.get("night1_weekday") in ("الأحد", "الاثنين", "الثلاثاء", "الأربعاء")
        v1 = "%s %s" % (day_ar(o["night1"]), "✅" if ok1 else "❌")
        if c.get("date_source") == "text":
            v1 += "\n(من كلام الضيف — تأكد)"
        free = o.get("night2_free")
        v2 = "%s · %s" % (day_ar(o.get("night2")),
                          "فاضية ✅" if free else ("ما ندري ❔" if free is None else "محجوزة ❌"))
        f += [{"name": "الليلة الأولى", "value": v1, "inline": True},
              {"name": "الليلة الثانية", "value": v2, "inline": True}]
        if o.get("night2_weekend"):
            f.append({"name": "⚠️ انتبه", "value": "الليلة الثانية ويكند — شاور المشرف", "inline": False})
    else:
        f.append({"name": "التاريخ", "value": "❔ ما عرفناه — اسأل الضيف", "inline": True})
    if o.get("total"):
        n2 = sar(o.get("night2_price"))
        if o.get("floored"):
            n2 += "\n(رفعناها للحد الأدنى %s)" % sar(o.get("floor"))
        f += [{"name": "الليلة الأولى", "value": sar(o.get("night1_price")), "inline": True},
              {"name": "الثانية (نص)", "value": n2, "inline": True},
              {"name": "المجموع", "value": "**%s**" % sar(o["total"]), "inline": True}]
    if o:
        f.append({"name": "العرض", "value": ("✅ ينطبق" if o.get("eligible") else
                                              "❌ ما ينطبق: " + "، ".join(o.get("reasons") or ["—"])),
                  "inline": False})
    f.append({"name": "المسؤول", "value": "%s · خلال %s دقيقة%s" % (
        c.get("who") or "مناوب صندوق الرسائل", c.get("mins") or 15,
        (" (قبل %s)" % c["by"]) if c.get("by") else ""), "inline": False})
    reply = c.get("reply") or ""
    dlabel, dtext = c.get("decline_label") or "", c.get("decline") or ""
    if reply and _open(a):
        f.append({"name": "📝 الرد اللي ينرسل للضيف لما تضغط ②", "value": _quote(reply), "inline": False})
    elif dtext and _open(a):
        f.append({"name": "📝 الرد اللي ينرسل لما تضغط «%s»" % dlabel, "value": _quote(dtext),
                  "inline": False})
    color, status = _status(a)
    steps = ("① افتح المحادثة وأرسل Special Offer بالمجموع فوق (Airbnb ما يسمح نرسله من برا)\n"
             "② اضغط «أرسلت العرض — بلّغ الضيف»") if not c.get("booked") else \
            ("① زِد الليلة بتعديل الحجز (Alteration) من Hostaway بنفس السعر\n"
             "② اضغط «أرسلت التعديل — بلّغ الضيف»")
    footer = status or (steps if reply else "")
    buttons = []
    if _open(a):
        if reply:
            buttons.append(("send", "② أرسلت التعديل — بلّغ الضيف" if c.get("booked")
                            else "② أرسلت العرض — بلّغ الضيف", GREEN))
        if dtext:
            buttons.append(("decline", dlabel, RED if o.get("night1") else BLUE))
        buttons.append(("claim", "🙋 أنا عليه", GREY))
        buttons.append(("done", "✅ خلصت بنفسي", GREY))
    links = []
    for i, (url, label) in enumerate((c.get("links") or [])[:2]):
        links.append((("① " if i == 0 and reply else "") + _cut(label, 70), url))
    return {"title": title, "description": desc, "color": color or GOLD, "fields": f,
            "footer": footer}, buttons, links


def _who_fields(c):
    f = []
    if c.get("guest"):
        f.append({"name": "الاسم", "value": _cut(c["guest"], 60), "inline": True})
    f.append({"name": "الجوال", "value": ("ينتهي بـ ••%s" % c["last4"]) if c.get("last4")
              else "في هاتف ← المحادثات", "inline": True})
    return f


def _owner_call(a):
    c = a["ctx"]
    st = a.get("state") or "open"
    f = _who_fields(c)
    f.append({"name": "اتصل قبل", "value": "%s (خلال %s ساعات)" % (c.get("by") or "—", c.get("hours") or 2),
              "inline": True})
    if st in ("open", "busy", "waiting"):
        f.append({"name": "لو ما رد — الرسالة اللي تنرسل له", "value": _quote(config.OWNER_NOANSWER_TEXT),
                  "inline": False})
    color, status = _status(a)
    buttons = []
    if st in ("open", "busy"):
        buttons = [("called", "📞 اتصلت — مهتم", GREEN), ("noanswer", "ما رد — أرسل له رسالة", GREY),
                   ("notint", "مو مهتم", GREY), ("claim", "🙋 أنا عليه", GREY)]
    elif st == "waiting":
        buttons = [("called", "📞 كلمته — مهتم", GREEN), ("notint", "مو مهتم", GREY)]
    return {"title": "📞 مالك يبي نكلمه",
            "description": "ضغط «%s» على رسالة «%s»" % (c.get("label") or "", template_title(c.get("template"))),
            "color": color or GOLD, "fields": f, "footer": status or "الرقم في هاتف ← المحادثات"}, buttons, []


def _owner_later(a):
    c = a["ctx"]
    return {"title": "⏸️ مالك قال «مو الحين»",
            "description": "على رسالة «%s» — لا نتصل الحين، نرجع له بعد شهرين." % template_title(c.get("template")),
            "color": MUT, "fields": _who_fields(c), "footer": ""}, [], []


def _prepared(a, title, send_label):
    """«وريني الشقق» / «وش إيليت؟»: sent already, or the prepared reply + a send button."""
    c = a["ctx"]
    st = a.get("state") or "open"
    f = _who_fields(c)
    f.append({"name": "الحملة", "value": template_title(c.get("template")), "inline": True})
    if st == "done" and a.get("action") in ("send", "auto"):
        f.append({"name": "✅ انرسل له على الواتساب", "value": _quote(c.get("text") or "", 700), "inline": False})
    elif c.get("text") and _open(a):
        why = c.get("why") or ""
        f.append({"name": "📝 الرد الجاهز%s" % ((" — ما انرسل: " + why) if why else ""),
                  "value": _quote(c["text"], 900), "inline": False})
    color, status = _status(a)
    if st == "done" and a.get("action") == "auto":
        status = "✅ انرسل تلقائياً · %s" % clock(a.get("acted_at"))
        color = OK
    buttons = []
    if _open(a):
        if c.get("text"):
            buttons.append(("send", send_label, GREEN))
        buttons += [("claim", "🙋 أنا عليه", GREY), ("done", "✅ رديت بنفسي", GREY)]
    elif st == "done" and a.get("action") == "auto":
        buttons = [("claim", "🙋 أنا أكمل معه", GREY)] if not a.get("claimed_by") else []
        if a.get("claimed_by"):
            status += "\n🙋 %s يكمل معه" % a["claimed_by"]
    return {"title": title % (c.get("guest") or "ضيف"), "description": "ضغط «%s»" % (c.get("label") or ""),
            "color": color or GOLD, "fields": f, "footer": status}, buttons, []


def _packages(a):
    c = a["ctx"]
    f = _who_fields(c)
    color, status = _status(a)
    buttons = [("claim", "🙋 أنا عليه", GREY), ("done", "✅ أرسلت له الباقات", GREY)] if _open(a) else []
    return {"title": "🎉 %s يبي يشوف باقات اللحظات" % (c.get("guest") or "ضيف"),
            "description": "ضغط «%s» — أرسل له الباقات من محادثة هاتف." % (c.get("label") or ""),
            "color": color or GOLD, "fields": f, "footer": status}, buttons, []


def _opt_out(a):
    c = a["ctx"]
    return {"title": "🚫 طلب إيقاف العروض",
            "description": "انضاف لقائمة الإيقاف: ما توصله أي حملة ثانية من النظام. "
                           "شيله من قوائم الحملات في هاتف (جهات الاتصال).",
            "color": WARN, "fields": _who_fields(c), "footer": ""}, [], []


_RENDER = {"codeword": _codeword, "owner_call": _owner_call, "owner_later": _owner_later,
           "show_units": lambda a: _prepared(a, "🏠 %s يبي يشوف الشقق", "📲 أرسل له الشقق الحين"),
           "elite_info": lambda a: _prepared(a, "⭐ %s يسأل وش إيليت", "📲 أرسل له شرح إيليت"),
           "show_packages": _packages, "opt_out": _opt_out}


def render(a):
    """An alert row → {"embed", "buttons", "links"} (see the module doc)."""
    embed, buttons, links = _RENDER[a["kind"]](a)
    e = {"title": _cut(embed["title"], 250), "description": _cut(embed.get("description"), 1500),
         "color": embed.get("color") or GOLD,
         "fields": [{"name": _cut(x["name"], 250), "value": _cut(x["value"], 1024) or "—",
                     "inline": bool(x.get("inline"))} for x in embed.get("fields") or []][:25]}
    if embed.get("footer"):
        e["footer"] = {"text": _cut(embed["footer"], 2000)}
    return {"embed": e, "buttons": [(k, _cut(lbl, 80), s) for k, lbl, s in buttons][:5],
            "links": [(_cut(lbl, 80), u) for lbl, u in links if u][:2]}
