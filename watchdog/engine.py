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

_SEV_ORDER = {"critical": 0, "warn": 1, "info": 2}
_SEV_EMOJI = {"critical": "🔴", "warn": "🟡", "info": "🔵"}

_ERR_LABELS = {
    "arrivals": "الوصول", "cleaning": "النظافة", "escalations": "التصعيدات",
    "pending": "الردود المعلقة", "promises": "الوعود", "tickets": "التذاكر",
    "coverage": "التغطية", "today": "أرقام اليوم", "health": "صحة النظام",
}

# ---------------- code-send classification ----------------

_CODE_KW_AR = ("كود", "رمز", "كلمة المرور", "كلمة مرور", "الباسوورد", "باسوورد", "رمز الدخول")
_CODE_KW_EN = ("code", "access code", "door code", "passcode", "password")


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
    """Newest OUTGOING code-bearing message (4-8 digit number near a code keyword)
    → {found, sender, sent_at}. Inbound messages never count."""
    best = None
    for m in msgs or []:
        if _is_inbound(m):
            continue
        body = m.get("body") or ""
        if not re.search(r"\b\d{4,8}\b", body):
            continue
        low = body.lower()
        if not (any(k in low for k in _CODE_KW_EN) or any(k in body for k in _CODE_KW_AR)):
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

    def add(key, severity, text, mention_name="", listing=""):
        flags.append({"key": key, "severity": severity,
                      "text": "%s %s" % (_SEV_EMOJI[severity], text),
                      "mention_name": mention_name, "listing": listing})

    for a in snap.get("arrivals") or []:
        h = float(a.get("hours_until") or 0)
        emp = a.get("employee") or "غير معروف"
        if (a.get("code_mode") == "manual") and not a.get("code_found"):
            sev = "critical" if h <= CODE_CRIT_H else "warn"
            add("code:%s:%s" % (a.get("listing_id"), a.get("arrival_date")), sev,
                "🔑 كود ما انرسل: %s — 👤 %s — الضيف يوصل خلال %s"
                % (a.get("unit"), emp, _h_label(h)),
                mention_name=a.get("employee") or "", listing=str(a.get("listing_id") or ""))
        if not a.get("cleaning_ok", True):
            sev = "critical" if h <= CLEAN_CRIT_H else "warn"
            add("clean:%s:%s" % (a.get("listing_id"), a.get("arrival_date")), sev,
                "🧹 الشقة مو جاهزة: %s — 👤 %s — الضيف يوصل خلال %s"
                % (a.get("unit"), emp, _h_label(h)),
                mention_name=a.get("employee") or "", listing=str(a.get("listing_id") or ""))

    for e in snap.get("escalations") or []:
        age = int(e.get("age_min") or 0)
        if age >= ESC_CRIT_MIN:
            sev = "critical"
        elif age >= ESC_WARN_MIN:
            sev = "warn"
        else:
            continue
        add("esc:%s" % e.get("id"), sev,
            "📣 تصعيد بدون استلام من %d دقيقة — %s (%s)"
            % (age, e.get("guest") or "ضيف", e.get("unit") or ""))

    for p in snap.get("pending") or []:
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
