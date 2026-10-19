# -*- coding: utf-8 -*-
"""maint_cleanup — a closed «صيانة» ticket room is saved, then deleted on day 3.

Team ruling 2026-10-19 (owner-approved): Discord sits against its 500-channel cap, and
closed maintenance rooms used to be KEPT forever («📦 أرشيف» still counts toward the cap).
Now:

    day 1   the ticket closes → the room is locked (as before) and stamped `delete_on`
            = close date + 2 days. It is NOT moved into the archive category any more.
    day 3   this module saves the room — every message AND every file as BYTES — into Google
            Drive (ops_archive._archive_channel, the same proven code as !ouja-archive), keeps
            a text copy on the bot's disk, writes the Drive link onto the dashboard ticket,
            and only then deletes the Discord room.

The fence, in order (any "no" keeps the room — "could not save" is never "deleted"):
    * the record is a maintenance ticket, status closed, with a `delete_on` stamp — tickets
      closed BEFORE this change have no stamp and are never touched (owner: separate decision)
    * the room fetched by its stored id still carries «مغلقة-» and the maint topic
    * Drive is configured, the archive read every message, and no file failed to upload
    * then delete

Contract (same as ops_archive / finance): this file never `import bot`; bot.py hands over its
LIVE module as `host`. Command: `!ouja-maint-clean` (status) / `!ouja-maint-clean run`.
"""

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone

import ops_archive

TRIGGER = "!ouja-maint-clean"
DELETE_AFTER_DAYS = 2            # close day = day 1 → deleted on day 3
DRIVE_FOLDER = "تذاكر الصيانة المحذوفة"
RETRY_HOURS = 6                  # a failed save is retried, but not every hour
PER_RUN = 10                     # Discord rate-limits channel deletion hard
PAUSE = 1.5
LOOP_MINUTES = 60

_HOST = None
_RUNNING = {"run": False}
_RIYADH = timezone(timedelta(hours=3))


def _now():
    return datetime.now(_RIYADH)


def _iso(d):
    return d.isoformat(timespec="seconds")


def _parse(s):
    try:
        d = datetime.fromisoformat(str(s))
    except (TypeError, ValueError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=_RIYADH)


# ------------------------------------------------------------------ pure rules

def delete_on(closed_at, days=DELETE_AFTER_DAYS):
    """'YYYY-MM-DD' the room goes: the close DATE (Riyadh) + `days`."""
    d = _parse(closed_at) or _now()
    return (d.astimezone(_RIYADH).date() + timedelta(days=days)).isoformat()


def due(tickets, now):
    """[(channel_id, rec)] whose room may be saved + deleted now. PURE."""
    out = []
    today = now.astimezone(_RIYADH).date().isoformat()
    for cid, rec in (tickets or {}).items():
        if not isinstance(rec, dict) or rec.get("kind") != "maint":
            continue
        if rec.get("status") != "closed" or not rec.get("delete_on"):
            continue
        if rec.get("room_deleted_at") or rec.get("cleanup_refused"):
            continue
        if str(rec["delete_on"]) > today:
            continue
        tried = _parse(rec.get("cleanup_tried_at"))
        if tried and now - tried < timedelta(hours=RETRY_HOURS):
            continue
        out.append((str(cid), rec))
    out.sort(key=lambda x: str(x[1].get("delete_on")))
    return out


def room_is_ours(ch):
    """The stored id must still point at a CLOSED maintenance room."""
    name = getattr(ch, "name", "") or ""
    topic = getattr(ch, "topic", "") or ""
    return name.startswith("مغلقة-") and "ouja-ticket:maint" in topic


def save_ok(entry):
    return bool(entry.get("completed") and entry.get("readable") is True
                and not entry.get("failed_attachments"))


# ------------------------------------------------------------------ the run

def _text_dir():
    d = os.path.join(os.environ.get("STATE_DIR", "/data"), "maint_transcripts")
    os.makedirs(d, exist_ok=True)
    return d


async def _text_copy(ch, cid):
    """A small text-only copy on the bot's disk (files live in Drive, never here)."""
    rows = []
    async for m in ch.history(limit=None, oldest_first=True):
        rows.append({"at": _iso(m.created_at) if getattr(m, "created_at", None) else "",
                     "author": str(getattr(m, "author", "") or ""),
                     "content": getattr(m, "content", "") or "",
                     "files": [getattr(a, "filename", "") for a in (getattr(m, "attachments", None) or [])]})
    path = os.path.join(_text_dir(), "%s.json" % cid)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"channel_id": cid, "name": getattr(ch, "name", ""), "messages": rows},
                  f, ensure_ascii=False)
    return len(rows)


async def _get_channel(guild, cid):
    ch = guild.get_channel(int(cid)) if hasattr(guild, "get_channel") else None
    if ch is None and hasattr(guild, "fetch_channel"):
        try:
            ch = await guild.fetch_channel(int(cid))
        except Exception as e:
            if type(e).__name__ == "NotFound":
                return None
            raise
    return ch


def _dash_note(host, rec, what):
    try:
        dash = host._dash_ticket(rec.get("dash_id"))
        if dash is not None:
            host._ticket_log(dash, "النظام", what)
            host._save_json("tickets.json", host._tickets[:1000])
    except Exception as e:
        print("[maint_cleanup] dashboard note skipped:", e)


async def run(guild, host, now=None, sink=None, pause=PAUSE, limit=PER_RUN):
    """One pass. -> {"deleted": [...], "kept": [...], "blocked": "" | reason}."""
    now = now or _now()
    rep = {"deleted": [], "kept": [], "blocked": ""}
    if _RUNNING["run"]:
        rep["blocked"] = "running"
        return rep
    todo = due(host._dtk.get("tickets", {}), now)[:limit]
    if not todo:
        return rep
    sink = sink or ops_archive.DriveSink(host)
    if not sink.configured():
        rep["blocked"] = "drive"
        return rep
    _RUNNING["run"] = True
    try:
        root = await asyncio.to_thread(sink.folder, sink.root_id(), ops_archive.ARCHIVE_ROOT_NAME)
        top = await asyncio.to_thread(sink.folder, root, DRIVE_FOLDER)
        month = await asyncio.to_thread(sink.folder, top, now.strftime("%Y-%m"))
        for i, (cid, rec) in enumerate(todo):
            rec["cleanup_tried_at"] = _iso(now)
            try:
                ch = await _get_channel(guild, cid)
            except Exception as e:
                rec["cleanup_error"] = "fetch: %s" % e
                rep["kept"].append(cid)
                continue
            if ch is None:
                rec["room_deleted_at"] = _iso(now)
                rec["cleanup_note"] = "كانت محذوفة"
                continue
            if not room_is_ours(ch):
                rec["cleanup_refused"] = "name/topic: %s | %s" % (
                    getattr(ch, "name", ""), (getattr(ch, "topic", "") or "")[:80])
                rep["kept"].append(cid)
                continue
            entry = ops_archive._entry_skeleton(ch)
            try:
                entry = await ops_archive._archive_channel(ch, sink, month, entry)
            except Exception as e:
                rec["cleanup_error"] = "drive: %s: %s" % (type(e).__name__, e)
                rep["kept"].append(cid)
                continue
            if not save_ok(entry):
                rec["cleanup_error"] = "save incomplete: %s file(s) failed, readable=%s" % (
                    len(entry.get("failed_attachments") or []), entry.get("readable"))
                rep["kept"].append(cid)
                continue
            url = ops_archive.DriveSink.folder_url(entry.get("drive_folder_id"))
            try:
                await _text_copy(ch, cid)
            except Exception as e:
                print("[maint_cleanup] text copy skipped (Drive has it):", cid, e)
            rec.update({"archive_url": url, "archived_at": _iso(now),
                        "archive_messages": entry.get("messages"),
                        "archive_files": entry.get("attachments")})
            rec.pop("cleanup_error", None)
            try:
                await ch.delete(reason="تذكرة صيانة مقفلة — انحفظت في Drive، تنحذف اليوم الثالث")
            except Exception as e:
                rec["cleanup_error"] = "delete: %s" % e
                rep["kept"].append(cid)
                continue
            rec["room_deleted_at"] = _iso(now)
            _dash_note(host, rec, "📦 غرفة الديسكورد انحذفت (اليوم الثالث). نسخة كاملة بالصور "
                                  "والفواتير في Drive: %s" % url)
            rep["deleted"].append(cid)
            if pause and i < len(todo) - 1:
                await asyncio.sleep(pause)
    finally:
        _RUNNING["run"] = False
        try:
            host._dtk_save()
        except Exception as e:
            print("[maint_cleanup] save failed:", e)
    return rep


def status(host, now=None):
    now = now or _now()
    recs = [r for r in (host._dtk.get("tickets", {}) or {}).values()
            if isinstance(r, dict) and r.get("kind") == "maint"]
    stamped = [r for r in recs if r.get("delete_on")]
    return {"waiting": sum(1 for r in stamped if not r.get("room_deleted_at")
                           and not r.get("cleanup_refused")),
            "due_now": len(due(host._dtk.get("tickets", {}), now)),
            "deleted": sum(1 for r in stamped if r.get("room_deleted_at")),
            "refused": sum(1 for r in stamped if r.get("cleanup_refused")),
            "errors": [r.get("cleanup_error") for r in stamped
                       if r.get("cleanup_error") and not r.get("room_deleted_at")][:3],
            "drive": ops_archive.DriveSink(host).configured()}


def status_text(s, rep=None):
    lines = ["🧹 **تنظيف تذاكر الصيانة** — الغرفة تنحفظ في Drive وتنحذف اليوم الثالث بعد القفل"]
    if not s["drive"]:
        lines.append("⚠️ Google Drive مو مربوط — ما راح تنحذف أي غرفة لين ينربط (ما نحذف بدون نسخة).")
    lines.append("تنتظر: %d · جاهزة الحين: %d · انحذفت: %d" % (s["waiting"], s["due_now"], s["deleted"]))
    if s["refused"]:
        lines.append("رفضت أحذف %d غرفة (اسمها أو وصفها تغيّر)." % s["refused"])
    for e in s["errors"]:
        lines.append("• آخر خطأ: %s" % str(e)[:160])
    if rep is not None:
        lines.append("")
        if rep.get("blocked") == "drive":
            lines.append("⏸️ ما انحذف شي: Drive مو مربوط.")
        elif rep.get("blocked") == "running":
            lines.append("⏳ فيه تنظيف شغال الحين.")
        else:
            lines.append("✅ انحذفت %d · بقت %d" % (len(rep["deleted"]), len(rep["kept"])))
    return chr(10).join(lines)[:1900]


# ------------------------------------------------------------------ the wire

def setup(bot, host=None):
    """Hourly pass + the status command. Called once from bot.py."""
    global _HOST
    _HOST = host
    started = {"loop": False}

    def _guild():
        gid = int(getattr(host, "GUILD_ID", 0) or 0)
        return bot.get_guild(gid) if gid else (bot.guilds[0] if bot.guilds else None)

    async def _loop():
        await asyncio.sleep(120)                  # let the bot settle after a deploy
        while True:
            try:
                g = _guild()
                if g is not None:
                    rep = await run(g, host)
                    if rep["deleted"] or rep["kept"]:
                        print("[maint_cleanup] deleted=%d kept=%d" % (len(rep["deleted"]), len(rep["kept"])))
            except Exception as e:
                print("[maint_cleanup] pass failed:", type(e).__name__, e)
            await asyncio.sleep(LOOP_MINUTES * 60)

    async def _on_ready():
        if not started["loop"]:
            started["loop"] = True
            asyncio.get_running_loop().create_task(_loop())

    async def _on_message(message):
        try:
            if getattr(message.author, "bot", False):
                return
            parts = (message.content or "").strip().split()
            if not parts or parts[0].lower() != TRIGGER:
                return
            if not ops_archive._may_archive(message):
                await ops_archive._reply(message, "🚫 هذا الأمر للإدارة فقط.")
                return
            rep = None
            if len(parts) > 1 and parts[1].lower() == "run":
                g = message.guild or _guild()
                rep = await run(g, host)
            await ops_archive._reply(message, status_text(status(host), rep))
        except Exception as e:
            print("maint_cleanup listener error:", type(e).__name__, e)

    bot.add_listener(_on_ready, "on_ready")
    bot.add_listener(_on_message, "on_message")
    print("maint_cleanup: hourly day-3 pass + !ouja-maint-clean registered")
    return _on_message
