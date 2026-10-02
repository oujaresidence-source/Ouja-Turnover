# -*- coding: utf-8 -*-
"""ops_tidy_rules — the PURE brain of `!ouja-tidy` (no discord import, no I/O).

Everything here takes plain dicts and returns plain dicts, so it is tested
offline against the real 2026-10-02 audit (tests/fixtures/tidy/audit_2026-10-02.json)
and then the Discord layer (ops_tidy.py) only *executes* what this file decided.

Input shape = exactly what `ops_audit.collect(guild)` returns (same keys, same
overwrite rows), so the fixture and the live server go through the same code.

Owner decisions this file encodes (Faisal, 2026-10-02 — see
docs/superpowers/specs/2026-10-02-discord-tidy-design.md):
  1. Nothing is deleted or renamed. Old/closed channels move to «📦 أرشيف N».
  2. The archive is visible to Managment (read-only) + admins + the owner.
  3. One channel per ticket stays (no Forum migration).
  4. ANY ticket-opening room («فتح» / «افتح» / «تكت», the bot's panel channels,
     and the old Ticket Tool panel `rr-tickets`) is never moved and its
     permissions are never touched.
  5. Live channels keep their permissions, EXCEPT the three leaks:
       - overflow categories («RR ٢», «صيانه ٢» …) copy their parent's overwrites
       - «تحصيل الحجوزات المباشرة» is locked (Accounting + Managment + closers)
       - the four price / revenue channels become Managment-only
"""

import re
from datetime import datetime, timezone

# ---------------------------------------------------------------- constants
STALE_DAYS = 60
ARCHIVE_CAP = 50                      # Discord: channels per category
ARCHIVE_PREFIX = "📦 أرشيف"
_AR_DIGITS = "٠١٢٣٤٥٦٧٨٩"
OVERFLOW_SUFFIXES = ("٢", "٣", "٤", "٥", "٦", "٧", "٨")   # same as bot._TK_OVERFLOW_SUFFIXES

PANEL_RE = re.compile(r"(فتح|افتح|تكت)")
CLOSED_RE = re.compile(r"^(مغلق|closed-)")
EXTRA_PANELS = {"rr-tickets"}         # old Ticket Tool panel the bot cannot read

UNTOUCHED_CATEGORIES = {"Managment", "الالتزام"}
ANNOUNCE = {"news", "مرجع"}

# Channels the bot finds BY NAME and pulls back into their category
# (bot.ensure_channel). They are never moved. ops_tidy.py extends this set at
# runtime from the live bot constants so a renamed env var is still respected.
BOT_OWNED_DEFAULT = {
    "pricing-log", "discount-heads-up", "revenue-report", "price-opportunities",
    "last-week-review", "oujact-schedule", "dispatch", "oujact-review",
    "guest-assistant", "knowledge", "escalations", "auto-replies", "musaed-quality",
    "تنسيق-الحفلات", "تحصيل-الملخص", "غرفة-المراقبة", "ouja-studio", "نشرة-الاسبوع",
    "wilt", "فتح-تذكرة-صيانة", "فتح-تذكرة-rr", "فتح-تذكرة-مشتريات", "مطابقة-الأسماء",
    "متابعة-الخروج", "team-calendar", "تسليم-الوحدات", "expenses-alerts", "finance-help",
    "متابعة-التقييمات",
}

# Price / revenue numbers — staff must not see company figures (owner rule 2026-09-20).
MGMT_ONLY = {"revenue-report", "price-opportunities", "pricing-log", "discount-heads-up"}

# Categories the owner approved as fully dead (their panels still stay — rule 4).
DEAD_CATEGORIES = {
    "DUMP", "Property Devolompment", "اداره مشروع الباقات", "Dora Hotels",
    "الماجدية 135", "عمارة النزهه", "COB", "اشتراكات النت", "Airbnb Requests",
    "🎬 تجربة الخروج", "Finance",
}

DIRECTPAY_CATEGORY = "تحصيل الحجوزات المباشرة"

# «رفع التقييم» (2026-10-03): its rooms are never archived, locked or renamed here — the review
# system itself deletes a room 7 days after it closes (owner ruling R7), after saving it.
REVIEW_CATEGORY = "طلبات التقييم"
REVIEW_TOPIC = "ouja-rv:"


def is_review_room(ch):
    cat = ch.get("category") or ""
    return (str(ch.get("topic") or "").startswith(REVIEW_TOPIC)
            or norm(cat) == norm(REVIEW_CATEGORY)
            or overflow_parent(cat, (REVIEW_CATEGORY,)) is not None)
TICKET_PARENTS = ("RR", "صيانه", "مشتريات", DIRECTPAY_CATEGORY)

MGMT_ROLE = "Managment"
DIRECTPAY_ROLES = ("Accounting", "Managment")


# ------------------------------------------------------------ small helpers
def norm(s):
    """Same normalisation as bot._tk_cat_norm (ة == ه, case/space-insensitive)."""
    return str(s or "").strip().lower().replace("ة", "ه")


def ar_num(n):
    return "".join(_AR_DIGITS[int(d)] for d in str(int(n)))


def archive_name(i):
    return f"{ARCHIVE_PREFIX} {ar_num(i)}"


def is_archive_category(name):
    return str(name or "").startswith(ARCHIVE_PREFIX)


def overflow_parent(cat_name, parents=TICKET_PARENTS):
    """'RR ٢' -> 'RR'; 'صيانه ٢' -> 'صيانه'; anything else -> None."""
    n = norm(cat_name)
    for p in parents:
        for suf in OVERFLOW_SUFFIXES:
            if n == norm(f"{p} {suf}"):
                return p
    return None


def _view_flag(row):
    """True allow / False deny / None inherit, for the view permission.
    discord.py iterates the flag as 'read_messages' (alias of view_channel)."""
    allow, deny = set(row.get("allow") or []), set(row.get("deny") or [])
    if allow & {"read_messages", "view_channel"}:
        return True
    if deny & {"read_messages", "view_channel"}:
        return False
    return None


def everyone_can_view(ch):
    """Channel-level answer used by the audit: no explicit @everyone view deny."""
    for row in ch.get("overwrites") or []:
        if row.get("target") == "@everyone":
            v = _view_flag(row)
            return True if v is None else v
    return True


def view_roles(ch):
    return sorted(r["target"] for r in (ch.get("overwrites") or [])
                  if r.get("kind") == "role" and r.get("target") != "@everyone"
                  and _view_flag(r) is True)


def age_days(ch, now):
    t = ch.get("last_message_at")
    if not t:
        return None
    dt = datetime.fromisoformat(t)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt).days


def is_panel(name, panel_names=()):
    return bool(PANEL_RE.search(name or "")) or name in EXTRA_PANELS or name in set(panel_names)


# ------------------------------------------------------------- classification
def classify_channel(ch, now, bot_owned=BOT_OWNED_DEFAULT, panel_names=()):
    """-> (decision, reason, action)

    decision ∈ {"keep", "restrict", "archive"}
    action   ∈ {None, "archive", "mgmt_only", "sync_to_category"}
    First matching rule wins; the ORDER is the contract (tests pin it).
    """
    name = ch.get("name") or ""
    cat = ch.get("category") or ""
    if is_panel(name, panel_names):
        return "keep", "روم فتح تذاكر — ما نلمسه", None
    if is_review_room(ch):
        return "keep", "غرفة رفع تقييم — نظامها يحذفها بعد ٧ أيام من القفل", None
    if name in ANNOUNCE:
        return "keep", "إعلانات للكل", None
    if cat in UNTOUCHED_CATEGORIES:
        return "keep", "قسم خاص ومقفل أصلاً", None
    if is_archive_category(cat):
        return "keep", "في الأرشيف من قبل", None
    if name in bot_owned:
        if name in MGMT_ONLY:
            return "restrict", "أرقام أسعار/إيراد — للمدراء بس", "mgmt_only"
        if overflow_parent(cat) or norm(cat) == norm(DIRECTPAY_CATEGORY):
            return "restrict", "يتبع صلاحيات قسمه بعد القفل", "sync_to_category"
        return "keep", "قناة يديرها البوت — تبقى مكانها", None
    if CLOSED_RE.match(name):
        return "archive", "تذكرة مقفلة", "archive"
    if cat in DEAD_CATEGORIES:
        return "archive", "القسم كله ميت", "archive"
    if not ch.get("accessible", True):
        return "archive", "البوت ما يقدر يقراها — أرشيف (ترجع بأمر واحد)", "archive"
    a = age_days(ch, now)
    if a is None:
        return "archive", "ما انكتب فيها شي أبد", "archive"
    if a > STALE_DAYS:
        return "archive", f"ما فيها رسالة من {a} يوم", "archive"
    if overflow_parent(cat) or norm(cat) == norm(DIRECTPAY_CATEGORY):
        return "restrict", "ثغرة: يتبع صلاحيات قسمه بعد القفل", "sync_to_category"
    return "keep", "شغّالة — صلاحياتها مثل ما هي", None


def category_fixes(categories):
    """Category-level permission fixes (the leaks), from the audit's category rows.
    -> [{"kind": "copy_parent", "category", "parent"} | {"kind": "lock_directpay", "category"}]
    Every overflow category copies its parent EVEN WHEN EMPTY, so the next spill is safe."""
    names = {c["name"] for c in categories}
    out = []
    for c in sorted(categories, key=lambda c: (c.get("position") is None, c.get("position") or 0)):
        parent = overflow_parent(c["name"])
        if parent and any(norm(n) == norm(parent) for n in names):
            real_parent = next(n for n in names if norm(n) == norm(parent))
            prow = next(x for x in categories if x["name"] == real_parent)
            out.append({"kind": "copy_parent", "category": c["name"], "parent": real_parent,
                        "parent_view_roles": view_roles(prow),
                        "parent_view_user_ids": sorted(r["target_id"] for r in (prow.get("overwrites") or [])
                                                       if r.get("kind") == "member" and _view_flag(r) is True)})
        elif norm(c["name"]) == norm(DIRECTPAY_CATEGORY):
            out.append({"kind": "lock_directpay", "category": c["name"]})
    return out


def assign_archive_slots(n_moves, existing_counts=None, cap=ARCHIVE_CAP):
    """Fill «📦 أرشيف ١» first, then ٢, ٣ … ; existing_counts = {index: channels already there}.
    -> list of archive indexes (1-based), one per move, in order."""
    existing_counts = dict(existing_counts or {})
    out, idx = [], 1
    for _ in range(n_moves):
        while existing_counts.get(idx, 0) >= cap:
            idx += 1
        out.append(idx)
        existing_counts[idx] = existing_counts.get(idx, 0) + 1
    return out


def build_plan(inv, now=None, bot_owned=BOT_OWNED_DEFAULT, panel_names=()):
    """The whole decision, as data. ops_tidy.py executes it verbatim."""
    now = now or datetime.now(timezone.utc)
    cats = inv.get("categories") or []
    existing = {}
    for c in cats:
        if is_archive_category(c["name"]):
            m = re.search(r"(\d+|[٠-٩]+)$", c["name"])
            if m:
                digits = m.group(1).translate(str.maketrans(_AR_DIGITS, "0123456789"))
                existing[int(digits)] = c.get("channel_count", 0)

    pos_of = {c["name"]: c.get("position") or 0 for c in cats}
    rows = []
    for ch in inv.get("channels") or []:
        decision, reason, action = classify_channel(ch, now, bot_owned, panel_names)
        rows.append({
            "id": str(ch.get("id")), "name": ch.get("name"), "category": ch.get("category"),
            "category_id": ch.get("category_id"), "position": ch.get("position"),
            "type": ch.get("type"), "everyone": everyone_can_view(ch), "roles": view_roles(ch),
            "age": age_days(ch, now), "decision": decision, "reason": reason, "action": action,
        })
    # stable, readable order: by old category position, then channel position
    rows.sort(key=lambda r: (pos_of.get(r["category"] or "", -1), r["position"] or 0))

    moves = [r for r in rows if r["action"] == "archive"]
    for r, slot in zip(moves, assign_archive_slots(len(moves), existing)):
        r["archive_index"] = slot
        r["archive_category"] = archive_name(slot)

    counts = {"keep": 0, "restrict": 0, "archive": 0}
    for r in rows:
        counts[r["decision"]] += 1
    return {
        "version": 1,
        "generated_at": now.isoformat(),
        "guild": (inv.get("guild") or {}).get("id"),
        "counts": counts,
        "archive_categories": sorted({r["archive_category"] for r in moves}),
        "category_fixes": category_fixes(cats),
        "channels": rows,
    }


# ------------------------------------------------------- who-loses-what report
def predict_after(member, row, fixes_by_cat, directpay_extra_ids=()):
    """Will `member` still see channel `row` after the plan runs?
    member = {"id", "name", "roles": [role names], "is_admin", "is_owner"}
    Returns True/False, or None when the plan does not touch this channel (unchanged)."""
    if member.get("is_admin") or member.get("is_owner"):
        return True
    roles = set(member.get("roles") or [])
    act = row.get("action")
    if act == "archive":
        return MGMT_ROLE in roles
    if act == "mgmt_only":
        return MGMT_ROLE in roles
    if act == "sync_to_category":
        fx = fixes_by_cat.get(row.get("category"))
        if fx and fx["kind"] == "lock_directpay":
            return bool(roles & set(DIRECTPAY_ROLES)) or str(member.get("id")) in {str(i) for i in directpay_extra_ids}
        if fx and fx["kind"] == "copy_parent":
            return (bool(roles & set(fx.get("parent_view_roles") or []))
                    or str(member.get("id")) in set(fx.get("parent_view_user_ids") or []))
    return None


def people_report(plan, members, visible_before, directpay_extra_ids=()):
    """members: list of member dicts (see predict_after).
    visible_before: {member_id: set(channel_ids the member can view NOW)} — computed live
    by ops_tidy.py with channel.permissions_for(member).view_channel.
    -> [{"member", "loses_live": [names], "loses_archive": n, "keeps": n}] sorted worst-first."""
    fixes = {f["category"]: f for f in plan.get("category_fixes") or []}
    by_id = {r["id"]: r for r in plan["channels"]}
    out = []
    for m in members:
        seen = visible_before.get(str(m["id"]), set())
        live, arch, keep = [], 0, 0
        for cid in seen:
            r = by_id.get(str(cid))
            if r is None:
                continue
            after = predict_after(m, r, fixes, directpay_extra_ids)
            if after is False:
                if r["action"] == "archive":
                    arch += 1
                else:
                    live.append(r["name"])
            else:
                keep += 1
        out.append({"member": m.get("name"), "id": str(m["id"]),
                    "loses_live": sorted(live), "loses_archive": arch, "keeps": keep})
    out.sort(key=lambda x: (-len(x["loses_live"]), -x["loses_archive"], x["member"] or ""))
    return out


# ----------------------------------------------------------- snapshot / undo
def snapshot_row(ch_state):
    """Normalise one live channel's restorable state (built by ops_tidy.py):
    {"id", "name", "category_id", "position", "synced", "overwrites": [
        {"type": "role"|"member", "id", "allow": int, "deny": int}]}"""
    return {
        "id": str(ch_state["id"]),
        "name": ch_state.get("name"),
        "category_id": str(ch_state.get("category_id") or ""),
        "position": ch_state.get("position"),
        "synced": bool(ch_state.get("synced")),
        "overwrites": sorted(
            [{"type": o["type"], "id": str(o["id"]), "allow": int(o["allow"]), "deny": int(o["deny"])}
             for o in (ch_state.get("overwrites") or [])],
            key=lambda o: (o["type"], o["id"])),
    }


def undo_order(snapshot_rows):
    """Restore in reverse execution order, so positions land where they were."""
    return list(reversed(snapshot_rows))


def summary_ar(plan):
    c = plan["counts"]
    lines = [
        f"📦 للأرشيف: **{c['archive']}** قناة ← {len(plan['archive_categories'])} قسم أرشيف",
        f"🔒 قفل ثغرات: **{c['restrict']}** قناة",
        f"🟢 تبقى مثل ما هي: **{c['keep']}** قناة",
    ]
    for f in plan.get("category_fixes") or []:
        if f["kind"] == "copy_parent":
            lines.append(f"• قسم «{f['category']}» ياخذ صلاحيات «{f['parent']}»")
        else:
            lines.append(f"• قسم «{f['category']}» ينقفل: المالية + المدراء + اللي يقفلون التحصيل")
    return "\n".join(lines)
