# -*- coding: utf-8 -*-
"""guide.routes — aiohttp handlers.

PUBLIC (no auth — guests open these with nothing, like /team-calendar):
  GET /guide, /guide/{slug}      → the 1:1 guest page (client renders by slug)
  GET /guide/data.json           → flat records (same shape the Netlify site used)
  GET /data.json                 → alias for the elite-map geo compat
  GET /guide/media/{slug}/{f}    → mirrored photos from STATE_DIR/guide_media
  GET /guide/fonts/{f}, /guide/logo.png

ADMIN (dashboard login + admin/ops role — double-gated like schedule writes):
  GET  /api/guide/admin          → units + entries for the dashboard tab
  POST /api/guide/unit           → edit one unit's fields
  POST /api/guide/entry          → add a FAQ/section entry
  POST /api/guide/entry/delete   → remove an entry
  POST /api/guide/import         → run the CSV import (thread)"""

import asyncio
import datetime
import mimetypes
import os
import re
import threading
import traceback
from pathlib import Path
from types import SimpleNamespace

from . import db, importer

HOST = SimpleNamespace(dash_auth=None, req_role=None, json_response=None, web=None,
                       state_dir=None, listings=None, csv_path=None)

_DIR = Path(__file__).resolve().parent
EDIT_ROLES = ("admin", "ops")
_SLUG_RX = re.compile(r"^[a-z0-9][a-z0-9\-_]{0,63}$")
_FNAME_RX = re.compile(r"^[A-Za-z0-9._\-]{1,80}$")


def wire(host):
    for k, v in (host or {}).items():
        setattr(HOST, k, v)


def _can_edit(request):
    try:
        return (HOST.req_role(request) if HOST.req_role else "viewer") in EDIT_ROLES
    except Exception:
        return False


def _deny():
    return HOST.json_response({"ok": False, "error": "غير مصرّح لك بالتعديل"}, 403)


def _safe_public(fn):
    async def _w(request):
        try:
            return await fn(request)
        except Exception:
            traceback.print_exc()
            return HOST.web.Response(status=500, text="temporary error")
    _w.__name__ = getattr(fn, "__name__", "w")
    return _w


def _safe(fn):
    async def _w(request):
        if not (HOST.dash_auth and HOST.dash_auth(request)):
            return HOST.json_response({"ok": False, "error": "unauthorized"}, 401)
        try:
            return await fn(request)
        except Exception:
            traceback.print_exc()
            return HOST.json_response({"ok": False, "error": "صار خطأ مؤقت"}, 200)
    _w.__name__ = getattr(fn, "__name__", "w")
    return _w


# ---------------- public ----------------

_page_cache = {"html": None}


async def page(request):
    if _page_cache["html"] is None:
        _page_cache["html"] = (_DIR / "templates" / "guide.html").read_text("utf-8")
    return HOST.web.Response(text=_page_cache["html"], content_type="text/html",
                             headers={"Cache-Control": "no-cache"})


async def data_json(request):
    recs = await asyncio.to_thread(db.public_records)
    return HOST.json_response(recs)


async def media(request):
    slug = (request.match_info.get("slug") or "").strip().lower()
    fname = request.match_info.get("fname") or ""
    if not (_SLUG_RX.match(slug) and _FNAME_RX.match(fname)):
        return HOST.web.Response(status=404, text="not found")
    path = os.path.join(HOST.state_dir or ".", "guide_media", slug, fname)
    if not os.path.isfile(path) or os.path.getsize(path) > importer.MAX_MEDIA_BYTES:
        return HOST.web.Response(status=404, text="not found")
    ctype = mimetypes.guess_type(fname)[0] or "application/octet-stream"
    return HOST.web.Response(body=open(path, "rb").read(), content_type=ctype,
                             headers={"Cache-Control": "public, max-age=86400"})


async def font(request):
    fname = request.match_info.get("fname") or ""
    if not _FNAME_RX.match(fname) or not fname.endswith(".woff2"):
        return HOST.web.Response(status=404, text="not found")
    path = _DIR / "static" / "fonts" / fname
    if not path.is_file():
        return HOST.web.Response(status=404, text="not found")
    return HOST.web.Response(body=path.read_bytes(), content_type="font/woff2",
                             headers={"Cache-Control": "public, max-age=604800"})


async def logo(request):
    path = _DIR / "static" / "logo.png"     # drop the real logo here when the owner sends it;
    if not path.is_file():                  # the page removes the <img> on 404 (same as live)
        return HOST.web.Response(status=404, text="not found")
    return HOST.web.Response(body=path.read_bytes(), content_type="image/png",
                             headers={"Cache-Control": "public, max-age=86400"})


# ---------------- admin ----------------

async def _body(request):
    try:
        d = await request.json()
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


async def api_admin(request):
    units = await asyncio.to_thread(db.units, False)
    entries = await asyncio.to_thread(db.all_entries)
    hostaway = []
    try:
        lm = await asyncio.to_thread(HOST.listings) if HOST.listings else {}
        hostaway = sorted(({"id": int(k), "name": str(v)} for k, v in (lm or {}).items()),
                          key=lambda x: x["name"])
    except Exception:
        hostaway = []
    return HOST.json_response({"ok": True, "units": units, "entries": entries,
                               "hostaway": hostaway, "can_edit": _can_edit(request)})


async def api_unit_save(request):
    if not _can_edit(request):
        return _deny()
    b = await _body(request)
    slug = (b.get("slug") or "").strip().lower()
    if not _SLUG_RX.match(slug):
        return HOST.json_response({"ok": False, "error": "معرّف غير صحيح"}, 200)
    fields = {k: str(b[k]).strip() for k in
              ("listing_name", "map_link", "wifi_name", "wifi_pass", "notes",
               "complex_caption", "building_caption", "elevator_caption", "door_caption")
              if k in b}
    if "active" in b:
        fields["active"] = 1 if b.get("active") in (1, "1", True, "true") else 0
    unlink = False
    if "listing_id" in b:                      # Hostaway link from the edit panel
        raw = str(b.get("listing_id") or "").strip()
        if raw:
            try:
                fields["listing_id"] = int(raw)
            except ValueError:
                return HOST.json_response({"ok": False, "error": "رقم Hostaway غير صحيح"}, 200)
        else:
            unlink = True                      # explicit empty = unlink
    if not fields and not unlink:
        return HOST.json_response({"ok": False, "error": "لا شيء للتعديل"}, 200)
    fields["updated_by"] = "dashboard"
    await asyncio.to_thread(db.upsert_unit, slug, **fields)
    if unlink:
        await asyncio.to_thread(db.execute,
                                "UPDATE guide_units SET listing_id=NULL WHERE slug=?", (slug,))
    return HOST.json_response({"ok": True, "unit": db.get_unit(slug)})


async def api_entry_add(request):
    if not _can_edit(request):
        return _deny()
    b = await _body(request)
    title_ar = (b.get("title_ar") or "").strip()
    body_ar = (b.get("body_ar") or "").strip()
    if not (title_ar or body_ar):
        return HOST.json_response({"ok": False, "error": "المحتوى مطلوب"}, 200)
    slug = (b.get("slug") or "").strip().lower()
    if slug and not _SLUG_RX.match(slug):
        return HOST.json_response({"ok": False, "error": "معرّف غير صحيح"}, 200)
    eid = await asyncio.to_thread(
        db.add_entry, slug, (b.get("section") or "faq"),
        title_ar, (b.get("title_en") or "").strip(),
        body_ar, (b.get("body_en") or "").strip(),
        None, int(b.get("sort") or 0), "published",
        (b.get("source") or "admin"), (b.get("by") or "dashboard"))
    return HOST.json_response({"ok": True, "id": eid})


async def api_entry_delete(request):
    if not _can_edit(request):
        return _deny()
    b = await _body(request)
    try:
        eid = int(b.get("id"))
    except (TypeError, ValueError):
        return HOST.json_response({"ok": False, "error": "bad id"}, 200)
    await asyncio.to_thread(db.del_entry, eid)
    return HOST.json_response({"ok": True})


# The import mirrors up to ~164 unique Drive photos — minutes of work. Running
# it inside the HTTP request hung the button and hit proxy timeouts, so it is a
# BACKGROUND JOB: POST /api/guide/import starts it (double-start guarded),
# GET /api/guide/import/status feeds the progress bar.
_import_state = {"running": False, "done": 0, "total": 0, "slug": "",
                 "report": None, "error": "", "started_at": "", "finished_at": ""}
_import_lock = threading.Lock()


def _run_import_job(csv_path, media_dir, lm):
    st = _import_state

    def _tick(done, total, slug):
        st["done"], st["total"], st["slug"] = done, total, slug
    try:
        rep = importer.import_csv(csv_path, media_dir, None, lm, True, progress=_tick)
        st["report"] = rep
    except Exception as e:
        st["error"] = "%s: %s" % (type(e).__name__, e)
    finally:
        st["running"] = False
        st["finished_at"] = datetime.datetime.now().isoformat(timespec="seconds")


async def api_import(request):
    if not _can_edit(request):
        return _deny()
    csv_path = HOST.csv_path or "supabase_export_listings.csv"
    if not os.path.isfile(csv_path):
        return HOST.json_response({"ok": False, "error": "ملف التصدير غير موجود: " + csv_path}, 200)
    with _import_lock:
        if _import_state["running"]:
            return HOST.json_response({"ok": True, "already_running": True,
                                       "state": dict(_import_state)})
        _import_state.update({"running": True, "done": 0, "total": 0, "slug": "",
                              "report": None, "error": "",
                              "started_at": datetime.datetime.now().isoformat(timespec="seconds"),
                              "finished_at": ""})
    lm = {}
    try:
        lm = HOST.listings() if HOST.listings else {}
    except Exception:
        lm = {}
    media_dir = os.path.join(HOST.state_dir or ".", "guide_media")
    threading.Thread(target=_run_import_job, args=(csv_path, media_dir, lm),
                     daemon=True).start()
    return HOST.json_response({"ok": True, "started": True})


async def api_import_status(request):
    if not (HOST.dash_auth and HOST.dash_auth(request)):
        return HOST.json_response({"ok": False, "error": "unauthorized"}, 401)
    return HOST.json_response({"ok": True, "state": dict(_import_state)})


def register_routes(app):
    r = app.router
    r.add_get("/guide", _safe_public(page))
    r.add_get("/guide/data.json", _safe_public(data_json))
    r.add_get("/data.json", _safe_public(data_json))       # elite-map geo compat
    r.add_get("/guide/logo.png", _safe_public(logo))
    r.add_get("/guide/fonts/{fname}", _safe_public(font))
    r.add_get("/guide/media/{slug}/{fname}", _safe_public(media))
    r.add_get("/guide/{slug}", _safe_public(page))
    r.add_get("/api/guide/admin", _safe(api_admin))
    r.add_post("/api/guide/unit", _safe(api_unit_save))
    r.add_post("/api/guide/entry", _safe(api_entry_add))
    r.add_post("/api/guide/entry/delete", _safe(api_entry_delete))
    r.add_post("/api/guide/import", _safe(api_import))
    r.add_get("/api/guide/import/status", _safe(api_import_status))
