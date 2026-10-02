# -*- coding: utf-8 -*-
"""ops_tidy — `!ouja-tidy plan|run|undo|status`: the Discord tidy-up for Ouja Residence.

What it does (owner-approved 2026-10-02, spec:
docs/superpowers/specs/2026-10-02-discord-tidy-design.md)
-----------------------------------------------------------------------------------
Old and closed channels move into «📦 أرشيف N» (Managment read-only), three permission
leaks are closed (overflow categories copy their parent, «تحصيل الحجوزات المباشرة» is
locked, the four price/revenue channels become Managment-only), and — after the first
successful `run` — every ticket that closes moves to the archive on its own.
Nothing is ever deleted or renamed. Every run is undoable from a snapshot.

The split
---------
* ops_tidy_rules.py is the PURE brain: it decides, from the `ops_audit.collect()`
  inventory, what happens to every channel. It is tested offline against the real audit.
* THIS file only executes that plan against Discord, with the safety rails:
  read-only `plan`, a typed confirm word, a snapshot posted BEFORE the first write,
  a re-check of every row right before it is written, panels never written, one
  operation at a time, and no handler can ever take the bot down.

Contract with bot.py (same as ops_audit / ops_archive)
------------------------------------------------------
`import ops_tidy` + `ops_tidy.setup(bot, host)`, where `host` is bot.py's LIVE module.
This file must NEVER `import bot` (bot.py runs as __main__; importing it by name would
boot a second bot). bot.py also calls the module-level helpers below:
`archive_closed_channel`, `directpay_overwrites`.

Note on the prefix: the bot's command prefix is "!ouja " (with a space), so "!ouja-tidy"
is NOT a prefix command and cannot collide with `process_commands`.
"""

import asyncio
import csv
import io
import json
import os
import re
import time
import traceback
from datetime import datetime, timedelta, timezone

import discord

import ops_audit
import ops_tidy_rules as R

# ---------------------------------------------------------------- constants
TRIGGER = "!ouja-tidy"

WORD_RUN = "نفّذ"
WORD_RUN_NO_REPORT = "نفّذ بدون تقرير"
WORD_UNDO = "رجّع"
CONFIRM_TIMEOUT = 300           # seconds to type the word
PLAN_MAX_AGE = timedelta(hours=24)
PROGRESS_EVERY = 6.0            # seconds between edits of the ONE progress message
SUMMARY_MAX = 1900              # Discord's limit is 2000; leave headroom
CACHE_WAIT = 10.0               # seconds to wait for the gateway cache to catch up

PLAN_FILE = "tidy_plan.json"
STATE_FILE = "tidy_state.json"

# bot.py constants holding the names of channels the bot finds BY NAME (never moved)
LIVE_CHANNEL_CONSTS = (
    "ESCALATION_CHANNEL", "AUTO_REPLY_CHANNEL", "ASSISTANT_CHANNEL", "KNOWLEDGE_CHANNEL",
    "CLEANING_REVIEW_CHANNEL", "OUJACT_SCHEDULE_CHANNEL", "DISPATCH_CHANNEL",
    "DISCOUNT_CHANNEL", "HEADS_UP_CHANNEL", "REVENUE_CHANNEL", "PRICE_OPP_CHANNEL",
    "WEEKLY_REVIEW_CHANNEL", "EXPENSE_ALERT_CHANNEL", "EVAL_CHANNEL", "SCHEDULE_OPS_CHANNEL",
    "ONB_OPS_CHANNEL", "DECOR_OPS_CHANNEL", "DIRECTPAY_SUMMARY_CHANNEL", "WATCHDOG_CHANNEL",
    "STUDIO_OPS_CHANNEL", "DIGEST_CHANNEL", "FINCHAT_ESC_CHANNEL", "WILT_CHANNEL",
    "WATCHMAN_ADMIN_CHANNEL",
)
PANEL_CONSTS = ("MAINT_PANEL_CHANNEL", "RR_PANEL_CHANNEL", "PROC_PANEL_CHANNEL")

_DIACRITICS = re.compile("[ً-ْ]")
_CLOSED_PREFIX = re.compile(r"^(?:مغلق[ةه]?-?|closed-)")
_ARCHIVE_INDEX = re.compile(r"(\d+|[٠-٩]+)$")

_HOST = None                    # bot.py's LIVE module (never `import bot`)
_BOT = None
_BUSY = {"op": None, "step": "", "started": None}    # one operation at a time, per process
_MEM = {"plan": None}                                 # the last plan, also on disk
_LOCK = {"loop": None, "lock": None}                  # serialises auto-archive moves


# ------------------------------------------------------------ small helpers
def _now():
    return datetime.now(timezone.utc)


def _parse_iso(s):
    try:
        dt = datetime.fromisoformat(str(s))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _pause():
    try:
        return max(0.0, float(os.environ.get("TIDY_PAUSE", "1.0") or 1.0))
    except Exception:
        return 1.0


def _norm_word(s):
    """Confirm words compare without Arabic diacritics: نفّذ == نفذ, رجّع == رجع."""
    return " ".join(_DIACRITICS.sub("", str(s or "")).split())


def _host_get(name, default=None):
    return getattr(_HOST, name, default) if _HOST is not None else default


def _save(name, obj):
    fn = _host_get("_save_json")
    if fn is None:
        return False
    try:
        return bool(fn(name, obj))
    except Exception as e:
        print("ops_tidy save error (%s):" % name, e)
        return False


def _load(name, default):
    fn = _host_get("_load_json")
    if fn is None:
        return default
    try:
        v = fn(name, default)
        return default if v is None else v
    except Exception:
        return default


def _state():
    s = _load(STATE_FILE, {})
    return s if isinstance(s, dict) else {}


def _dp_ids():
    fn = _host_get("_dp_close_ids")
    try:
        return [int(x) for x in (fn() if callable(fn) else [])]
    except Exception:
        return []


def live_names():
    """The bot-owned channel names as configured RIGHT NOW (a renamed env var still counts)."""
    out = set()
    for n in LIVE_CHANNEL_CONSTS:
        v = _host_get(n)
        if isinstance(v, str) and v.strip():
            out.add(v.strip())
    try:
        fn = getattr(getattr(_host_get("_checkout"), "flow", None), "board_channel_name", None)
        if callable(fn):
            out.add(str(fn()))
    except Exception:
        pass
    return out


def live_panels():
    out = set()
    for n in PANEL_CONSTS:
        v = _host_get(n)
        if isinstance(v, str) and v.strip():
            out.add(v.strip())
    return out


def _is_panel(name, panels=None):
    """R.is_panel, plus the same test on the name without a «مغلقة-» prefix — a panel that
    somebody renamed «مغلقة-rr-tickets» is still a panel and is still never written."""
    panels = live_panels() if panels is None else panels
    n = str(name or "")
    if R.is_panel(n, panels):
        return True
    bare = _CLOSED_PREFIX.sub("", n)
    return bare != n and R.is_panel(bare, panels)


def _role_named(guild, name):
    for r in getattr(guild, "roles", None) or []:
        if getattr(r, "name", None) == name:
            return r
    return None


def _find_category(guild, name):
    cats = list(getattr(guild, "categories", None) or [])
    hit = next((c for c in cats if c.name == name), None)
    return hit or next((c for c in cats if R.norm(c.name) == R.norm(name)), None)


def _archive_index(name):
    m = _ARCHIVE_INDEX.search(str(name or ""))
    if not m:
        return None
    return int(m.group(1).translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")))


def _ov_copy(ov):
    if ov is None:
        return discord.PermissionOverwrite()
    a, d = ov.pair()
    return discord.PermissionOverwrite.from_pair(a, d)


# The bot's own overwrite. Deliberately NO manage_channels / manage_permissions: Discord only
# lets a guild ADMINISTRATOR put Manage Permissions into a channel overwrite, and the bot is
# admin only during the owner's run — every later archive create would 403. Its server-wide
# role already carries what it needs to move and lock rooms.
_BOT_FULL = dict(view_channel=True, send_messages=True, read_message_history=True,
                 embed_links=True, attach_files=True)


# -------------------------------------------------- overwrite builders (shared)
def archive_overwrites(guild):
    """«📦 أرشيف N»: hidden from @everyone, Managment reads (never writes), the bot keeps all."""
    ow = {}
    everyone = getattr(guild, "default_role", None)
    if everyone is not None:
        ow[everyone] = discord.PermissionOverwrite(view_channel=False)
    role_name = (os.environ.get("TIDY_ARCHIVE_ROLE") or "").strip() or R.MGMT_ROLE
    role = _role_named(guild, role_name)
    if role is not None:
        ow[role] = discord.PermissionOverwrite(
            view_channel=True, read_message_history=True, send_messages=False,
            add_reactions=False, create_public_threads=False, create_private_threads=False,
            send_messages_in_threads=False)
    me = getattr(guild, "me", None)
    if me is not None:
        ow[me] = discord.PermissionOverwrite(**_BOT_FULL)
    return ow


def directpay_overwrites(guild, existing=None):
    """«تحصيل الحجوزات المباشرة» locked: MERGED into what is there, never dropping an entry.
    @everyone loses view; Accounting + Managment + the ping role + every closer + the bot see."""
    ow = {t: _ov_copy(o) for t, o in dict(existing or {}).items()}

    def put(target, **flags):
        if target is None:
            return
        key = next((k for k in ow if getattr(k, "id", None) == getattr(target, "id", None)), target)
        ov = ow.get(key)
        ov = discord.PermissionOverwrite() if ov is None else ov
        ov.update(**flags)
        ow[key] = ov

    put(getattr(guild, "default_role", None), view_channel=False)
    for name in R.DIRECTPAY_ROLES:
        put(_role_named(guild, name), view_channel=True)
    try:
        ping = int(_host_get("DIRECTPAY_PING_ROLE_ID", 0) or 0)
    except Exception:
        ping = 0
    if ping:
        put(guild.get_role(ping), view_channel=True)
    for uid in _dp_ids():
        put(guild.get_member(uid) or discord.Object(id=uid, type=discord.Member), view_channel=True)
    put(getattr(guild, "me", None), **_BOT_FULL)
    return ow


# ----------------------------------------------------------- snapshot shapes
def _target_type(t):
    if isinstance(t, discord.Role) or hasattr(t, "mentionable"):
        return "role"
    if isinstance(t, discord.Object) and getattr(t, "type", None) is discord.Role:
        return "role"
    return "member"


def _ow_rows(overwrites):
    rows = []
    for t, ov in (overwrites or {}).items():
        a, d = ov.pair()
        rows.append({"type": _target_type(t), "id": str(t.id), "allow": a.value, "deny": d.value})
    return rows


def _channel_state(ch):
    return R.snapshot_row({
        "id": ch.id, "name": getattr(ch, "name", None),
        "category_id": getattr(ch, "category_id", None),
        "position": getattr(ch, "position", None),
        "synced": bool(getattr(ch, "permissions_synced", False)),
        "overwrites": _ow_rows(getattr(ch, "overwrites", {})),
    })


def _rebuild(guild, rows):
    out = {}
    for o in rows or []:
        tid = int(o["id"])
        if o.get("type") == "role":
            t = guild.get_role(tid) or discord.Object(id=tid, type=discord.Role)
        else:
            t = guild.get_member(tid) or discord.Object(id=tid, type=discord.Member)
        out[t] = discord.PermissionOverwrite.from_pair(discord.Permissions(int(o["allow"])),
                                                       discord.Permissions(int(o["deny"])))
    return out


def _ow_key(ows):
    out = []
    for t, ov in (ows or {}).items():
        a, d = ov.pair()
        if a.value or d.value:
            out.append((str(t.id), a.value, d.value))
    return sorted(out)


async def _wait_cached(guild, cid, want=None):
    """discord.py's sync_permissions reads the category from the CACHE, which the gateway
    updates a moment after the REST call. Wait (bounded) until the cache has caught up, or a
    channel synced right after a category edit would copy the OLD overwrites."""
    deadline = time.monotonic() + CACHE_WAIT
    key = _ow_key(want) if want is not None else None
    while True:
        c = guild.get_channel(cid)
        if c is not None and (key is None or _ow_key(c.overwrites) == key):
            return True
        if time.monotonic() >= deadline:
            print("ops_tidy: cache did not catch up for", cid)
            return False
        await asyncio.sleep(0.25)


# --------------------------------------------------------------- auto-archive
def _auto_archive_on():
    env = (os.environ.get("TIDY_AUTO_ARCHIVE") or "").strip()
    if env == "0":
        return False
    if env == "1":
        return True
    return bool(_state().get("auto_archive"))


def _archive_lock():
    loop = asyncio.get_running_loop()
    if _LOCK["loop"] is not loop:
        _LOCK["loop"], _LOCK["lock"] = loop, asyncio.Lock()
    return _LOCK["lock"]


async def _archive_slot(guild):
    """The first «📦 أرشيف N» with room (< 50); the next one is created when all are full."""
    arch = sorted(((_archive_index(c.name) or 0, c) for c in guild.categories
                   if R.is_archive_category(c.name)), key=lambda x: x[0])
    for _i, c in arch:
        if len(c.channels) < R.ARCHIVE_CAP:
            return c
    nxt = (max(i for i, _c in arch) + 1) if arch else 1
    cat = await guild.create_category(R.archive_name(nxt), overwrites=archive_overwrites(guild),
                                      position=len(guild.categories))
    await _wait_cached(guild, cat.id)
    return cat


async def archive_closed_channel(ch):
    """Move a just-closed ticket into the archive. ON only after the first successful `run`
    (or TIDY_AUTO_ARCHIVE=1; TIDY_AUTO_ARCHIVE=0 forces it off). Never raises: the close
    itself must always complete. -> True when moved, False otherwise."""
    try:
        if not _auto_archive_on():
            return False
        if _is_panel(getattr(ch, "name", "")):
            return False
        cat = getattr(ch, "category", None)
        cname = getattr(cat, "name", "") or ""
        if R.is_archive_category(cname) or cname in R.UNTOUCHED_CATEGORIES:
            return False
        async with _archive_lock():
            dest = await _archive_slot(ch.guild)
            await ch.edit(category=dest, sync_permissions=True, overwrites=dict(dest.overwrites))
        return True
    except Exception as e:
        print("ops_tidy auto-archive skipped (non-fatal):", type(e).__name__, e)
        return False


# ------------------------------------------------------------------ messaging
async def _reply(message, text, files=None):
    kw = {"files": files} if files else {}
    try:
        return await message.reply(text, mention_author=False, **kw)
    except Exception:
        try:
            return await message.channel.send(text, **kw)
        except Exception as e:
            print("ops_tidy reply failed:", e)
            return None


def _fit(lines, tail=None):
    """Join lines under SUMMARY_MAX, cutting whole lines and saying so."""
    out, used = [], 0
    tail = tail or []
    budget = SUMMARY_MAX - sum(len(t) + 1 for t in tail)
    for i, ln in enumerate(lines):
        if used + len(ln) + 1 > budget:
            out.append("… والباقي في الملف المرفق (%d سطر)" % (len(lines) - i))
            break
        out.append(ln)
        used += len(ln) + 1
    return "\n".join(out + tail)[:SUMMARY_MAX + 90]


async def _confirm(bot, message, word):
    def check(m):
        return (getattr(m.author, "id", None) == message.author.id
                and getattr(m.channel, "id", None) == message.channel.id)
    try:
        got = await bot.wait_for("message", check=check, timeout=CONFIRM_TIMEOUT)
    except Exception:
        return False
    return _norm_word(getattr(got, "content", "")) == _norm_word(word)


def _file(data, filename):
    return discord.File(io.BytesIO(data), filename=filename)


# ----------------------------------------------------------------------- plan
async def _people(guild, plan, bot):
    """Who loses what. None when the gateway never gave us the members (intent off)."""
    if getattr(getattr(bot, "intents", None), "members", None) is False:
        return None
    try:
        if not getattr(guild, "chunked", True):
            await guild.chunk()
    except Exception as e:
        print("ops_tidy chunk failed:", e)
    humans = [m for m in (getattr(guild, "members", None) or []) if not getattr(m, "bot", False)]
    if not humans:
        return None
    owner_id = getattr(guild, "owner_id", None)
    chans = [(r["id"], guild.get_channel(int(r["id"]))) for r in plan["channels"]]
    members, visible = [], {}
    for m in humans:
        perms = getattr(m, "guild_permissions", None)
        members.append({
            "id": str(m.id),
            "name": getattr(m, "display_name", None) or getattr(m, "name", "?"),
            "roles": [r.name for r in (getattr(m, "roles", None) or []) if r.name != "@everyone"],
            "is_admin": bool(getattr(perms, "administrator", False)),
            "is_owner": owner_id == m.id,
        })
        seen = set()
        for cid, ch in chans:
            if ch is None:
                continue
            try:
                if ch.permissions_for(m).view_channel:
                    seen.add(cid)
            except Exception:
                pass
        visible[str(m.id)] = seen
        await asyncio.sleep(0)
    return R.people_report(plan, members, visible, directpay_extra_ids=_dp_ids())


def _people_csv(report):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["الاسم", "يفقد قنوات شغالة", "عددها", "يفقد من الأرشيف", "يبقى يشوف"])
    for p in report or []:
        w.writerow([p["member"], "، ".join(p["loses_live"]), len(p["loses_live"]),
                    p["loses_archive"], p["keeps"]])
    return ("﻿" + buf.getvalue()).encode("utf-8")


def _plan_text(plan, report):
    lines = ["🧹 **خطة ترتيب ديسكورد** — تجربة بس، ما تغيّر أي شي في السيرفر.", "",
             R.summary_ar(plan), ""]
    if report is None:
        lines += ["ℹ️ ملف «مين يفقد وش» ما انحسب: يحتاج تشغيل «Server Members Intent» من موقع "
                  "ديسكورد للمطورين **و** `MEMBERS_INTENT=1` في Railway.",
                  "تقدر تنفّذ بدونه، بس كلمة التأكيد بتكون: **%s**" % WORD_RUN_NO_REPORT]
    else:
        red = [p for p in report if p["loses_live"]]
        if red:
            lines.append("**%d شخص بيفقدون قنوات شغّالة:**" % len(red))
            for p in red:
                names = p["loses_live"]
                lines.append("🔴 %s — %s%s" % (p["member"], "، ".join(names[:6]),
                                              " … (+%d)" % (len(names) - 6) if len(names) > 6 else ""))
        else:
            lines.append("🟢 ولا أحد بيفقد قناة شغّالة — اللي يختفي عنهم أرشيف بس.")
    tail = ["", "📎 مرفق: الخطة كاملة + ملف الأشخاص.", "للتنفيذ: `!ouja-tidy run`"]
    return _fit(lines, tail)


async def handle_plan(message, bot):
    guild = message.guild
    _BUSY["step"] = "أقرأ السيرفر"
    inv = await ops_audit.collect(guild)
    panels = live_panels()
    plan = R.build_plan(inv, bot_owned=R.BOT_OWNED_DEFAULT | live_names(), panel_names=panels)
    plan["panel_names"] = sorted(panels)
    _BUSY["step"] = "أحسب مين يفقد وش"
    report = await _people(guild, plan, bot)
    plan["people"] = report
    plan["requested_by"] = str(getattr(message.author, "id", ""))
    _MEM["plan"] = plan
    _save(PLAN_FILE, plan)
    day = _now().date().isoformat()
    files = [_file(json.dumps(plan, ensure_ascii=False, indent=1).encode("utf-8"),
                   "tidy_plan_%s.json" % day),
             _file(_people_csv(report), "tidy_people_%s.csv" % day)]
    await _reply(message, _plan_text(plan, report), files=files)


# ------------------------------------------------------------------------ run
def _current_plan():
    plan = _MEM.get("plan") or _load(PLAN_FILE, None)
    return plan if isinstance(plan, dict) and plan.get("channels") is not None else None


class _Run:
    """Counts + the single progress message for one run/undo."""

    def __init__(self, status):
        self.status = status
        self.moved = self.locked = self.restored = self.forbidden = 0
        self.skipped = []
        self.t0 = time.monotonic()
        self._last = 0.0

    def skip(self, name, reason):
        self.skipped.append({"name": name, "reason": reason})

    async def tick(self, text, force=False):
        _BUSY["step"] = text
        now = time.monotonic()
        if self.status is None or (not force and now - self._last < PROGRESS_EVERY):
            return
        self._last = now
        try:
            await self.status.edit(content=text)
        except Exception:
            pass

    async def write(self, name, fn):
        """One Discord write. Forbidden/NotFound/anything else → skip with the reason; never abort."""
        ok = False
        try:
            await fn()
            ok = True
        except discord.Forbidden:
            self.forbidden += 1
            self.skip(name, "البوت ما عنده صلاحية (Forbidden)")
        except discord.NotFound:
            self.skip(name, "ما عادت موجودة")
        except Exception as e:
            self.skip(name, ("%s: %s" % (type(e).__name__, e))[:120])
        pause = _pause()
        if pause:
            await asyncio.sleep(pause)
        return ok

    def elapsed(self):
        s = int(time.monotonic() - self.t0)
        return "%d:%02d" % (s // 60, s % 60)


def _recheck(guild, row, panels, run):
    """The live channel for a plan row, or None (and a logged skip) when it changed."""
    ch = guild.get_channel(int(row["id"]))
    if ch is None:
        run.skip(row["name"], "ما عادت موجودة")
        return None
    if str(getattr(ch, "category_id", None) or "") != str(row.get("category_id") or ""):
        run.skip(row["name"], "تغيّر قسمها بعد الخطة")
        return None
    if row.get("action") == "archive" and R.CLOSED_RE.match(row.get("name") or "") \
            and not R.CLOSED_RE.match(ch.name or ""):
        run.skip(ch.name, "انفتحت من جديد بعد الخطة")
        return None
    if _is_panel(ch.name, panels) or _is_panel(row.get("name"), panels):
        run.skip(ch.name, "روم فتح تذاكر — ما ينلمس")
        return None
    cat = getattr(ch, "category", None)
    if getattr(cat, "name", None) in R.UNTOUCHED_CATEGORIES:
        run.skip(ch.name, "قسم خاص — ما ينلمس")
        return None
    return ch


def _mgmt_targets(guild):
    """(target, flags) for a price/revenue channel. The bot goes FIRST so it never locks itself
    out mid-way; Operation is denied only if that role exists."""
    out = []
    me = getattr(guild, "me", None)
    if me is not None:
        out.append((me, dict(view_channel=True, send_messages=True, read_message_history=True,
                             embed_links=True, attach_files=True)))
    out.append((guild.default_role, dict(view_channel=False)))
    op = _role_named(guild, "Operation")
    if op is not None:
        out.append((op, dict(view_channel=False)))
    mg = _role_named(guild, R.MGMT_ROLE)
    if mg is not None:
        out.append((mg, dict(view_channel=True)))
    return out


async def _execute(message, guild, plan):
    runid = _now().strftime("%Y%m%d-%H%M%S")
    panels = set(plan.get("panel_names") or []) | live_panels()
    rows = plan.get("channels") or []
    fixes = plan.get("category_fixes") or []
    sync_rows = [r for r in rows if r.get("action") == "sync_to_category"]
    mgmt_rows = [r for r in rows if r.get("action") == "mgmt_only"]
    moves = [r for r in rows if r.get("action") == "archive"]

    # 1) the snapshot — taken and POSTED before the first write
    snap_ch = []
    for r in sync_rows + mgmt_rows + moves:
        ch = guild.get_channel(int(r["id"]))
        if ch is not None and not _is_panel(ch.name, panels):
            snap_ch.append(_channel_state(ch))
    snap_cat = []
    for f in fixes:
        cat = _find_category(guild, f["category"])
        if cat is not None:
            snap_cat.append(_channel_state(cat))
    snap = {"version": 1, "runid": runid, "guild": str(guild.id), "taken_at": _now().isoformat(),
            "channels": snap_ch, "categories": snap_cat}
    snap_name = "tidy_snapshot_%s.json" % runid
    _save(snap_name, snap)
    try:
        await message.channel.send(
            "📸 صورة الوضع قبل أي تغيير (%d قناة، %d قسم). احتفظ فيها: لو ضاع ملف Railway، "
            "ارفعها مع `!ouja-tidy undo` ويرجع كل شي منها." % (len(snap_ch), len(snap_cat)),
            file=_file(json.dumps(snap, ensure_ascii=False).encode("utf-8"), snap_name))
    except Exception as e:
        await _reply(message, "❌ ما قدرت أرسل صورة الوضع، فما غيّرت أي شي.\n```\n%s\n```"
                     % ("%s: %s" % (type(e).__name__, e))[:800])
        return
    st = _state()
    st["snapshots"] = [s for s in (st.get("snapshots") or []) if s != snap_name] + [snap_name]
    _save(STATE_FILE, st)

    status = None
    try:
        status = await message.channel.send("⏳ بدأ الترتيب… بحدّث هالرسالة نفسها.")
    except Exception:
        pass
    run = _Run(status)

    # 2) category fixes (the leaks)
    fixed, unlocked = [], set()     # unlocked = categories whose lock did NOT land
    for f in fixes:
        cat = _find_category(guild, f["category"])
        if cat is None:
            run.skip(f["category"], "القسم ما عاد موجود")
            continue
        unlocked.add(str(cat.id))
        if f["kind"] == "copy_parent":
            parent = _find_category(guild, f["parent"])
            if parent is None:
                run.skip(f["category"], "القسم الأصلي «%s» ما عاد موجود" % f["parent"])
                continue
            want = dict(parent.overwrites)
        else:
            want = directpay_overwrites(guild, existing=cat.overwrites)
        await run.tick("🔒 أقفل قسم «%s»" % cat.name)
        if await run.write(cat.name, lambda c=cat, w=want: c.edit(overwrites=w)):
            run.locked += 1
            fixed.append((cat.id, want))
            unlocked.discard(str(cat.id))
    for cid, want in fixed:
        if not await _wait_cached(guild, cid, want):
            unlocked.add(str(cid))      # unconfirmed lock: a sync would copy the OLD overwrites

    # 3) channels that follow their (now locked) category — never one whose lock failed, or
    #    syncing would copy the still-OPEN overwrites over whatever the channel had
    for r in sync_rows:
        if str(r.get("category_id") or "") in unlocked:
            run.skip(r["name"], "قفل القسم ما نجح — ما ربطتها")
            continue
        ch = _recheck(guild, r, panels, run)
        if ch is None:
            continue
        await run.tick("🔒 أربط «%s» بصلاحيات قسمها" % ch.name)
        if await run.write(ch.name, lambda c=ch: c.edit(sync_permissions=True)):
            run.locked += 1

    # 4) price / revenue channels → Managment only (merged, never replaced)
    for r in mgmt_rows:
        ch = _recheck(guild, r, panels, run)
        if ch is None:
            continue
        await run.tick("🔒 «%s» للمدراء بس" % ch.name)
        ok = True
        for target, flags in _mgmt_targets(guild):
            ov = ch.overwrites_for(target)
            ov.update(**flags)
            if not await run.write(ch.name, lambda c=ch, t=target, o=ov: c.set_permissions(t, overwrite=o)):
                ok = False
                break
        if ok:
            run.locked += 1

    # 5) archive categories (found or created at the bottom), then the moves
    arch = {}
    for name in sorted({r["archive_category"] for r in moves if r.get("archive_category")}):
        cat = _find_category(guild, name)
        if cat is None:
            await run.tick("📦 أسوي «%s»" % name)
            created = []

            async def _mk(n=name):
                created.append(await guild.create_category(
                    n, overwrites=archive_overwrites(guild), position=len(guild.categories)))
            if await run.write(name, _mk) and created:
                cat = created[0]
                await _wait_cached(guild, cat.id)
        if cat is not None:
            arch[name] = cat
    for i, r in enumerate(moves, 1):
        dest = arch.get(r.get("archive_category"))
        if dest is None:
            run.skip(r["name"], "قسم الأرشيف ما انسوى")
            continue
        ch = _recheck(guild, r, panels, run)
        if ch is None:
            continue
        await run.tick("📦 %d/%d — «%s»" % (i, len(moves), ch.name))
        # overwrites passed explicitly too: discord.py's sync reads the category from the CACHE,
        # and a just-created archive may not be there yet (the channel would keep its old ones)
        if await run.write(ch.name, lambda c=ch, d=dest: c.edit(category=d, sync_permissions=True,
                                                                overwrites=dict(d.overwrites))):
            run.moved += 1

    # 6) the record + the final word
    plan["ran_at"] = _now().isoformat()
    _MEM["plan"] = plan
    _save(PLAN_FILE, plan)
    success = (run.moved + run.locked) > 0
    st = _state()
    st["last_run"] = {"runid": runid, "finished_at": _now().isoformat(), "took": run.elapsed(),
                      "moved": run.moved, "locked": run.locked, "skipped": len(run.skipped),
                      "forbidden": run.forbidden, "snapshot": snap_name}
    if success:
        st["auto_archive"] = True
    _save(STATE_FILE, st)

    lines = ["✅ **خلص الترتيب** في %s" % run.elapsed(),
             "📦 انتقلت للأرشيف: **%d**" % run.moved,
             "🔒 انقفلت صلاحياتها: **%d**" % run.locked,
             "⏭ تجاوزت: **%d**" % len(run.skipped)]
    for s in run.skipped[:12]:
        lines.append("• %s — %s" % (s["name"], s["reason"]))
    if len(run.skipped) > 12:
        lines.append("• … و%d ثانية" % (len(run.skipped) - 12))
    lines += ["", "ما انحذف شي، وما تغيّر اسم أي قناة."]
    if success:
        lines.append("ومن الحين أي تذكرة تتسكّر تروح للأرشيف من نفسها.")
    if run.forbidden:
        lines += ["", "⚠️ %d قناة ما قدر البوت يوصل لها (Forbidden). عطّ رول البوت صلاحية "
                      "Administrator مؤقتاً، وبعدها `!ouja-tidy plan` ثم `!ouja-tidy run` — "
                      "بيكمل الباقي بس." % run.forbidden]
    lines += ["", "للتراجع: `!ouja-tidy undo` وبعدها اكتب **%s** — يرجّع كل شي مثل ما كان." % WORD_UNDO]
    text = _fit(lines)
    if status is not None:
        try:
            await status.edit(content=text)
            return
        except Exception:
            pass
    await _reply(message, text)


async def handle_run(message, bot):
    guild = message.guild
    plan = _current_plan()
    born = _parse_iso((plan or {}).get("generated_at"))
    if plan is None or born is None or _now() - born > PLAN_MAX_AGE:
        await _reply(message, "ما فيه خطة جديدة (آخر ٢٤ ساعة). اكتب `!ouja-tidy plan` أول، وراجع الملف، "
                              "وبعدها `!ouja-tidy run`.")
        return
    if str(plan.get("guild") or "") not in ("", str(guild.id)):
        await _reply(message, "هالخطة لسيرفر ثاني. اكتب `!ouja-tidy plan` هنا أول.")
        return
    if plan.get("ran_at"):
        await _reply(message, "هالخطة انتفّذت من قبل. اكتب `!ouja-tidy plan` من جديد لو تبي تكمّل الباقي.")
        return
    word = WORD_RUN if plan.get("people") is not None else WORD_RUN_NO_REPORT
    c = plan.get("counts") or {}
    await _reply(message, "⚠️ بنقل **%d** قناة للأرشيف ونقفل **%d** (ما فيه حذف ولا تغيير أسماء، "
                          "وكل شي يرجع بـ `!ouja-tidy undo`).\nاكتب **%s** خلال ٥ دقايق عشان أبدأ. "
                          "أي شي ثاني = إلغاء." % (c.get("archive", 0), c.get("restrict", 0), word))
    _BUSY["step"] = "أنتظر كلمة التأكيد"
    if not await _confirm(bot, message, word):
        await _reply(message, "تمام، ألغيت — ما تغيّر أي شي.")
        return
    await _execute(message, guild, plan)


# ----------------------------------------------------------------------- undo
async def _snapshot_from_message(message):
    for a in getattr(message, "attachments", None) or []:
        if str(getattr(a, "filename", "")).lower().endswith(".json"):
            try:
                snap = json.loads((await a.read()).decode("utf-8"))
                if isinstance(snap, dict) and "channels" in snap:
                    return snap
            except Exception as e:
                print("ops_tidy: attached snapshot unreadable:", e)
    return None


async def handle_undo(message, bot):
    guild = message.guild
    st = _state()
    name = (st.get("snapshots") or [None])[-1]
    snap = _load(name, None) if name else None
    if not isinstance(snap, dict):
        snap, name = await _snapshot_from_message(message), None
    if not isinstance(snap, dict):
        await _reply(message, "ما لقيت صورة وضع محفوظة. ارفع ملف `tidy_snapshot_….json` (اللي أرسلته وقت "
                              "التشغيل) مع نفس الأمر: `!ouja-tidy undo`.")
        return
    if str(snap.get("guild") or "") not in ("", str(guild.id)):
        await _reply(message, "هالصورة لسيرفر ثاني — ما رجّعت شي.")
        return
    chans, cats = snap.get("channels") or [], snap.get("categories") or []
    await _reply(message, "↩️ بيرجع **%d** قناة و**%d** قسم مثل ما كانت قبل التشغيل (%s).\n"
                          "اكتب **%s** خلال ٥ دقايق. أي شي ثاني = إلغاء."
                          % (len(chans), len(cats), str(snap.get("taken_at") or "")[:16], WORD_UNDO))
    _BUSY["step"] = "أنتظر كلمة التأكيد"
    if not await _confirm(bot, message, WORD_UNDO):
        await _reply(message, "تمام، ألغيت — ما تغيّر أي شي.")
        return
    status = None
    try:
        status = await message.channel.send("⏳ أرجّع… بحدّث هالرسالة نفسها.")
    except Exception:
        pass
    run = _Run(status)
    panels = live_panels()

    # categories FIRST, so a channel that was synced re-syncs to the ORIGINAL overwrites
    restored = []
    for c in cats:
        cat = guild.get_channel(int(c["id"]))
        if cat is None:
            run.skip(c.get("name") or c["id"], "القسم ما عاد موجود")
            continue
        want = _rebuild(guild, c.get("overwrites"))
        await run.tick("↩️ قسم «%s»" % cat.name)
        if await run.write(cat.name, lambda k=cat, w=want: k.edit(overwrites=w)):
            run.restored += 1
            restored.append((cat.id, want))
    for cid, want in restored:
        await _wait_cached(guild, cid, want)

    order = R.undo_order(chans)
    for i, row in enumerate(order, 1):
        ch = guild.get_channel(int(row["id"]))
        if ch is None:
            run.skip(row.get("name") or row["id"], "ما عادت موجودة")
            continue
        if _is_panel(ch.name, panels):
            run.skip(ch.name, "روم فتح تذاكر — ما ينلمس")
            continue
        old = None
        if row.get("category_id"):
            old = guild.get_channel(int(row["category_id"]))
            if old is None:
                run.skip(ch.name, "قسمها القديم ما عاد موجود")
                continue
        await run.tick("↩️ %d/%d — «%s»" % (i, len(order), ch.name))
        # only a channel that MOVED goes back with a position (discord.py re-numbers the whole
        # category for a position write); a channel that only lost permissions just gets them back
        where = {}
        if str(getattr(ch, "category_id", None) or "") != str(row.get("category_id") or ""):
            where = {"category": old}
            if row.get("position") is not None and getattr(ch, "position", None) != row.get("position"):
                where["position"] = row.get("position")
        if row.get("synced") and old is not None:
            fn = (lambda c=ch, kw=where: c.edit(sync_permissions=True, **kw))
        else:
            fn = (lambda c=ch, kw=where, w=_rebuild(guild, row.get("overwrites")):
                  c.edit(overwrites=w, **kw))
        if await run.write(ch.name, fn):
            run.restored += 1

    st = _state()
    if name:
        st["snapshots"] = [s for s in (st.get("snapshots") or []) if s != name]
    st["auto_archive"] = False          # the owner wanted things back — stop moving closed tickets too
    st["last_undo"] = {"finished_at": _now().isoformat(), "took": run.elapsed(),
                       "restored": run.restored, "skipped": len(run.skipped)}
    _save(STATE_FILE, st)
    plan = _current_plan()
    if plan is not None:
        plan["ran_at"] = plan.get("ran_at") or _now().isoformat()
        _MEM["plan"] = plan

    lines = ["↩️ **رجع كل شي** في %s" % run.elapsed(),
             "✅ رجع لمكانه وصلاحياته: **%d**" % run.restored,
             "⏭ تجاوزت: **%d**" % len(run.skipped)]
    for s in run.skipped[:12]:
        lines.append("• %s — %s" % (s["name"], s["reason"]))
    lines += ["", "أقسام «📦 أرشيف» باقية (فاضية) — ما نحذف شي.",
              "والنقل التلقائي للتذاكر المقفلة وقف."]
    text = _fit(lines)
    if status is not None:
        try:
            await status.edit(content=text)
            return
        except Exception:
            pass
    await _reply(message, text)


# --------------------------------------------------------------------- status
async def handle_status(message):
    if _BUSY.get("op"):
        await _reply(message, "⏳ شغّال الحين: `%s` — %s" % (_BUSY["op"], _BUSY.get("step") or "…"))
        return
    st = _state()
    lr = st.get("last_run")
    lines = []
    if lr:
        lines += ["🧹 **آخر تشغيل:** %s (أخذ %s)" % (str(lr.get("finished_at"))[:16].replace("T", " "),
                                                    lr.get("took")),
                  "📦 انتقلت: **%s** · 🔒 انقفلت: **%s** · ⏭ تجاوزت: **%s**"
                  % (lr.get("moved"), lr.get("locked"), lr.get("skipped"))]
    else:
        lines.append("ما فيه تشغيل سابق.")
    lu = st.get("last_undo")
    if lu:
        lines.append("↩️ آخر تراجع: %s — رجع **%s**" % (str(lu.get("finished_at"))[:16].replace("T", " "),
                                                      lu.get("restored")))
    lines.append("📦 النقل التلقائي للتذاكر المقفلة: **%s**" % ("شغّال" if _auto_archive_on() else "واقف"))
    await _reply(message, "\n".join(lines))


# ------------------------------------------------------------------ the wire
HELP = ("🧹 `!ouja-tidy plan` — الخطة (قراءة بس)\n"
        "`!ouja-tidy run` — التنفيذ (كلمة **%s**)\n"
        "`!ouja-tidy undo` — التراجع (كلمة **%s**)\n"
        "`!ouja-tidy status` — وين وصلنا" % (WORD_RUN, WORD_UNDO))


async def handle_message(message, bot):
    parts = (message.content or "").strip().split()
    if not parts or parts[0].lower() != TRIGGER:
        return
    if message.guild is None:
        await _reply(message, "هذا الأمر يشتغل داخل السيرفر فقط.")
        return
    if not ops_audit._is_allowed(message):
        return                                   # anyone else: ignored silently
    sub = parts[1].lower() if len(parts) > 1 else ""
    if sub == "status":
        await handle_status(message)
        return
    handler = {"plan": handle_plan, "run": handle_run, "undo": handle_undo}.get(sub)
    if handler is None:
        await _reply(message, HELP)
        return
    if _BUSY.get("op"):
        await _reply(message, "⏳ فيه عملية شغّالة الحين (`%s`) — انتظرها تخلص." % _BUSY["op"])
        return
    _BUSY.update(op=sub, step="بداية", started=_now().isoformat())
    try:
        await handler(message, bot)
    except Exception as e:
        err = "%s: %s" % (type(e).__name__, e)
        print("ops_tidy error:", err)
        traceback.print_exc()
        await _reply(message, "❌ وقف بخطأ — اللي انكتب في الرسائل فوق هو اللي صار، والباقي ما انلمس.\n"
                              "```\n%s\n```" % err[:1400])
    finally:
        _BUSY.update(op=None, step="", started=None)


def setup(bot, host=None):
    """Register the `!ouja-tidy` listener. Called once from bot.py."""
    global _HOST, _BOT
    _HOST, _BOT = host, bot

    async def _ops_tidy_on_message(message):
        try:
            if getattr(message.author, "bot", False):
                return
            await handle_message(message, bot)
        except Exception as e:                      # belt AND braces
            print("ops_tidy listener error:", type(e).__name__, e)

    bot.add_listener(_ops_tidy_on_message, "on_message")
    print("ops_tidy: !ouja-tidy plan|run|undo|status listener registered")
    return _ops_tidy_on_message
