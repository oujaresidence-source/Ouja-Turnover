# -*- coding: utf-8 -*-
"""watchdog.engine — PURE deterministic logic (no I/O, stdlib only): code-send
classification, automation fingerprinting (the Aseel rule), flag computation, and the
phone-first Discord renderers. TDD-locked by tests/test_watchdog_engine.py.

Golden rule: every number here comes from the snapshot the collector proved; a failed
collector section arrives in snap["errors"] and renders as «غير معروف» — never guessed."""

import hashlib
import re

# ---------------- thresholds (hours / minutes) ----------------
CODE_CRIT_H = 3.0          # arrival ≤3h + manual code missing → critical
CLEAN_CRIT_H = 3.0         # arrival ≤3h + cleaning not approved → critical
ESC_CRIT_MIN = 120
ESC_WARN_MIN = 45
PEND_CRIT_MIN = 120
PEND_WARN_MIN = 30
STALE_CLEAN_H = 36
MAX_FLAG_LINES = 8         # summary shows at most this many flags, then «+N أخرى»
STALE_AGE_MIN = 48 * 60    # older conversations = archive noise, not live flags

_SEV_ORDER = {"critical": 0, "warn": 1, "info": 2}
_SEV_EMOJI = {"critical": "🔴", "warn": "🟡", "info": "🔵"}

_ERR_LABELS = {
    "arrivals": "الوصول", "cleaning": "النظافة", "escalations": "التصعيدات",
    "pending": "الردود المعلقة", "promises": "الوعود", "tickets": "التذاكر",
    "coverage": "التغطية", "today": "أرقام اليوم", "health": "صحة النظام",
}

# ---------------- code-send classification ----------------
# Owner rule (2026-07-05): the UNIT door code is any digit run ending with «#».
# A code whose nearby context says «خارجي» (building/gate code) is NOT the unit code.

_EXT_MARKERS = ("خارجي", "خارجى", "خارجية", "بوابة", "البوابة", "external", "gate")


# Invisible bidi control marks (RLM/LRM/embedding/isolates) — Airbnb/WhatsApp insert
# them around «#» in RTL text; they broke the live C08 detection (2026-07-05).
_BIDI_CTRL = re.compile("[‎‏‪-‮⁦-⁩؜]")
# RTL typing can store the hash on EITHER side of the digit run («1234#» or «#1234»)
_CODE_PAT = re.compile(r"\d{3,10}\s*#|#\s*\d{3,10}")


def _has_unit_code(body):
    text = _BIDI_CTRL.sub("", body or "")
    prev_end = 0
    for m in _CODE_PAT.finditer(text):
        # the marker context is what sits between the previous code and this one —
        # so «الكود الخارجي 1234# وكود الشقة 5678#» counts the second code
        ctx = text[max(prev_end, m.start() - 40):m.start()]
        prev_end = m.end()
        if any(k in ctx for k in _EXT_MARKERS):
            continue
        return True
    return False


def _is_inbound(m):
    for k in ("isIncoming", "incoming"):
        try:
            if int(m.get(k) or 0) == 1:
                return True
        except Exception:
            pass
    return False


def _sender(m):
    """Which team member sent this outgoing message ('' unknown) — mirrors bot's
    _wm_sender_name, duplicated here so the engine stays pure/import-free."""
    u = m.get("user")
    if isinstance(u, dict):
        nm = (u.get("name")
              or " ".join(str(x) for x in (u.get("firstName"), u.get("lastName")) if x)).strip()
        if nm:
            return nm
    for k in ("userName", "agentName", "sentBy", "fromName", "senderName", "authorName"):
        v = str(m.get(k) or "").strip()
        if v:
            return v
    return ""


def classify_code_send(msgs):
    """Newest OUTGOING message carrying a UNIT door code (digits ending with «#»,
    excluding «خارجي»-marked gate codes) → {found, sender, sent_at}. Inbound never counts."""
    best = None
    for m in msgs or []:
        if _is_inbound(m):
            continue
        if not _has_unit_code(m.get("body") or ""):
            continue
        ts = str(m.get("date") or m.get("insertedOn") or "")
        if best is None or ts > best["sent_at"]:
            best = {"found": True, "sender": _sender(m), "sent_at": ts}
    return best or {"found": False, "sender": "", "sent_at": ""}


# ---------------- automation fingerprint (the Aseel rule) ----------------

_GREETINGS = {"مرحبا", "مرحباً", "هلا", "أهلا", "اهلا", "أهلاً", "hi", "hello", "dear",
              "عزيزي", "عزيزتي"}


def normalize_body(body):
    """Template fingerprint text: digits→#, punctuation stripped, the word right after a
    greeting (usually the guest's name) dropped, lowercased."""
    t = re.sub(r"\d+", "#", str(body or ""))
    t = re.sub(r"[^\w\s#؀-ۿ]", " ", t)
    words = [w for w in t.split() if len(w) > 1 or w == "#"]
    out, skip = [], False
    for w in words:
        if skip:
            skip = False
            continue
        lw = w.lower()
        out.append(lw)
        if lw in _GREETINGS:
            skip = True
    return " ".join(out)


def body_fp(body):
    return hashlib.sha1(normalize_body(body).encode("utf-8")).hexdigest()[:16]


def fp_is_automated(rec):
    """Automation = same template seen ≥3 times across ≥3 conversations with send
    clock-times inside a 40-minute band (e.g. the 11 AM checkout blast)."""
    if not rec or int(rec.get("n") or 0) < 3:
        return False
    if len(set(rec.get("convs") or [])) < 3:
        return False
    mins = rec.get("minutes") or []
    return bool(mins) and (max(mins) - min(mins)) <= 40


# ---------------- flags ----------------

def split_live_stale(items):
    """(live_items, stale_count) — anything older than STALE_AGE_MIN is archive noise."""
    live = [i for i in (items or []) if int(i.get("age_min") or 0) <= STALE_AGE_MIN]
    return live, len(items or []) - len(live)


def _h_label(h):
    if h <= 1.0:
        return "أقل من ساعة"
    if h < 2.0:
        return "ساعة ونص" if h >= 1.4 else "ساعة"
    return "%d ساعة" % round(h)


def compute_flags(snap, now):
    """Snapshot → ordered flag list [{key, severity, text, mention_name, listing}].
    Only `manual` code-mode apartments are code-checked; auto ones are Hostaway's job."""
    flags = []

    def add(key, severity, text, mention_name="", listing="", kind=""):
        flags.append({"key": key, "severity": severity,
                      "text": "%s %s" % (_SEV_EMOJI[severity], text),
                      "mention_name": mention_name, "listing": listing, "kind": kind})

    for a in snap.get("arrivals") or []:
        h = float(a.get("hours_until") or 0)
        emp = a.get("employee") or "غير معروف"
        when = ("الضيف واصل من %s" % _h_label(-h)) if h < 0 else ("الضيف يوصل خلال %s" % _h_label(h))
        if (a.get("code_mode") == "manual") and not a.get("code_found"):
            sev = "critical" if h <= CODE_CRIT_H else "warn"
            add("code:%s:%s" % (a.get("listing_id"), a.get("arrival_date")), sev,
                "🔑 كود ما انرسل: %s — 👤 %s — %s" % (a.get("unit"), emp, when),
                mention_name=a.get("employee") or "", listing=str(a.get("listing_id") or ""))
        if not a.get("cleaning_ok", True):
            sev = "critical" if h <= CLEAN_CRIT_H else "warn"
            add("clean:%s:%s" % (a.get("listing_id"), a.get("arrival_date")), sev,
                "🧹 الشقة مو جاهزة: %s — 👤 %s — %s" % (a.get("unit"), emp, when),
                mention_name=a.get("employee") or "", listing=str(a.get("listing_id") or ""))

    live_esc, _ = split_live_stale(snap.get("escalations"))
    for e in live_esc:
        age = int(e.get("age_min") or 0)
        if age >= ESC_CRIT_MIN:
            sev = "critical"
        elif age >= ESC_WARN_MIN:
            sev = "warn"
        else:
            continue
        kind = e.get("kind") or ""
        label = {"booking": " (حجز مؤكد)", "inquiry": " (استفسار)"}.get(kind, "")
        add("esc:%s" % e.get("id"), sev,
            "📣 تصعيد%s بدون استلام من %d دقيقة — %s (%s)"
            % (label, age, e.get("guest") or "ضيف", e.get("unit") or ""), kind=kind)

    live_pend, _ = split_live_stale(snap.get("pending"))
    for p in live_pend:
        age = int(p.get("age_min") or 0)
        if age >= PEND_CRIT_MIN:
            sev = "critical"
        elif age >= PEND_WARN_MIN:
            sev = "warn"
        else:
            continue
        add("pend:%s" % p.get("id"), sev,
            "💬 رد ينتظر الاعتماد من %d دقيقة — %s (%s)"
            % (age, p.get("guest") or "ضيف", p.get("unit") or ""))

    for pr in snap.get("promises") or []:
        who = pr.get("promised_by") or "غير معروف"
        if pr.get("expired"):
            add("prom:%s" % pr.get("id"), "critical",
                "🤝 وعد منتهي بدون تنفيذ — 👤 %s (%s)" % (who, pr.get("apartment") or ""),
                mention_name=pr.get("promised_by") or "")
        elif float(pr.get("overdue_h") or 0) > 0:
            add("prom:%s" % pr.get("id"), "warn",
                "🤝 وعد متأخر %d ساعة — 👤 %s (%s)"
                % (round(float(pr.get("overdue_h") or 0)), who, pr.get("apartment") or ""),
                mention_name=pr.get("promised_by") or "")

    for c in snap.get("cleaning_stale") or []:
        add("stale:%s" % c.get("key", c.get("unit")), "warn",
            "🧹 غرفة تنظيف مفتوحة من %d ساعة بدون تقرير — %s"
            % (round(float(c.get("opened_h") or 0)), c.get("unit") or ""))

    cov = snap.get("coverage") or {}
    if cov and not cov.get("ok", True):
        add("cov:today", "warn",
            "👥 توزيع اليوم غير متوازن (فرق %s شقق)" % cov.get("imbalance", "?"))

    tk = snap.get("tickets") or []
    n_unassigned = sum(1 for t in tk if not t.get("assigned_to"))
    if n_unassigned:
        add("tk:unassigned", "info", "🛠️ %d تذكرة بدون مسؤول" % n_unassigned)

    health = snap.get("health") or {}
    if health.get("disk_fallback"):
        add("health:disk", "critical", "💾 التخزين على وضع الطوارئ — القرص ممتلئ أو معطل")
    if health.get("api_ok") is False:
        add("health:api", "critical", "🔌 Hostaway ما يرد — البيانات الحية متوقفة")

    flags.sort(key=lambda f: _SEV_ORDER.get(f["severity"], 9))
    return flags


# ---------------- renderers (PHONE-FIRST: short lines, ≤12 lines, no tables) ----------------

def _counts_line(snap):
    esc_n = len(snap.get("escalations") or [])
    pend_n = len(snap.get("pending") or [])
    prom_over = sum(1 for p in (snap.get("promises") or [])
                    if p.get("expired") or float(p.get("overdue_h") or 0) > 0)
    return "📩 معلق: %d تصعيد · %d رد ينتظر · %d وعد متأخر" % (esc_n, pend_n, prom_over)


def _today_lines(snap):
    t = snap.get("today") or {}
    cs = snap.get("codes_summary") or {}
    lines = ["🏠 اليوم: %s وصول · %s مغادرة · %s ساكن"
             % (t.get("arr_n", "؟"), t.get("dep_n", "؟"), t.get("occupied", "؟"))]
    parts = []
    if t.get("tight_n"):
        parts.append("⚡ %d تسليم بنفس اليوم" % t["tight_n"])
    if cs.get("manual_total"):
        parts.append("🔑 أكواد يدوية: %d/%d مرسلة" % (cs.get("sent", 0), cs["manual_total"]))
    if parts:
        lines.append(" · ".join(parts))
    return lines


def _errors_line(snap):
    errs = snap.get("errors") or []
    if not errs:
        return ""
    labels = "، ".join(_ERR_LABELS.get(e, e) for e in errs)
    return "⚪ غير معروف (تعذّر الفحص): %s" % labels


def render_summary(flags, snap, ts_label):
    lines = []
    if not flags:
        lines.append("🟢 كل شي تمام — %s" % ts_label)
        lines.extend(_today_lines(snap))
        lines.append(_counts_line(snap))
    else:
        worst = flags[0]["severity"]
        header = "🔴 وضع يحتاج تدخل" if worst == "critical" else "🟡 فيه ملاحظات"
        lines.append("%s — %s" % (header, ts_label))
        shown = flags[:MAX_FLAG_LINES]
        lines.extend(f["text"] for f in shown)
        if len(flags) > MAX_FLAG_LINES:
            lines.append("… +%d أخرى" % (len(flags) - MAX_FLAG_LINES))
        lines.extend(_today_lines(snap)[:1])
    err = _errors_line(snap)
    if err:
        lines.append(err)
    return "\n".join(lines[:12])


# ---------------- categorized embeds (the phone-first detailed report) ----------------

def _age_label(m):
    m = int(m or 0)
    if m < 60:
        return "%d دقيقة" % m
    if m < 48 * 60:
        return "%d ساعة" % round(m / 60)
    return "%d يوم" % round(m / 1440)


def _nights_label(n):
    n = int(n or 0)
    if n == 1:
        return "ليلة"
    if n == 2:
        return "ليلتين"
    if 3 <= n <= 10:
        return "%d ليال" % n
    return "%d ليلة" % n


def _cap(desc, limit=3900):
    if len(desc) <= limit:
        return desc
    cut = desc[:limit]
    return cut[:cut.rfind("\n")] + "\n… القائمة أطول — الباقي بالدورة الجاية"


def render_embeds(flags, snap, ts_label):
    """Snapshot + flags → list of embed dicts {title, color(red|gold|green|gray), desc}.
    Every fact traces to the snapshot; unknown sections are named with their reason."""
    embeds = []
    sev_by_key = {f["key"]: f["severity"] for f in flags}
    worst = flags[0]["severity"] if flags else ""
    head_color = "red" if worst == "critical" else ("gold" if worst else "green")
    head_title = ("🔴 وضع يحتاج تدخل — %s" if head_color == "red" else
                  "🟡 فيه ملاحظات — %s" if head_color == "gold" else
                  "🟢 كل شي تمام — %s") % ts_label
    live_esc, stale_esc = split_live_stale(snap.get("escalations"))
    live_pend, stale_pend = split_live_stale(snap.get("pending"))
    live_esc = sorted(live_esc, key=lambda x: -int(x.get("age_min") or 0))
    live_pend = sorted(live_pend, key=lambda x: -int(x.get("age_min") or 0))
    t = snap.get("today") or {}
    cs = snap.get("codes_summary") or {}
    head = ["🏠 اليوم: %s وصول · %s مغادرة · %s ساكن"
            % (t.get("arr_n", "؟"), t.get("dep_n", "؟"), t.get("occupied", "؟"))]
    if t.get("tight_n"):
        head.append("⚡ %d تسليم بنفس اليوم" % t["tight_n"])
    if cs.get("manual_total"):
        head.append("🔑 أكواد يدوية: %d/%d مرسلة" % (cs.get("sent", 0), cs["manual_total"]))
    prom_over = len(snap.get("promises") or [])
    head.append("📩 حي الآن: %d تصعيد · %d رد ينتظر · %d وعد متأخر"
                % (len(live_esc), len(live_pend), prom_over))
    embeds.append({"title": head_title, "color": head_color, "desc": _cap("\n".join(head))})

    # 🏠 arrivals — full context per guest
    arrs = snap.get("arrivals") or []
    if arrs:
        lines, has_crit, has_warn = [], False, False
        for a in arrs:
            code_key = "code:%s:%s" % (a.get("listing_id"), a.get("arrival_date"))
            clean_key = "clean:%s:%s" % (a.get("listing_id"), a.get("arrival_date"))
            if sev_by_key.get(code_key) == "critical" or sev_by_key.get(clean_key) == "critical":
                has_crit = True
            elif code_key in sev_by_key or clean_key in sev_by_key:
                has_warn = True
            if a.get("code_mode") == "manual":
                if a.get("code_found"):
                    code = "🟡 أُرسل متأخر" if a.get("code_late") else "✅ مرسل"
                else:
                    code = "🔴 ما انرسل"
            else:
                code = "🔁 تلقائي"
            clean = "✅ جاهزة" if a.get("cleaning_ok", True) else "🔴 مو جاهزة"
            contract = "✅ العقد موقّع" if a.get("signed") else "❌ العقد غير موقّع"
            bits = ["👤 %s" % (a.get("employee") or "غير معروف"),
                    "🔑 %s" % code, "🧹 %s" % clean, contract]
            if a.get("nights"):
                bits.append(_nights_label(a["nights"]))
            if a.get("price"):
                bits.append("%s ر.س" % a["price"])
            if a.get("open_tickets"):
                bits.append("🛠️ %d تذكرة مفتوحة" % a["open_tickets"])
            lines.append("⏰ %s · **%s** — %s\n%s"
                         % (a.get("time_label") or "؟", a.get("guest"), a.get("unit"),
                            " · ".join(bits)))
        color = "red" if has_crit else ("gold" if has_warn else "gray")
        embeds.append({"title": "🏠 وصول اليوم (%d)" % len(arrs), "color": color,
                       "desc": _cap("\n\n".join(lines))})

    # 🚪 departures
    deps = snap.get("departures") or []
    if deps:
        lines = ["**%s** — %s · 🧹 %s" % (d.get("guest"), d.get("unit"),
                                          d.get("employee") or "غير معروف") for d in deps]
        embeds.append({"title": "🚪 مغادرات اليوم (%d)" % len(deps), "color": "gray",
                       "desc": _cap("\n".join(lines))})

    # 🧹 cleaning problems
    stale_clean = snap.get("cleaning_stale") or []
    if stale_clean:
        lines = ["🟡 %s — مفتوحة من %s بدون تقرير"
                 % (c.get("unit"), _age_label(float(c.get("opened_h") or 0) * 60))
                 for c in stale_clean]
        embeds.append({"title": "🧹 نظافة متأخرة (%d)" % len(stale_clean), "color": "gold",
                       "desc": _cap("\n".join(lines))})

    # 📩 conversations (live only, deduped upstream, capped + archive count)
    if live_esc or live_pend or stale_esc or stale_pend:
        lines = []
        for e in live_esc:
            lines.append("📣 تصعيد بدون استلام من %s — %s (%s)"
                         % (_age_label(e.get("age_min")), e.get("guest"), e.get("unit")))
        for p in live_pend:
            extra = " · %d رسائل" % p["n"] if int(p.get("n") or 1) > 1 else ""
            lines.append("💬 رد ينتظر الاعتماد من %s — %s (%s)%s"
                         % (_age_label(p.get("age_min")), p.get("guest"), p.get("unit"), extra))
        if len(lines) > 13:
            hidden = len(lines) - 13
            lines = lines[:13] + ["… +%d أخرى" % hidden]
        if not lines:
            lines.append("✅ لا شي حي يحتاج تدخل")
        archived = stale_esc + stale_pend
        if archived:
            lines.append("🗄️ أرشيف قديم: %d — أقدم من يومين، ما يُحسب" % archived)
        color = "red" if any(e.get("age_min", 0) >= ESC_CRIT_MIN for e in live_esc) else (
            "gold" if (live_esc or live_pend) else "gray")
        embeds.append({"title": "📩 محادثات تحتاج الفريق", "color": color,
                       "desc": _cap("\n".join(lines))})

    # 🤝 promises
    proms = snap.get("promises") or []
    if proms:
        lines = []
        for p in proms:
            mark = "🔴 منتهي" if p.get("expired") else ("🟡 متأخر %d ساعة"
                                                        % round(float(p.get("overdue_h") or 0)))
            lines.append("%s — 👤 %s (%s)" % (mark, p.get("promised_by") or "غير معروف",
                                              p.get("apartment") or ""))
        color = "red" if any(p.get("expired") for p in proms) else "gold"
        embeds.append({"title": "🤝 وعود متأخرة (%d)" % len(proms), "color": color,
                       "desc": _cap("\n".join(lines))})

    # 👥 today's coverage
    cov = snap.get("coverage") or {}
    working = cov.get("working") or []
    if working or cov.get("off_names"):
        lines = ["%s %s — %d شقة" % (w.get("emoji") or "👤", w.get("name"), int(w.get("n") or 0))
                 for w in working]
        if cov.get("off_names"):
            lines.append("🌙 إجازة اليوم: %s" % "، ".join(cov["off_names"]))
        if not cov.get("ok", True):
            lines.append("⚠️ التوزيع غير متوازن (فرق %s شقق)" % cov.get("imbalance", "?"))
        embeds.append({"title": "👥 توزيع الموظفين اليوم", "color": "gray",
                       "desc": _cap("\n".join(lines))})

    # 🔧 system + unknown sections (with the real reason)
    sys_lines = []
    health = snap.get("health") or {}
    if health.get("disk_fallback"):
        sys_lines.append("💾 التخزين على وضع الطوارئ — القرص ممتلئ أو معطل")
    if health.get("api_ok") is False:
        sys_lines.append("🔌 Hostaway ما يرد — البيانات الحية متوقفة")
    detail = snap.get("errors_detail") or {}
    for e in snap.get("errors") or []:
        why = str(detail.get(e) or "").strip()
        sys_lines.append("⚪ غير معروف (تعذّر الفحص): %s%s"
                         % (_ERR_LABELS.get(e, e), (" — %s" % why[:120]) if why else ""))
    if sys_lines:
        embeds.append({"title": "🔧 النظام", "color": "red" if (health.get("disk_fallback")
                       or health.get("api_ok") is False) else "gray",
                       "desc": _cap("\n".join(sys_lines))})

    return embeds[:10]


def render_compact(flags, snap, ts_label, link_url=""):
    """Discord is the ALARM, the page is the report: one small embed — status, three
    numbers, top-3 criticals, link. Owner feedback 2026-07-05: long reports are
    unreadable on the phone inside Discord."""
    worst = flags[0]["severity"] if flags else ""
    color = "red" if worst == "critical" else ("gold" if worst else "green")
    title = ("🔴 يحتاج تدخل — %s" if color == "red" else
             "🟡 فيه ملاحظات — %s" if color == "gold" else
             "🟢 كل شي تمام — %s") % ts_label
    t = snap.get("today") or {}
    cs = snap.get("codes_summary") or {}
    live_esc, _ = split_live_stale(snap.get("escalations"))
    live_pend, _ = split_live_stale(snap.get("pending"))
    lines = ["🏠 %s وصول · %s مغادرة · %s ساكن"
             % (t.get("arr_n", "؟"), t.get("dep_n", "؟"), t.get("occupied", "؟"))]
    bits = []
    if cs.get("manual_total"):
        bits.append("🔑 %d/%d" % (cs.get("sent", 0), cs["manual_total"]))
    bits.append("📩 %d" % (len(live_esc) + len(live_pend)))
    bits.append("🤝 %d" % len(snap.get("promises") or []))
    lines.append(" · ".join(bits))
    crits = [f for f in flags if f["severity"] == "critical"]
    if crits:
        lines.append("")
        for f in crits[:3]:
            lines.append(f["text"])
        if len(crits) > 3:
            lines.append("… +%d حرجة أخرى" % (len(crits) - 3))
    if snap.get("errors"):
        lines.append("⚪ فحوصات تعذّرت: %d — التفاصيل في الصفحة" % len(snap["errors"]))
    if link_url:
        lines.append("")
        lines.append("📱 [التقرير الكامل — اضغط هنا](%s)" % link_url)
    return {"title": title, "color": color, "desc": _cap("\n".join(lines), 2000)}


def render_critical(flag, mention_text=""):
    lines = [flag["text"]]
    if mention_text:
        lines.append(mention_text)
    return "\n".join(lines)


# ---------------- scoreboard ----------------

def scoreboard(stats, code_sends, promise_rows, esc_claims):
    """Per-employee proven metrics. Unknown senders ('' names) are logged upstream but
    NEVER get a scoreboard row — the golden rule."""
    board = {}

    def row(name):
        if not name:
            return None
        return board.setdefault(name, {
            "name": name, "replies": 0, "resp_avg": 0, "_rsum": 0.0, "_rn": 0,
            "codes_on_time": 0, "codes_total": 0, "kept_pct": None, "_pk": 0, "_pt": 0,
            "esc_claims": 0, "automations_skipped": 0})

    for s in stats or []:
        r = row((s.get("employee") or "").strip())
        if r is None:
            continue
        r["replies"] += int(s.get("replies") or 0)
        r["_rsum"] += float(s.get("resp_min_sum") or 0)
        r["_rn"] += int(s.get("resp_min_n") or 0)
        r["automations_skipped"] += int(s.get("automations_skipped") or 0)

    for c in code_sends or []:
        r = row((c.get("sent_by") or "").strip())
        if r is None:
            continue
        r["codes_total"] += 1
        r["codes_on_time"] += 1 if c.get("on_time") else 0

    for p in promise_rows or []:
        r = row((p.get("promised_by") or "").strip())
        if r is None:
            continue
        st = p.get("status")
        if st == "done":
            r["_pk"] += 1
            r["_pt"] += 1
        elif st == "expired":
            r["_pt"] += 1

    for e in esc_claims or []:
        r = row((e.get("claimed_by_name") or "").strip())
        if r is None:
            continue
        r["esc_claims"] += 1

    out = []
    for r in board.values():
        r["resp_avg"] = round(r["_rsum"] / r["_rn"]) if r["_rn"] else 0
        r["kept_pct"] = round(100 * r["_pk"] / r["_pt"]) if r["_pt"] else None
        for k in ("_rsum", "_rn", "_pk", "_pt"):
            r.pop(k)
        out.append(r)
    out.sort(key=lambda r: (-(r["kept_pct"] if r["kept_pct"] is not None else -1),
                            -r["replies"]))
    return out


def render_scoreboard(board):
    lines = ["🏆 لوحة الأسبوع — أرقام مثبتة فقط"]
    for r in board[:10]:
        bits = []
        if r["kept_pct"] is not None:
            bits.append("وعود %d%%" % r["kept_pct"])
        bits.append("ردود %d" % r["replies"])
        if r["resp_avg"]:
            bits.append("متوسط الرد %d د" % r["resp_avg"])
        if r["codes_total"]:
            bits.append("أكواد %d/%d باكر" % (r["codes_on_time"], r["codes_total"]))
        if r["esc_claims"]:
            bits.append("تصعيدات %d" % r["esc_claims"])
        lines.append("👤 %s — %s" % (r["name"], " · ".join(bits)))
        if r["automations_skipped"]:
            lines.append("   (استبعدنا %d رسالة أتمتة — ما تنحسب)" % r["automations_skipped"])
    if len(board) < 1:
        lines.append("لا يوجد بيانات كافية بعد")
    return "\n".join(lines)
