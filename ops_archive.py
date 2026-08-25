# -*- coding: utf-8 -*-
"""ops_archive — full-fidelity Discord archive (+ a guarded purge) for Ouja Residence.

Why this exists
---------------
The server sits at 244 of Discord's 500 channels. `!ouja-audit` proved 85 of them
are dead and 49 more only LOOK dead (the bot cannot read them). Before anything is
deleted, every single channel — alive, dead, and unreadable — has to exist somewhere
outside Discord, with its files, forever.

The one rule that makes this real
---------------------------------
Discord CDN attachment URLs are SIGNED and expire in ~24 hours. An archive that
stores links is worthless by tomorrow. So every attachment is DOWNLOADED
(`attachment.read()` -> bytes) and the bytes themselves are uploaded to Drive. A URL
is only ever recorded as extra metadata, never as the backup.

Contract with the rest of the bot
---------------------------------
* Self-contained. `bot.py` only does `import ops_archive` + `ops_archive.setup(bot, host)`.
  `host` is bot.py's own live module object — this file must NEVER `import bot`
  (bot.py runs as __main__; importing it by name would boot a second bot). Same
  contract the `finance/` package uses.
* It reuses bot.py's EXISTING Google Drive client (the cleanproof one). It does not
  build a second Drive integration and it does not read a second set of credentials.
* No Drive => ABORT. Never a silent fallback to the Railway disk: that volume does
  not survive a redeploy, so a "backup" living there is not a backup.
* It can never take the bot down: every handler is wrapped, and Drive/network work
  runs off the event loop via asyncio.to_thread so guests and turnovers keep flowing.
* Deleting is a separate command, gated four ways (see PURGE below).

Triggers
--------
    !ouja-archive           start (refuses if an unfinished run from today exists)
    !ouja-archive resume    continue the unfinished run, skipping finished channels
    !ouja-archive fresh     throw away today's progress and start over
    !ouja-purge             delete ONLY the confirmed-dead channels from today's manifest

Note on the prefix: the bot's command prefix is "!ouja " (with a space), so
"!ouja-archive" / "!ouja-purge" are NOT prefix commands and cannot collide with
`process_commands`.
"""

import asyncio
import hashlib
import html as _html
import io
import json
import os
import re
import traceback
from datetime import datetime, timedelta, timezone

import discord

# ---------------------------------------------------------------- constants
TRIGGER_ARCHIVE = "!ouja-archive"
TRIGGER_PURGE   = "!ouja-purge"

ARCHIVE_ROOT_NAME = "Ouja Archive"    # top folder created inside the existing Drive root

STALE_DAYS      = 60          # same definition the audit used: dead = no message in 60 days
ATTACH_RETRIES  = 2           # retries AFTER the first attempt (so 3 tries total)
ATTACH_BACKOFF  = 1.5         # seconds, multiplied by the attempt number

CHANNEL_PAUSE   = 1.0         # breather between channels (Discord is strict)
MSG_PAUSE_EVERY = 500         # messages between breathers inside one channel
MSG_PAUSE       = 1.0
PROGRESS_EVERY  = 6.0         # seconds between status-message edits (ONE message, edited)

PURGE_PAUSE     = 1.5         # Discord rate-limits channel deletion very hard
CONFIRM_WORD    = "احذف"      # the owner must TYPE this. A button is not enough.
CONFIRM_TIMEOUT = 300         # seconds to type it

SUMMARY_MAX     = 1900        # Discord's limit is 2000; leave headroom

_RUNNING = {"archive": False, "purge": False}   # one at a time, per process


# ------------------------------------------------------------ small helpers
def _now():
    return datetime.now(timezone.utc)


def _iso(dt):
    if not dt:
        return None
    try:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return str(dt)


def _parse_iso(s):
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _type_name(obj):
    t = getattr(obj, "type", None)
    if t is None:
        return "unknown"
    return getattr(t, "name", None) or str(t)


def _is_category(ch):
    return _type_name(ch) == "category"


def _archivable(ch):
    """Anything that holds messages. Categories and objects with no history API out."""
    return (not _is_category(ch)) and hasattr(ch, "history")


def _safe_name(name, fallback="file"):
    """Drive/OS-safe file or folder name. Never empty, never a path."""
    s = str(name or "").replace("/", "-").replace("\\", "-").strip()
    s = re.sub(r"[\x00-\x1f]", "", s)
    return (s or fallback)[:120]


def _human_bytes(n):
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%.0f %s" % (n, unit)) if unit == "B" else ("%.1f %s" % (n, unit))
        n /= 1024
    return "%.1f GB" % n


def _state_dir():
    base = os.environ.get("STATE_DIR", "/data")
    d = os.path.join(base, "ops_archive")
    os.makedirs(d, exist_ok=True)
    return d


def _state_path():
    return os.path.join(_state_dir(), "state.json")


def _manifest_path(day):
    return os.path.join(_state_dir(), "manifest_%s.json" % day)


def _read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _is_owner(message):
    owner_id = (os.environ.get("OWNER_DISCORD_ID") or "").strip()
    return bool(owner_id) and str(getattr(message.author, "id", "")) == owner_id


def _is_admin(message):
    perms = getattr(message.author, "guild_permissions", None)
    return bool(perms is not None and getattr(perms, "administrator", False))


def _may_archive(message):
    """Owner by id, else any guild administrator — same gate as !ouja-audit."""
    return _is_owner(message) or _is_admin(message)


def _may_purge(message):
    """Stricter: the owner ONLY when OWNER_DISCORD_ID is set (deletion is forever).
    With no OWNER_DISCORD_ID configured it falls back to guild administrators."""
    if (os.environ.get("OWNER_DISCORD_ID") or "").strip():
        return _is_owner(message)
    return _is_admin(message)


def _purge_dryrun():
    return (os.environ.get("ARCHIVE_PURGE_DRYRUN", "1") or "1").strip() != "0"


# ------------------------------------------------------------------- storage
class DriveSink:
    """Where the archive writes.

    Deliberately thin: the Drive client, the credentials and the find-or-create-folder
    helper all come from bot.py's EXISTING cleanproof integration. The only thing this
    class adds is a generic "upload these bytes" call, because the cleanproof one is
    hard-wired to a cleaning report.

    Every method here is BLOCKING (googleapiclient is sync) — callers must go through
    asyncio.to_thread so the live bot keeps serving guests.
    """

    def __init__(self, host):
        self.host = host
        self._service = None

    def configured(self):
        try:
            return bool(self.host is not None and self.host._cleanproof_drive_configured())
        except Exception:
            return False

    def root_id(self):
        return getattr(self.host, "CLEANING_DRIVE_ROOT_FOLDER_ID", "") or ""

    def _svc(self):
        if self._service is None:
            svc = self.host._cleanproof_get_drive_service()
            if svc is None:
                raise RuntimeError("Google Drive is not configured")
            self._service = svc
        return self._service

    def folder(self, parent_id, name):
        return self.host._cleanproof_drive_find_or_create_folder(self._svc(), parent_id, name)

    def upload(self, folder_id, filename, data, mime=None):
        from googleapiclient.http import MediaIoBaseUpload
        media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime or "application/octet-stream",
                                  resumable=True)
        created = self._svc().files().create(
            body={"name": filename, "parents": [folder_id]},
            media_body=media, fields="id,webViewLink", supportsAllDrives=True).execute()
        fid = created.get("id", "")
        return {"id": fid,
                "url": created.get("webViewLink") or ("https://drive.google.com/file/d/%s/view" % fid)}

    @staticmethod
    def folder_url(folder_id):
        return "https://drive.google.com/drive/folders/%s" % folder_id if folder_id else ""


# ------------------------------------------------------------- message model
def _message_row(msg):
    """One archived message. Pure — no I/O, so tests can assert the shape."""
    author = getattr(msg, "author", None)
    ref = getattr(msg, "reference", None)
    embeds = []
    for e in (getattr(msg, "embeds", None) or []):
        try:
            embeds.append(e.to_dict())
        except Exception:
            embeds.append({"unreadable_embed": str(e)[:400]})
    reactions = []
    for r in (getattr(msg, "reactions", None) or []):
        try:
            reactions.append({"emoji": str(getattr(r, "emoji", "")), "count": getattr(r, "count", None)})
        except Exception:
            pass
    return {
        "id": str(getattr(msg, "id", "")),
        "ts": _iso(getattr(msg, "created_at", None)),
        "edited_ts": _iso(getattr(msg, "edited_at", None)),
        "author_name": str(getattr(author, "display_name", None) or getattr(author, "name", "") or ""),
        "author_username": str(author) if author is not None else "",
        "author_id": str(getattr(author, "id", "") or ""),
        "is_bot": bool(getattr(author, "bot", False)),
        "content": getattr(msg, "content", "") or "",
        "reply_to": str(getattr(ref, "message_id", "") or "") or None,
        "embeds": embeds,
        "reactions": reactions,
        "pinned": bool(getattr(msg, "pinned", False)),
        "attachments": [],          # filled in as the bytes actually land in Drive
    }


# ---------------------------------------------------------------- transcript
_TRANSCRIPT_CSS = """
:root { color-scheme: light dark; }
body { margin:0; padding:24px; background:#fbfaf8; color:#1c1a17;
       font-family:"IBM Plex Sans Arabic","Segoe UI",Tahoma,sans-serif; line-height:1.6; }
h1 { font-size:20px; margin:0 0 4px; }
.meta { color:#6b6459; font-size:13px; margin-bottom:20px; }
.m { display:flex; gap:12px; padding:10px 12px; border-radius:10px; }
.m + .m { margin-top:2px; }
.m:nth-child(even) { background:#f4f1ec; }
.who { font-weight:600; min-width:150px; }
.who .u { display:block; font-weight:400; font-size:11px; color:#8a8175; }
.body { flex:1; min-width:0; }
.t { color:#8a8175; font-size:11px; font-family:ui-monospace,monospace; }
.txt { white-space:pre-wrap; overflow-wrap:anywhere; }
.bot { color:#9a7b26; font-size:11px; }
.att { margin-top:6px; }
.att img { max-width:min(420px,100%); border-radius:8px; display:block; }
.att a { color:#7a5f18; font-size:12px; }
.sys { color:#8a8175; font-size:12px; font-style:italic; }
.none { color:#8a8175; padding:24px; text-align:center; }
"""


def build_transcript(meta, rows):
    """A readable RTL page. Images point at the RELATIVE files/ path, so downloading
    the channel folder and opening this file shows the whole history with pictures.
    Each image also carries its Drive link, because Google Drive's own preview cannot
    resolve relative paths."""
    out = [
        "<!doctype html>",
        '<html dir="rtl" lang="ar"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        "<title>%s</title>" % _html.escape(str(meta.get("name") or "channel")),
        "<style>%s</style></head><body>" % _TRANSCRIPT_CSS,
        "<h1>#%s</h1>" % _html.escape(str(meta.get("name") or "")),
        '<div class="meta">%s · %s رسالة · أُرشفت %s</div>' % (
            _html.escape(str(meta.get("category") or "بدون تصنيف")),
            len(rows), _html.escape(str(meta.get("archived_at") or "")[:19])),
    ]
    if not rows:
        out.append('<div class="none">ما فيها ولا رسالة.</div>')
    for r in rows:
        who = _html.escape(r.get("author_name") or "?")
        user = _html.escape(r.get("author_username") or "")
        ts = _html.escape((r.get("ts") or "")[:19].replace("T", " "))
        body = ['<div class="m"><div class="who">%s<span class="u">%s</span></div><div class="body">' % (who, user)]
        badge = '<span class="bot">bot</span> ' if r.get("is_bot") else ""
        body.append('<div class="t">%s%s%s</div>' % (
            badge, ts, " · رد على رسالة" if r.get("reply_to") else ""))
        if r.get("content"):
            body.append('<div class="txt">%s</div>' % _html.escape(r["content"]))
        for a in (r.get("attachments") or []):
            path = "files/" + _html.escape(a.get("stored_as") or "")
            label = _html.escape(a.get("filename") or "file")
            if a.get("failed"):
                body.append('<div class="att sys">⚠️ مرفق ما انحفظ: %s — %s</div>'
                            % (label, _html.escape(str(a.get("error") or ""))))
            elif str(a.get("content_type") or "").startswith("image/"):
                body.append('<div class="att"><img src="%s" alt="%s" loading="lazy">'
                            '<a href="%s">%s · %s</a></div>'
                            % (path, label, _html.escape(a.get("drive_url") or path),
                               label, _human_bytes(a.get("size"))))
            else:
                body.append('<div class="att"><a href="%s">📎 %s · %s</a></div>'
                            % (path, label, _human_bytes(a.get("size"))))
        if r.get("embeds"):
            body.append('<div class="sys">— %d بطاقة/embed محفوظة داخل messages.json</div>' % len(r["embeds"]))
        body.append("</div></div>")
        out.append("".join(body))
    out.append("</body></html>")
    return "\n".join(out).encode("utf-8")


# --------------------------------------------------------------- the archive
def _new_state(guild, day):
    return {
        "date": day,
        "guild_id": str(getattr(guild, "id", "")),
        "guild_name": getattr(guild, "name", "?"),
        "started_at": _iso(_now()),
        "root_folder_id": "",
        "date_folder_id": "",
        "channels": {},
    }


def _entry_skeleton(ch):
    cat = getattr(ch, "category", None)
    return {
        "id": str(getattr(ch, "id", "")),
        "name": getattr(ch, "name", "?"),
        "type": _type_name(ch),
        "category": getattr(cat, "name", None),
        "readable": None,
        "reason": None,
        "messages": 0,
        "attachments": 0,
        "bytes": 0,
        "failed_attachments": [],
        "last_message_id": None,
        "last_message_at": None,
        "drive_folder_id": "",
        "messages_sha256": "",
        "completed": False,
        "archived_at": None,
    }


async def _archive_channel(ch, sink, date_folder_id, entry, tick=None):
    """Archive ONE channel into Drive. Mutates + returns `entry`.

    Unreadable channels are NOT skipped: they still get a folder and a messages.json
    saying {"unreadable": true, ...} so the archive is a complete, honest index.
    """
    cat_name = _safe_name(getattr(getattr(ch, "category", None), "name", None) or "بدون-تصنيف", "بدون-تصنيف")
    cat_folder = await asyncio.to_thread(sink.folder, date_folder_id, cat_name)
    ch_folder = await asyncio.to_thread(sink.folder, cat_folder, _safe_name(getattr(ch, "name", "channel"), "channel"))
    entry["drive_folder_id"] = ch_folder

    rows, files_folder, seq = [], "", 0
    unreadable_reason = None
    try:
        async for msg in ch.history(limit=None, oldest_first=True):
            row = _message_row(msg)
            for att in (getattr(msg, "attachments", None) or []):
                seq += 1
                stored_as = "%03d_%s" % (seq, _safe_name(getattr(att, "filename", "file")))
                rec = {
                    "filename": getattr(att, "filename", "file"),
                    "stored_as": stored_as,
                    "size": getattr(att, "size", None),
                    "content_type": getattr(att, "content_type", None) or "",
                    "source_url": getattr(att, "url", ""),      # metadata only — it EXPIRES
                }
                data, err = None, None
                for attempt in range(1 + ATTACH_RETRIES):
                    try:
                        data = await att.read()               # <-- the BYTES. never the URL.
                        break
                    except Exception as e:
                        err = "%s: %s" % (type(e).__name__, e)
                        if attempt < ATTACH_RETRIES:
                            await asyncio.sleep(ATTACH_BACKOFF * (attempt + 1))
                if data is None:
                    rec["failed"] = True
                    rec["error"] = err or "unknown"
                    entry["failed_attachments"].append({"message_id": row["id"], **rec})
                else:
                    if not files_folder:
                        files_folder = await asyncio.to_thread(sink.folder, ch_folder, "files")
                    try:
                        up = await asyncio.to_thread(sink.upload, files_folder, stored_as, data,
                                                     rec["content_type"])
                        rec["drive_file_id"] = up.get("id", "")
                        rec["drive_url"] = up.get("url", "")
                        rec["size"] = rec["size"] or len(data)
                        entry["attachments"] += 1
                        entry["bytes"] += len(data)
                    except Exception as e:
                        rec["failed"] = True
                        rec["error"] = "drive: %s: %s" % (type(e).__name__, e)
                        entry["failed_attachments"].append({"message_id": row["id"], **rec})
                row["attachments"].append(rec)
            rows.append(row)
            if len(rows) % MSG_PAUSE_EVERY == 0:
                await asyncio.sleep(MSG_PAUSE)
                if tick:
                    await tick(entry, len(rows))
            else:
                await asyncio.sleep(0)          # never hog the event loop
        entry["readable"] = True
    except discord.Forbidden:
        unreadable_reason = "forbidden — البوت ما عنده صلاحية يقرأ هذي القناة"
    except Exception as e:
        unreadable_reason = "%s: %s" % (type(e).__name__, e)

    if unreadable_reason is not None:
        entry["readable"] = False
        entry["reason"] = unreadable_reason
        payload = json.dumps({"unreadable": True, "reason": unreadable_reason,
                              "channel": {k: entry[k] for k in ("id", "name", "type", "category")},
                              "archived_at": _iso(_now())},
                             ensure_ascii=False, indent=2).encode("utf-8")
    else:
        entry["messages"] = len(rows)
        if rows:
            entry["last_message_id"] = rows[-1]["id"]
            entry["last_message_at"] = rows[-1]["ts"]
        payload = json.dumps({"unreadable": False,
                              "channel": {k: entry[k] for k in ("id", "name", "type", "category")},
                              "archived_at": _iso(_now()),
                              "message_count": len(rows),
                              "messages": rows},
                             ensure_ascii=False, indent=2).encode("utf-8")

    entry["messages_sha256"] = hashlib.sha256(payload).hexdigest()
    await asyncio.to_thread(sink.upload, ch_folder, "messages.json", payload, "application/json")

    meta = dict(entry)
    meta["archived_at"] = _iso(_now())
    tpayload = build_transcript(meta, rows)
    await asyncio.to_thread(sink.upload, ch_folder, "transcript.html", tpayload, "text/html")

    entry["archived_at"] = _iso(_now())
    entry["completed"] = True
    return entry


def build_manifest(state, channels_order=None):
    """Pure: the manifest is just the finished state, totalled up."""
    entries = list((state.get("channels") or {}).values())
    if channels_order:
        pos = {str(c): i for i, c in enumerate(channels_order)}
        entries.sort(key=lambda e: pos.get(str(e.get("id")), 10 ** 6))
    readable = [e for e in entries if e.get("readable")]
    return {
        "date": state.get("date"),
        "guild": {"id": state.get("guild_id"), "name": state.get("guild_name")},
        "started_at": state.get("started_at"),
        "generated_at": _iso(_now()),
        "drive_folder_id": state.get("date_folder_id", ""),
        "drive_folder_url": DriveSink.folder_url(state.get("date_folder_id", "")),
        "totals": {
            "channels": len(entries),
            "readable": len(readable),
            "unreadable": len(entries) - len(readable),
            "messages": sum(int(e.get("messages") or 0) for e in entries),
            "attachments": sum(int(e.get("attachments") or 0) for e in entries),
            "bytes": sum(int(e.get("bytes") or 0) for e in entries),
            "failed_attachments": sum(len(e.get("failed_attachments") or []) for e in entries),
        },
        "channels": entries,
    }


async def archive_guild(guild, sink, day=None, state=None, progress=None):
    """Walk EVERY message-bearing channel and mirror it into Drive. Returns the manifest.

    `state` (resume): channels already marked completed are skipped untouched.
    """
    day = day or _now().date().isoformat()
    state = state or _new_state(guild, day)
    state.setdefault("channels", {})

    channels = [c for c in (getattr(guild, "channels", []) or []) if _archivable(c)]
    channels.sort(key=lambda c: (str(getattr(getattr(c, "category", None), "name", "") or ""),
                                 str(getattr(c, "name", ""))))

    if not state.get("root_folder_id"):
        state["root_folder_id"] = await asyncio.to_thread(sink.folder, sink.root_id(), ARCHIVE_ROOT_NAME)
    if not state.get("date_folder_id"):
        state["date_folder_id"] = await asyncio.to_thread(sink.folder, state["root_folder_id"], day)
    _save_state(state)

    total = len(channels)
    done = sum(1 for e in state["channels"].values() if e.get("completed"))
    last_tick = [0.0]

    async def emit(entry, msgs=None, force=False):
        if not progress:
            return
        loop_t = asyncio.get_event_loop().time()
        if not force and (loop_t - last_tick[0]) < PROGRESS_EVERY:
            return
        last_tick[0] = loop_t
        try:
            await progress(done, total, entry, msgs)
        except Exception:
            pass

    for ch in channels:
        cid = str(getattr(ch, "id", ""))
        prev = state["channels"].get(cid)
        if prev and prev.get("completed"):
            continue                                  # resume: already safely in Drive
        entry = _entry_skeleton(ch)
        state["channels"][cid] = entry
        await emit(entry, 0, force=True)
        try:
            await _archive_channel(ch, sink, state["date_folder_id"], entry,
                                   tick=lambda e, n: emit(e, n))
        except Exception as e:
            # A channel that blows up must not kill the run — record it and move on.
            entry["readable"] = False
            entry["reason"] = "archive_error: %s: %s" % (type(e).__name__, e)
            entry["completed"] = False
            print("ops_archive: channel failed", entry.get("name"), entry["reason"])
        done += 1
        state["updated_at"] = _iso(_now())
        _save_state(state)
        await emit(entry, entry.get("messages"), force=True)
        await asyncio.sleep(CHANNEL_PAUSE)

    manifest = build_manifest(state, [str(getattr(c, "id", "")) for c in channels])
    payload = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
    await asyncio.to_thread(sink.upload, state["date_folder_id"], "manifest.json", payload,
                            "application/json")
    _write_json(_manifest_path(day), manifest)
    state["finished_at"] = _iso(_now())
    _save_state(state)
    return manifest


def _save_state(state):
    try:
        _write_json(_state_path(), state)
    except Exception as e:
        print("ops_archive: could not save resume state:", e)


def load_state():
    return _read_json(_state_path(), None)


def load_manifest(day):
    return _read_json(_manifest_path(day), None)


# ----------------------------------------------------------------- the purge
def deletable(entry, now=None, stale_days=STALE_DAYS):
    """(ok, reason). The ONLY place that decides a channel may be deleted.

    Unreadable channels are never deletable — they only LOOK dead because the bot
    cannot see inside them.
    """
    now = now or _now()
    if not entry.get("completed"):
        return False, "الأرشفة ما اكتملت لهذي القناة"
    if not entry.get("readable"):
        return False, "البوت ما يقدر يقرأ القناة — ممنوع حذفها"
    if entry.get("type") != "text":
        return False, "ليست قناة نصية عادية"
    if not entry.get("messages_sha256"):
        return False, "ما فيه بصمة للأرشيف"
    if entry.get("failed_attachments"):
        return False, "فيه مرفقات ما انحفظت في الأرشيف"
    if not isinstance(entry.get("messages"), int):
        return False, "عدد الرسائل غير معروف"
    last = _parse_iso(entry.get("last_message_at"))
    if last is not None and (now - last) <= timedelta(days=stale_days):
        return False, "فيها رسائل خلال آخر %d يوم" % stale_days
    return True, ""


def purge_candidates(manifest, now=None, stale_days=STALE_DAYS):
    ok, blocked = [], []
    for e in (manifest.get("channels") or []):
        good, why = deletable(e, now=now, stale_days=stale_days)
        (ok if good else blocked).append(e if good else {**e, "blocked_reason": why})
    return ok, blocked


async def verify_unchanged(ch, entry):
    """(ok, reason) — re-read the channel NOW. Anything that moved since the archive
    is skipped, never deleted."""
    try:
        newest = None
        async for m in ch.history(limit=1):
            newest = m
            break
    except discord.Forbidden:
        return False, "صارت غير مقروءة"
    except Exception as e:
        return False, "%s: %s" % (type(e).__name__, e)
    newest_id = str(getattr(newest, "id", "")) if newest is not None else None
    if newest_id != (entry.get("last_message_id") or None):
        return False, "وصلتها رسالة جديدة بعد الأرشفة"
    if newest is not None:
        at = getattr(newest, "created_at", None)
        if at is not None and (_now() - (at if at.tzinfo else at.replace(tzinfo=timezone.utc))) \
                <= timedelta(days=STALE_DAYS):
            return False, "آخر رسالة أحدث من %d يوم" % STALE_DAYS
    return True, ""


async def run_purge(guild, manifest, dryrun=True, now=None, pause=PURGE_PAUSE, reason=""):
    """Delete the approved channels. Stops the WHOLE run on the first hard error and
    reports exactly what was already gone."""
    cands, blocked = purge_candidates(manifest, now=now)
    deleted, skipped, error = [], [], None
    by_id = {str(getattr(c, "id", "")): c for c in (getattr(guild, "channels", []) or [])}
    for e in cands:
        ch = by_id.get(str(e.get("id")))
        if ch is None:
            skipped.append({**e, "skip_reason": "القناة ما عادت موجودة"})
            continue
        ok, why = await verify_unchanged(ch, e)
        if not ok:
            skipped.append({**e, "skip_reason": why})
            continue
        if dryrun:
            skipped.append({**e, "skip_reason": "تجربة فقط (DRYRUN) — ما حذفنا شيء"})
            continue
        try:
            await ch.delete(reason=reason or "Ouja archive purge — archived to Drive first")
            deleted.append({"id": e.get("id"), "name": e.get("name")})
        except Exception as ex:
            error = "%s: %s — وقفنا كل شيء عند «%s»" % (type(ex).__name__, ex, e.get("name"))
            break
        await asyncio.sleep(pause)
    return {"deleted": deleted, "skipped": skipped, "blocked": blocked,
            "candidates": len(cands), "dryrun": bool(dryrun), "error": error}


# ------------------------------------------------------------------ handlers
def _archive_summary(manifest, resumed=False):
    t = manifest.get("totals") or {}
    lines = [
        "✅ **خلص الأرشيف** — كل القنوات صارت محفوظة في Google Drive"
        + (" (كمّلنا من وين وقفنا)" if resumed else ""),
        "",
        "📦 القنوات: **%d** (منها %d قدر يقرأها البوت، و%d مقفلة عليه)"
        % (t.get("channels", 0), t.get("readable", 0), t.get("unreadable", 0)),
        "💬 الرسائل: **%s**" % f"{t.get('messages', 0):,}",
        "📎 الملفات والصور: **%s** (%s) — محفوظة كملفات فعلية، مو روابط"
        % (f"{t.get('attachments', 0):,}", _human_bytes(t.get("bytes", 0))),
    ]
    if t.get("failed_attachments"):
        lines.append("⚠️ مرفقات ما انحفظت: **%d** — مكتوبة بالتفصيل داخل messages.json"
                     % t["failed_attachments"])
    url = manifest.get("drive_folder_url")
    if url:
        lines += ["", "📁 مجلد الأرشيف: %s" % url]
    lines += ["", "📎 ملف manifest.json مرفق — فيه كل قناة وعدد رسائلها وبصمتها.",
              "الخطوة الجاية (اختيارية): `!ouja-purge` يحذف **فقط** القنوات الميتة المؤكدة."]
    text = "\n".join(lines)
    return text[:SUMMARY_MAX]


async def handle_archive(message):
    parts = (message.content or "").strip().split()
    mode = (parts[1].lower() if len(parts) > 1 else "")
    if message.guild is None:
        await _reply(message, "هذا الأمر يشتغل داخل السيرفر فقط.")
        return
    if not _may_archive(message):
        await _reply(message, "🔒 هذا الأمر للمالك أو الأدمن فقط.")
        return
    if _RUNNING["archive"]:
        await _reply(message, "⏳ فيه أرشفة شغالة الحين — انتظرها تخلص.")
        return

    host = _HOST
    sink = DriveSink(host)
    if not sink.configured() or not sink.root_id():
        await _reply(message,
                     "❌ **ما أقدر أبدأ: Google Drive مو مربوط.**\n"
                     "الأرشيف لازم ينحفظ في Drive. قرص Railway ما ينفع — يروح مع أول تحديث، "
                     "فما راح أحفظ عليه أبد.\n"
                     "الحل: تأكد من `CLEANING_DRIVE_ROOT_FOLDER_ID` ومفتاح جوجل في Railway "
                     "(نفس اللي يستخدمه رفع صور التنظيف)، ثم أعد المحاولة.")
        return

    day = _now().date().isoformat()
    state = load_state()
    resumed = False
    if state and state.get("date") == day and mode != "fresh":
        finished = state.get("finished_at")
        if mode == "resume" or not finished:
            if mode != "resume" and not finished:
                await _reply(message,
                             "⚠️ فيه أرشفة اليوم ما كملت. اكتب `!ouja-archive resume` تكمل من وين وقفنا، "
                             "أو `!ouja-archive fresh` تبدأ من الصفر.")
                return
            resumed = True
        else:
            state = _new_state(message.guild, day)
    else:
        state = _new_state(message.guild, day)

    _RUNNING["archive"] = True
    status = None
    try:
        status = await message.reply(
            "⏳ أبدأ الأرشفة… راح أنزّل كل الرسائل وكل الصور والملفات وأرفعها لـ Google Drive.\n"
            "هذي تأخذ وقت طويل — بحدّث هذي الرسالة نفسها بالتقدم.", mention_author=False)
    except Exception:
        status = None

    async def progress(done, total, entry, msgs):
        if status is None:
            return
        extra = ("" if msgs is None else " · %s رسالة" % f"{msgs:,}")
        try:
            await status.edit(content="📦 %d/%d — «%s»%s\n(الأرشفة شغالة… ما راح أحذف أي شيء)"
                                      % (done, total, entry.get("name", "?"), extra))
        except Exception:
            pass

    try:
        manifest = await archive_guild(message.guild, sink, day=day, state=state, progress=progress)
        summary = _archive_summary(manifest, resumed=resumed)
        if status is not None:
            await status.edit(content=summary)
        else:
            await message.channel.send(summary)
        payload = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        await message.channel.send(files=[discord.File(io.BytesIO(payload),
                                                       filename="ouja_archive_manifest_%s.json" % day)])
    except Exception as e:
        err = "%s: %s" % (type(e).__name__, e)
        print("ops_archive error:", err)
        traceback.print_exc()
        note = ("❌ الأرشفة وقفت بخطأ. اللي خلص محفوظ في Drive — اكتب `!ouja-archive resume` "
                "تكمل من وين وقفنا.\nابعث هذا السطر لفيصل:\n```\n" + err[:1400] + "\n```")
        try:
            if status is not None:
                await status.edit(content=note)
            else:
                await message.channel.send(note)
        except Exception:
            pass
    finally:
        _RUNNING["archive"] = False


def _purge_preview(manifest, cands, blocked, dryrun):
    head = "🧹 **تنظيف القنوات الميتة**" + (" — وضع التجربة (ما راح ينحذف شيء)" if dryrun else "")
    lines = [head, "",
             "📄 المانيفست: %s · قنوات مؤرشفة: %d" % (manifest.get("date"),
                                                      (manifest.get("totals") or {}).get("channels", 0)),
             "🗑 مرشّحة للحذف: **%d**" % len(cands),
             "🛡 محميّة (ما راح تنحذف): **%d**" % len(blocked), ""]
    for e in cands[:25]:
        lines.append("• %s — %s رسالة · آخر رسالة %s"
                     % (e.get("name"), e.get("messages"), (e.get("last_message_at") or "ولا رسالة")[:10]))
    if len(cands) > 25:
        lines.append("• … و%d قناة ثانية (القائمة كاملة في الملف المرفق)" % (len(cands) - 25))
    if not dryrun:
        lines += ["", "⚠️ الحذف نهائي وما فيه تراجع. القنوات كلها محفوظة في Drive.",
                  "اكتب كلمة **%s** خلال 5 دقائق عشان أبدأ. أي شيء ثاني = إلغاء." % CONFIRM_WORD]
    else:
        lines += ["", "ℹ️ `ARCHIVE_PURGE_DRYRUN=1` — هذي تجربة فقط. "
                      "لما تكون جاهز غيّرها لـ `0` في Railway وأعد الأمر."]
    return "\n".join(lines)[:SUMMARY_MAX]


async def handle_purge(message, bot=None):
    if message.guild is None:
        await _reply(message, "هذا الأمر يشتغل داخل السيرفر فقط.")
        return
    if not _may_purge(message):
        await _reply(message, "🔒 أمر الحذف للمالك فقط.")
        return
    if _RUNNING["purge"] or _RUNNING["archive"]:
        await _reply(message, "⏳ فيه عملية شغالة الحين — انتظرها تخلص.")
        return

    day = _now().date().isoformat()
    manifest = load_manifest(day)
    if not manifest:
        await _reply(message,
                     "❌ ما فيه أرشيف بتاريخ اليوم (%s).\n"
                     "الحذف ممنوع بدون أرشيف من نفس اليوم. شغّل `!ouja-archive` أول." % day)
        return

    cands, blocked = purge_candidates(manifest)
    dryrun = _purge_dryrun()
    full = json.dumps({"candidates": cands, "blocked": blocked}, ensure_ascii=False, indent=2)
    try:
        await message.channel.send(
            _purge_preview(manifest, cands, blocked, dryrun),
            files=[discord.File(io.BytesIO(full.encode("utf-8")),
                                filename="ouja_purge_plan_%s.json" % day)])
    except Exception:
        pass
    if not cands:
        await _reply(message, "ما فيه ولا قناة تستحق الحذف — كلها إما حيّة أو ما يقدر البوت يقرأها.")
        return

    if not dryrun:
        def check(m):
            return (m.author.id == message.author.id and m.channel.id == message.channel.id
                    and (m.content or "").strip() == CONFIRM_WORD)
        try:
            await bot.wait_for("message", check=check, timeout=CONFIRM_TIMEOUT)
        except Exception:
            await _reply(message, "⌛ ما وصلتني كلمة «%s» — ألغيت العملية، ما حذفت شيء." % CONFIRM_WORD)
            return

    _RUNNING["purge"] = True
    status = None
    try:
        status = await message.channel.send("🧹 أشتغل…")
    except Exception:
        pass
    try:
        res = await run_purge(message.guild, manifest, dryrun=dryrun,
                              reason="Ouja archive purge by %s" % message.author)
        lines = ["🧹 **خلص التنظيف**" + (" — تجربة فقط، ما انحذف ولا قناة" if res["dryrun"] else ""),
                 "🗑 انحذفت: **%d**" % len(res["deleted"]),
                 "⏭ تخطّينا: **%d**" % len(res["skipped"]),
                 "🛡 محميّة من الأصل: **%d**" % len(res["blocked"])]
        for s in res["skipped"][:10]:
            lines.append("• %s — %s" % (s.get("name"), s.get("skip_reason")))
        if res["error"]:
            lines += ["", "❌ وقفنا بخطأ: " + str(res["error"])[:500],
                      "اللي انحذف قبل الوقفة: " + (", ".join(d["name"] for d in res["deleted"]) or "ولا شيء")]
        out = "\n".join(lines)[:SUMMARY_MAX]
        if status is not None:
            await status.edit(content=out)
        else:
            await message.channel.send(out)
    except Exception as e:
        err = "%s: %s" % (type(e).__name__, e)
        print("ops_archive purge error:", err)
        traceback.print_exc()
        await _reply(message, "❌ التنظيف وقف بخطأ:\n```\n" + err[:1400] + "\n```")
    finally:
        _RUNNING["purge"] = False


async def _reply(message, text):
    try:
        await message.reply(text, mention_author=False)
    except Exception:
        try:
            await message.channel.send(text)
        except Exception:
            pass


# ------------------------------------------------------------------ the wire
_HOST = None      # bot.py's live module object (never `import bot` — see the docstring)


def setup(bot, host=None):
    """Register the archive + purge listeners. Called once from bot.py."""
    global _HOST
    _HOST = host

    async def _ops_archive_on_message(message):
        try:
            if getattr(message.author, "bot", False):
                return
            head = (message.content or "").strip().split(" ")[0].lower()
            if head == TRIGGER_ARCHIVE:
                await handle_archive(message)
            elif head == TRIGGER_PURGE:
                await handle_purge(message, bot=bot)
        except Exception as e:                       # belt AND braces
            print("ops_archive listener error:", type(e).__name__, e)

    bot.add_listener(_ops_archive_on_message, "on_message")
    print("ops_archive: !ouja-archive / !ouja-purge listeners registered")
    return _ops_archive_on_message
