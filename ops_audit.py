"""ops_audit — READ-ONLY Discord server inventory for Ouja Residence.

Why this exists
---------------
The Discord server has grown to hundreds of channels across ~15 categories and
the ops team is drowning. Before anybody restructures anything, the owner needs
hard numbers: how close the server is to Discord's hard caps, which channels are
dead, and which channels every single member can see. Screenshots don't answer
that. This module does.

Contract with the rest of the bot
---------------------------------
* Self-contained. `bot.py` only does `import ops_audit` + `ops_audit.setup(bot)`.
* READ-ONLY: it never creates, edits, moves, deletes, or re-permissions any
  Discord object. The only writes are its own status message + two attachments.
* It can never take the bot down: the whole handler is wrapped, and any failure
  is reported back into the status message with the real exception type + text.
* Rate-limit polite: a ~1s breather every 25 channels, every history read capped.

Trigger:  !ouja-audit          (normal)
          !ouja-audit deep     (also counts messages in the last 30 days)

Note on the prefix: the bot's command prefix is "!ouja " (with a space), so
"!ouja-audit" is NOT a prefix command and can't collide with `process_commands`.
"""

import asyncio
import csv
import io
import json
import os
import traceback
from datetime import datetime, timedelta, timezone

import discord

# ---------------------------------------------------------------- constants
TRIGGER = "!ouja-audit"

MAX_CHANNELS        = 500     # Discord: channels per guild
MAX_CATEGORIES      = 50      # Discord: categories per guild
MAX_CHANNELS_PER_CAT = 50     # Discord: channels inside one category
MAX_ACTIVE_THREADS  = 1000    # Discord: active (non-archived) threads per guild

STALE_DAYS      = 60          # no message in 60 days (or ever) => dead channel
NEAR_CAP_RATIO  = 0.80        # warn once the guild passes 80% of the channel cap

SLEEP_EVERY     = 25          # channels between rate-limit breathers
SLEEP_SECONDS   = 1.0
PROGRESS_EVERY  = 50          # channels between status-message edits

DEEP_WINDOW_DAYS = 30         # `deep` mode: window for the message count
DEEP_MESSAGE_CAP = 200        # `deep` mode: hard cap on messages read per channel

TOPIC_MAX       = 400         # topics are truncated to keep the files readable
SUMMARY_MAX     = 1900        # Discord message limit is 2000; leave headroom


# ------------------------------------------------------------ small helpers
def _iso(dt):
    """UTC ISO-8601 string, or None."""
    if not dt:
        return None
    try:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return str(dt)


def _type_name(obj):
    """'text' / 'voice' / 'forum' / 'category' … for real and fake channels."""
    t = getattr(obj, "type", None)
    if t is None:
        return "unknown"
    return getattr(t, "name", None) or str(t)


def _is_category(ch):
    return _type_name(ch) == "category"


def _is_stale(last_message_at, now, days=STALE_DAYS):
    """A channel is dead if its last message is older than `days` — or if it
    never had one at all. `None` in means stale."""
    if last_message_at is None:
        return True
    dt = last_message_at
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt) > timedelta(days=days)


def _overwrite_target_kind(target):
    """Roles expose .mentionable; members don't. Works for discord.py objects
    and for the duck-typed fakes used in tests."""
    return "role" if hasattr(target, "mentionable") else "member"


def _overwrite_rows(overwrites):
    """[{target, target_id, kind, allow[], deny[], hides_channel, grants_view}]

    `discord.PermissionOverwrite` iterates as (permission_name, True/False/None)
    where True = explicitly allowed, False = explicitly denied, None = inherit.
    """
    rows = []
    for target, ov in (overwrites or {}).items():
        allow, deny = [], []
        try:
            for name, value in ov:
                if value is True:
                    allow.append(name)
                elif value is False:
                    deny.append(name)
        except Exception:
            pass
        rows.append({
            "target": getattr(target, "name", str(target)),
            "target_id": str(getattr(target, "id", "")),
            "kind": _overwrite_target_kind(target),
            "allow": sorted(allow),
            "deny": sorted(deny),
            "hides_channel": "view_channel" in deny,
            "grants_view": "view_channel" in allow,
        })
    rows.sort(key=lambda r: (r["kind"], r["target"]))
    return rows


def _everyone_denied_view(ch, default_role):
    """True when @everyone has view_channel explicitly denied on this object."""
    try:
        ov = (ch.overwrites or {}).get(default_role)
    except Exception:
        return False
    if ov is None:
        return False
    return getattr(ov, "view_channel", None) is False


def _is_allowed(message):
    """Owner by id (OWNER_DISCORD_ID), else any guild administrator."""
    owner_id = (os.environ.get("OWNER_DISCORD_ID") or "").strip()
    if owner_id and str(getattr(message.author, "id", "")) == owner_id:
        return True
    perms = getattr(message.author, "guild_permissions", None)
    return bool(perms is not None and getattr(perms, "administrator", False))


# ------------------------------------------------------------- the inventory
async def _last_message(ch):
    """(last_message_at, last_message_by, accessible, error).

    Forum channels have no `history()`; locked channels raise Forbidden. Neither
    is a failure — we record it so the owner can see WHY a row is blank.
    """
    if not hasattr(ch, "history"):
        return None, None, True, "no_history_api"
    try:
        async for msg in ch.history(limit=1):
            author = getattr(msg, "author", None)
            return (getattr(msg, "created_at", None),
                    str(author) if author is not None else None,
                    True, None)
        return None, None, True, None          # accessible, simply empty
    except discord.Forbidden:
        return None, None, False, "forbidden"
    except Exception as e:
        return None, None, False, type(e).__name__


async def _deep_count(ch, now):
    """Messages in the last DEEP_WINDOW_DAYS, capped at DEEP_MESSAGE_CAP."""
    if not hasattr(ch, "history"):
        return None
    after = now - timedelta(days=DEEP_WINDOW_DAYS)
    try:
        n = 0
        async for _ in ch.history(limit=DEEP_MESSAGE_CAP, after=after):
            n += 1
        return n
    except Exception:
        return None


def _visibility(ch, members):
    """(can_see, of_members) — non-bot members whose permissions_for() grants
    view_channel. Returns (None, None) when the members intent is off; we do
    NOT guess a number the gateway never gave us."""
    if not members:
        return None, None
    seen = 0
    for m in members:
        try:
            if ch.permissions_for(m).view_channel:
                seen += 1
        except Exception:
            pass
    return seen, len(members)


async def collect(guild, deep=False, progress=None):
    """Walk the guild and return the full inventory dict. Read-only."""
    now = datetime.now(timezone.utc)

    all_channels = list(getattr(guild, "channels", []) or [])
    categories = [c for c in all_channels if _is_category(c)]
    channels   = [c for c in all_channels if not _is_category(c)]

    default_role = getattr(guild, "default_role", None)

    # Members are only available when the members intent is on AND the cache is
    # warm. Anything else => None, never a guess.
    members = [m for m in (getattr(guild, "members", []) or [])
               if not getattr(m, "bot", False)]

    # --- active threads (one API call for the whole guild)
    threads, threads_error = [], None
    try:
        threads = list(await guild.active_threads() or [])
    except Exception as e:
        threads_error = f"{type(e).__name__}: {e}"
    threads_by_parent = {}
    for th in threads:
        pid = str(getattr(th, "parent_id", "") or "")
        threads_by_parent[pid] = threads_by_parent.get(pid, 0) + 1

    # --- roles
    roles = []
    for r in (getattr(guild, "roles", []) or []):
        member_count = None
        if members or getattr(r, "members", None):
            try:
                member_count = len([m for m in r.members])
            except Exception:
                member_count = None
        perms = getattr(r, "permissions", None)
        roles.append({
            "name": getattr(r, "name", "?"),
            "id": str(getattr(r, "id", "")),
            "member_count": member_count,
            "position": getattr(r, "position", None),
            "is_admin": bool(getattr(perms, "administrator", False)) if perms is not None else None,
            "mentionable": bool(getattr(r, "mentionable", False)),
        })
    roles.sort(key=lambda r: (r["position"] is None, -(r["position"] or 0)))

    # --- categories
    cat_rows = []
    for cat in categories:
        kids = [c for c in channels
                if str(getattr(getattr(c, "category", None), "id", "")) == str(getattr(cat, "id", ""))]
        cat_rows.append({
            "name": getattr(cat, "name", "?"),
            "id": str(getattr(cat, "id", "")),
            "position": getattr(cat, "position", None),
            "channel_count": len(kids),
            "at_cap": len(kids) >= MAX_CHANNELS_PER_CAT,
            "everyone_denied_view": _everyone_denied_view(cat, default_role),
            "overwrites": _overwrite_rows(getattr(cat, "overwrites", {})),
        })
    cat_rows.sort(key=lambda c: (c["position"] is None, c["position"] or 0))

    # --- channels
    total = len(channels)
    ch_rows = []
    for idx, ch in enumerate(channels, start=1):
        last_at, last_by, accessible, err = await _last_message(ch)
        can_see, of_members = _visibility(ch, members)
        topic = getattr(ch, "topic", None) or ""
        row = {
            "name": getattr(ch, "name", "?"),
            "id": str(getattr(ch, "id", "")),
            "type": _type_name(ch),
            "category": getattr(getattr(ch, "category", None), "name", None),
            "category_id": str(getattr(getattr(ch, "category", None), "id", "") or ""),
            "position": getattr(ch, "position", None),
            "topic": topic[:TOPIC_MAX],
            "created_at": _iso(getattr(ch, "created_at", None)),
            "last_message_at": _iso(last_at),
            "last_message_by": last_by,
            "accessible": accessible,
            "read_note": err,
            "stale": _is_stale(last_at, now),
            "active_threads": threads_by_parent.get(str(getattr(ch, "id", "")), 0),
            "restricted": _everyone_denied_view(ch, default_role),
            "can_see": can_see,
            "of_members": of_members,
            "overwrites": _overwrite_rows(getattr(ch, "overwrites", {})),
        }
        if deep:
            row["messages_30d"] = await _deep_count(ch, now)
            row["messages_30d_capped_at"] = DEEP_MESSAGE_CAP
        ch_rows.append(row)

        if idx % SLEEP_EVERY == 0:
            await asyncio.sleep(SLEEP_SECONDS)
        else:
            await asyncio.sleep(0)            # never hog the event loop
        if progress and (idx % PROGRESS_EVERY == 0):
            try:
                await progress(idx, total)
            except Exception:
                pass

    inv = {
        "guild": {
            "name": getattr(guild, "name", "?"),
            "id": str(getattr(guild, "id", "")),
            "generated_at": _iso(now),
            "member_count": getattr(guild, "member_count", None),
        },
        "mode": "deep" if deep else "normal",
        "members_intent_available": bool(members),
        "limits": {
            "channels": {"used": len(channels), "max": MAX_CHANNELS},
            "channels_including_categories": {"used": len(all_channels), "max": MAX_CHANNELS},
            "categories": {"used": len(categories), "max": MAX_CATEGORIES},
            "active_threads": {"used": None if threads_error else len(threads),
                               "max": MAX_ACTIVE_THREADS,
                               "error": threads_error},
        },
        "roles": roles,
        "categories": cat_rows,
        "channels": ch_rows,
    }
    inv["warnings"] = build_warnings(inv)
    return inv


# -------------------------------------------------------------- derived data
def build_warnings(inv):
    """Arabic, owner-readable. Pure function of the inventory."""
    out = []
    ch_used = inv["limits"]["channels"]["used"]
    if ch_used > MAX_CHANNELS * NEAR_CAP_RATIO:
        pct = round(ch_used * 100.0 / MAX_CHANNELS)
        out.append(f"⚠️ عدد القنوات {ch_used} من {MAX_CHANNELS} ({pct}%) — قريب من حد ديسكورد.")

    cats_used = inv["limits"]["categories"]["used"]
    if cats_used > MAX_CATEGORIES * NEAR_CAP_RATIO:
        out.append(f"⚠️ عدد التصنيفات {cats_used} من {MAX_CATEGORIES} — قريب من الحد.")

    for c in inv["categories"]:
        if c["at_cap"]:
            out.append(f"🚫 التصنيف «{c['name']}» ممتلئ ({c['channel_count']}/{MAX_CHANNELS_PER_CAT}) "
                       f"— ما يقبل قناة جديدة.")

    stale = [c for c in inv["channels"] if c["stale"]]
    if stale:
        out.append(f"🕸 {len(stale)} قناة ميتة (بدون رسائل من أكثر من {STALE_DAYS} يوم أو ما فيها ولا رسالة).")

    total_members = None
    for c in inv["channels"]:
        if c.get("of_members"):
            total_members = c["of_members"]
            break
    if total_members:
        everyone = [c for c in inv["channels"] if c.get("can_see") == total_members]
        out.append(f"🌍 {len(everyone)} قناة يشوفها كل الأعضاء ({total_members} عضو).")
    else:
        open_ch = [c for c in inv["channels"] if not c["restricted"]]
        out.append("ℹ️ صلاحية «Server Members Intent» مغلقة، فما قدرنا نحسب عدد من يشوف كل قناة بالضبط. "
                   f"تقديريًا {len(open_ch)} قناة مفتوحة لـ @everyone (بدون منع صريح).")

    blocked = [c for c in inv["channels"] if not c["accessible"]]
    if blocked:
        out.append(f"🔒 {len(blocked)} قناة ما قدر البوت يقرأ رسائلها (صلاحيات) — تظهر بدون تاريخ آخر رسالة.")

    if inv["limits"]["active_threads"]["error"]:
        out.append("⚠️ ما قدرنا نجيب الثريدات النشطة: " + str(inv["limits"]["active_threads"]["error"]))
    return out


CSV_COLUMNS = [
    "category", "channel", "id", "type", "position", "stale", "restricted",
    "last_message_at", "last_message_by", "accessible", "read_note",
    "active_threads", "can_see", "of_members", "created_at",
    "hides_from", "grants_view_to", "overwrite_count", "messages_30d", "topic",
]


def build_csv(inv):
    """utf-8-sig so Arabic opens correctly in Excel (no BOM => mojibake)."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_COLUMNS)
    for c in inv["channels"]:
        ov = c.get("overwrites") or []
        w.writerow([
            c.get("category") or "",
            c.get("name") or "",
            c.get("id") or "",
            c.get("type") or "",
            "" if c.get("position") is None else c["position"],
            "yes" if c.get("stale") else "no",
            "yes" if c.get("restricted") else "no",
            c.get("last_message_at") or "",
            c.get("last_message_by") or "",
            "yes" if c.get("accessible") else "no",
            c.get("read_note") or "",
            c.get("active_threads", 0),
            "" if c.get("can_see") is None else c["can_see"],
            "" if c.get("of_members") is None else c["of_members"],
            c.get("created_at") or "",
            " | ".join(o["target"] for o in ov if o["hides_channel"]),
            " | ".join(o["target"] for o in ov if o["grants_view"]),
            len(ov),
            "" if c.get("messages_30d") is None else c["messages_30d"],
            (c.get("topic") or "").replace("\r", " ").replace("\n", " "),
        ])
    return buf.getvalue().encode("utf-8-sig")


def build_summary(inv):
    """The Arabic message the owner actually reads."""
    g = inv["guild"]
    lim = inv["limits"]
    ch = lim["channels"]
    cats = lim["categories"]
    th = lim["active_threads"]
    stale = sum(1 for c in inv["channels"] if c["stale"])
    blocked = sum(1 for c in inv["channels"] if not c["accessible"])
    capped = sum(1 for c in inv["categories"] if c["at_cap"])
    pct = round(ch["used"] * 100.0 / MAX_CHANNELS)

    lines = [
        f"✅ **جرد سيرفر ديسكورد — {g['name']}**",
        f"🕒 {(g['generated_at'] or '')[:16]} UTC · الوضع: "
        + ("مفصّل (deep)" if inv["mode"] == "deep" else "سريع"),
        "",
        f"📦 القنوات: **{ch['used']}** من {ch['max']}  ({pct}%)",
        f"🗂 التصنيفات: **{cats['used']}** من {cats['max']}"
        + (f" · منها {capped} ممتلئ" if capped else ""),
        f"🧵 الثريدات النشطة: **{'؟' if th['used'] is None else th['used']}** من {th['max']}",
        f"👥 الأدوار: **{len(inv['roles'])}**",
        f"🕸 قنوات ميتة (+{STALE_DAYS} يوم بدون رسالة): **{stale}**",
    ]

    total_members = None
    for c in inv["channels"]:
        if c.get("of_members"):
            total_members = c["of_members"]
            break
    if total_members:
        everyone = sum(1 for c in inv["channels"] if c.get("can_see") == total_members)
        lines.append(f"🌍 قنوات يشوفها كل الأعضاء: **{everyone}** من {ch['used']}")
    else:
        open_ch = sum(1 for c in inv["channels"] if not c["restricted"])
        lines.append(f"🌍 قنوات مفتوحة لـ @everyone: **{open_ch}** (تقديري — صلاحية الأعضاء مغلقة)")
    if blocked:
        lines.append(f"🔒 قنوات ما قدر البوت يقرأها: **{blocked}**")

    if inv["warnings"]:
        lines += ["", "**تنبيهات:**"] + ["• " + w for w in inv["warnings"][:8]]
        if len(inv["warnings"]) > 8:
            lines.append(f"• … و{len(inv['warnings']) - 8} تنبيه إضافي داخل ملف JSON.")

    lines += ["", "📎 التفاصيل الكاملة في الملفين المرفقين (JSON للتحليل، CSV للإكسل).",
              "🔒 هذا الأمر **قراءة فقط** — ما عدّل ولا حذف ولا حرّك أي شيء."]

    text = "\n".join(lines)
    if len(text) > SUMMARY_MAX:
        text = text[:SUMMARY_MAX] + "\n… (اختصرنا الرسالة — كل التفاصيل في المرفقات)"
    return text


def build_files(inv, day=None):
    """The two attachments: JSON (analysis) + CSV (Excel)."""
    day = day or (inv["guild"]["generated_at"] or "")[:10] or "today"
    payload = json.dumps(inv, ensure_ascii=False, indent=2).encode("utf-8")
    return [
        discord.File(io.BytesIO(payload), filename=f"ouja_audit_{day}.json"),
        discord.File(io.BytesIO(build_csv(inv)), filename=f"ouja_audit_{day}.csv"),
    ]


# ------------------------------------------------------------------ the wire
async def handle_message(message):
    """The listener body. Never raises — failures land in the status message."""
    if getattr(message.author, "bot", False):
        return
    parts = (message.content or "").strip().split()
    if not parts or parts[0].lower() != TRIGGER:
        return
    deep = len(parts) > 1 and parts[1].lower() in ("deep", "عميق", "مفصل", "مفصّل")

    if message.guild is None:
        try:
            await message.reply("هذا الأمر يشتغل داخل السيرفر فقط.", mention_author=False)
        except Exception:
            pass
        return

    if not _is_allowed(message):
        try:
            await message.reply("🔒 هذا الأمر للمالك أو الأدمن فقط.", mention_author=False)
        except Exception:
            pass
        return

    status = None
    try:
        status = await message.reply(
            "⏳ أبدأ جرد السيرفر… (قراءة فقط، ما راح أعدّل أي شيء)"
            + ("\nالوضع مفصّل — راح يأخذ وقت أطول." if deep else ""),
            mention_author=False)
    except Exception:
        status = None

    async def progress(done, total):
        if status is None:
            return
        try:
            await status.edit(content=f"⏳ {done}/{total} قناة… (قراءة فقط)")
        except Exception:
            pass

    try:
        inv = await collect(message.guild, deep=deep, progress=progress)
        summary = build_summary(inv)
        if status is not None:
            await status.edit(content=summary)
        else:
            await message.channel.send(summary)
        await message.channel.send(files=build_files(inv))
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        print("ops_audit error:", err)
        traceback.print_exc()
        note = ("❌ الجرد وقف بخطأ. ابعث هذا السطر لفيصل:\n```\n" + err[:1500] + "\n```")
        try:
            if status is not None:
                await status.edit(content=note)
            else:
                await message.channel.send(note)
        except Exception:
            pass


# =====================================================================
# TEMPORARY DIAGNOSTIC — !ouja-msgdump                    (added 2026-07-27)
# ---------------------------------------------------------------------
# WHY: we cannot tell, from the outside, which outgoing guest messages went
# through Hostaway and which did not, nor which human sent them. The code we
# have today reads only `body` / `isIncoming` / `date` and throws the rest of
# the message object away. This dumps EVERY key Hostaway returns so the owner
# can see the fields we ignore — `sentUsingHostaway` above all.
#
# READ-ONLY: two GET endpoints, nothing written to Hostaway, nothing written
# to Discord except its own reply + one JSON attachment.
#
# TO REMOVE: delete this whole block (down to "END TEMPORARY") and drop
# `TRIGGER_MSGDUMP` from the listener in `setup()`. Nothing else depends on it.
# =====================================================================
TRIGGER_MSGDUMP  = "!ouja-msgdump"
MSGDUMP_CONVOS   = 10      # how many conversations to pull (owner-specified)
MSGDUMP_MAX_CHARS = 7_000_000   # safety cap on the attachment (Discord: 8 MB)

_HOST = None   # bot.py's LIVE module object — this file must NEVER `import bot`

# Redaction. The point of the dump is METADATA, so we blank content and guest
# identity and keep every other key exactly as Hostaway returned it. The key
# NAME always survives — you always see that a field exists and how long its
# value was, so nothing hides silently.
_MD_TEXT_KEYS = ("body", "bodyplain", "subject", "preview", "snippet",
                 "lastmessage", "text", "message")
_MD_PII_SUBSTR = ("guestname", "firstname", "lastname", "fullname",
                  "phone", "mobile", "whatsapp", "email",
                  "picture", "avatar", "recipientname")


def _md_should_redact(key):
    k = str(key).lower()
    if k in _MD_TEXT_KEYS or "body" in k:
        return True
    return any(s in k for s in _MD_PII_SUBSTR)


def _md_redact_value(value):
    """Same '<redacted: N chars>' shape for everything we blank."""
    if value is None:
        return None
    if isinstance(value, str):
        return f"<redacted: {len(value)} chars>"
    return f"<redacted: {len(str(value))} chars, {type(value).__name__}>"


def _md_redact(obj, _path="", _hit=None):
    """Deep copy with content + guest identity blanked. Returns (obj, [paths])."""
    hit = [] if _hit is None else _hit
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            here = f"{_path}.{k}" if _path else str(k)
            if _md_should_redact(k):
                out[k] = _md_redact_value(v)
                hit.append(here)
            else:
                out[k], _ = _md_redact(v, here, hit)
        return out, hit
    if isinstance(obj, list):
        out = []
        for i, v in enumerate(obj):
            r, _ = _md_redact(v, f"{_path}[{i}]", hit)
            out.append(r)
        return out, hit
    return obj, hit


def _md_is_incoming(msg):
    return bool(msg.get("isIncoming"))


def _md_from_hostaway(msg):
    """True / False / None(unknown) from `sentUsingHostaway`.

    None means the key was absent or null — a THIRD shape, not a synonym for
    False. Collapsing them would erase the very thing we are looking for.
    """
    if "sentUsingHostaway" not in msg:
        return None
    v = msg.get("sentUsingHostaway")
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("1", "true", "yes"):
            return True
        if s in ("0", "false", "no", ""):
            return False
        return None
    return bool(v)


def _md_sort_key(msg):
    """Newest-first ordering: Hostaway dates sort fine as plain strings."""
    stamp = ""
    for k in ("date", "insertedOn", "updatedOn"):
        v = msg.get(k)
        if isinstance(v, str) and v:
            stamp = v
            break
    try:
        mid = int(msg.get("id") or 0)
    except (TypeError, ValueError):
        mid = 0
    return (stamp, mid)


_MD_BUCKETS = ("sent_using_hostaway", "not_sent_using_hostaway", "flag_missing")


def _md_pick_shapes(messages):
    """Newest OUTGOING message of each shape. (buckets, outgoing_count)."""
    picked = {b: None for b in _MD_BUCKETS}
    outgoing = [m for m in messages if isinstance(m, dict) and not _md_is_incoming(m)]
    for m in sorted(outgoing, key=_md_sort_key, reverse=True):
        flag = _md_from_hostaway(m)
        bucket = ("sent_using_hostaway" if flag is True else
                  "not_sent_using_hostaway" if flag is False else "flag_missing")
        if picked[bucket] is None:
            picked[bucket] = m
    return picked, len(outgoing)


def _md_keys(obj):
    return sorted(obj.keys()) if isinstance(obj, dict) else []


def build_msgdump(raw, generated_at=None):
    """Pure builder: raw fetch -> the dict we write to the .json file."""
    convos_out, seen = [], {b: [] for b in _MD_BUCKETS}

    for row in raw.get("conversations") or []:
        convo = row.get("conversation") if isinstance(row.get("conversation"), dict) else {}
        msgs = [m for m in (row.get("messages") or []) if isinstance(m, dict)]
        picked, n_out = _md_pick_shapes(msgs)

        # The conversation object may carry the whole thread inline; that is the
        # same data as the messages section, so we note it instead of repeating it.
        convo_copy = dict(convo)
        for k, v in list(convo_copy.items()):
            if isinstance(v, list) and v and isinstance(v[0], dict) and "isIncoming" in v[0]:
                convo_copy[k] = f"<omitted: {len(v)} embedded message objects — see messages below>"
        convo_red, convo_hits = _md_redact(convo_copy)

        entry = {
            "order_index": row.get("order_index"),
            "conversation_id": row.get("id"),
            "fetch_error": row.get("error"),
            "message_count": len(msgs),
            "outgoing_count": n_out,
            "conversation_object": convo_red,
            "conversation_object_keys": _md_keys(convo),
            "conversation_redacted_paths": sorted(set(convo_hits)),
            "messages": {},
            "missing_shapes": [],
        }
        for bucket in _MD_BUCKETS:
            msg = picked[bucket]
            if msg is None:
                entry["missing_shapes"].append(bucket)
                entry["messages"][bucket] = None
                continue
            red, hits = _md_redact(msg)
            entry["messages"][bucket] = {
                "raw": red,
                "keys": _md_keys(msg),
                "redacted_paths": sorted(set(hits)),
                "sentUsingHostaway_raw": repr(msg.get("sentUsingHostaway", "<key absent>")),
            }
            seen[bucket].append(set(msg.keys()))
        if len(entry["missing_shapes"]) == len(_MD_BUCKETS):
            entry["note"] = "no outgoing messages in this conversation"
        convos_out.append(entry)

    # The whole point: which keys appear on one shape but not the other.
    union = {b: sorted(set().union(*seen[b])) if seen[b] else [] for b in _MD_BUCKETS}
    a, b = set(union["sent_using_hostaway"]), set(union["not_sent_using_hostaway"])
    return {
        "_what_this_is": (
            "TEMPORARY diagnostic dump of Hostaway conversations + their newest "
            "OUTGOING message of each shape. Read-only. Message text, guest names, "
            "phone numbers and e-mails are replaced by '<redacted: N chars>'; every "
            "other key is exactly as Hostaway returned it."
        ),
        "_redaction_rule": {
            "text_keys": list(_MD_TEXT_KEYS),
            "identity_substrings": list(_MD_PII_SUBSTR),
            "note": "a key is blanked if its NAME matches — the name and value length always survive",
        },
        "generated_at": generated_at,
        "conversations_requested": raw.get("requested"),
        "conversations_returned": len(convos_out),
        "conversation_order": "exactly as GET /conversations returned them (order_index 0 = first)",
        "list_endpoint_params": raw.get("params"),
        "list_fetch_error": raw.get("error"),
        "field_comparison": {
            "keys_on_sent_using_hostaway": union["sent_using_hostaway"],
            "keys_on_not_sent_using_hostaway": union["not_sent_using_hostaway"],
            "keys_on_flag_missing": union["flag_missing"],
            "only_when_sent_using_hostaway": sorted(a - b),
            "only_when_not_sent_using_hostaway": sorted(b - a),
            "on_both": sorted(a & b),
        },
        "shape_counts": {bucket: sum(1 for c in convos_out
                                     if (c["messages"] or {}).get(bucket)) for bucket in _MD_BUCKETS},
        "conversations": convos_out,
    }


def _md_fetch(api_get, limit=MSGDUMP_CONVOS):
    """The blocking part (requests). Runs in a worker thread. Read-only GETs."""
    params = {"limit": limit, "includeResources": 1}
    raw = {"requested": limit, "params": dict(params), "error": None, "conversations": []}
    try:
        convos = ((api_get("/conversations", params=params) or {}).get("result")) or []
    except Exception as e:
        raw["error"] = f"{type(e).__name__}: {e}"
        return raw

    for idx, convo in enumerate(convos[:limit]):
        convo = convo if isinstance(convo, dict) else {}
        cid = convo.get("id")
        row = {"order_index": idx, "id": cid, "conversation": convo,
               "messages": [], "error": None}
        if cid is None:
            row["error"] = "conversation has no id"
        else:
            try:
                row["messages"] = ((api_get(f"/conversations/{cid}/messages") or {})
                                   .get("result")) or []
            except Exception as e:
                row["error"] = f"{type(e).__name__}: {e}"
        raw["conversations"].append(row)
    return raw


def build_msgdump_summary(dump):
    counts = dump.get("shape_counts") or {}
    fc = dump.get("field_comparison") or {}
    lines = [
        "🔎 **!ouja-msgdump** — نسخة تشخيصية مؤقتة (قراءة فقط).",
        f"• محادثات: {dump.get('conversations_returned')} من {dump.get('conversations_requested')}",
        f"• رسائل انطلقت عبر Hostaway: {counts.get('sent_using_hostaway', 0)}",
        f"• رسائل ما انطلقت عبر Hostaway: {counts.get('not_sent_using_hostaway', 0)}",
        f"• الحقل `sentUsingHostaway` مو موجود أصلًا: {counts.get('flag_missing', 0)}",
    ]
    only_a = fc.get("only_when_sent_using_hostaway") or []
    only_b = fc.get("only_when_not_sent_using_hostaway") or []
    if only_a or only_b:
        lines.append(f"• فروق الحقول بين الشكلين: {len(only_a)} / {len(only_b)} حقل مختلف — التفاصيل بالملف.")
    else:
        lines.append("• الشكلان بنفس الحقول تمامًا (أو ما توفر أحد الشكلين) — شوف الملف.")
    if dump.get("list_fetch_error"):
        lines.append(f"⚠️ خطأ من Hostaway: {str(dump['list_fetch_error'])[:300]}")
    lines += ["", "🔒 ما أرسلنا ولا عدّلنا أي شيء — قراءة فقط.",
              "🙈 نص الرسائل وأسماء الضيوف وأرقامهم مخفية، والباقي كامل بالملف."]
    text = "\n".join(lines)
    return text if len(text) <= SUMMARY_MAX else text[:SUMMARY_MAX]


async def handle_msgdump(message):
    """The listener body for !ouja-msgdump. Never raises."""
    if getattr(message.author, "bot", False):
        return
    parts = (message.content or "").strip().split()
    if not parts or parts[0].lower() != TRIGGER_MSGDUMP:
        return

    if message.guild is None:
        try:
            await message.reply("هذا الأمر يشتغل داخل السيرفر فقط.", mention_author=False)
        except Exception:
            pass
        return

    if not _is_allowed(message):
        try:
            await message.reply("🔒 هذا الأمر للمالك أو الأدمن فقط.", mention_author=False)
        except Exception:
            pass
        return

    status = None
    try:
        status = await message.reply(
            f"⏳ أسحب آخر {MSGDUMP_CONVOS} محادثات من Hostaway… (قراءة فقط، ما راح أرسل ولا أعدّل شيء)",
            mention_author=False)
    except Exception:
        status = None

    try:
        api_get = getattr(_HOST, "api_get", None)
        if api_get is None:
            raise RuntimeError("ops_audit.setup(bot, host) was called without the host "
                               "module — no api_get available")
        raw = await asyncio.to_thread(_md_fetch, api_get, MSGDUMP_CONVOS)
        dump = build_msgdump(raw, generated_at=_iso(datetime.now(timezone.utc)))

        payload = json.dumps(dump, ensure_ascii=False, indent=2)
        if len(payload) > MSGDUMP_MAX_CHARS:
            payload = payload[:MSGDUMP_MAX_CHARS] + "\n… TRUNCATED (file size cap)"
        day = (dump.get("generated_at") or "")[:10] or "today"
        f = discord.File(io.BytesIO(payload.encode("utf-8")),
                         filename=f"ouja_msgdump_{day}.json")

        summary = build_msgdump_summary(dump)
        if status is not None:
            await status.edit(content=summary)
        else:
            await message.channel.send(summary)
        await message.channel.send(file=f)
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        print("ops_audit msgdump error:", err)
        traceback.print_exc()
        note = ("❌ التشخيص وقف بخطأ. ابعث هذا السطر لفيصل:\n```\n" + err[:1500] + "\n```")
        try:
            if status is not None:
                await status.edit(content=note)
            else:
                await message.channel.send(note)
        except Exception:
            pass
# ============================ END TEMPORARY ==========================


def setup(bot, host=None):
    """Register the read-only listeners. Called once from bot.py.

    `host` is bot.py's own LIVE module object (for `api_get`) — this file must
    NEVER `import bot`. It stays optional so the audit half works without it.
    """
    global _HOST
    _HOST = host

    async def _ops_audit_on_message(message):
        try:
            head = (message.content or "").strip().split(" ")[0].lower()
            if head == TRIGGER_MSGDUMP:
                await handle_msgdump(message)
            else:
                await handle_message(message)
        except Exception as e:                      # belt AND braces
            print("ops_audit listener error:", type(e).__name__, e)

    bot.add_listener(_ops_audit_on_message, "on_message")
    print("ops_audit: !ouja-audit + !ouja-msgdump listeners registered (read-only)")
    return _ops_audit_on_message
