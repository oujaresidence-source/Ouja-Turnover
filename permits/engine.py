# -*- coding: utf-8 -*-
"""
permits.engine — the rules of «التصاريح». PURE: no database, no Discord, no clock.
The caller always passes `today` / `now`, which is what makes every rule here testable
(tests/test_permits_engine.py locks them).

THE GUARANTEE THIS MODULE SERVES
--------------------------------
No permit expires without a ticket. So:

* ONE band function. The dashboard, the digest, the ticket card and the reminders all
  colour from `band()`, so they cannot disagree about how urgent something is.
* A ticket opens at `days_left <= lead` — `<=`, never `==`. If the bot was down on day 10,
  it opens on day 9, or on day −3 (catch-up). An unknown date never opens a ticket; it
  is shouted about in the digest every day instead.
* Text builders respect Discord's hard limits (25 fields, 1024 per value, 6000 per embed,
  2000 per message) by construction, so a long note can never make a post fail.
* Unit matching is unique-or-nothing. Two candidates means no link, never a pick.
"""

import datetime
import json
import os
import re

from . import dates

SEED_TYPE = "تصريح مرافق الضيافة السياحية الخاصة"
SEED_ISSUER = "وزارة السياحة"

TYPE_SUGGESTIONS = [
    SEED_TYPE,
    "ترخيص وحدة/مرفق ضيافة — وزارة السياحة",
    "رخصة بلدية",
    "شهادة الدفاع المدني",
    "تصريح أعمال/دخول من إدارة المجمع",
    "السجل التجاري",
    "رخصة فال",
    "اشتراك الغرفة التجارية",
]

TYPE_DEFAULTS = {
    SEED_TYPE: {
        "short": "تصريح ضيافة سياحية",
        "issuer": SEED_ISSUER,
        "renew_notes": "التجديد من منصة وزارة السياحة — يحتاج موافقة المالك عبر نفاذ",
    },
}

LIVE_STATUSES = ("active",)
LIVE_TICKET_STATES = ("opening", "open")

BAND_META = {
    "expired":  {"ar": "منتهي",        "en": "Expired",       "emoji": "🔴", "color": 0xE5484D},
    "urgent":   {"ar": "عاجل",         "en": "Urgent",        "emoji": "🚨", "color": 0xF0603A},
    "due":      {"ar": "يحتاج تجديد",  "en": "Renew now",     "emoji": "🟠", "color": 0xE8862A},
    "upcoming": {"ar": "قريب",         "en": "Coming up",     "emoji": "🟡", "color": 0xE2B33C},
    "ok":       {"ar": "سليم",         "en": "Healthy",       "emoji": "🟢", "color": 0x3BA55D},
    "unknown":  {"ar": "ناقص بيانات",  "en": "Missing data",  "emoji": "⚪", "color": 0x8A8F98},
}
BAND_ORDER = ("unknown", "expired", "urgent", "due", "upcoming", "ok")
URGENT_MAX = 3

# Discord's hard limits (https://discord.com/developers/docs/resources/message#embed-object-embed-limits)
EMBED_MAX_FIELDS = 25
EMBED_FIELD_VALUE = 1024
EMBED_FIELD_NAME = 256
EMBED_TITLE = 256
EMBED_TOTAL = 6000
MSG_CHUNK = 1900


# ---------------- config (read at CALL time — a Railway variable change needs no deploy) ----------------

_DEFAULTS = {"lead_days": 10, "headsup_days": 30, "daily_hour": 13, "open_from": 9,
             "open_to": 22, "tick_min": 5}
_ENV_INT = {"lead_days": ("PERMITS_LEAD_DAYS", 0, 365), "headsup_days": ("PERMITS_HEADSUP_DAYS", 0, 365),
            "daily_hour": ("PERMITS_DAILY_HOUR", 0, 23), "open_from": ("PERMITS_OPEN_FROM", 0, 23),
            "open_to": ("PERMITS_OPEN_TO", 1, 24), "tick_min": ("PERMITS_TICK_MIN", 1, 60)}


def _int_in(raw, default, lo, hi, name):
    s = str(raw if raw is not None else "").strip()
    if not s:
        return default
    try:
        v = int(s)
    except ValueError:
        print("[permits] %s=%r is not a number — using %s" % (name, s, default))
        return default
    if v < lo or v > hi:
        print("[permits] %s=%r out of range — using %s" % (name, s, default))
        return default
    return v


def cfg(env=None):
    """Every knob, read now. `env` is os.environ unless a test passes a dict."""
    env = os.environ if env is None else env
    out = {}
    for key, (name, lo, hi) in _ENV_INT.items():
        out[key] = _int_in(env.get(name), _DEFAULTS[key], lo, hi, name)
    out["digest_channel"] = (str(env.get("PERMITS_DIGEST_CHANNEL") or "").strip()
                             or "تنبيهات-التصاريح")
    role = str(env.get("PERMITS_PING_ROLE_ID") or "").strip()
    out["ping_role_id"] = int(role) if role.isdigit() else 0
    raw_ids = str(env.get("PERMITS_ESCALATE_IDS") or "").replace("،", ",")
    ids = [int(p.strip()) for p in raw_ids.split(",") if p.strip().isdigit()]
    out["escalate_ids"] = ids or None          # None → bot.py falls back to MAINT_CLOSE_IDS
    out["force_dry"] = str(env.get("PERMITS_FORCE_DRY") or "0").strip() == "1"
    return out


# ---------------- dates & bands ----------------

def _iso(today):
    if isinstance(today, datetime.datetime):
        return today.date().isoformat()
    if isinstance(today, datetime.date):
        return today.isoformat()
    return str(today)[:10]


def days_left(end_iso, today):
    """Whole days from today to the end date (inclusive validity: 0 = ends today)."""
    try:
        end = datetime.date.fromisoformat(str(end_iso)[:10])
        now = datetime.date.fromisoformat(_iso(today))
    except (TypeError, ValueError):
        return None
    return (end - now).days


def band(left, lead_days=10, headsup_days=30):
    """'expired' | 'urgent' | 'due' | 'upcoming' | 'ok' | 'unknown'. THE one band function.

    urgent is always 0–3; due is 4…lead (empty when lead ≤ 3); upcoming is lead…headsup."""
    if left is None:
        return "unknown"
    if left < 0:
        return "expired"
    if left <= URGENT_MAX:
        return "urgent"
    if left <= lead_days:
        return "due"
    if left <= headsup_days:
        return "upcoming"
    return "ok"


def lead_for(permit, c):
    v = (permit or {}).get("lead_days")
    try:
        return int(v) if v is not None and str(v).strip() != "" else c["lead_days"]
    except (TypeError, ValueError):
        return c["lead_days"]


def is_live(permit):
    return str((permit or {}).get("status") or "") in LIVE_STATUSES


def describe(permit, today, c):
    """The permit plus days_left / band / lead — computed once, read everywhere."""
    p = dict(permit or {})
    lead = lead_for(p, c)
    left = None if p.get("needs_data") else days_left(p.get("end_date"), today)
    p["days_left"] = left
    p["lead"] = lead
    p["band"] = band(left, lead, c["headsup_days"])
    return p


def counts(rows):
    """Band counts over LIVE rows only (renewed/cancelled/superseded are history)."""
    out = {b: 0 for b in BAND_ORDER}
    for r in rows:
        if not is_live(r):
            continue
        out[r.get("band") or "unknown"] = out.get(r.get("band") or "unknown", 0) + 1
    out["alert"] = out["expired"] + out["urgent"] + out["due"] + out["unknown"]
    out["total"] = sum(out[b] for b in BAND_ORDER)
    return out


def should_open(permit, today, c):
    """Ticket rule: live, dated, not needs_data, and days_left ≤ lead (catch-up included)."""
    if not is_live(permit) or (permit or {}).get("needs_data"):
        return False
    left = days_left(permit.get("end_date"), today)
    return left is not None and left <= lead_for(permit, c)


def in_open_window(hour, c):
    return c["open_from"] <= int(hour) < c["open_to"]


def plan(permits, live_ticket_pids, now, c, golive_sweep=False):
    """What should happen to permits this tick. PURE.

    -> {"open": [pid], "waiting": [pid due but outside the open window], "unknown": [pid]}

    `golive_sweep`: the first tick after an admin switched to live — EXPIRED permits open
    even in quiet hours that one time (the go-live confirm already told them how many)."""
    today = _iso(now)
    inside = in_open_window(now.hour, c)
    out = {"open": [], "waiting": [], "unknown": []}
    for p in permits:
        if not is_live(p):
            continue
        pid = p.get("id")
        if p.get("needs_data") or not p.get("end_date"):
            out["unknown"].append(pid)
            continue
        if not should_open(p, today, c) or pid in live_ticket_pids:
            continue
        expired = (days_left(p.get("end_date"), today) or 0) < 0
        if inside or (golive_sweep and expired):
            out["open"].append(pid)
        else:
            out["waiting"].append(pid)
    return out


def reminder_due(ticket, now, c):
    """Once per Riyadh day per OPEN ticket, at or after the daily hour."""
    if str((ticket or {}).get("state") or "") != "open":
        return False
    if now.hour < c["daily_hour"]:
        return False
    return str(ticket.get("last_reminder_date") or "") != _iso(now)


def summary_due(now, last_date, hour):
    """directpay's latch: once per Riyadh day from `hour` on; `last_date` is PERSISTED."""
    if now.hour < int(hour):
        return False
    return _iso(now) != str(last_date or "")


def reminder_mentions(band_name, resp_id, c):
    """(user_ids, role_ids) a reminder may ping. due → responsible; urgent → + role;
    expired → + the escalation people."""
    users = [str(resp_id)] if str(resp_id or "").strip() else []
    roles = []
    if band_name == "urgent" and c.get("ping_role_id"):
        roles.append(str(c["ping_role_id"]))
    if band_name == "expired":
        for i in (c.get("escalate_ids") or []):
            if str(i) not in users:
                users.append(str(i))
    return users, roles


# ---------------- words ----------------

def n_days(n):
    n = abs(int(n))
    if n == 1:
        return "يوم واحد"
    if n == 2:
        return "يومين"
    if 3 <= n <= 10:
        return "%d أيام" % n
    return "%d يوم" % n


def left_text(left):
    if left is None:
        return "تاريخ الانتهاء غير معروف"
    if left == 0:
        return "ينتهي اليوم"
    if left < 0:
        return "منتهي من " + n_days(left)
    return "باقي " + n_days(left)


def end_words(iso):
    """'2026-10-11 · ٣٠ ربيع الآخر ١٤٤٨هـ' — both calendars (Hijri blank if unavailable)."""
    if not iso:
        return "—"
    h = dates.to_hijri_str(iso)
    return iso + (" · " + h if h else "")


def gregorian_words(iso):
    """'1 أكتوبر 2026' — Western digits, Arabic month (the digest header style)."""
    try:
        d = datetime.date.fromisoformat(str(iso)[:10])
    except (TypeError, ValueError):
        return ""
    return "%d %s %d" % (d.day, dates.MONTHS_AR[d.month], d.year)


def unit_label(permit, unit_name=""):
    p = permit or {}
    return (unit_name or p.get("unit_text") or p.get("building") or "الشركة").strip() or "الشركة"


def type_default(permit, key):
    return (TYPE_DEFAULTS.get((permit or {}).get("permit_type") or "") or {}).get(key, "")


def open_issues(permit):
    try:
        items = json.loads((permit or {}).get("review_issues") or "[]")
    except (TypeError, ValueError):
        return []
    return [i for i in items if isinstance(i, dict) and not i.get("cleared_at")]


def extras(permit):
    try:
        d = json.loads((permit or {}).get("extra_json") or "{}")
    except (TypeError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


# ---------------- channel naming ----------------

_SLUG_KEEP = re.compile(r"[^a-z0-9ء-ي]+")


def channel_slug(source):
    """channel_name()-style ASCII slug; Arabic letters kept when that is all there is,
    because an unlinked «العارض ـ ابو ماجد» must still name its room. ≤ 40 chars."""
    s = dates.clean_text(source).lower().replace("ـ", " ")
    ascii_slug = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    ascii_slug = re.sub(r"^ouja-", "", ascii_slug)
    slug = ascii_slug if ascii_slug else _SLUG_KEEP.sub("-", s).strip("-")
    slug = re.sub(r"^(ouja|عوجا)-", "", slug)
    return slug[:40].strip("-")


def channel_name(tid, source):
    return "تصريح-%03d-%s" % (int(tid), channel_slug(source) or "permit")


def topic(pid, tid, end_date):
    return "ouja-permit: pid:%s tid:%s end:%s" % (pid, tid, end_date or "?")


_TOPIC = re.compile(r"^ouja-permit:\s*pid:(\d+)\s+tid:(\d+)")


def parse_topic(text):
    m = _TOPIC.match(str(text or ""))
    return (int(m.group(1)), int(m.group(2))) if m else None


# ---------------- the ticket card ----------------

def _cut(s, n):
    s = str(s if s is not None else "")
    return s if len(s) <= n else s[: n - 1] + "…"


def embed_size(card):
    total = len(card.get("title") or "") + len(card.get("description") or "") + len(card.get("footer") or "")
    for name, value, _inline in card.get("fields") or []:
        total += len(name) + len(value)
    return total


def ticket_card(permit, tid, today, c, unit_name="", responsible="", dashboard_url="",
                replaced_tid=None):
    """The pinned card as plain data: {title, description, color, fields:[(name, value, inline)],
    footer, content}. bot.py turns it into a discord.Embed verbatim.

    NEVER includes the holder's ID digits — only the holder's NAME reaches Discord (§2.3)."""
    p = describe(permit, today, c)
    meta = BAND_META[p["band"]]
    unit = unit_label(p, unit_name)
    fixed = []

    def add(name, value, inline=True):
        v = str(value if value is not None else "").strip()
        if v:
            fixed.append((name, _cut(v, EMBED_FIELD_VALUE), inline))

    add("🏷️ النوع", p.get("permit_type"))
    add("🔢 الرقم", p.get("permit_no"))
    add("🏠 الشقة/المبنى", unit)
    add("🏛️ جهة الإصدار", p.get("issuer") or type_default(p, "issuer"))
    add("👤 باسم", p.get("holder"))
    addr = " · ".join(x for x in (
        p.get("district"), p.get("street"),
        ("مبنى " + p["building_no"]) if p.get("building_no") else "",
        ("وحدة " + p["unit_no"]) if p.get("unit_no") else "") if x)
    if p.get("ownership_kind"):
        addr = (addr + " — " if addr else "") + p["ownership_kind"]
    add("📍 العنوان", addr, False)
    if p.get("doc_url"):
        add("📎 التصريح الحالي", "[افتح التصريح](%s)" % p["doc_url"])
    issues = open_issues(p)
    if issues:
        add("⚠️ تحتاج مراجعة", "\n".join("• " + str(i.get("text_ar") or i.get("code")) for i in issues), False)
    add("📅 البداية", end_words(p.get("start_date")) if p.get("start_date") else "")
    add("📅 النهاية", end_words(p.get("end_date")) if p.get("end_date") else
        ("غير مقروء: «%s»" % p.get("end_date_raw") if p.get("end_date_raw") else "غير معروف"))
    add("⏳ المتبقي", left_text(p["days_left"]))
    if p.get("cost_sar") not in (None, ""):
        try:
            add("💰 التكلفة", "%s ر.س" % ("{:,.0f}".format(float(p["cost_sar"]))))
        except (TypeError, ValueError):
            pass
    add("🛠️ طريقة التجديد", p.get("renew_notes") or type_default(p, "renew_notes"), False)
    add("📝 ملاحظات", p.get("notes"), False)

    tail = [("👷 المسؤول", _cut(responsible or "—", EMBED_FIELD_VALUE), True),
            ("🔗 الداشبورد", _cut(("[افتح صفحة التصاريح](%s)" % dashboard_url) if dashboard_url else "—",
                                  EMBED_FIELD_VALUE), True)]
    extra_items = [(_cut("➕ " + str(k), EMBED_FIELD_NAME), _cut(v, EMBED_FIELD_VALUE), True)
                   for k, v in extras(p).items() if str(v if v is not None else "").strip()]
    room = EMBED_MAX_FIELDS - len(fixed) - len(tail)
    if len(extra_items) > room:
        keep = max(room - 1, 0)
        rest = extra_items[keep:]
        extra_items = extra_items[:keep] + [("معلومات إضافية", _cut(
            "\n".join("%s: %s" % (n.replace("➕ ", ""), v) for n, v, _i in rest), EMBED_FIELD_VALUE), False)]
    fields = fixed + extra_items + tail

    card = {
        "title": _cut("📄 تصريح #%03d — %s · %s" % (int(tid), p.get("permit_type") or "تصريح", unit), EMBED_TITLE),
        "description": ("التذكرة السابقة #%03d انحذفت — هذي بديلتها" % int(replaced_tid)) if replaced_tid else "",
        "color": meta["color"],
        "fields": fields,
        "footer": "permit:%s · ticket:%s" % (p.get("id"), tid),
        "content": ("🚨 **عاجل** · " if p["band"] in ("urgent", "expired") else "")
        + (responsible or "") + " — تذكرة تجديد تصريح",
    }
    # Total embed budget: shorten the longest values (extras first, never the tail) until it fits.
    guard = 0
    while embed_size(card) > EMBED_TOTAL - 50 and guard < 200:
        guard += 1
        body = card["fields"][:-len(tail)]
        if not body:
            break
        i = max(range(len(body)), key=lambda k: len(body[k][1]))
        name, value, inline = body[i]
        if len(value) <= 40:
            break
        card["fields"][i] = (name, _cut(value, max(40, len(value) // 2)), inline)
    return card


# ---------------- reminder + closing notes ----------------

def reminder_text(permit, ticket, today, c, unit_name="", mentions=""):
    p = describe(permit, today, c)
    unit = unit_label(p, unit_name)
    typ = p.get("permit_type") or "التصريح"
    left = p["days_left"]
    if p["band"] == "expired":
        body = "🔴 منتهي من %s — %s · %s. التشغيل بدون تصريح ساري مخاطرة. جدّدوه اليوم." % (
            n_days(left), typ, unit)
    elif left == 0:
        body = "🚨 ينتهي **اليوم** — %s · %s. وش وضع التجديد؟" % (typ, unit)
    elif p["band"] == "urgent":
        body = "🚨 باقي %s فقط على انتهاء %s — %s. وش وضع التجديد؟" % (n_days(left), typ, unit)
    else:
        body = "⏰ باقي %s على انتهاء %s — %s. وش وضع التجديد؟" % (
            n_days(left) if left is not None else "؟", typ, unit)
    lines = [((mentions + " ") if mentions else "") + body]
    t = ticket or {}
    if t.get("claimed_by"):
        since = str(t.get("claimed_at") or "")[:10]
        lines.append("✋ مستلمها **%s**%s — التذكير يستمر يومياً لين تتجدد."
                     % (t["claimed_by"], (" من " + since) if since else ""))
    else:
        lines.append("ما أحد استلمها — اضغط «✋ أستلمها».")
    return "\n".join(lines)


def renewed_note(new_end, today):
    left = days_left(new_end, today)
    return "✅ تجدّد — ينتهي الجديد %s (%s)" % (end_words(new_end), n_days(left) if left is not None else "؟")


def cancelled_note(reason, by):
    return "🚫 لن يُجدَّد — %s\nبواسطة: %s" % (reason, by)


def corrected_note(new_end, today, reason, by):
    return ("✏️ تصحيح تاريخ: ينتهي %s (%s) — صار خارج نافذة التجديد فانقفلت التذكرة.\nالسبب: %s · بواسطة: %s"
            % (end_words(new_end), left_text(days_left(new_end, today)), reason, by))


# ---------------- the daily digest ----------------

def chunk(lines, limit=MSG_CHUNK):
    """Join lines into messages ≤ limit chars (a single over-long line is hard-cut)."""
    out, buf = [], ""
    for ln in lines:
        ln = ln if len(ln) <= limit else ln[: limit - 1] + "…"
        if buf and len(buf) + 1 + len(ln) > limit:
            out.append(buf)
            buf = ln
        else:
            buf = (buf + "\n" + ln) if buf else ln
    if buf:
        out.append(buf)
    return out


def _ticket_bits(r, guild_id=None, mode="live"):
    t = r.get("ticket") or None
    bits = []
    if t and t.get("id"):
        tag = "تذكرة #%03d" % int(t["id"])
        if t.get("channel_id"):
            tag += " <#%s>" % t["channel_id"]
        elif t.get("state") == "opening":
            tag += " (قيد الفتح)"
        bits.append(tag)
    elif mode == "dry":
        bits.append("وضع التجربة — ما انفتحت تذكرة")
    else:
        bits.append("تنفتح تذكرتها بأقرب وقت")
    return bits


def digest_messages(rows, today, c, problems=(), renewed=(), mode="live"):
    """-> (messages, mention_user_ids). `rows` are describe()d permits enriched by the
    service with: unit_name, ticket (dict|None), resp_name, resp_id.

    Only the responsible people of EXPIRED/URGENT items are mentioned (<@id>); everyone
    else appears by name, so the digest never becomes a daily ping storm."""
    live = [r for r in rows if is_live(r)]
    by = {b: [] for b in BAND_ORDER}
    for r in live:
        by[r.get("band") or "unknown"].append(r)
    for b in by:
        by[b].sort(key=lambda r: (r.get("days_left") if r.get("days_left") is not None else -10 ** 6,
                                  str(r.get("unit_name") or r.get("unit_text") or "")))
    today_iso = _iso(today)
    head = "📋 تقرير التصاريح اليومي — %s %s" % (dates.weekday_ar(today_iso), gregorian_words(today_iso))
    hj = dates.to_hijri_str(today_iso)
    if hj:
        head += " · " + hj
    nothing_wrong = not (by["expired"] or by["urgent"] or by["due"] or by["unknown"] or problems)
    if nothing_wrong:
        nxt = sorted([r for r in live if r.get("days_left") is not None], key=lambda r: r["days_left"])
        if nxt:
            r = nxt[0]
            line = "📋 %s — ✅ كل التصاريح سليمة — أقرب انتهاء: %s · %s بعد %d يوم (%s)" % (
                gregorian_words(today_iso), r.get("permit_type") or "تصريح", unit_label(r, r.get("unit_name")),
                r["days_left"], r.get("end_date"))
        else:
            line = "📋 %s — ✅ ما فيه تصاريح مسجّلة تحتاج متابعة" % gregorian_words(today_iso)
        lines = [line]
        if renewed:                       # good news still gets said — under the one line
            lines += ["✅ تجدّد أمس"] + ["• %s · %s بواسطة %s" % (
                rn.get("permit_type") or "تصريح", rn.get("unit_name") or "—", rn.get("by") or "—")
                for rn in renewed]
        return chunk(lines), []

    mentions = []

    def who(r, ping):
        rid, nm = str(r.get("resp_id") or "").strip(), str(r.get("resp_name") or "").strip()
        if ping and rid:
            if rid not in mentions:
                mentions.append(rid)
            return "المسؤول <@%s>" % rid
        return ("المسؤول " + nm) if nm else "ما فيه مسؤول معيّن"

    def claimed(r):
        t = r.get("ticket") or {}
        if not t:
            return ""
        return ("مستلمة من " + t["claimed_by"]) if t.get("claimed_by") else "لم يستلمها أحد"

    def item(r, ping, with_ticket=True):
        bits = [r.get("permit_type") or "تصريح", unit_label(r, r.get("unit_name"))]
        if r.get("permit_no"):
            bits.append("رقم " + str(r["permit_no"]))
        bits.append(left_text(r.get("days_left")))
        if r.get("band") in ("due", "urgent", "upcoming") and r.get("end_date"):
            bits.append("ينتهي " + gregorian_words(r["end_date"]))
        if with_ticket:
            bits += _ticket_bits(r, mode=mode)
            bits.append(who(r, ping))
            cl = claimed(r)
            if cl:
                bits.append(cl)
        return "• " + " · ".join(b for b in bits if b)

    orange = by["urgent"] + by["due"]
    lines = [head,
             "🔴 منتهية: %d   🟠 تحتاج تجديد (≤%d أيام): %d   🟡 قريبة (≤%d): %d   ⚪ ناقصة بيانات: %d   🟢 سليمة: %d"
             % (len(by["expired"]), c["lead_days"], len(orange), c["headsup_days"], len(by["upcoming"]),
                len(by["unknown"]), len(by["ok"]))]
    if by["expired"]:
        lines += ["", "🔴 منتهية"] + [item(r, True) for r in by["expired"]]
    if orange:
        lines += ["", "🟠 تحتاج تجديد"] + [item(r, r.get("band") == "urgent") for r in orange]
    if by["upcoming"]:
        lines += ["", "🟡 قريبة (للعلم — تنفتح تذكرتها تلقائياً عند %d أيام)" % c["lead_days"]]
        lines += [item(r, False, with_ticket=False) for r in by["upcoming"]]
    if by["unknown"]:
        lines += ["", "⚪ ناقصة بيانات (لازم أحد يكمّلها من الداشبورد)"]
        for r in by["unknown"]:
            raw = r.get("end_date_raw") or ""
            lines.append("• %s · %s · %s" % (r.get("permit_type") or "تصريح", unit_label(r, r.get("unit_name")),
                                             ("تاريخ الانتهاء غير مقروء: «%s»" % raw) if raw
                                             else "تاريخ الانتهاء مو مسجّل"))
    if problems:
        lines += ["", "⚠️ مشاكل النظام"]
        for pr in problems:
            lines.append("• فشل فتح تذكرة #%03d: %s — يُعاد المحاولة تلقائياً"
                         % (int(pr.get("tid") or 0), _cut(pr.get("error") or "خطأ غير معروف", 200)))
    if renewed:
        lines += ["", "✅ تجدّد أمس"]
        for rn in renewed:
            lines.append("• %s · %s بواسطة %s" % (rn.get("permit_type") or "تصريح",
                                                 rn.get("unit_name") or "—", rn.get("by") or "—"))
    return chunk(lines), mentions


# ---------------- import: headers ----------------

HEADER_SYNONYMS = {
    "serial": ["م", "#", "serial", "no.", "مسلسل", "تسلسل"],
    "unit_text": ["اسم الوحدة", "الشقة", "الوحدة", "العقار", "unit", "apartment", "listing", "unit name"],
    "permit_no": ["رقم التصريح", "رقم الترخيص", "رقم الرخصة", "الرقم", "permit no", "licence no",
                  "license no", "permit number", "licence number", "license number", "number"],
    "holder": ["اسم المصرح له", "المصرح له", "باسم", "صاحب التصريح", "holder", "issued to"],
    "doc": ["ملف التصريح", "الملف", "المرفق", "file", "document", "attachment"],
    "start_date": ["تاريخ الاصدار", "البدايه", "من", "issue date", "start", "valid from", "start date"],
    "end_date": ["تاريخ الانتهاء", "النهايه", "ينتهي", "الي", "expiry", "end", "valid to",
                 "expiry date", "end date", "expires"],
    "holder_id": ["رقم الهويه", "الهويه", "السجل المدني", "الاقامه", "national id", "iqama",
                  "id number", "رقم السجل المدني", "رقم الاقامه"],
    "district": ["الحي", "district"],
    "street": ["الشارع", "street"],
    "building_no": ["رقم المبني", "المبني", "building no", "building"],
    "unit_no": ["رقم الوحده", "unit no"],
    "ownership_kind": ["نوع العقار", "نوع الملكيه", "ownership", "property type"],
    "permit_type": ["النوع", "نوع التصريح", "type"],
    "issuer": ["جهه الاصدار", "الجهه", "issuer", "authority"],
    "responsible": ["المسؤول", "المتابع", "responsible", "assignee"],
    "renew_notes": ["طريقه التجديد", "ملاحظات التجديد", "renewal"],
    "notes": ["ملاحظات", "notes"],
}

_ID_WORDS = ("هويه", "سجل مدني", "السجل المدني", "اقامه", "national id", "iqama", "id number")


def _norm_ar(s):
    s = dates.clean_text(s).lower()
    s = s.replace("ـ", "")
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ة", "ه"), ("ى", "ي")):
        s = s.replace(a, b)
    return s


def norm_header(h):
    """-> (normalised text, calendar hint 'hijri'|'gregorian'|None). Parenthetical text is
    removed but remembered: «(هجري)» is a calendar hint, not part of the name."""
    s = _norm_ar(h)
    hint = None
    for inner in re.findall(r"\(([^)]*)\)", s):
        if "هجري" in inner or "hijri" in inner:
            hint = "hijri"
        elif "ميلادي" in inner or "gregorian" in inner:
            hint = "gregorian"
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"[_\-:./]+", " ", s)
    return " ".join(s.split()), hint


_SYN = {f: [norm_header(x)[0] for x in xs] for f, xs in HEADER_SYNONYMS.items()}


def map_header(h):
    """-> (field | None, calendar hint). Exact synonym first; then the longest synonym
    whose every word appears in the header (short ones like «من» only ever match exactly)."""
    s, hint = norm_header(h)
    if not s:
        return None, hint
    for field, syns in _SYN.items():
        if s in syns:
            return field, hint
    words = set(s.split())
    best, best_len = None, 0
    for field, syns in _SYN.items():
        for syn in syns:
            if len(syn) < 4:
                continue
            if set(syn.split()) <= words and len(syn) > best_len:
                best, best_len = field, len(syn)
    return best, hint


def is_id_header(h):
    s = norm_header(h)[0]
    return any(w in s for w in _ID_WORDS)


def detect_header_row(rows, scan=10):
    """Index (0-based) of the row with the most synonym hits among the first `scan`."""
    best, best_hits = 0, -1
    for i, row in enumerate(rows[:scan]):
        hits = sum(1 for cell in (row or []) if cell is not None and map_header(cell)[0])
        if hits > best_hits:
            best, best_hits = i, hits
    return best


def guess_date_columns(data_rows, candidate_cols):
    """When no header says «end date»: columns where most filled cells read as dates.
    -> (start_col | None, end_col | None); the column with the LATEST median date is the end."""
    found = []
    for col in candidate_cols:
        vals = [r[col] for r in data_rows if col < len(r) and r[col] not in (None, "")]
        if not vals:
            continue
        isos = [dates.parse_date(v)["iso"] for v in vals]
        good = sorted(x for x in isos if x)
        if len(good) * 2 >= len(vals) and good:
            found.append((good[len(good) // 2], col))
    if not found:
        return None, None
    found.sort()
    end_col = found[-1][1]
    start_col = found[-2][1] if len(found) >= 2 else None
    return start_col, end_col


# ---------------- unit matching (unique-or-nothing) ----------------

# Guide slugs from supabase_export_listings.csv (a stale snapshot). High/medium-confidence
# hints only, and a hint is used ONLY when it resolves to exactly one live listing.
SEED_HINTS = {
    "h8": "h8-vlg", "a5": "a5-mlq", "malqa 1": "1-mlq", "c08": "c08-mj", "e5 mlq": "e5mlq",
    "e15 عرقه": "e15", "العارض a11": "a11", "b20": "qurtuba-b20", "103 narjis": "103-nrjs",
    "11b royal": "ro-11", "jood 12": "jood12", "c2": "c2-nfl",
}


def norm_unit(s):
    s = _norm_ar(s)
    s = re.sub(r"\bouja\b|عوجا", " ", s)
    s = re.sub(r"[|\-_/·.,]+", " ", s)
    return " ".join(s.split())


def slug_unit(s):
    return re.sub(r"[^a-z0-9]+", "-", norm_unit(s)).strip("-")


def _compact(s):
    return re.sub(r"[^a-z0-9]+", "", norm_unit(s))


def hint_for(unit_text):
    return SEED_HINTS.get(norm_unit(unit_text))


def match_unit(text, listings, hint=None):
    """-> (listing_id | None, how, candidate_ids). how ∈ exact | slug | hint | contains | ''.

    Order: exact normalised → exact slug → the hint (if it resolves to ONE listing) →
    a UNIQUE whole-word contains-match. Two candidates at any step is no match."""
    active = [l for l in (listings or []) if l.get("active", True)]
    t = norm_unit(text)
    if not t:
        return None, "", []

    def names(l):
        return [n for n in (l.get("internal_name"), l.get("public_name")) if str(n or "").strip()]

    def pick(pred):
        ids = []
        for l in active:
            if any(pred(n) for n in names(l)) and l["id"] not in ids:
                ids.append(l["id"])
        return ids

    ids = pick(lambda n: norm_unit(n) == t)
    if len(ids) == 1:
        return ids[0], "exact", ids
    if len(ids) > 1:
        return None, "", ids
    ts = slug_unit(text)
    if ts:
        ids = pick(lambda n: slug_unit(n) == ts)
        if len(ids) == 1:
            return ids[0], "slug", ids
        if len(ids) > 1:
            return None, "", ids
    hint = hint if hint is not None else hint_for(text)
    if hint:
        hc = re.sub(r"[^a-z0-9]+", "", hint)
        ids = pick(lambda n: slug_unit(n) == hint or _compact(n) == hc)
        if len(ids) == 1:
            return ids[0], "hint", ids
    if len(t) >= 2:
        pat = re.compile(r"(^| )" + re.escape(t) + r"( |$)")
        ids = pick(lambda n: bool(pat.search(norm_unit(n))) or
                   (len(norm_unit(n)) >= 2 and re.search(r"(^| )" + re.escape(norm_unit(n)) + r"( |$)", t)))
        if len(ids) == 1:
            return ids[0], "contains", ids
        return None, "", ids
    return None, "", []
