# -*- coding: utf-8 -*-
"""
campaigns.service — the three jobs. Every function is blocking and never raises; bot.py runs
them off the event loop.

    on_guest_message(item)   (1) a Hostaway guest message → a code-word alert in «عروض-خاصة»
    on_hatif(payload)        (2) a Hatif template button tap → alert / prepared reply / opt-out.
                             Returns True when the message was a campaign tap (or a typed
                             «ايقاف»), so hatif.service leaves it alone.
    weekly_tick(now)         (3) Sunday 09:00 Riyadh → one Discord report, latched in the db.
"""
import datetime
import json
import traceback

from . import cards, config, db, engine
from .host import HOST

OFFERS, OWNERS = "offers", "owners"


def _post(where, text, role_id="", card=None):
    """One Discord message. With a card, bot.py posts the embed + buttons (the text is the
    fallback when Discord refuses the embed); a host without card support gets the text."""
    fn = getattr(HOST, "post", None)
    if not fn:
        return
    try:
        if card is not None and _takes_card(fn):
            fn(where, str(text)[:1990], role_id or "", card=card)
        else:
            fn(where, str(text)[:1990], role_id or "")
    except Exception:
        traceback.print_exc()


def _takes_card(fn):
    try:
        import inspect
        return "card" in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False


def _card_alert(kind, ctx, state="open", action=None):
    """Store the alert, then paint its card. Returns the card dict (with alert_id) or None
    when the db is unavailable (the plain text still posts)."""
    try:
        aid = db.new_alert(kind, ctx, state)
        if action:
            db.end_alert_action(aid, state, "النظام", action)
        card = cards.render(db.alert(aid))
        card["alert_id"] = aid
        return card
    except Exception:
        traceback.print_exc()
        return None


def _log(text):
    fn = getattr(HOST, "log_event", None)
    if fn:
        try:
            fn("campaign", text)
        except Exception:
            pass


def _now():
    fn = getattr(HOST, "now", None)
    return fn() if fn else datetime.datetime.now()


def _utc_iso(dt):
    """db rows are stored in naive UTC; convert a (Riyadh) aware datetime for a range query."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return dt.replace(microsecond=0).isoformat()


def _dm(iso):
    try:
        d = datetime.date.fromisoformat(str(iso)[:10])
        return "%s %d/%d" % (engine.WEEKDAY_AR[d.weekday()], d.day, d.month)
    except (TypeError, ValueError):
        return str(iso or "—")


def _sar(v):
    try:
        return "{:,} ر.س".format(int(v))
    except (TypeError, ValueError):
        return "—"


# =====================================================================================
# (1) the code-word watcher
# =====================================================================================
_CONFIRMED = ("new", "modified")


def on_guest_message(it):
    try:
        return _on_guest_message(it if isinstance(it, dict) else {})
    except Exception as e:
        traceback.print_exc()
        return {"outcome": "error", "error": type(e).__name__}


def _request_dates(it):
    ci, co = it.get("checkin"), it.get("checkout")
    if ci:
        return str(ci)[:10], (str(co)[:10] if co else None), "reservation"
    fn = getattr(HOST, "dates_from_text", None)
    if fn:
        try:
            s, e, conf = fn(it.get("history") or it.get("guest_text") or "")
            if s and conf != "low":
                return s, e, "text"
        except Exception:
            traceback.print_exc()
    return None, None, None


def _offer_for(it, hit, arrival, departure):
    lid = it.get("listing_id")
    days = []
    floor = 0
    if arrival and lid is not None:
        a = datetime.date.fromisoformat(arrival)
        try:
            days = HOST.require("calendar")(lid, a, a + datetime.timedelta(days=1)) or []
        except Exception as e:
            print("[campaigns] calendar read failed:", type(e).__name__)
            days = []
        try:
            floor = int(HOST.require("floor")(lid) or 0)
        except Exception as e:
            print("[campaigns] floor read failed:", type(e).__name__)
            floor = 0
    return engine.second_night_offer(arrival, departure, days, floor,
                                     hit.get("discount_pct", 50), hit.get("nights") or (6, 0, 1, 2))


def _on_guest_message(it):
    if not config.watch_enabled():
        return {"outcome": "off"}
    hit = engine.match_codeword(it.get("guest_text"))
    if not hit:
        return {"outcome": "none"}
    mid = it.get("message_id")
    if not mid:
        return {"outcome": "ignored"}
    arrival, departure, src = _request_dates(it)
    row = {"code": hit["code"], "conversation_id": it.get("conversation_id"),
           "reservation_id": it.get("reservation_id"), "listing_id": it.get("listing_id"),
           "unit": it.get("unit"), "guest": it.get("guest"),
           "guest_key": engine.name_key(it.get("guest")), "res_status": it.get("res_status"),
           "check_in": arrival, "check_out": departure,
           "body": engine.normalize(it.get("guest_text"))[:200], "created_at": _utc_iso(_now())}
    if not db.claim_hit(mid, row):
        return {"outcome": "duplicate"}
    try:
        offer = (_offer_for(it, hit, arrival, departure) if hit.get("kind") == "second_night"
                 else None)
        who = None
        fn = getattr(HOST, "responsible", None)
        if fn:
            try:
                who = fn(it.get("listing_id"), it.get("unit"))
            except Exception:
                who = None
        links = []
        fn = getattr(HOST, "links", None)
        if fn and it.get("reservation_id"):
            try:
                links = fn(it.get("reservation_id"), it.get("comm_type")) or []
            except Exception:
                links = []
        now = _now()
        text = alert_text(it, hit, offer, who, links, now, src)
        card = _card_alert("codeword", _codeword_ctx(it, hit, offer, who, links, now, src))
        _post(OFFERS, text, config.offer_role_id(), card=card)
        db.finish_hit(mid, offer or {})
        _log("كلمة سر «%s» · %s · %s" % (hit["phrase"], it.get("guest") or "ضيف", it.get("unit") or ""))
        return {"outcome": "alerted", "offer": offer, "text": text}
    except Exception:
        db.release_hit(mid)              # the next poll tries again
        raise


def alert_text(it, hit, offer, who, links, now, date_source=None):
    st = str(it.get("res_status") or "").lower()
    booked = st in _CONFIRMED
    lines = ["🎯 **كلمة سر «%s»** — %s" % (hit["phrase"], hit.get("title") or hit["code"]),
             "الضيف: **%s** · الشقة: **%s**" % (it.get("guest") or "ضيف", it.get("unit") or "—"),
             "المحادثة: %s" % ("حجز مؤكد" if booked else ("استفسار" if st else "رسالة"))]
    if offer is not None:
        if offer.get("night1"):
            req = "التاريخ المطلوب: %s" % _dm(offer["night1"])
            if offer.get("nights_requested"):
                req += " (%s)" % ("ليلة وحدة" if offer["nights_requested"] == 1
                                  else "%d ليالي" % offer["nights_requested"])
            if date_source == "text":
                req += " — من كلام الضيف، تأكد منه"
            lines.append(req)
            ok1 = offer["night1_weekday"] in ("الأحد", "الاثنين", "الثلاثاء", "الأربعاء")
            lines.append("الليلة الأولى بين الأحد والأربعاء؟ %s %s" % ("✅" if ok1 else "❌",
                                                                     offer["night1_weekday"]))
            free = offer.get("night2_free")
            lines.append("الليلة الثانية فاضية؟ %s %s" % (
                "✅" if free else ("❔" if free is None else "❌"), _dm(offer["night2"])))
            if offer.get("night2_weekend"):
                lines.append("⚠️ الليلة الثانية ويكند — شاور المشرف قبل ترسل العرض")
        else:
            lines.append("التاريخ المطلوب: ❔ ما عرفناه — اسأل الضيف عن التاريخ")
        if offer.get("total"):
            lines.append("")
            lines.append("💰 **العرض الجاهز (Special Offer):**")
            lines.append("• الليلة الأولى: %s (سعر التقويم)" % _sar(offer["night1_price"]))
            n2 = "• الليلة الثانية: %s (نص %s)" % (_sar(offer["night2_price"]), _sar(offer["night2_full"]))
            if offer.get("floored"):
                n2 += " — رفعناها للحد الأدنى %s" % _sar(offer["floor"])
            lines.append(n2)
            lines.append("• **المجموع: %s** — دخول %s · خروج %s" % (
                _sar(offer["total"]), _dm(offer["offer_checkin"]), _dm(offer["offer_checkout"])))
        if offer.get("eligible"):
            lines.append("✅ العرض ينطبق")
        else:
            lines.append("❌ العرض ما ينطبق: " + "، ".join(offer.get("reasons") or ["—"]))
            lines.append("رد على الضيف بلطف واقترح تاريخ ثاني بين الأحد والأربعاء، أو شاور المشرف.")
    lines.append("")
    mins = config.act_within_min()
    by = (now + datetime.timedelta(minutes=mins)).strftime("%I:%M %p") if hasattr(now, "strftime") else ""
    who_txt = ("المسؤول عن الشقة اليوم: **%s**" % who) if who else "المسؤول: مناوب صندوق الرسائل"
    lines.append("⏱️ %s — أرسل العرض خلال %d دقيقة%s" % (who_txt, mins, (" (قبل %s)" % by) if by else ""))
    if booked:
        lines.append("الضيف حاجز أصلاً: زِد الليلة الثانية بتعديل الحجز (Alteration) بنفس السعر.")
    else:
        lines.append("الطريقة: صندوق Hostaway ← المحادثة ← Special Offer بالمجموع فوق.")
    for url, label in (links or [])[:3]:
        lines.append("%s: %s" % (label, url))
    lines.append("رقم المحادثة في Hostaway: %s" % (it.get("conversation_id") or "—"))
    return "\n".join(lines)


def _codeword_ctx(it, hit, offer, who, links, now, date_source=None):
    """What the code-word card shows and what its buttons send (Airbnb thread, via Hostaway)."""
    st = str(it.get("res_status") or "").lower()
    mins = config.act_within_min()
    by = ""
    if hasattr(now, "strftime"):
        t = now + datetime.timedelta(minutes=mins)
        by = "%d:%02d %s" % (t.hour % 12 or 12, t.minute, "ص" if t.hour < 12 else "م")
    ctx = {"guest": it.get("guest") or "ضيف", "first": cards.first_name(it.get("guest")),
           "unit": it.get("unit"), "phrase": hit.get("phrase"), "title": hit.get("title") or hit.get("code"),
           "code": hit.get("code"), "booked": st in _CONFIRMED, "res_status": st,
           "offer": offer or {}, "date_source": date_source, "who": who, "mins": mins, "by": by,
           "links": [[u, l] for u, l in (links or [])[:3]],
           "conversation_id": it.get("conversation_id"), "comm_type": it.get("comm_type")}
    ctx["reply"] = cards.codeword_reply(ctx) if offer is not None else ""
    if offer is not None:
        ctx["decline_label"], ctx["decline"] = cards.codeword_decline(ctx)
    return ctx


# =====================================================================================
# (2) Hatif button taps
# =====================================================================================
def _first_text(v):
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, dict):
        for k in ("text", "title", "label", "body", "payload"):
            if isinstance(v.get(k), str) and v[k].strip():
                return v[k].strip()
        for k in ("buttonReply", "button_reply", "button"):
            if isinstance(v.get(k), dict):
                return _first_text(v[k])
    return ""


def _hint(v):
    """A template name Hatif may put on the tap (id / payload / templateName)."""
    if isinstance(v, dict):
        for k in ("templateName", "template_name", "id", "payload"):
            x = v.get(k)
            if isinstance(x, str):
                # longest name first: «ouja_midweek_half_img» must not read as «ouja_midweek_half»
                for t in sorted(config.TEMPLATES, key=len, reverse=True):
                    if t in x:
                        return t
        t = v.get("template")
        if isinstance(t, dict):
            return _hint({"templateName": t.get("name")})
        if isinstance(t, str):
            return _hint({"templateName": t})
    return None


def extract_tap(p):
    """(label, hinted_template, source, raw_keys) for a button tap, else (None, ...).

    Shapes accepted, because Hatif's docs do not show a template quick-reply tap:
      * `interactiveReply` (what Hatif documents for button/list taps) — dict or string
      * Meta's raw `button` / `buttonReply` / `quickReply` objects
      * messageType Button / Interactive / QuickReply with the label in `body`
      * a plain inbound Text whose WHOLE body is exactly one of our campaign labels
    """
    raw_keys = sorted(k for k in p.keys() if isinstance(k, str))
    hinted = _hint(p) or _hint(p.get("context") or {})
    for k in ("interactiveReply", "button", "buttonReply", "quickReply", "interactive"):
        v = p.get(k)
        if v:
            label = _first_text(v)
            if label:
                return label, (_hint(v) or hinted), k, raw_keys
    mt = str(p.get("messageType") or "").lower()
    body = str(p.get("body") or "").strip()
    if body and mt in ("button", "interactive", "quickreply", "quick_reply"):
        return body, hinted, "messageType", raw_keys
    if body and engine.button_kind(body):
        return body, hinted, "text", raw_keys
    return None, None, None, raw_keys


def on_hatif(p):
    try:
        return bool(_on_hatif(p if isinstance(p, dict) else {}))
    except Exception:
        traceback.print_exc()
        return False


def _hatif_api():
    """(client, hatif_config) when the Hatif API can be called, else (None, hatif_config)."""
    try:
        from hatif import client as hc, config as hcfg
    except Exception:
        return None, None
    return (hc if hcfg.configured() else None), hcfg


_seen_channel = {"id": None}


def remember_channel(p):
    """The WhatsApp channel id every inbound Hatif event carries — kept so the per-person sender
    knows where to send without HATIF_CHANNEL_ID (that env var also FILTERS the reader: a wrong
    value there would silence it, so it is not needed for sending)."""
    ch = str((p or {}).get("channelId") or "").strip()
    if not ch or p.get("direction") != "Inbound" or _seen_channel["id"] == ch:
        return
    try:
        db.set_setting("hatif_channel", ch)
        _seen_channel["id"] = ch
    except Exception:
        traceback.print_exc()


def known_channel():
    return db.get_setting("hatif_channel", "") or ""


def _on_hatif(p):
    remember_channel(p)
    if not config.buttons_enabled() or p.get("direction") != "Inbound":
        return False
    label, hinted, source, raw_keys = extract_tap(p)
    kind = engine.button_kind(label) if label else None
    if not kind and engine.is_stop_message(p.get("body")):
        label, kind, source = str(p.get("body") or "").strip(), "opt_out", "typed"
    if not kind:
        if label and source != "text":
            # an interactive tap that is not ours (the Hatif menu flow): leave it alone, but
            # print its SHAPE (keys only, no values) so a new Hatif format shows in the logs
            print("[campaigns] non-campaign tap via %s, keys=%s" % (source, raw_keys))
        return False
    eid = p.get("conversationEventId") or p.get("messageId")
    cid = p.get("conversationId")
    if not eid:
        return False
    template = engine.resolve_template(label, hinted) if kind != "opt_out" else hinted
    row = {"conversation_id": cid, "contact_id": p.get("contactId"), "template": template,
           "label": label, "kind": kind, "created_at": _utc_iso(_now()),
           "raw_keys": json.dumps({"source": source, "keys": raw_keys})}
    if not db.claim_tap(eid, row):
        return True                                     # a Hatif retry — already handled

    # who tapped: only through the Hatif API (the webhook carries no number)
    hc, hcfg = _hatif_api()
    conv, phone = {}, ""
    if hc and cid:
        try:
            conv = hc.get_conversation(cid) or {}
            phone = engine.normalize_phone(conv.get("phoneNumber"))
        except Exception as e:
            print("[campaigns] conversation read failed:", type(e).__name__)
    salt = db.salt()
    pkey = engine.phone_key(phone, salt) if phone else ""
    l4 = engine.last4(phone)
    guest = str(conv.get("contactName") or conv.get("name") or p.get("contactName") or "").strip()[:60]
    db.update_tap(eid, phone_key=pkey, last4=l4, guest=guest or None,
                  guest_key=engine.name_key(guest) or None)
    ctx = {"eid": eid, "cid": cid, "contact_id": p.get("contactId"), "template": template,
           "label": label, "kind": kind, "phone": phone, "pkey": pkey, "last4": l4, "guest": guest,
           "conv": conv, "hc": hc, "hcfg": hcfg, "source": source,
           "channel": p.get("channelId") or conv.get("channelId")}
    outcome = _ROUTES[kind](ctx)
    db.update_tap(eid, outcome=outcome)
    _log("زر حملة «%s» · %s" % (label, template or "قالب غير محدد"))
    return True


def _who(ctx):
    bits = []
    if ctx.get("guest"):
        bits.append("**%s**" % ctx["guest"])
    if ctx.get("last4"):
        bits.append("رقم ينتهي بـ ••%s" % ctx["last4"])
    if not bits:
        bits.append("جهة اتصال بهاتف (بدون مفاتيح API ما نعرف الرقم)")
    return " · ".join(bits)


def _tpl(ctx):
    return ctx.get("template") or "قالب غير محدد"


def _opt_keys(ctx):
    keys = []
    if ctx.get("pkey"):
        keys.append(ctx["pkey"])
    if ctx.get("contact_id"):
        keys.append("contact:%s" % ctx["contact_id"])
    return keys


def _card_base(ctx):
    """The tap facts a card needs — never the phone number (last 4 + the Hatif ids only)."""
    return {k: ctx.get(k) for k in ("guest", "last4", "template", "label", "cid", "contact_id",
                                     "eid", "kind", "channel")}


def _route_owner_call(ctx):
    now = _now()
    t = now + datetime.timedelta(hours=config.owner_call_within_h())
    by = t.strftime("%I:%M %p")
    card = _card_alert("owner_call", dict(_card_base(ctx), hours=config.owner_call_within_h(),
                                          by="%d:%02d %s" % (t.hour % 12 or 12, t.minute,
                                                             "ص" if t.hour < 12 else "م")))
    _post(OWNERS, "📞 **مالك يبي نكلمه** — ضغط «%s» (%s)\n%s\n⏱️ اتصل خلال %d ساعات (قبل %s). "
                  "الرقم في هاتف ← المحادثات%s."
          % (ctx["label"], _tpl(ctx), _who(ctx), config.owner_call_within_h(), by,
             (" (المحادثة %s)" % ctx["cid"]) if ctx.get("cid") else ""), config.owners_role_id(),
          card=card)
    return "alerted"


def _route_owner_later(ctx):
    _post(OWNERS, "⏸️ مالك ضغط «%s» — لا نتصل الحين. %s" % (ctx["label"], _who(ctx)),
          card=_card_alert("owner_later", _card_base(ctx)))
    return "logged"


def _route_packages(ctx):
    _post(OFFERS, "🎉 **يبي يشوف باقات اللحظات** — ضغط «%s» (%s)\n%s\nأرسل له الباقات من محادثة هاتف."
          % (ctx["label"], _tpl(ctx), _who(ctx)), card=_card_alert("show_packages", _card_base(ctx)))
    return "alerted"


def _next_midweek_night(now):
    """Tonight when it is Sun–Wed before 22:00, else the coming Sunday."""
    d = now.date() if isinstance(now, datetime.datetime) else now
    if d.weekday() in (6, 0, 1, 2) and getattr(now, "hour", 0) < 22:
        return d
    d += datetime.timedelta(days=1)
    while d.weekday() != 6:
        d += datetime.timedelta(days=1)
    return d


def _units_reply(ctx):
    """The availability list for the next Sun–Wed night, from the guest site's own search."""
    from hatif import engine as he
    night = _next_midweek_night(_now())
    req = {"check_in": night.isoformat(), "check_out": (night + datetime.timedelta(days=1)).isoformat(),
           "nights": 1, "assumed_nights": False}
    out = HOST.require("search")(req["check_in"], req["check_out"], None, None, None)
    site = "oujares.com"
    fn = getattr(HOST, "site_host", None)
    if fn:
        try:
            site = fn() or site
        except Exception:
            pass
    text = he.build_reply(req, out, site, ctx["hcfg"].max_units() if ctx.get("hcfg") else 6)
    if ctx.get("template") in config.MIDWEEK_TEMPLATES:
        text += ("\n\nتبي الليلة الثانية بنص السعر؟ راسلنا من محادثة Airbnb للشقة بكلمة «عرض نص» "
                 "قبل ما تحجز، ونرسل لك العرض.")
    return text


def _send_or_hold(ctx, text):
    """('sent' | 'held', why). Live only when both dry-runs are off, the API works, the number
    is allowed, the person did not opt out, and no staff member holds the conversation."""
    hc, hcfg = ctx.get("hc"), ctx.get("hcfg")
    if config.buttons_dryrun():
        return "held", "تجربة (CAMPAIGN_BUTTONS_DRYRUN=1)"
    if hcfg is None or not hc:
        return "held", "مفاتيح Hatif API مو مركبة"
    if hcfg.dryrun():
        return "held", "تجربة (HATIF_DRYRUN=1)"
    if not ctx.get("phone"):
        return "held", "ما عرفنا رقم الضيف"
    allow = hcfg.test_numbers()
    if allow and ctx["phone"] not in allow:
        return "held", "الرقم مو من أرقام التجربة"
    if db.is_opted_out(_opt_keys(ctx), ctx.get("contact_id")):
        return "held", "الشخص طالب إيقاف العروض"
    assignee = (ctx.get("conv") or {}).get("assigneeId")
    if assignee and assignee != hcfg.bot_user_id():
        return "held", "المحادثة مسندة لموظف في هاتف"
    channel = ctx.get("channel") or hcfg.channel_id()
    try:
        hc.send_text(channel, ctx["phone"], text)
    except Exception as e:
        return "held", "تعذر الإرسال (%s)" % type(e).__name__
    return "sent", ""


def _route_show_units(ctx):
    try:
        text = _units_reply(ctx)
    except Exception as e:
        traceback.print_exc()
        text, state, why = None, "held", "تعذر البحث عن الشقق (%s)" % type(e).__name__
    else:
        state, why = _send_or_hold(ctx, text)
    head = "🏠 **يبي يشوف الشقق** — ضغط «%s» (%s)\n%s" % (ctx["label"], _tpl(ctx), _who(ctx))
    if text and state == "sent":
        body = "✅ انرسلت له قائمة المتاح على الواتساب:\n" + text
    elif text:
        body = "📝 الرد الجاهز (ما انرسل — %s). انسخه وأرسله من هاتف:\n%s" % (why, text)
    else:
        body = "⚠️ %s — رد عليه بنفسك من هاتف." % why
    _post(OFFERS, head + "\n" + body, card=_prepared_card("show_units", ctx, text, state, why))
    return "sent" if state == "sent" else "prepared"


def _prepared_card(kind, ctx, text, state, why):
    c = dict(_card_base(ctx), text=text or "", why=("" if state == "sent" else why))
    if state == "sent":
        return _card_alert(kind, c, state="done", action="auto")
    return _card_alert(kind, c)


def _route_elite(ctx):
    text = config.elite_text()
    state, why = _send_or_hold(ctx, text)
    head = "⭐ **يسأل وش إيليت** — ضغط «%s» (%s)\n%s" % (ctx["label"], _tpl(ctx), _who(ctx))
    if state == "sent":
        body = "✅ انرسل له شرح إيليت."
    else:
        body = "📝 الرد الجاهز (ما انرسل — %s):\n%s" % (why, text)
    _post(OFFERS, head + "\n" + body, card=_prepared_card("elite_info", ctx, text, state, why))
    return "sent" if state == "sent" else "prepared"


def _route_opt_out(ctx):
    """ONE row per person: keyed by the phone key, else the Hatif contact, else the chat."""
    if db.is_opted_out(_opt_keys(ctx), ctx.get("contact_id")):
        return "already_out"
    key = (ctx.get("pkey") or ("contact:%s" % ctx["contact_id"] if ctx.get("contact_id") else "")
           or ("conv:%s" % ctx["cid"] if ctx.get("cid") else ""))
    new = db.add_optout(key, ctx.get("contact_id"), ctx.get("cid"), ctx.get("last4"),
                        ctx.get("source") or "button", ctx.get("template"), _utc_iso(_now()))
    if new:
        _post(OFFERS, "🚫 **إيقاف العروض** — %s\nانضاف لقائمة الإيقاف. شيله من قوائم الحملات في هاتف "
                      "(جهات الاتصال) عشان ما توصله حملة ثانية." % _who(ctx),
              card=_card_alert("opt_out", _card_base(ctx)))
    return "opted_out" if new else "already_out"


_ROUTES = {"owner_call": _route_owner_call, "owner_later": _route_owner_later,
           "show_units": _route_show_units, "elite_info": _route_elite,
           "show_packages": _route_packages, "opt_out": _route_opt_out}


# =====================================================================================
# (4) the buttons on a Discord card — one press does the job, nobody copies or types
# =====================================================================================
_PRESS_FROM = {"send": ("open", "waiting"), "decline": ("open",), "called": ("open", "waiting"),
               "noanswer": ("open",), "notint": ("open", "waiting"), "done": ("open", "waiting")}

_HOSTAWAY_REFUSED = {
    "blocked_kill_switch": "الإرسال للضيوف موقوف (مفتاح الطوارئ ASSISTANT_SEND_KILL)",
    "firewall_blocked": "الجدار الناري منع الرسالة — راجعها وأرسلها بيدك",
}


def press(message_id, action, actor):
    """A button on a card. Blocking, never raises → {"ok", "msg", "card"}: msg goes to the
    presser only, card (when not None) repaints the message for everyone."""
    try:
        return _press(message_id, str(action or ""), str(actor or "—")[:60])
    except Exception as e:
        traceback.print_exc()
        return {"ok": False, "msg": "صار خطأ (%s) — جرّب مرة ثانية" % type(e).__name__, "card": None}


def paint(alert_id):
    c = cards.render(db.alert(alert_id))
    c["alert_id"] = alert_id
    return c


def _press(message_id, action, actor):
    a = db.alert_by_message(message_id)
    if not a:
        return {"ok": False, "msg": "ما لقيت هالتنبيه — يمكن قديم من قبل التحديث.", "card": None}
    aid = a["id"]
    if action == "claim":
        if a.get("claimed_by") and a["claimed_by"] != actor:
            return {"ok": False, "msg": "%s ماسكه من قبل." % a["claimed_by"], "card": None}
        db.claim_alert(aid, actor)
        return {"ok": True, "msg": "تمام، انكتب اسمك عليه ✓", "card": paint(aid)}
    allowed = _PRESS_FROM.get(action)
    if not allowed:
        return {"ok": False, "msg": "زر غير معروف.", "card": None}
    prev = db.begin_alert_action(aid, allowed)
    if prev is None:
        return {"ok": False, "msg": "هالتنبيه خلص، أو أحد ثاني يشتغل عليه الحين.", "card": paint(aid)}
    try:
        state, done_as, note, msg = _act(a, action, prev)
    except Exception:
        db.end_alert_action(aid, prev)
        raise
    if done_as is None:                      # held: back where it was, with the reason on the card
        db.end_alert_action(aid, prev, note=note)
    else:
        db.end_alert_action(aid, state, actor, done_as, note)
    _log("زر كرت «%s» · %s · %s" % (action, a["kind"], "تم" if done_as else "ما تم"))
    return {"ok": done_as is not None, "msg": msg, "card": paint(aid)}


def _act(a, action, prev):
    """(new_state, recorded_action | None when nothing happened, note, message to the presser)."""
    c, kind = a["ctx"], a["kind"]
    if action == "done":
        return "done", "done", None, "تمام ✓"
    if action == "called":
        return "done", "called", None, "تمام ✓ — سجّلنا إنه مهتم"
    if action == "notint":
        return "dismissed", "notint", None, "تمام ✓"
    if action == "noanswer":
        ok, why = _hatif_send(c, config.OWNER_NOANSWER_TEXT)
        if ok:
            return "waiting", "noanswer", None, "انرسلت له الرسالة على الواتساب ✓"
        return prev, None, why, "ما انرسلت: %s. أرسلها من هاتف بنفسك." % why
    if kind == "codeword" and action in ("send", "decline"):
        text = c.get("reply") if action == "send" else c.get("decline")
        if not text:
            return prev, None, None, "ما فيه رد جاهز لهالتنبيه."
        ok, why = _airbnb_send(c, text)
        if ok:
            return "done", action, None, "انرسل للضيف في محادثة Airbnb ✓"
        return prev, None, why, "ما انرسل: %s." % why
    if kind in ("show_units", "elite_info") and action == "send":
        text = c.get("text") or ""
        if kind == "show_units":
            try:                                   # fresh availability at press time
                hc, hcfg = _hatif_api()
                text = _units_reply({"template": c.get("template"), "hcfg": hcfg}) or text
            except Exception as e:
                print("[campaigns] units refresh failed:", type(e).__name__)
        if not text:
            return prev, None, None, "ما فيه رد جاهز."
        ok, why = _hatif_send(c, text)
        if ok:
            db.set_alert_ctx(a["id"], dict(c, text=text, why=""))
            return "done", "send", None, "انرسل له على الواتساب ✓"
        return prev, None, why, "ما انرسل: %s." % why
    return prev, None, None, "هالزر ما يخص هالتنبيه."


def _hatif_send(c, text):
    """(sent, why) — the same gates as a tap: both dry-runs, the keys, the test-number list,
    the opt-out list, a chat held by a staff member. The number is read from Hatif now."""
    hc, hcfg = _hatif_api()
    conv, phone = {}, ""
    if hc and c.get("cid"):
        try:
            conv = hc.get_conversation(c["cid"]) or {}
            phone = engine.normalize_phone(conv.get("phoneNumber"))
        except Exception as e:
            return False, "تعذر قراءة المحادثة من هاتف (%s)" % type(e).__name__
    ctx = {"hc": hc, "hcfg": hcfg, "phone": phone, "contact_id": c.get("contact_id"), "conv": conv,
           "pkey": engine.phone_key(phone, db.salt()) if phone else "",
           "channel": c.get("channel") or conv.get("channelId")}
    state, why = _send_or_hold(ctx, text)
    return state == "sent", why


def _airbnb_send(c, text):
    """(sent, why) — into the guest's Airbnb thread through Hostaway, with Musaed's own gates
    (kill switch, outbound firewall, duplicate guard) inside HOST.send_guest."""
    if config.buttons_dryrun():
        return False, "تجربة (CAMPAIGN_BUTTONS_DRYRUN=1) — انسخ الرد وأرسله من Hostaway"
    fn = getattr(HOST, "send_guest", None)
    if not fn:
        return False, "الإرسال من ديسكورد مو مركّب"
    if not c.get("conversation_id"):
        return False, "ما عندنا رقم المحادثة"
    try:
        r = fn(c["conversation_id"], text, c.get("comm_type") or "")
    except Exception as e:
        return False, "Hostaway رفض (%s)" % type(e).__name__
    if isinstance(r, str) and r in _HOSTAWAY_REFUSED:
        return False, _HOSTAWAY_REFUSED[r]
    return True, ""                         # sent, or the same text already went (duplicate guard)


def is_suppressed(phone=None, contact_id=None):
    """For any future sender: True when this number / Hatif contact asked to stop."""
    keys = []
    if phone:
        keys.append(engine.phone_key(phone, db.salt()))
    if contact_id:
        keys.append("contact:%s" % contact_id)
    return db.is_opted_out(keys, contact_id)


# =====================================================================================
# (3) the weekly report
# =====================================================================================
def weekly_tick(now=None):
    try:
        return _weekly_tick(now or _now())
    except Exception as e:
        traceback.print_exc()
        return {"outcome": "error", "error": type(e).__name__}


def _weekly_tick(now):
    if not config.report_enabled():
        return {"outcome": "off"}
    last = db.get_setting("report_date", "")
    if not engine.should_fire(now, last, config.report_day(), config.report_hour()):
        return {"outcome": "not_due"}
    if not db.claim_setting("report_date", last, now.date().isoformat()):
        return {"outcome": "claimed_elsewhere"}
    stats = build_stats(now)
    text = engine.report_text(stats)
    _post(OFFERS, text)
    return {"outcome": "posted", "stats": stats, "text": text}


def _parse_dt(v):
    s = str(v or "").strip().replace("T", " ")
    for fmt, n in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d %H:%M", 16), ("%Y-%m-%d", 10)):
        try:
            return datetime.datetime.strptime(s[:n], fmt)
        except ValueError:
            continue
    return None


def _bookings(start, end):
    """Confirmed reservations near [start, end) (naive UTC), indexed for matching. Kept whatever
    their creation time: an inquiry that turns into a booking keeps its id, and Hostaway's
    reservationDate may be the inquiry's own date."""
    fn = getattr(HOST, "reservations", None)
    rows = []
    if fn:
        try:
            rows = fn(start.date(), end.date()) or []
        except Exception:
            traceback.print_exc()
            rows = []
    salt = db.salt()
    out = []
    for r in rows:
        if str(r.get("status") or "").lower() not in _CONFIRMED:
            continue
        name = r.get("guestName") or " ".join(
            x for x in (r.get("guestFirstName"), r.get("guestLastName")) if x)
        out.append({"id": str(r.get("id") or ""),
                    "made": _parse_dt(r.get("reservationDate") or r.get("insertedOn")),
                    "name": engine.name_key(name),
                    "pkey": engine.phone_key(r.get("phone") or r.get("guestPhone"), salt)})
    return out


def _booked(made_at, name_key, pkey, res_id, bookings, days):
    """Same reservation id now confirmed, or a confirmed booking CREATED within `days` after
    the hit / tap with the same phone or the same guest name."""
    t0 = _parse_dt(made_at)
    if t0 is None:
        return False
    t1 = t0 + datetime.timedelta(days=days)
    for b in bookings:
        if res_id and b["id"] == str(res_id):
            return True
        if b["made"] is None or not (t0 <= b["made"] <= t1):
            continue
        if pkey and b["pkey"] and b["pkey"] == pkey:
            return True
        if name_key and b["name"] and b["name"] == name_key:
            return True
    return False


def build_stats(now):
    s_local, e_local = engine.week_window(now)
    s, e = _utc_iso(s_local), _utc_iso(e_local)
    days = config.match_days()
    hits = db.hits_between(s, e)
    taps = db.taps_between(s, e)
    s_dt = datetime.datetime.fromisoformat(s)
    e_dt = datetime.datetime.fromisoformat(e)
    bookings = _bookings(s_dt, e_dt) if (hits or taps) else []
    by_code = {}
    for h in hits:
        spec = config.CODEWORDS.get(h["code"]) or {}
        b = by_code.setdefault(h["code"], {"title": spec.get("title") or h["code"], "n": 0, "booked": 0})
        b["n"] += 1
        # an already-confirmed booking that typed the word only counts when a NEW one follows
        res_id = (None if str(h.get("res_status") or "").lower() in _CONFIRMED
                  else h.get("reservation_id"))
        if _booked(h["created_at"], h.get("guest_key"), None, res_id, bookings, days):
            b["booked"] += 1
    by_tpl, booked_taps, counted = {}, 0, 0
    for t in taps:
        if t.get("kind") == "opt_out":
            continue
        k = t.get("template") or "?"
        by_tpl.setdefault(k, {})
        by_tpl[k][t["kind"]] = by_tpl[k].get(t["kind"], 0) + 1
        if t.get("kind") in ("owner_call", "owner_later"):
            continue                                     # owners don't book a night
        counted += 1
        if _booked(t["created_at"], t.get("guest_key"), t.get("phone_key"), None, bookings, days):
            booked_taps += 1
    return {"start": s_local, "end": e_local, "hits": by_code, "taps": by_tpl,
            "taps_booked": booked_taps, "taps_total": counted,
            "optouts": len(db.optouts(s, e)), "match_days": days}


def status():
    return {
        "enabled": config.enabled(), "watch": config.watch_enabled(), "buttons": config.buttons_enabled(),
        "buttons_dryrun": config.buttons_dryrun(), "report": config.report_enabled(),
        "codewords": {k: v.get("phrases") for k, v in config.CODEWORDS.items()},
        "optouts_total": len(db.optouts()), "last_report": db.get_setting("report_date", ""),
        "recent_taps": db.recent_taps(30),
    }
