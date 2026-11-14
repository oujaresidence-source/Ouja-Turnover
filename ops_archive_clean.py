# -*- coding: utf-8 -*-
"""ops_archive_clean — «!ouja-clean-archive»: save every room in «📦 أرشيف N» into the
dashboard, THEN delete it from Discord. Built 2026-11-14 for the 500-channel cap.

Owner rule, verbatim: «أهم شي تأكد إن غير الصور كل شي مسجل في الداشبورد».
So, per room:
  * every message, every bot card (embed) and every NON-photo file is written to the
    dashboard's own disk (STATE_DIR/discord_archive) and readable at /discord-archive;
  * photos are recorded as a line (name + size), their bytes are never downloaded;
  * the room is deleted ONLY when that save is complete: readable, a plain text room,
    fingerprinted, zero failed non-photo files, no threads, and no new message since.
Anything else is KEPT in Discord and the reason is reported. Kept is always safe.

Scope: only rooms whose category starts with «📦 أرشيف» (the ones !ouja-tidy and the
ticket close already moved there). Live rooms are never even read. Unlike !ouja-purge
there is no 60-day rule — these rooms are closed by definition.

Same safety switch as !ouja-purge: ARCHIVE_PURGE_DRYRUN=1 (the default) saves
everything and deletes nothing. Real deletion = 0 in Railway + the owner types «احذف».

Contract: never `import bot`. bot.py calls setup(bot, host) and register_routes(app).
This file has NO backslashes in PAGE_HTML (same trap as DASHBOARD_HTML).
"""

import asyncio
import json
import os
import shutil
import traceback

import ops_archive

TRIGGER = "!ouja-clean-archive"
ARCHIVE_PREFIX = "📦 أرشيف"
PHOTO_EXT = {"jpg", "jpeg", "png", "gif", "webp", "heic", "heif", "bmp", "tif", "tiff", "avif"}
PROGRESS_EVERY = 10          # rooms between status-message edits
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

_HOST = None


# ------------------------------------------------------------------ storage
def _store_dir():
    d = os.path.join(os.environ.get("STATE_DIR", "/data"), "discord_archive")
    os.makedirs(d, exist_ok=True)
    return d


def _rooms_dir():
    d = os.path.join(_store_dir(), "rooms")
    os.makedirs(d, exist_ok=True)
    return d


def _index_path():
    return os.path.join(_store_dir(), "index.json")


def _inside_store(path):
    root = os.path.realpath(_store_dir())
    p = os.path.realpath(path)
    return p == root or p.startswith(root + os.sep)


def _safe_part(name, fallback):
    s = ops_archive._safe_name(name, fallback)
    if s.startswith("."):
        s = "_" + s
    return s


class LocalSink:
    """The dashboard-side store. Same interface ops_archive._archive_channel writes to
    (folder / upload), so the proven archive code is reused, not copied."""

    def configured(self):
        return True

    def root_id(self):
        return _rooms_dir()

    def folder(self, parent_id, name):
        path = os.path.join(parent_id, _safe_part(name, "folder"))
        if not _inside_store(path):
            raise ValueError("path escapes the archive store")
        os.makedirs(path, exist_ok=True)
        return path

    def upload(self, folder_id, filename, data, mime=None):
        path = os.path.join(folder_id, _safe_part(filename, "file"))
        if not _inside_store(path):
            raise ValueError("path escapes the archive store")
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
        return {"id": path, "url": ""}


def load_index():
    return ops_archive._read_json(_index_path(), {}) or {}


def _save_index(idx):
    ops_archive._write_json(_index_path(), idx)


def _index_row(entry):
    return {
        "id": entry.get("id"), "name": entry.get("name"), "category": entry.get("category"),
        "type": entry.get("type"), "readable": entry.get("readable"),
        "reason": entry.get("reason"), "completed": entry.get("completed"),
        "messages": entry.get("messages"), "files": entry.get("attachments"),
        "bytes": entry.get("bytes"), "photos_skipped": int(entry.get("photos_skipped") or 0),
        "failed": len(entry.get("failed_attachments") or []),
        "last_message_id": entry.get("last_message_id"),
        "last_message_at": entry.get("last_message_at"),
        "sha256": entry.get("messages_sha256"), "folder": entry.get("drive_folder_id"),
        "archived_at": entry.get("archived_at"), "deleted_at": None,
    }


def saved_ok(row):
    """(ok, reason) — the ONLY gate between «saved» and «deleted»."""
    if not row.get("completed"):
        return False, "الحفظ ما اكتمل"
    if not row.get("readable"):
        return False, "البوت ما يقدر يقرأها"
    if row.get("type") != "text":
        return False, "مو روم نصي عادي"
    if not row.get("sha256"):
        return False, "ما فيه بصمة للحفظ"
    if row.get("failed"):
        return False, "فيه ملف (غير الصور) ما انحفظ"
    if not isinstance(row.get("messages"), int):
        return False, "عدد الرسائل غير معروف"
    if not row.get("folder") or not os.path.isfile(os.path.join(row["folder"], "messages.json")):
        return False, "ملف الحفظ مو موجود"
    return True, ""


def is_photo(att):
    ct = str(getattr(att, "content_type", "") or "").lower()
    if ct.startswith("image/"):
        return True
    fn = str(getattr(att, "filename", "") or "").lower()
    return "." in fn and fn.rsplit(".", 1)[1] in PHOTO_EXT


# ---------------------------------------------------------------- readers
def list_rooms():
    rows = list(load_index().values())
    rows.sort(key=lambda r: (r.get("deleted_at") or r.get("archived_at") or ""), reverse=True)
    return [{k: v for k, v in r.items() if k != "folder"} for r in rows]


def read_room(cid):
    row = load_index().get(str(cid))
    if not row or not row.get("folder"):
        return None
    path = os.path.join(row["folder"], "messages.json")
    if not _inside_store(path) or not os.path.isfile(path):
        return None
    data = ops_archive._read_json(path, None)
    if data is None:
        return None
    data["room"] = {k: v for k, v in row.items() if k != "folder"}
    return data


def read_file(cid, stored_as):
    s = str(stored_as or "")
    if not s or "/" in s or chr(92) in s or s.startswith("."):
        return None
    row = load_index().get(str(cid))
    if not row or not row.get("folder"):
        return None
    path = os.path.join(row["folder"], "files", s)
    if not _inside_store(path) or not os.path.isfile(path):
        return None
    with open(path, "rb") as f:
        return f.read()


# ---------------------------------------------------------------- discord
def _is_archive_cat(c):
    return str(getattr(c, "name", "") or "").startswith(ARCHIVE_PREFIX)


def _cat_index(name):
    tail = ""
    for ch in reversed(str(name or "").translate(_AR_DIGITS)):
        if ch.isdigit():
            tail = ch + tail
        else:
            break
    return int(tail) if tail else 0


def archive_categories(guild):
    cats = [c for c in (getattr(guild, "categories", []) or []) if _is_archive_cat(c)]
    cats.sort(key=lambda c: (_cat_index(c.name), getattr(c, "id", 0)))
    return cats


def archive_rooms(guild):
    ids = {getattr(c, "id", None) for c in archive_categories(guild)}
    return [ch for ch in (getattr(guild, "channels", []) or [])
            if not ops_archive._is_category(ch)
            and getattr(getattr(ch, "category", None), "id", None) in ids]


def preview(guild):
    return {"rooms": len(archive_rooms(guild)), "categories": len(archive_categories(guild)),
            "dryrun": ops_archive._purge_dryrun()}


async def _newest_id(ch):
    async for m in ch.history(limit=1):
        return str(getattr(m, "id", ""))
    return None


async def _has_threads(ch):
    if getattr(ch, "threads", None):
        return True
    fn = getattr(ch, "archived_threads", None)
    if fn is None:
        return False
    async for _t in fn(limit=1):
        return True
    return False


async def run_clean(guild, dryrun=True, pause=ops_archive.PURGE_PAUSE, reason="", progress=None):
    """Save every archive room, delete the ones that saved cleanly. Never raises for one
    room; stops the whole run on the first failed DELETE (Discord said no)."""
    cats = archive_categories(guild)
    rooms = archive_rooms(guild)
    idx = load_index()
    sink = LocalSink()
    saved, deleted, kept, would, error = 0, [], [], [], None

    for n, ch in enumerate(rooms, 1):
        cid = str(getattr(ch, "id", ""))
        base = {"id": cid, "name": getattr(ch, "name", "?"),
                "category": getattr(getattr(ch, "category", None), "name", None)}
        if progress and n % PROGRESS_EVERY == 0:
            try:
                await progress(n, len(rooms))
            except Exception:
                pass
        if ops_archive._type_name(ch) != "text":
            kept.append({**base, "reason": "مو روم نصي عادي"})
            continue
        try:
            if await _has_threads(ch):
                kept.append({**base, "reason": "فيها threads — حذفها يحذفها"})
                continue
            newest = await _newest_id(ch)
            row = idx.get(cid)
            fresh = not (row and saved_ok(row)[0] and row.get("last_message_id") == newest
                         and not row.get("deleted_at"))
            if fresh:
                room_dir = os.path.join(_rooms_dir(), _safe_part(cid, "room"))
                shutil.rmtree(room_dir, ignore_errors=True)
                os.makedirs(room_dir, exist_ok=True)
                entry = ops_archive._entry_skeleton(ch)
                entry["photos_skipped"] = 0
                await ops_archive._archive_channel(ch, sink, room_dir, entry,
                                                   keep_bytes=lambda a: not is_photo(a))
                row = _index_row(entry)
                idx[cid] = row
                _save_index(idx)
                saved += 1
            ok, why = saved_ok(row)
            if not ok:
                kept.append({**base, "reason": why})
                continue
            if fresh and await _newest_id(ch) != row.get("last_message_id"):
                kept.append({**base, "reason": "وصلتها رسالة جديدة وقت الحفظ"})
                continue
        except Exception as e:
            kept.append({**base, "reason": "%s: %s" % (type(e).__name__, e)})
            continue

        if dryrun:
            would.append(base)
            continue
        try:
            await ch.delete(reason=reason or "Ouja clean-archive — saved to the dashboard first")
        except Exception as e:
            error = "%s: %s — وقفنا عند «%s»" % (type(e).__name__, e, base["name"])
            break
        row["deleted_at"] = ops_archive._iso(ops_archive._now())
        _save_index(idx)
        deleted.append(base)
        if pause:
            await asyncio.sleep(pause)

    cats_deleted = []
    if not dryrun and error is None and cats:
        gone = {d["id"] for d in deleted}
        for c in cats[1:]:                       # the first archive category always stays
            left = [x for x in (getattr(c, "channels", []) or [])
                    if str(getattr(x, "id", "")) not in gone]
            if left:
                continue
            try:
                await c.delete(reason="Ouja clean-archive — empty archive category")
                cats_deleted.append(c.name)
            except Exception as e:
                error = "%s: %s — القسم «%s»" % (type(e).__name__, e, c.name)
                break
            if pause:
                await asyncio.sleep(pause)

    return {"rooms": len(rooms), "saved": saved, "deleted": deleted, "kept": kept,
            "would_delete": would, "categories_deleted": cats_deleted,
            "dryrun": bool(dryrun), "error": error}


# ---------------------------------------------------------------- the command
def _summary(rep):
    dry = rep["dryrun"]
    lines = ["🧹 **تنظيف الأرشيف — خلص**" + (" (تجربة: ما انحذف شيء)" if dry else ""),
             "📦 رومات الأرشيف: **%d**" % rep["rooms"],
             "💾 انحفظت في الداشبورد هالمرة: **%d**" % rep["saved"]]
    if dry:
        lines.append("🗑 جاهزة للحذف لما تشغّله فعلي: **%d**" % len(rep["would_delete"]))
    else:
        lines.append("🗑 انحذفت من ديسكورد: **%d**" % len(rep["deleted"]))
        if rep["categories_deleted"]:
            lines.append("🗂 أقسام أرشيف فاضية انحذفت: **%d**" % len(rep["categories_deleted"]))
    lines.append("🛡 بقت في ديسكورد (ما انحذفت): **%d**" % len(rep["kept"]))
    for k in rep["kept"][:10]:
        lines.append("• %s — %s" % (k.get("name"), k.get("reason")))
    if len(rep["kept"]) > 10:
        lines.append("• … و%d غيرها" % (len(rep["kept"]) - 10))
    if rep["error"]:
        lines += ["", "❌ وقفنا بخطأ: " + str(rep["error"])[:400]]
    lines += ["", "📖 تقرأها كلها من الداشبورد: **oujares.com/discord-archive** (للأدمن)"]
    if dry:
        lines += ["", "ℹ️ `ARCHIVE_PURGE_DRYRUN=1` — للحذف الفعلي غيّرها لـ `0` في Railway وأعد الأمر."]
    return "\n".join(lines)[:ops_archive.SUMMARY_MAX]


async def handle(message, bot):
    if message.guild is None:
        await ops_archive._reply(message, "هذا الأمر يشتغل داخل السيرفر فقط.")
        return
    if not ops_archive._may_purge(message):
        await ops_archive._reply(message, "🔒 هذا الأمر للمالك فقط.")
        return
    running = ops_archive._RUNNING
    if running.get("purge") or running.get("archive") or running.get("clean"):
        await ops_archive._reply(message, "⏳ فيه عملية أرشفة أو حذف شغالة — انتظرها تخلص.")
        return
    p = preview(message.guild)
    if not p["rooms"]:
        await ops_archive._reply(message, "✅ ما فيه ولا روم في أقسام «📦 أرشيف» — ما فيه شيء أسويه.")
        return
    dry = p["dryrun"]
    head = ["🧹 **تنظيف الأرشيف**" + (" — تجربة" if dry else ""),
            "📦 فيه **%d** روم في **%d** قسم أرشيف." % (p["rooms"], p["categories"]),
            "كل روم: أحفظ رسائله وبطاقاته وملفاته (غير الصور) في الداشبورد، وبعدها أحذفه.",
            "أي روم ما ينحفظ كامل = يبقى في ديسكورد."]
    if dry:
        head.append("ℹ️ وضع التجربة: بحفظ كل شيء وما بحذف ولا روم.")
    else:
        head += ["", "⚠️ الحذف من ديسكورد نهائي.",
                 "اكتب كلمة **%s** خلال 5 دقائق عشان أبدأ. أي شيء ثاني = إلغاء." % ops_archive.CONFIRM_WORD]
    await ops_archive._reply(message, "\n".join(head))
    if not dry:
        def check(m):
            return (m.author.id == message.author.id and m.channel.id == message.channel.id
                    and (m.content or "").strip() == ops_archive.CONFIRM_WORD)
        try:
            await bot.wait_for("message", check=check, timeout=ops_archive.CONFIRM_TIMEOUT)
        except Exception:
            await ops_archive._reply(message, "⌛ ما وصلتني كلمة «%s» — ألغيت، ما حذفت شيء."
                                     % ops_archive.CONFIRM_WORD)
            return

    running["clean"] = True
    status = None
    try:
        status = await message.channel.send("⏳ أشتغل… 0/%d" % p["rooms"])
    except Exception:
        pass

    async def progress(n, total):
        if status is not None:
            await status.edit(content="⏳ أشتغل… %d/%d" % (n, total))

    try:
        rep = await run_clean(message.guild, dryrun=dry, progress=progress,
                              reason="Ouja clean-archive by %s" % message.author)
        out = _summary(rep)
        if status is not None:
            await status.edit(content=out)
        else:
            await message.channel.send(out)
    except Exception as e:
        err = "%s: %s" % (type(e).__name__, e)
        print("ops_archive_clean error:", err)
        traceback.print_exc()
        await ops_archive._reply(message, "❌ وقف بخطأ: " + err[:1400])
    finally:
        running["clean"] = False


def setup(bot, host=None):
    global _HOST
    _HOST = host

    async def _clean_on_message(message):
        try:
            if getattr(message.author, "bot", False):
                return
            head = (message.content or "").strip().split(" ")[0].lower()
            if head == TRIGGER:
                await handle(message, bot)
        except Exception as e:
            print("ops_archive_clean listener error:", type(e).__name__, e)

    bot.add_listener(_clean_on_message, "on_message")
    print("ops_archive_clean: %s listener registered" % TRIGGER)
    return _clean_on_message


# ---------------------------------------------------------------- dashboard
def may_read(host, request):
    """Admins only — these rooms hold tickets, guests' details and money talk."""
    try:
        return bool(host is not None and host._dash_auth(request)
                    and host._req_role(request) == "admin")
    except Exception:
        return False


def _json(data, status=200):
    from aiohttp import web
    return web.json_response(data, status=status, dumps=lambda o: json.dumps(o, ensure_ascii=False))


def _deny():
    return _json({"ok": False, "error": "للأدمن فقط — سجّل دخول الداشبورد"}, 403)


async def api_rooms(request):
    if not may_read(_HOST, request):
        return _deny()
    rows = await asyncio.to_thread(list_rooms)
    return _json({"ok": True, "rooms": rows})


async def api_room(request):
    if not may_read(_HOST, request):
        return _deny()
    data = await asyncio.to_thread(read_room, request.match_info.get("cid"))
    if data is None:
        return _json({"ok": False, "error": "ما لقيت هالروم"}, 404)
    return _json({"ok": True, **data})


async def api_file(request):
    from aiohttp import web
    if not may_read(_HOST, request):
        return _deny()
    name = request.match_info.get("name")
    data = await asyncio.to_thread(read_file, request.match_info.get("cid"), name)
    if data is None:
        return _json({"ok": False, "error": "ما لقيت الملف"}, 404)
    return web.Response(body=data, content_type="application/octet-stream",
                        headers={"Content-Disposition": 'attachment; filename="%s"'
                                 % str(name).replace('"', "")})


async def page(request):
    from aiohttp import web
    return web.Response(text=PAGE_HTML, content_type="text/html")


def register_routes(app):
    g = app.router.add_get
    g("/discord-archive", page)
    g("/api/discord-archive/rooms", api_rooms)
    g("/api/discord-archive/room/{cid}", api_room)
    g("/api/discord-archive/file/{cid}/{name}", api_file)


PAGE_HTML = """<!doctype html>
<html dir="rtl" lang="ar"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>أرشيف ديسكورد · عوجا</title>
<style>
:root{--bg:#f7f4ef;--card:#fffdf9;--ink:#2a251e;--mute:#7a7064;--line:#e6dfd3;--gold:#9a7b26;--gold-soft:#f3ead3}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:"IBM Plex Sans Arabic","Segoe UI",Tahoma,sans-serif;line-height:1.6}
header{padding:18px 20px;border-bottom:1px solid var(--line);background:var(--card)}
h1{font-size:19px;margin:0}
.sub{color:var(--mute);font-size:13px}
.wrap{display:grid;grid-template-columns:320px 1fr;min-height:calc(100vh - 70px)}
aside{border-left:1px solid var(--line);background:var(--card);overflow:auto;max-height:calc(100vh - 70px)}
#q{width:calc(100% - 24px);margin:12px;padding:9px 12px;border:1px solid var(--line);border-radius:8px;font:inherit;background:var(--bg)}
.room{display:block;width:100%;text-align:right;padding:10px 14px;border:0;border-top:1px solid var(--line);background:none;font:inherit;cursor:pointer;color:inherit}
.room:hover,.room.on{background:var(--gold-soft)}
.room b{display:block;font-size:14px;font-weight:600}
.room span{color:var(--mute);font-size:12px}
main{padding:18px 22px;overflow:auto;max-height:calc(100vh - 70px)}
.m{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;margin-bottom:8px}
.who{font-weight:600;font-size:14px}
.t{color:var(--mute);font-size:12px;margin-inline-start:8px;font-weight:400}
.txt{white-space:pre-wrap;overflow-wrap:anywhere;margin-top:4px}
.emb{border-inline-start:3px solid var(--gold);background:var(--bg);padding:8px 12px;margin-top:6px;border-radius:6px;white-space:pre-wrap;overflow-wrap:anywhere}
.emb .et{font-weight:600}
.att{font-size:13px;margin-top:6px;color:var(--mute)}
.att button{font:inherit;color:var(--gold);background:none;border:0;padding:0;cursor:pointer;text-decoration:underline}
.empty{color:var(--mute);padding:40px;text-align:center}
.tag{display:inline-block;font-size:11px;padding:1px 8px;border-radius:99px;background:var(--gold-soft);color:var(--gold);margin-inline-start:6px}
@media (max-width:760px){.wrap{grid-template-columns:1fr}aside{max-height:40vh;border-left:0;border-bottom:1px solid var(--line)}}
</style></head><body>
<header><h1>أرشيف ديسكورد</h1><div class="sub" id="sub">الرومات اللي انحفظت قبل ما تنحذف — الرسائل والبطاقات والملفات (الصور ما تنحفظ)</div></header>
<div class="wrap">
<aside><input id="q" placeholder="ابحث باسم الروم أو القسم"><div id="list"></div></aside>
<main id="view"><div class="empty">اختر روم من القائمة</div></main>
</div>
<script>
var TOKEN = localStorage.getItem('ouja_token') || '';
var ROOMS = [];
var CUR = null;
function hdr(){ return TOKEN ? {'X-Token': TOKEN} : {}; }
function el(tag, cls, text){ var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
function when(s){
  if (!s) return '';
  var d = new Date(s);
  if (isNaN(d.getTime())) return String(s).slice(0, 16);
  return d.toLocaleString('en-GB', {timeZone: 'Asia/Riyadh', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false});
}
function api(path){
  return fetch(path, {headers: hdr(), credentials: 'same-origin'}).then(function(r){
    return r.json().then(function(j){ if (!r.ok) throw new Error(j.error || ('HTTP ' + r.status)); return j; });
  });
}
function drawList(){
  var q = document.getElementById('q').value.trim();
  var box = document.getElementById('list');
  box.textContent = '';
  var shown = ROOMS.filter(function(r){ return !q || (r.name || '').indexOf(q) >= 0 || (r.category || '').indexOf(q) >= 0; });
  if (!shown.length){ box.appendChild(el('div', 'empty', 'ما فيه رومات')); return; }
  shown.forEach(function(r){
    var b = el('button', 'room' + (CUR === r.id ? ' on' : ''));
    b.setAttribute('data-id', r.id);
    var name = el('b', null, '#' + r.name);
    if (r.deleted_at) name.appendChild(el('span', 'tag', 'انحذف'));
    b.appendChild(name);
    b.appendChild(el('span', null, (r.messages || 0) + ' رسالة · ' + (r.category || '') + ' · ' + when(r.deleted_at || r.archived_at)));
    box.appendChild(b);
  });
}
function embedText(e){
  var parts = [];
  if (e.author && e.author.name) parts.push(e.author.name);
  if (e.title) parts.push(e.title);
  if (e.description) parts.push(e.description);
  (e.fields || []).forEach(function(f){ parts.push((f.name || '') + ': ' + (f.value || '')); });
  if (e.footer && e.footer.text) parts.push(e.footer.text);
  return parts;
}
function download(cid, a){
  fetch('/api/discord-archive/file/' + encodeURIComponent(cid) + '/' + encodeURIComponent(a.stored_as), {headers: hdr(), credentials: 'same-origin'})
    .then(function(r){ if (!r.ok) throw new Error('HTTP ' + r.status); return r.blob(); })
    .then(function(b){ var u = URL.createObjectURL(b); var l = document.createElement('a'); l.href = u; l.download = a.filename || a.stored_as; document.body.appendChild(l); l.click(); l.remove(); setTimeout(function(){ URL.revokeObjectURL(u); }, 4000); })
    .catch(function(err){ alert('ما قدرت أنزّل الملف: ' + err.message); });
}
function openRoom(cid){
  CUR = cid; drawList();
  var v = document.getElementById('view');
  v.textContent = ''; v.appendChild(el('div', 'empty', 'جاري التحميل…'));
  api('/api/discord-archive/room/' + encodeURIComponent(cid)).then(function(d){
    v.textContent = '';
    var room = d.room || {};
    var h = el('h1', null, '#' + (room.name || ''));
    v.appendChild(h);
    v.appendChild(el('div', 'sub', (room.category || '') + ' · ' + (d.message_count || 0) + ' رسالة · انحفظ ' + when(room.archived_at) + (room.deleted_at ? ' · انحذف من ديسكورد ' + when(room.deleted_at) : '')));
    v.appendChild(el('div', null, ' '));
    if (d.unreadable){ v.appendChild(el('div', 'empty', 'البوت ما قدر يقرأ هالروم')); return; }
    var msgs = d.messages || [];
    if (!msgs.length){ v.appendChild(el('div', 'empty', 'ما فيه ولا رسالة')); return; }
    msgs.forEach(function(m){
      var box = el('div', 'm');
      var who = el('div', 'who', m.author_name || '?');
      who.appendChild(el('span', 't', when(m.ts) + (m.is_bot ? ' · بوت' : '')));
      box.appendChild(who);
      if (m.content) box.appendChild(el('div', 'txt', m.content));
      (m.embeds || []).forEach(function(e){
        var parts = embedText(e);
        if (!parts.length) return;
        var eb = el('div', 'emb');
        eb.appendChild(el('div', 'et', parts[0]));
        if (parts.length > 1) eb.appendChild(el('div', null, parts.slice(1).join(String.fromCharCode(10))));
        box.appendChild(eb);
      });
      (m.attachments || []).forEach(function(a){
        var line = el('div', 'att');
        if (a.skipped_photo){ line.textContent = '🖼 صورة (ما انحفظت): ' + (a.filename || ''); }
        else if (a.failed){ line.textContent = '⚠️ ملف ما انحفظ: ' + (a.filename || ''); }
        else {
          line.appendChild(document.createTextNode('📎 '));
          var b = el('button', null, a.filename || a.stored_as);
          b.setAttribute('data-file', a.stored_as);
          b.setAttribute('data-cid', cid);
          b.setAttribute('data-name', a.filename || '');
          line.appendChild(b);
        }
        box.appendChild(line);
      });
      v.appendChild(box);
    });
  }).catch(function(err){ v.textContent = ''; v.appendChild(el('div', 'empty', 'ما قدرت أفتح الروم: ' + err.message)); });
}
document.getElementById('list').addEventListener('click', function(ev){
  var b = ev.target.closest('[data-id]'); if (b) openRoom(b.getAttribute('data-id'));
});
document.getElementById('view').addEventListener('click', function(ev){
  var b = ev.target.closest('[data-file]');
  if (b) download(b.getAttribute('data-cid'), {stored_as: b.getAttribute('data-file'), filename: b.getAttribute('data-name')});
});
document.getElementById('q').addEventListener('input', drawList);
api('/api/discord-archive/rooms').then(function(d){
  ROOMS = d.rooms || [];
  var gone = ROOMS.filter(function(r){ return r.deleted_at; }).length;
  document.getElementById('sub').textContent = ROOMS.length + ' روم محفوظ · ' + gone + ' منها انحذف من ديسكورد · الصور ما تنحفظ';
  drawList();
}).catch(function(err){
  document.getElementById('list').appendChild(el('div', 'empty', err.message));
  document.getElementById('view').textContent = '';
  document.getElementById('view').appendChild(el('div', 'empty', 'لازم تكون مسجّل دخول الداشبورد كأدمن. افتح الداشبورد وسجّل، وبعدين ارجع لهالصفحة.'));
});
</script>
</body></html>
"""
