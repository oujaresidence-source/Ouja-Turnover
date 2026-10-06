# -*- coding: utf-8 -*-
"""
owner_meet.routes — every web door of «اجتماع المالك».

Login-gated (the role middleware maps /api/meet/ to the «meet» permission for reads AND writes;
the HTML pages below are not /api/, so each one re-checks login + permission itself):
    GET  /api/meet/owners                     owners + their units + their last presented meeting
    GET  /api/meet/meetings?owner=            meetings of one owner
    POST /api/meet/meetings                   {owner, lids, kind, first, last} | {rebuild: id} -> starts a build
    GET  /api/meet/meetings/{id}              status, readiness, version
    GET|POST /api/meet/meetings/{id}/cursor   presentation <-> presenter sync (phone fallback)
    GET  /api/meet/airbnb                     latest Airbnb report import + rows still to map
    POST /api/meet/airbnb/import              multipart file -> a NEW dated import (same file = no-op)
    POST /api/meet/airbnb/map                 {airbnb_id, lid} -> confirm which unit a report row is
    GET  /meet/{id}                           the shared presentation (owner half of the snapshot only)
    GET  /meet/{id}/notes                     the presenter window (never shared)
    POST /api/meet/meetings/{id}/record (+/delete), /presented, /send (admin), /reopen (admin + reason)
    GET  /api/meet/meetings/{id}/wa           302 to wa.me with the owner link — Faisal taps it himself
    GET|POST /api/meet/commitments            follow-up of past commitments (chapter 0 evidence)
    POST /api/meet/links/{token}/revoke       admin
Public, no login:
    GET  /m/{token}  /m/{token}.pdf           the owner's read-only link (rate-limited; unknown/revoked = plain 404)
    GET  /meet/static/{name}                  the three JS files (allow-list)
    GET  /meet/font/{name}                    the five Thmanyah files (allow-list)

Every handler that touches data or disk runs on HOST.web_thread — never the default thread
executor (the guest-site starvation lesson). Nothing here sends anything to an owner.
"""

import collections
import copy
import datetime
import json
import os
import secrets
import threading
import time
import traceback
import urllib.parse

from . import abnb, airbnb_import, config, db, jobs, money, pdf, periods, privacy, render
from .host import HOST

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(PKG_DIR, "static")
FONT_DIR = os.path.join(os.path.dirname(PKG_DIR), "fonts")
STATIC_FILES = ("stage.js", "notes.js", "owner_meet_tab.js")
FONT_NAMES = tuple(n for _f, _w, n in render.FONT_FILES)
TAB = "meet"

_cursor = {}
_cursor_lock = threading.Lock()
_static_cache = {}


async def _run(fn, *a, **kw):
    return await HOST.web_thread(fn, *a, **kw)


def _json(data, status=200):
    return HOST.json_response(data, status)


def _role(request):
    try:
        return HOST.req_role(request) or "viewer"
    except Exception:
        return "viewer"


def _actor(request):
    try:
        return HOST.actor(request) or ""
    except Exception:
        return ""


def can_use(request):
    """Logged in AND the «meet» page ticked for this user (admins always)."""
    try:
        if not HOST.dash_auth(request):
            return False
        if _role(request) == "admin":
            return True
        return bool(HOST.tab_allowed and HOST.tab_allowed(request, TAB))
    except Exception:
        return False


def _safe(handler):
    async def _w(request):
        if not HOST.dash_auth(request):
            return _json({"ok": False, "error": "unauthorized", "error_ar": "سجّل دخول"}, 401)
        if not can_use(request):
            return _json({"ok": False, "error": "forbidden", "error_ar": "صفحة «اجتماع المالك» غير مفعّلة لحسابك"}, 403)
        try:
            return await handler(request)
        except HOST.web.HTTPException:
            raise                                   # a deliberate redirect / 404 is an answer, not a crash
        except Exception:
            traceback.print_exc()
            return _json({"ok": False, "error": "server_error",
                          "error_ar": "صار خطأ في السيرفر — حاول مرة ثانية"}, 500)
    _w.__name__ = getattr(handler, "__name__", "meet_handler")
    return _w


def js_version():
    try:
        return str(int(max(os.path.getmtime(os.path.join(STATIC_DIR, n)) for n in STATIC_FILES)))
    except OSError:
        return "0"


# ------------------------------------------------------------------ cores (blocking, run on web_thread)
def core_owners():
    out = []
    meta = HOST.listings_meta() or {}
    for o in HOST.owners() or []:
        units = []
        for u in o.get("units") or []:
            lid = u.get("lid")
            if lid is None:
                continue
            units.append({"lid": int(lid), "name": (meta.get(int(lid)) or {}).get("name") or u.get("apartment") or str(lid)})
        if not units:
            continue
        last = db.last_meeting_before(o["owner"], "9999-12-31")
        out.append({"owner": o["owner"], "units": units,
                    "last": ({"id": last["id"], "meeting_date": last["meeting_date"], "period_to": last["period_to"]}
                             if last else None)})
    return {"ok": True, "owners": out}


def _row(m):
    return {k: m.get(k) for k in ("id", "owner", "lids", "meeting_date", "period_kind", "period_from", "period_to",
                                  "months", "state", "build_progress", "build_step", "build_error")}


def core_meetings(owner):
    return {"ok": True, "meetings": [_row(m) for m in db.meetings_for(owner)]}


def _today():
    return HOST.now().date() if HOST.now else datetime.date.today()


def core_create(body, actor):
    body = body or {}
    if body.get("rebuild"):
        m = db.meeting(body["rebuild"])
        if not m:
            return 404, {"ok": False, "error_ar": "الاجتماع غير موجود"}
        if m["state"] in ("sent",):
            return 409, {"ok": False, "error_ar": "اجتماع أُرسل للمالك لا يُعاد تجهيزه — افتح نسخة جديدة"}
        if jobs.running(m["id"]):
            return 200, {"ok": True, "id": m["id"]}
        cur = periods.mkey(_today())
        period = {"kind": m["period_kind"], "start": m["period_from"], "end": m["period_to"],
                  "months": m["months"], "partial": cur if cur in m["months"] else None}
        jobs.start(m["id"], {"owner": m["owner"], "lids": m["lids"], "period": period, "meeting_date": m["meeting_date"]})
        return 200, {"ok": True, "id": m["id"]}
    owner = (body.get("owner") or "").strip()
    if not owner:
        return 400, {"ok": False, "error_ar": "اختر المالك"}
    all_lids = [int(x) for x in (HOST.owner_lids(owner) or [])]
    if not all_lids:
        return 400, {"ok": False, "error_ar": "ما لقينا شقق مربوطة بهذا المالك"}
    try:
        lids = [int(x) for x in (body.get("lids") or [])]
    except (TypeError, ValueError):
        return 400, {"ok": False, "error_ar": "اختيار الشقق غير صحيح"}
    if not lids:
        return 400, {"ok": False, "error_ar": "اختر شقة واحدة على الأقل"}
    if any(l not in all_lids for l in lids):
        return 400, {"ok": False, "error_ar": "شقة ليست لهذا المالك"}
    today = _today()
    last = db.last_meeting_before(owner, "9999-12-31")
    try:
        period = periods.resolve(body.get("kind") or "quarter", today,
                                 last_end=(last or {}).get("period_to"),
                                 first_mkey=(body.get("first") or "")[:7] or None,
                                 last_mkey=(body.get("last") or "")[:7] or None)
    except ValueError as e:
        return 400, {"ok": False, "error_ar": str(e)}
    scope = [] if set(lids) == set(all_lids) else lids
    # A second press of «تجهيز» (or a double-click) must not queue a second identical build behind
    # the first — that is how the queue fills up. Same owner + units + period + day = the same meeting.
    same = db.q1("SELECT * FROM meet_meetings WHERE owner=? AND lids=? AND period_from=? AND period_to=? "
                 "AND meeting_date=? AND state IN ('building','ready','presented') ORDER BY id DESC LIMIT 1",
                 (owner, json.dumps([int(x) for x in lids]), period["start"], period["end"], today.isoformat()))
    if same:
        if same["state"] == "building" and not jobs.running(same["id"]):
            jobs.start(same["id"], {"owner": owner, "lids": scope, "period": period, "meeting_date": today.isoformat()})
        return 200, {"ok": True, "id": same["id"], "existing": True}
    mid = db.create_meeting(owner, lids, period, today.isoformat(), actor)
    db.log_event(mid, "created", {"kind": period["kind"], "months": period["months"]}, actor)
    jobs.start(mid, {"owner": owner, "lids": scope, "period": period, "meeting_date": today.isoformat()})
    return 200, {"ok": True, "id": mid}


def core_status(mid):
    m = db.meeting(mid)
    if not m:
        return 404, {"ok": False, "error_ar": "الاجتماع غير موجود"}
    if m["state"] == "building" and not jobs.running(mid):
        # «building» with no live job = a build this process never owned (a restart) or one that died
        # silently: start it again instead of leaving the bar at «في الطابور» forever.
        cur = periods.mkey(_today())
        jobs.start(mid, {"owner": m["owner"], "lids": [] if len(m["lids"]) == len(HOST.owner_lids(m["owner"]) or [])
                         else m["lids"], "period": {"kind": m["period_kind"], "start": m["period_from"], "end": m["period_to"],
                                                    "months": m["months"], "partial": cur if cur in m["months"] else None},
                         "meeting_date": m["meeting_date"]})
        m = db.meeting(mid)
    snap = db.snapshot(mid) if m["state"] != "building" else None
    out = {"ok": True, "meeting": _row(m), "version": None, "readiness": [], "can_send": False,
           "queue": jobs.queue_info(mid) if m["state"] == "building" else None}
    if snap:
        data = snap["data"]
        ok, why = money.can_send(data)
        out.update(version=snap["version"], readiness=(data.get("presenter") or {}).get("readiness") or [],
                   can_send=ok, send_block=why, data_as_of=snap.get("data_as_of"), frozen=bool(snap["frozen"]))
    base = _base()
    out["links"] = [dict(l, url=base + "/m/" + l["token"], pdf=base + "/m/" + l["token"] + ".pdf")
                    for l in db.links_for(mid)]
    out["record"] = db.record(mid)
    return 200, out


def _base():
    try:
        return (HOST.link_base() or "").rstrip("/") if HOST.link_base else ""
    except Exception:
        return ""


# ------------------------------------------------------------------ the meeting record (S5)
def core_record_add(mid, body, actor):
    m = db.meeting(mid)
    if not m:
        return 404, {"ok": False, "error_ar": "الاجتماع غير موجود"}
    if m["state"] == "sent":
        return 409, {"ok": False, "error_ar": "أُرسل الاجتماع للمالك — أعد فتحه لتعديل السجل"}
    kind = (body or {}).get("kind")
    text = " ".join(str((body or {}).get("text") or "").split())[:500]
    if kind not in db.SIDES or not text:
        return 400, {"ok": False, "error_ar": "اكتب نص القرار أو الالتزام"}
    due = str((body or {}).get("due") or "")[:10] or None
    if due:
        try:
            datetime.date.fromisoformat(due)
        except ValueError:
            return 400, {"ok": False, "error_ar": "تاريخ الموعد غير صحيح"}
    if kind == "decision":
        amt = body.get("amount_sar")
        try:
            amt = float(amt) if amt not in (None, "") else None
        except (TypeError, ValueError):
            return 400, {"ok": False, "error_ar": "المبلغ غير صحيح"}
        db.add_decision(mid, text, amt, body.get("lid"), actor)
    else:
        db.add_commitment(mid, kind, text, body.get("role") or "", due, body.get("lid"),
                          str(body.get("linked_ticket") or "").strip()[:64], actor)
    if m["state"] == "ready":
        db.set_build(mid, state="presented")
    return 200, {"ok": True, "record": db.record(mid)}


def core_record_delete(mid, body):
    m = db.meeting(mid)
    if not m:
        return 404, {"ok": False, "error_ar": "الاجتماع غير موجود"}
    if m["state"] == "sent":
        return 409, {"ok": False, "error_ar": "أُرسل الاجتماع للمالك — لا يُحذف من سجله"}
    try:
        db.delete_record("decision" if (body or {}).get("kind") == "decision" else "commitment", int(body.get("id")))
    except (TypeError, ValueError):
        return 400, {"ok": False, "error_ar": "سطر غير صحيح"}
    return 200, {"ok": True, "record": db.record(mid)}


def core_presented(mid, actor):
    m = db.meeting(mid)
    if not m:
        return 404, {"ok": False, "error_ar": "الاجتماع غير موجود"}
    if m["state"] in ("ready", "reopened"):
        db.set_build(mid, state="presented")
        db.log_event(mid, "presented", "", actor)
    return 200, {"ok": True}


def core_commitments(owner):
    rows = db.q("SELECT c.*, m.meeting_date FROM meet_commitments c JOIN meet_meetings m ON m.id=c.meeting_id "
                "WHERE m.owner=? ORDER BY m.meeting_date DESC, c.id", (owner,))
    return {"ok": True, "commitments": rows}


def core_commitment_update(cid, body, actor):
    c = db.commitment(cid)
    if not c:
        return 404, {"ok": False, "error_ar": "الالتزام غير موجود"}
    st = (body or {}).get("status")
    if st is not None and st not in db.STATUSES:
        return 400, {"ok": False, "error_ar": "حالة غير معروفة"}
    db.update_commitment(cid, status=st, evidence=(body or {}).get("evidence"),
                         linked_ticket=(body or {}).get("linked_ticket"), by=actor)
    return 200, {"ok": True, "commitment": db.commitment(cid)}


# ------------------------------------------------------------------ sending (S5) — only by Faisal's button
PDF_DIR = "owner_meet_pdfs"


def pdf_path(mid, version):
    d = os.path.join(config.state_dir(), PDF_DIR)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "meeting-%d-v%d.pdf" % (int(mid), int(version)))


def _agreed(rec):
    return {"decisions": [{"text": d["text"], "amount_sar": d.get("amount_sar")} for d in rec["decisions"]],
            "commitments": [{"side": c["side"], "text": c["text"], "due": c.get("due")} for c in rec["commitments"]]}


def core_send(mid, actor, role):
    if role != "admin":
        return 403, {"ok": False, "error_ar": "الإرسال للمالك للمدير فقط"}
    m = db.meeting(mid)
    if not m:
        return 404, {"ok": False, "error_ar": "الاجتماع غير موجود"}
    snap = db.snapshot(mid)
    if snap is None:
        return 409, {"ok": False, "error_ar": "جهّز الاجتماع أولاً"}
    if m["state"] == "sent" and snap["frozen"]:
        link = db.active_link(mid, snap["version"])
        if link:
            return 200, {"ok": True, "already": True, "token": link["token"], "url": _base() + "/m/" + link["token"]}
    data = snap["data"]
    ok, why = money.can_send(data)
    if not ok:
        return 409, {"ok": False, "error_ar": why}
    new = copy.deepcopy(data)
    new["owner"]["agreed"] = _agreed(db.record(mid))
    new["meta"]["sent_at"] = db._now()
    forbidden = (new.get("presenter") or {}).get("forbidden") or {}
    hits = privacy.scan(render.owner_page_html(new, "x") + render.presentation_html(new, 0), forbidden)
    if hits:
        line = privacy.readiness_line(hits)
        return 409, {"ok": False, "error_ar": line["text_ar"], "privacy": line["kinds"]}
    ver, _sha = db.save_snapshot(mid, new)
    db.freeze(mid, ver)
    token = secrets.token_urlsafe(32)
    db.create_link(token, mid, ver, actor)
    db.set_build(mid, state="sent")
    db.log_event(mid, "sent", {"version": ver}, actor)
    jobs._pool.submit(pdf.to_pdf, new, pdf_path(mid, ver))
    return 200, {"ok": True, "token": token, "url": _base() + "/m/" + token, "version": ver}


def core_reopen(mid, body, actor, role):
    if role != "admin":
        return 403, {"ok": False, "error_ar": "إعادة الفتح للمدير فقط"}
    reason = " ".join(str((body or {}).get("reason") or "").split())
    if not reason:
        return 400, {"ok": False, "error_ar": "اكتب سبب إعادة الفتح"}
    m = db.meeting(mid)
    snap = db.snapshot(mid)
    if not m or not snap:
        return 404, {"ok": False, "error_ar": "الاجتماع غير موجود"}
    if not snap["frozen"]:
        return 409, {"ok": False, "error_ar": "الاجتماع لم يُرسل بعد"}
    data = copy.deepcopy(snap["data"])
    data["owner"].pop("agreed", None)
    data["meta"].pop("sent_at", None)
    ver, _sha = db.save_snapshot(mid, data)
    db.execute("UPDATE meet_snapshots SET reopen_reason=?, reopened_by=? WHERE meeting_id=? AND version=?",
               (reason, actor, int(mid), ver))
    db.set_build(mid, state="reopened")
    db.log_event(mid, "reopened", {"reason": reason, "version": ver}, actor)
    return 200, {"ok": True, "version": ver}


def core_revoke(token, actor, role):
    if role != "admin":
        return 403, {"ok": False, "error_ar": "إيقاف الرابط للمدير فقط"}
    l = db.link(token)
    if not l:
        return 404, {"ok": False, "error_ar": "الرابط غير موجود"}
    db.revoke_link(token)
    db.log_event(l["meeting_id"], "revoked", {"token_tail": token[-4:]}, actor)
    return 200, {"ok": True}


def core_wa(mid, actor):
    """-> the wa.me URL for the owner's phone with the link and Faisal's signature, or None."""
    m = db.meeting(mid)
    snap = db.snapshot(mid)
    if not m or not snap or not snap["frozen"]:
        return None, "أرسل الاجتماع أولاً ليتكوّن رابط المالك"
    link = db.active_link(mid, snap["version"])
    if not link:
        return None, "لا يوجد رابط مفعّل لهذا الاجتماع"
    phone = "".join(ch for ch in str(HOST.owner_phone(m["owner"]) if HOST.owner_phone else "") if ch.isdigit())
    if phone.startswith("05"):
        phone = "966" + phone[1:]
    if not phone:
        return None, "رقم المالك غير مسجّل في ملفه (المركز المالي ← الملاك)"
    nl = chr(10)
    text = ("السلام عليكم %s،" % m["owner"] + nl + nl + "هذا ملخص اجتماعنا اليوم عن شقتك، فيه كل ما عرضناه وما اتفقنا عليه:"
            + nl + _base() + "/m/" + link["token"] + nl + nl + "نلاحق كل ريال لشقتك." + nl + "فيصل — عوجا")
    db.log_event(mid, "wa_opened", "", actor)
    return "https://wa.me/%s?text=%s" % (phone, urllib.parse.quote(text)), None


# ------------------------------------------------------------------ the owner's public door (S5)
class _Limiter(object):
    """Sliding one-minute windows per key (aqd/routes.py pattern)."""

    def __init__(self, per_min):
        self.per_min, self.hits, self.lock = per_min, {}, threading.Lock()

    def ok(self, key):
        now = time.time()
        with self.lock:
            dq = self.hits.setdefault(key, collections.deque())
            while dq and now - dq[0] > 60:
                dq.popleft()
            if len(dq) >= self.per_min:
                return False
            dq.append(now)
            return True


IP_LIMIT = _Limiter(30)
TOKEN_LIMIT = _Limiter(20)


def _ip(request):
    return (request.headers.get("X-Forwarded-For") or request.remote or "?").split(",")[0].strip()


def _limited(request, token):
    return not (IP_LIMIT.ok(_ip(request)) and TOKEN_LIMIT.ok(token))


def core_owner_page(token):
    l = db.link(token)
    if not l or not l["active"]:
        return None
    snap = db.snapshot(l["meeting_id"], l["snapshot_version"])
    if not snap:
        return None
    m = db.meeting(l["meeting_id"])
    rt = None
    try:
        rt = HOST.owner_portal_token(m["owner"]) if HOST.owner_portal_token else None
    except Exception:
        rt = None
    db.touch_link(token)
    db.log_event(l["meeting_id"], "opened", "", "owner")
    return render.owner_page_html(snap["data"], token, rt)


def core_owner_pdf(token):
    l = db.link(token)
    if not l or not l["active"]:
        return None, False
    path = pdf_path(l["meeting_id"], l["snapshot_version"])
    db.log_event(l["meeting_id"], "pdf", "", "owner")
    return path, os.path.isfile(path)


def cursor_get(mid):
    with _cursor_lock:
        c = dict(_cursor.get(int(mid)) or {"i": 0, "by": "", "seq": 0})
    c["ok"] = True
    return c


def cursor_set(mid, i, by):
    with _cursor_lock:
        c = _cursor.get(int(mid)) or {"i": 0, "by": "", "seq": 0}
        c = {"i": max(0, int(i)), "by": by if by in ("stage", "notes") else "stage", "seq": c["seq"] + 1}
        _cursor[int(mid)] = c
        return dict(c, ok=True)


def core_page(mid, which):
    snap = db.snapshot(mid)
    if snap is None:
        return None
    if which == "notes":
        return render.notes_html(snap["data"], mid, js_version())
    return render.presentation_html(snap["data"], mid, js_version())


def _read_static(name):
    path = os.path.join(STATIC_DIR, name)
    mt = os.path.getmtime(path)
    hit = _static_cache.get(name)
    if hit and hit[0] == mt:
        return hit[1]
    with open(path, encoding="utf-8") as f:
        text = f.read()
    _static_cache[name] = (mt, text)
    return text


def core_airbnb():
    imp, rows = abnb.latest()
    mp = abnb.mapping(rows) if rows else {"by_airbnb": {}, "unmapped": []}
    titles = {}
    try:
        titles = HOST.listing_titles() or {} if HOST.listing_titles else {}
    except Exception:
        titles = {}
    meta = HOST.listings_meta() or {} if HOST.listings_meta else {}
    choices = sorted(({"lid": int(l), "name": (meta.get(int(l)) or {}).get("name") or t} for l, t in titles.items()),
                     key=lambda x: x["name"] or "")
    return {"ok": True, "latest": imp and {k: imp[k] for k in ("id", "data_as_of", "filename", "rows", "fx_sar_per_usd", "at")},
            "imports": abnb.imports()[:10], "mapped": len(mp["by_airbnb"]), "unmapped": mp["unmapped"], "choices": choices}


def core_airbnb_import(data, filename, actor):
    try:
        res = abnb.import_file(data, filename, actor)
    except ValueError as e:
        return 400, {"ok": False, "error_ar": str(e)}
    out = core_airbnb()
    out["imported"] = res
    return 200, out


def core_airbnb_map(body, actor):
    aid = str((body or {}).get("airbnb_id") or "").strip()
    if not aid.isdigit():
        return 400, {"ok": False, "error_ar": "سطر Airbnb غير صحيح"}
    lid = (body or {}).get("lid")
    try:
        lid = int(lid) if lid not in (None, "") else None
    except (TypeError, ValueError):
        return 400, {"ok": False, "error_ar": "الشقة غير صحيحة"}
    abnb.confirm(aid, lid, actor, method="manual" if lid is not None else "none")
    return 200, core_airbnb()


async def _multipart(request, limit):
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
                    raise ValueError(airbnb_import.ERR_TOO_BIG)
                chunks.append(chunk)
            data = b"".join(chunks)
        else:
            fields[part.name] = (await part.text()).strip()
    return fields, filename, data


# ------------------------------------------------------------------ handlers
async def _body(request):
    try:
        return await request.json()
    except Exception:
        return {}


async def api_record(request):
    mid = int(request.match_info["id"])
    if request.method == "POST":
        status, out = await _run(core_record_add, mid, await _body(request), _actor(request))
        return _json(out, status)
    return _json({"ok": True, "record": await _run(db.record, mid)})


async def api_record_delete(request):
    status, out = await _run(core_record_delete, int(request.match_info["id"]), await _body(request))
    return _json(out, status)


async def api_presented(request):
    status, out = await _run(core_presented, int(request.match_info["id"]), _actor(request))
    return _json(out, status)


async def api_commitments(request):
    return _json(await _run(core_commitments, (request.query.get("owner") or "").strip()))


async def api_commitment_update(request):
    status, out = await _run(core_commitment_update, int(request.match_info["cid"]), await _body(request), _actor(request))
    return _json(out, status)


async def api_send(request):
    status, out = await _run(core_send, int(request.match_info["id"]), _actor(request), _role(request))
    return _json(out, status)


async def api_reopen(request):
    status, out = await _run(core_reopen, int(request.match_info["id"]), await _body(request), _actor(request), _role(request))
    return _json(out, status)


async def api_revoke(request):
    status, out = await _run(core_revoke, request.match_info["token"], _actor(request), _role(request))
    return _json(out, status)


async def api_wa(request):
    url, err = await _run(core_wa, int(request.match_info["id"]), _actor(request))
    if not url:
        return HOST.web.Response(text=err, status=409, content_type="text/plain", charset="utf-8")
    raise HOST.web.HTTPFound(url)


async def handle_owner_page(request):
    token = request.match_info["token"]
    if _limited(request, token):
        raise HOST.web.HTTPTooManyRequests()
    html = await _run(core_owner_page, token)
    if html is None:
        raise HOST.web.HTTPNotFound()
    return HOST.web.Response(text=html, content_type="text/html", charset="utf-8",
                             headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow",
                                      "Referrer-Policy": "no-referrer"})


async def handle_owner_pdf(request):
    token = request.match_info["token"]
    if _limited(request, token):
        raise HOST.web.HTTPTooManyRequests()
    path, ready = await _run(core_owner_pdf, token)
    if path is None:
        raise HOST.web.HTTPNotFound()
    if not ready:                                  # still printing, or printing failed: the page is the fallback
        raise HOST.web.HTTPFound("/m/" + token)
    return HOST.web.FileResponse(path, headers={"Content-Type": "application/pdf", "Cache-Control": "no-store",
                                                "Content-Disposition": 'inline; filename="ouja-owner-meeting.pdf"'})

async def api_airbnb(request):
    return _json(await _run(core_airbnb))


async def api_airbnb_import(request):
    try:
        _f, filename, data = await _multipart(request, airbnb_import.MAX_BYTES)
    except ValueError as e:
        return _json({"ok": False, "error_ar": str(e)}, 400)
    if not data:
        return _json({"ok": False, "error_ar": "اختر ملف التقرير أولاً"}, 400)
    status, out = await _run(core_airbnb_import, data, filename, _actor(request))
    return _json(out, status)


async def api_airbnb_map(request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    status, out = await _run(core_airbnb_map, body, _actor(request))
    return _json(out, status)

async def api_owners(request):
    return _json(await _run(core_owners))


async def api_meetings(request):
    owner = (request.query.get("owner") or "").strip()
    return _json(await _run(core_meetings, owner))


async def api_create(request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    status, data = await _run(core_create, body, _actor(request))
    return _json(data, status)


async def api_status(request):
    status, data = await _run(core_status, int(request.match_info["id"]))
    return _json(data, status)


async def api_cursor(request):
    mid = int(request.match_info["id"])
    if request.method == "POST":
        try:
            body = await request.json()
        except Exception:
            body = {}
        try:
            i = int(body.get("i") or 0)
        except (TypeError, ValueError):
            i = 0
        return _json(cursor_set(mid, i, body.get("by")))
    return _json(cursor_get(mid))


def _login_redirect():
    raise HOST.web.HTTPFound("/dashboard#meet")


async def _page(request, which):
    if not HOST.dash_auth(request):
        _login_redirect()
    if not can_use(request):
        return HOST.web.Response(text="صفحة «اجتماع المالك» غير مفعّلة لحسابك", status=403,
                                 content_type="text/plain", charset="utf-8")
    html = await _run(core_page, int(request.match_info["id"]), which)
    if html is None:
        raise HOST.web.HTTPNotFound()
    return HOST.web.Response(text=html, content_type="text/html", charset="utf-8",
                             headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"})


async def page_present(request):
    return await _page(request, "present")


async def page_notes(request):
    return await _page(request, "notes")


async def handle_static(request):
    name = request.match_info["name"]
    if name not in STATIC_FILES:
        raise HOST.web.HTTPNotFound()
    text = await _run(_read_static, name)
    return HOST.web.Response(text=text, content_type="application/javascript", charset="utf-8",
                             headers={"Cache-Control": "no-cache"})


async def handle_font(request):
    name = request.match_info["name"]
    if name not in FONT_NAMES:
        raise HOST.web.HTTPNotFound()
    path = os.path.join(FONT_DIR, name)
    if not await _run(os.path.isfile, path):
        raise HOST.web.HTTPNotFound()
    return HOST.web.FileResponse(path, headers={"Cache-Control": "public, max-age=31536000, immutable",
                                                "Content-Type": "font/woff2"})


def register(app):
    if not config.enabled():
        return
    r = app.router
    r.add_get("/api/meet/owners", _safe(api_owners))
    r.add_get("/api/meet/meetings", _safe(api_meetings))
    r.add_post("/api/meet/meetings", _safe(api_create))
    r.add_get("/api/meet/meetings/{id:[0-9]+}", _safe(api_status))
    r.add_get("/api/meet/meetings/{id:[0-9]+}/cursor", _safe(api_cursor))
    r.add_post("/api/meet/meetings/{id:[0-9]+}/cursor", _safe(api_cursor))
    r.add_get("/api/meet/airbnb", _safe(api_airbnb))
    r.add_post("/api/meet/airbnb/import", _safe(api_airbnb_import))
    r.add_post("/api/meet/airbnb/map", _safe(api_airbnb_map))
    r.add_get("/api/meet/meetings/{id:[0-9]+}/record", _safe(api_record))
    r.add_post("/api/meet/meetings/{id:[0-9]+}/record", _safe(api_record))
    r.add_post("/api/meet/meetings/{id:[0-9]+}/record/delete", _safe(api_record_delete))
    r.add_post("/api/meet/meetings/{id:[0-9]+}/presented", _safe(api_presented))
    r.add_post("/api/meet/meetings/{id:[0-9]+}/send", _safe(api_send))
    r.add_post("/api/meet/meetings/{id:[0-9]+}/reopen", _safe(api_reopen))
    r.add_get("/api/meet/meetings/{id:[0-9]+}/wa", _safe(api_wa))
    r.add_get("/api/meet/commitments", _safe(api_commitments))
    r.add_post("/api/meet/commitments/{cid:[0-9]+}", _safe(api_commitment_update))
    r.add_post("/api/meet/links/{token:[A-Za-z0-9_-]+}/revoke", _safe(api_revoke))
    r.add_get("/m/{token:[A-Za-z0-9_-]+}.pdf", handle_owner_pdf)
    r.add_get("/m/{token:[A-Za-z0-9_-]+}", handle_owner_page)
    r.add_get("/meet/static/{name}", handle_static)
    r.add_get("/meet/font/{name}", handle_font)
    r.add_get("/meet/{id:[0-9]+}", page_present)
    r.add_get("/meet/{id:[0-9]+}/notes", page_notes)
