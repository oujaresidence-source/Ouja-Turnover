# -*- coding: utf-8 -*-
"""
permits.routes — /api/permits/* for «التصاريح» (+ the tab's static JS).

Thin aiohttp wrappers around `core_*` functions that take plain values and return
(status, dict), so tests drive the rules without a web server. EVERY database or file
call from a handler goes through HOST.web_thread (the web pool) — never the default
executor, which the bot's own background work can jam (CLAUDE.md trap 6).

WHO MAY DO WHAT
  read   — login + the `permits` page permission (bot.py's _ROLE_READ_RULES).
  edit   — the above + role admin/ops (can_edit_permits), re-checked in every write.
  admin  — «لن يُجدَّد», switching the mode, clearing a review flag.
  public — ONLY /permits/static/permits_tab.js: code, no data.

Dashboard writes that affect Discord (renew / cancel / correct) only ENQUEUE outbox rows;
the loop delivers them within one tick.
"""

import csv
import io
import json
import os
import re
import traceback
import uuid

from . import dates, db, engine, importer, service
from .host import HOST

EDIT_ROLES = ("admin", "ops")
STATIC_JS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "permits_tab.js")
DOC_EXT = {"pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
           "heic": "image/heic", "webp": "image/webp"}
DOC_MAX = 10 * 1024 * 1024


# ---------------- roles ----------------

def _role(request):
    try:
        return HOST.req_role(request) if HOST.req_role else "viewer"
    except Exception:
        return "viewer"


def can_edit_permits(request):
    return _role(request) in EDIT_ROLES


def is_admin(request):
    return _role(request) == "admin"


def _actor(request):
    try:
        return HOST.actor(request) if HOST.actor else ""
    except Exception:
        return ""


def _now():
    return service._now()


# ---------------- read models ----------------

def _ticket_view(t):
    if not t:
        return None
    url = ""
    if t.get("channel_id") and HOST.guild_id:
        url = "https://discord.com/channels/%s/%s" % (HOST.guild_id, t["channel_id"])
    return {"id": t["id"], "state": t["state"], "channel_id": t.get("channel_id") or "", "url": url,
            "claimed_by": t.get("claimed_by") or "", "opened_at": t.get("opened_at"),
            "last_error": t.get("last_error") or "", "attempts": t.get("attempts") or 0}


def _row(p, today, c, lmap, live):
    d = engine.describe(p, today, c)
    rec = lmap.get(p.get("listing_id")) if p.get("listing_id") else None
    rname, _rid = service.responsible(p)
    left = d["days_left"]
    return {
        "id": p["id"], "permit_type": p["permit_type"], "permit_no": p.get("permit_no") or "",
        "type_short": engine.type_default(p, "short") or p["permit_type"],
        "unit": engine.unit_label(p, (rec or {}).get("internal_name") or ""),
        "unit_text": p.get("unit_text") or "", "listing_id": p.get("listing_id"),
        "linked": bool(rec) or bool(p.get("listing_id")),
        "listing_active": (bool(rec.get("active", True)) if rec else (None if not p.get("listing_id") else False)),
        "scope": p.get("scope"), "building": p.get("building") or "", "district": p.get("district") or "",
        "issuer": p.get("issuer") or engine.type_default(p, "issuer"), "holder": p.get("holder") or "",
        "start_date": p.get("start_date"), "end_date": p.get("end_date"),
        "end_hijri": dates.to_hijri_str(p.get("end_date")) if p.get("end_date") else "",
        "end_date_raw": p.get("end_date_raw") or "", "days_left": left, "band": d["band"],
        "lead": d["lead"], "needs_data": bool(p.get("needs_data")), "date_issue": p.get("date_issue") or "",
        "review_open": len(engine.open_issues(p)), "responsible": rname,
        "ticket": _ticket_view(live.get(p["id"])),
        "opens_in": (left - d["lead"]) if (left is not None and left > d["lead"]) else 0,
    }


def _sort_key(r):
    order = {"unknown": 0, "expired": 1}
    return (order.get(r["band"], 2), r["days_left"] if r["days_left"] is not None else -10 ** 6, r["unit"])


def core_summary(now=None):
    return 200, service.summary(now or _now())


def core_list(now=None, role="viewer"):
    now = now or _now()
    c = engine.cfg()
    today = service._riyadh_day(now)
    lmap = service.listing_map()
    live = {t["permit_id"]: t for t in db.live_tickets()}
    rows = sorted((_row(p, today, c, lmap, live) for p in db.permits("active")), key=_sort_key)
    s = service.summary(now, c)
    out = {"ok": True, "today": today, "rows": rows, "counts": s["counts"], "mode": s["mode"],
           "last_tick_at": s["last_tick_at"], "last_discord_ok_at": s["last_discord_ok_at"],
           "problems": s["problems"], "lead_days": c["lead_days"], "headsup_days": c["headsup_days"],
           "can_edit": role in EDIT_ROLES, "is_admin": role == "admin",
           "type_suggestions": engine.TYPE_SUGGESTIONS,
           "listings": sorted([{"id": k, "name": v.get("internal_name") or v.get("public_name") or ("#%s" % k)}
                               for k, v in lmap.items() if v.get("active", True)], key=lambda x: x["name"].lower())}
    if s["mode"]["mode"] == "dry":
        out["would_open"] = service.would_open(now, c)
    return 200, out


def core_item(pid, now=None, role="viewer"):
    now = now or _now()
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return 400, {"ok": False, "error_ar": "رقم غير صالح", "error_en": "bad id"}
    p = db.permit(pid)
    if not p:
        return 404, {"ok": False, "error_ar": "التصريح غير موجود", "error_en": "not found"}
    c = engine.cfg()
    today = service._riyadh_day(now)
    lmap = service.listing_map()
    live = {t["permit_id"]: t for t in db.live_tickets()}
    row = _row(p, today, c, lmap, live)
    full = {k: p.get(k) for k in db.PERMIT_FIELDS if k not in ("holder_id_last4", "doc_path")}
    full.update({"id": p["id"], "created_at": p.get("created_at"), "updated_at": p.get("updated_at")})
    full["extra"] = engine.extras(p)
    full["review_issues"] = json.loads(p.get("review_issues") or "[]")
    full["has_doc"] = bool(p.get("doc_path"))
    full["start_hijri"] = dates.to_hijri_str(p.get("start_date")) if p.get("start_date") else ""
    full["renew_notes_default"] = engine.type_default(p, "renew_notes")
    if role in EDIT_ROLES and p.get("holder_id_last4"):
        full["holder_id_masked"] = "•••• " + p["holder_id_last4"]
    chain_ids = [x["id"] for x in db.chain(pid)]
    chain = [{"id": x["id"], "status": x["status"], "permit_no": x.get("permit_no"), "start_date": x.get("start_date"),
              "end_date": x.get("end_date"), "source": x.get("source")} for x in db.chain(pid)]
    events = db.events_for(chain_ids, 80)
    for e in events:
        e["payload"] = json.loads(e.pop("payload_json") or "{}")
    tickets = [_ticket_view(t) for t in db.tickets_for(pid)]
    return 200, {"ok": True, "row": row, "permit": full, "chain": chain, "events": events, "tickets": tickets,
                 "can_edit": role in EDIT_ROLES, "is_admin": role == "admin"}


def core_months(now=None):
    now = now or _now()
    today = service._riyadh_day(now)
    y, m = int(today[:4]), int(today[5:7])
    months = []
    for i in range(12):
        mm = (m - 1 + i) % 12 + 1
        yy = y + (m - 1 + i) // 12
        months.append({"key": "%04d-%02d" % (yy, mm), "label_ar": dates.MONTHS_AR[mm], "year": yy, "items": []})
    idx = {mo["key"]: mo for mo in months}
    lmap = service.listing_map()
    for p in db.permits("active"):
        key = str(p.get("end_date") or "")[:7]
        if key in idx:
            idx[key]["items"].append({"id": p["id"], "unit": engine.unit_label(p, service.unit_name(p, lmap)),
                                      "permit_type": p["permit_type"], "end_date": p["end_date"]})
    for mo in months:
        mo["count"] = len(mo["items"])
        mo["items"].sort(key=lambda x: x["end_date"])
    return 200, {"ok": True, "months": months}


def core_parse_date(value, now=None):
    """The live «as you type» preview: the server's reading of a date, in words and Hijri."""
    now = now or _now()
    pd = dates.parse_date(value)
    iso = pd["iso"]
    return 200, {"ok": True, "iso": iso, "issue": pd["issue"], "calendar": pd["calendar"],
                 "words": dates.words_ar(iso), "hijri": dates.to_hijri_str(iso) if iso else "",
                 "days_left": engine.days_left(iso, service._riyadh_day(now)) if iso else None}


def core_preview_live(now=None):
    now = now or _now()
    w = service.would_open(now)
    return 200, {"ok": True, "count": len(w), "items": w, "mode": service.mode_info()}


_CSV_COLS = [("id", "#"), ("permit_type", "النوع"), ("permit_no", "رقم التصريح"), ("unit", "الشقة/المبنى"),
             ("issuer", "جهة الإصدار"), ("holder", "باسم"), ("start_date", "البداية (ميلادي)"),
             ("start_hijri", "البداية (هجري)"), ("end_date", "النهاية (ميلادي)"), ("end_hijri", "النهاية (هجري)"),
             ("days_left", "المتبقي (أيام)"), ("band_ar", "الحالة"), ("ticket", "التذكرة"),
             ("responsible", "المسؤول"), ("district", "الحي"), ("notes", "ملاحظات")]


def core_export_csv(now=None):
    now = now or _now()
    _st, data = core_list(now, "viewer")
    notes = {p["id"]: p.get("notes") or "" for p in db.permits("active")}
    starts = {p["id"]: p.get("start_date") for p in db.permits("active")}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([h for _k, h in _CSV_COLS])
    for r in data["rows"]:
        r = dict(r)
        r["start_hijri"] = dates.to_hijri_str(starts.get(r["id"])) if starts.get(r["id"]) else ""
        r["band_ar"] = engine.BAND_META[r["band"]]["ar"]
        r["ticket"] = ("#%03d" % r["ticket"]["id"]) if r.get("ticket") else ""
        r["notes"] = notes.get(r["id"], "")
        w.writerow(["" if r.get(k) is None else r.get(k) for k, _h in _CSV_COLS])
    return buf.getvalue().encode("utf-8-sig")


# ---------------- writes ----------------

def _clean_payload(b):
    return {k: b.get(k) for k in service.EDITABLE if k in b}


def core_create(b, actor, now=None):
    now = now or _now()
    data = _clean_payload(b)
    if not str(data.get("permit_type") or "").strip():
        return 400, {"ok": False, "error_ar": "اختر نوع التصريح", "error_en": "type is required"}
    for k in ("start_date", "end_date"):
        raw = data.get(k)
        pd = dates.parse_date(raw) if str(raw or "").strip() else {"iso": None, "issue": ""}
        if str(raw or "").strip() and not pd["iso"]:
            return 400, {"ok": False, "error_ar": "ما قدرنا نقرأ التاريخ «%s»" % raw, "error_en": "bad date"}
        data[k] = pd["iso"]
        data[k + "_raw"] = dates.clean_text(raw)
        if k == "end_date":
            data["date_issue"] = pd["issue"]
    if data.get("doc_url") and not service.safe_url(data["doc_url"]):
        return 400, {"ok": False, "error_ar": "رابط المستند لازم يبدأ بـ https://", "error_en": "doc_url must be https"}
    lid = b.get("listing_id")
    if str(lid or "").strip().isdigit():
        data["listing_id"] = int(lid)
        data["listing_link_kind"] = "manual"
    for k in ("lead_days", "cost_sar"):
        v = str(data.get(k) if data.get(k) is not None else "").replace(",", "").strip()
        try:
            data[k] = (int(v) if k == "lead_days" else float(v)) if v else None
        except ValueError:
            return 400, {"ok": False, "error_ar": "قيمة رقمية غير صالحة", "error_en": "bad number"}
    data["scope"] = data.get("scope") or ("unit" if (data.get("unit_text") or data.get("listing_id")) else "other")
    data["source"] = "manual"
    data["review_issues"] = []
    pid = db.insert_permit(data, actor)
    db.log_event("created", pid, payload={"source": "manual"}, actor=actor)
    return 200, {"ok": True, "id": pid}


def core_update(b, actor, now=None):
    now = now or _now()
    r = service.update(b.get("id"), _clean_payload(b), actor, service._riyadh_day(now), reason=b.get("reason") or "")
    return (200 if r["ok"] else 400), r


def core_cancel(b, actor, admin):
    r = service.cancel(b.get("id"), b.get("reason"), actor, allowed=admin)
    return (200 if r["ok"] else (403 if not admin else 400)), r


def core_mode(b, actor):
    r = service.set_mode(b.get("mode"), b.get("confirm"), actor)
    return (200 if r["ok"] else 400), r


def core_link(b, actor):
    r = service.link(b.get("id"), b.get("listing_id"), actor)
    return (200 if r["ok"] else 400), r


def core_review_clear(b, actor):
    r = service.review_clear(b.get("id"), b.get("code"), b.get("note"), actor)
    return (200 if r["ok"] else 400), r


# ---------------- documents (path from the id ONLY — never from user input) ----------------

def _docs_root():
    base = HOST.state_dir or os.environ.get("STATE_DIR") or "."
    return os.path.realpath(os.path.join(base, "permits_docs"))


def safe_ext(filename):
    m = re.search(r"\.([A-Za-z0-9]{1,5})$", str(filename or ""))
    ext = (m.group(1).lower() if m else "")
    return ext if ext in DOC_EXT else ""


def save_doc(pid, filename, data):
    """-> relative path 'permits_docs/<id>/<uuid>.<ext>'. The original name is NEVER part
    of the path (F21) — only its extension, checked against an allow-list."""
    ext = safe_ext(filename)
    if not ext:
        raise ValueError("bad_type")
    if not data:
        raise ValueError("empty")
    if len(data) > DOC_MAX:
        raise ValueError("too_large")
    rel_dir = os.path.join("permits_docs", str(int(pid)))
    root = _docs_root()
    os.makedirs(os.path.join(root, str(int(pid))), exist_ok=True)
    name = "%s.%s" % (uuid.uuid4().hex, ext)
    with open(os.path.join(root, str(int(pid)), name), "wb") as f:
        f.write(data)
    return os.path.join(rel_dir, name)


def doc_file(pid):
    """-> (absolute path, content type) or (None, None). Built from the stored row only,
    and refused unless it resolves inside permits_docs/."""
    try:
        p = db.permit(int(pid))
    except (TypeError, ValueError):
        return None, None
    rel = (p or {}).get("doc_path") or ""
    if not rel:
        return None, None
    root = _docs_root()
    full = os.path.realpath(os.path.join(os.path.dirname(root), rel))
    if not full.startswith(root + os.sep) or not os.path.isfile(full):
        return None, None
    return full, DOC_EXT.get(safe_ext(full), "application/octet-stream")


def core_doc_upload(pid, filename, data, actor):
    p = db.permit(pid) if str(pid or "").isdigit() else None
    if not p:
        return 404, {"ok": False, "error_ar": "التصريح غير موجود", "error_en": "not found"}
    try:
        rel = save_doc(p["id"], filename, data)
    except ValueError as e:
        msg = {"bad_type": "نقبل PDF أو صورة (jpg/png/heic/webp) بس", "too_large": "الملف أكبر من ١٠ ميجا",
               "empty": "الملف فاضي"}.get(str(e), "ملف غير صالح")
        return 400, {"ok": False, "error_ar": msg, "error_en": str(e)}
    clean = re.sub(r"[^\w؀-ۿ .()-]+", "_", os.path.basename(str(filename or "")))[:120]
    db.update_permit(p["id"], {"doc_path": rel, "doc_name": clean or p.get("doc_name") or ""}, actor)
    db.log_event("doc_uploaded", p["id"], payload={"name": clean}, actor=actor)
    return 200, {"ok": True}


def core_renew(fields, filename, data, actor, admin, now=None):
    now = now or _now()
    pid = fields.get("id")
    p = db.permit(pid) if str(pid or "").isdigit() else None
    if not p:
        return 404, {"ok": False, "error_ar": "التصريح غير موجود", "error_en": "not found"}
    rel = ""
    if data:
        try:
            rel = save_doc(p["id"], filename, data)
        except ValueError as e:
            return 400, {"ok": False, "error_ar": "المستند غير صالح (PDF أو صورة، أقل من ١٠ ميجا)", "error_en": str(e)}
    r = service.renew(p["id"], fields.get("end_date"), actor, service._riyadh_day(now),
                      new_no=fields.get("permit_no") or "", notes=fields.get("notes") or "",
                      override_reason=fields.get("override_reason") or "", via="dashboard",
                      doc_path=rel, is_admin=admin, start_date=fields.get("start_date") or None)
    if not r["ok"] and rel:
        try:
            os.remove(os.path.join(os.path.dirname(_docs_root()), rel))
        except OSError:
            pass
    return (200 if r["ok"] else 400), r


# ---------------- import ----------------

def core_import_preview(source, filename, data, default_type):
    try:
        if source == "onboarding":
            if not HOST.onb_reader:
                return 400, {"ok": False, "error_ar": "مشاريع التشغيل غير متاحة", "error_en": "onboarding unavailable"}
            pv = importer.from_onboarding(HOST.onb_reader, default_type)
        else:
            pv = importer.parse(data, filename, default_type=default_type)
    except importer.ImportError_ as e:
        return 400, {"ok": False, "error_ar": str(e), "error_en": "unreadable file"}
    importer.mark_existing(pv)
    return 200, {"ok": True, "preview": pv}


def core_import_commit(source, filename, data, default_type, decisions, actor, now=None):
    """RE-PARSES the upload server-side — a date edited in the browser is never stored."""
    now = now or _now()
    st, res = core_import_preview(source, filename, data, default_type)
    if st != 200:
        return st, res
    out = importer.commit(res["preview"], actor, source="onboarding" if source == "onboarding" else "import",
                          decisions=decisions)
    today = service._riyadh_day(now)
    for pid in out["ids"]:                        # an updated date may move a ticket out of its window
        p = db.permit(pid)
        lt = db.live_ticket(pid)
        if p and lt and p.get("end_date") and not p.get("needs_data") \
                and not engine.should_open(p, today, engine.cfg()):
            with db.transaction() as cx:
                service._close_live_ticket(cx, pid, "corrected", engine.corrected_note(
                    p.get("end_date"), today, "تحديث من الاستيراد", actor), actor)
    try:
        from .seed import seed as _seed
        _seed.link_units(lambda: list(service.listing_map().values()))
    except Exception as e:
        print("[permits] post-import link failed:", e)
    return 200, dict(out, ok=True)


# ---------------- aiohttp wrappers ----------------

def _json(body, status=200):
    return HOST.json_response(body, status)


def _guard(request):
    if not HOST.dash_auth(request):
        return _json({"ok": False, "error": "unauthorized", "error_ar": "سجّل دخول", "error_en": "login"}, 401)
    return None


def _safe(fn):
    async def _w(request):
        g = _guard(request)
        if g:
            return g
        try:
            return await fn(request)
        except Exception as e:
            traceback.print_exc()
            return _json({"ok": False, "error_ar": "صار خطأ غير متوقع — جرّب مرة ثانية",
                          "error_en": "%s: %s" % (type(e).__name__, e)}, 500)
    _w.__name__ = getattr(fn, "__name__", "w")
    return _w


def _need_edit(request):
    if not can_edit_permits(request):
        return _json({"ok": False, "error_ar": "التعديل للمدير أو فريق التشغيل بس", "error_en": "edit needs admin/ops"}, 403)
    return None


def _need_admin(request):
    if not is_admin(request):
        return _json({"ok": False, "error_ar": "هذي للمدير بس", "error_en": "admin only"}, 403)
    return None


async def _body(request):
    try:
        b = await request.json()
        return b if isinstance(b, dict) else {}
    except Exception:
        return {}


async def _multipart(request, limit):
    """-> (fields, filename, bytes). Same shape as mot/routes._multipart."""
    reader = await request.multipart()
    fields, filename, data = {}, "", b""
    async for part in reader:
        if part.name == "file":
            filename = part.filename or ""
            chunks, total = [], 0
            while True:
                chunk = await part.read_chunk()
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    raise ValueError("too_large")
                chunks.append(chunk)
            data = b"".join(chunks)
        else:
            fields[part.name] = (await part.text()).strip()
    return fields, filename, data


def _reply(pair):
    st, body = pair
    return _json(body, st)


async def _run(fn, *a, **kw):
    return await HOST.web_thread(fn, *a, **kw)


async def api_summary(request):
    return _reply(await _run(core_summary))


async def api_list(request):
    return _reply(await _run(core_list, None, _role(request)))


async def api_item(request):
    return _reply(await _run(core_item, request.query.get("id"), None, _role(request)))


async def api_months(request):
    return _reply(await _run(core_months))


async def api_parse_date(request):
    return _reply(await _run(core_parse_date, request.query.get("v") or ""))


async def api_preview_live(request):
    return _reply(await _run(core_preview_live))


async def api_doc(request):
    path, ctype = await _run(doc_file, request.query.get("id"))
    if not path:
        return _json({"ok": False, "error_ar": "ما فيه مستند", "error_en": "no document"}, 404)
    data = await _run(lambda: open(path, "rb").read())
    return HOST.web.Response(body=data, content_type=ctype,
                             headers={"Content-Disposition": "inline", "Cache-Control": "private, no-store"})


async def api_export(request):
    body = await _run(core_export_csv)
    return HOST.web.Response(body=body, content_type="text/csv", charset="utf-8",
                             headers={"Content-Disposition": "attachment; filename=permits.csv"})


async def api_create(request):
    g = _need_edit(request)
    if g:
        return g
    b = await _body(request)
    return _reply(await _run(core_create, b, _actor(request)))


async def api_update(request):
    g = _need_edit(request)
    if g:
        return g
    b = await _body(request)
    return _reply(await _run(core_update, b, _actor(request)))


async def api_renew(request):
    g = _need_edit(request)
    if g:
        return g
    if (request.content_type or "").startswith("multipart/"):
        try:
            fields, filename, data = await _multipart(request, DOC_MAX)
        except ValueError:
            return _json({"ok": False, "error_ar": "الملف أكبر من ١٠ ميجا", "error_en": "too large"}, 400)
    else:
        fields, filename, data = await _body(request), "", b""
    return _reply(await _run(core_renew, fields, filename, data, _actor(request), is_admin(request)))


async def api_cancel(request):
    g = _need_admin(request)
    if g:
        return g
    b = await _body(request)
    return _reply(await _run(core_cancel, b, _actor(request), True))


async def api_doc_upload(request):
    g = _need_edit(request)
    if g:
        return g
    try:
        fields, filename, data = await _multipart(request, DOC_MAX)
    except ValueError:
        return _json({"ok": False, "error_ar": "الملف أكبر من ١٠ ميجا", "error_en": "too large"}, 400)
    return _reply(await _run(core_doc_upload, fields.get("id"), filename, data, _actor(request)))


async def _import_inputs(request):
    if (request.content_type or "").startswith("multipart/"):
        fields, filename, data = await _multipart(request, importer.MAX_BYTES)
    else:
        fields, filename, data = await _body(request), "", b""
    try:
        decisions = json.loads(fields.get("decisions") or "{}") if isinstance(fields.get("decisions"), str) \
            else (fields.get("decisions") or {})
    except ValueError:
        decisions = {}
    return (fields.get("source") or "file", filename, data,
            (fields.get("default_type") or "").strip() or engine.SEED_TYPE, decisions)


async def api_import_preview(request):
    g = _need_edit(request)
    if g:
        return g
    try:
        source, filename, data, dtype, _d = await _import_inputs(request)
    except ValueError:
        return _json({"ok": False, "error_ar": "الملف أكبر من ٥ ميجا", "error_en": "too large"}, 400)
    return _reply(await _run(core_import_preview, source, filename, data, dtype))


async def api_import_commit(request):
    g = _need_edit(request)
    if g:
        return g
    try:
        source, filename, data, dtype, decisions = await _import_inputs(request)
    except ValueError:
        return _json({"ok": False, "error_ar": "الملف أكبر من ٥ ميجا", "error_en": "too large"}, 400)
    return _reply(await _run(core_import_commit, source, filename, data, dtype, decisions, _actor(request)))


async def api_mode(request):
    g = _need_admin(request)
    if g:
        return g
    b = await _body(request)
    return _reply(await _run(core_mode, b, _actor(request)))


async def api_link(request):
    g = _need_edit(request)
    if g:
        return g
    b = await _body(request)
    return _reply(await _run(core_link, b, _actor(request)))


async def api_review_clear(request):
    g = _need_admin(request)
    if g:
        return g
    b = await _body(request)
    return _reply(await _run(core_review_clear, b, _actor(request)))


# ---------------- the tab's script (public: code, no data) ----------------

_js_cache = {"mtime": None, "text": ""}


def js_version():
    try:
        return str(int(os.path.getmtime(STATIC_JS)))
    except OSError:
        return "0"


def _js_text():
    m = os.path.getmtime(STATIC_JS)
    if _js_cache["mtime"] != m:
        with open(STATIC_JS, encoding="utf-8") as f:
            _js_cache["text"] = f.read()
        _js_cache["mtime"] = m
    return _js_cache["text"]


async def handle_static_js(request):
    text = await _run(_js_text)
    return HOST.web.Response(text=text, content_type="application/javascript",
                             headers={"Cache-Control": "no-cache"})


def register(app):
    g = app.router.add_get
    p = app.router.add_post
    g("/permits/static/permits_tab.js", handle_static_js)
    g("/api/permits/summary", _safe(api_summary))
    g("/api/permits/list", _safe(api_list))
    g("/api/permits/item", _safe(api_item))
    g("/api/permits/months", _safe(api_months))
    g("/api/permits/preview-live", _safe(api_preview_live))
    g("/api/permits/parse-date", _safe(api_parse_date))
    g("/api/permits/doc", _safe(api_doc))
    g("/api/permits/export.csv", _safe(api_export))
    p("/api/permits/create", _safe(api_create))
    p("/api/permits/update", _safe(api_update))
    p("/api/permits/renew", _safe(api_renew))
    p("/api/permits/cancel", _safe(api_cancel))
    p("/api/permits/doc-upload", _safe(api_doc_upload))
    p("/api/permits/import/preview", _safe(api_import_preview))
    p("/api/permits/import/commit", _safe(api_import_commit))
    p("/api/permits/mode", _safe(api_mode))
    p("/api/permits/link", _safe(api_link))
    p("/api/permits/review-clear", _safe(api_review_clear))
