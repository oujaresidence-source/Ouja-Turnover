# -*- coding: utf-8 -*-
"""Ouja Finance ERP v2 — المركز المالي الجديد.

The new finance system. Lives ENTIRELY in this package — never inside bot.py.
bot.py mounts it with a ~6-line patch inside start_web_server():

    import sys as _erp_sys, finance as _finance_erp
    _finance_erp.mount(app, _erp_sys.modules[__name__])

DESIGN CONTRACT (META-1 of the build prompt):
- We NEVER `import bot`. bot.py runs as __main__; importing it by name would
  execute the whole 45k-line monolith a SECOND time (second Discord client,
  second web server). Instead bot.py hands us its live module object at mount
  time and every reuse of existing functions/data goes through `api.B.<name>`.
- Auth is the dashboard's own: B._dash_auth (login) + B._user_can (roles).
- STATE_DIR data files are sacred: this package reuses bot.py's loaders and
  stores; it does not invent parallel copies of existing data.

Files:
    __init__.py        routes + handlers (this file)
    api.py             thin bridge to bot.py's functions/data + auth helpers
    statements.py      financial statements + budget math (pure, testable)
    templates/erp.html SPA shell (re-read per request — no stale-template pain)
    static/erp.js      front-end
    static/erp.css     styles (Ouja OS tokens copied from the dashboard)
"""

import os
import json
import time
import asyncio
import pathlib
from datetime import datetime, timezone, timedelta

from aiohttp import web

from . import api
from . import owners as OW

# Bumped on EVERY shipped slice — this string + commit + build time is the
# owner's 5-second proof that a deploy actually reached production.
ERP_VERSION = "2.2.8"

_DIR = pathlib.Path(__file__).resolve().parent
_BOOT = time.time()
_KSA = timezone(timedelta(hours=3))


def _detect_commit():
    """Short git hash of the running build. Railway injects RAILWAY_GIT_COMMIT_SHA;
    local dev falls back to reading .git directly (no subprocess)."""
    for k in ("RAILWAY_GIT_COMMIT_SHA", "GIT_COMMIT", "SOURCE_VERSION", "COMMIT_SHA"):
        v = (os.environ.get(k) or "").strip()
        if v:
            return v[:10]
    try:
        root = _DIR.parent
        head = (root / ".git" / "HEAD").read_text("utf-8").strip()
        if not head.startswith("ref:"):
            return head[:10]
        ref = head.split(None, 1)[1].strip()
        ref_file = root / ".git" / ref
        if ref_file.exists():
            return ref_file.read_text("utf-8").strip()[:10]
        packed = root / ".git" / "packed-refs"
        if packed.exists():
            for line in packed.read_text("utf-8").splitlines():
                if line.endswith(ref):
                    return line.split(" ", 1)[0][:10]
    except Exception:
        pass
    return "unknown"


_COMMIT = _detect_commit()
_BUILT = datetime.fromtimestamp(_BOOT, _KSA).strftime("%Y-%m-%d %H:%M") + " KSA"


def version_info():
    return {
        "ok": True,
        "app": "ouja-finance-erp",
        "version": ERP_VERSION,
        "commit": _COMMIT,
        "built": _BUILT,
        "uptime_s": int(time.time() - _BOOT),
    }


# Branded "open it from the dashboard" gate — same idea as the invest 403 page.
_GATE_HTML = """<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>عوجا — المركز المالي</title>
<style>body{margin:0;font-family:'Tajawal',-apple-system,system-ui,sans-serif;background:#F5F5F7;color:#1D1D1F;
display:flex;align-items:center;justify-content:center;min-height:100vh}
.c{background:#fff;border:1px solid #E8E8ED;border-radius:18px;padding:40px 44px;max-width:420px;text-align:center;
box-shadow:0 4px 12px rgba(0,0,0,.06)}
h1{font-size:19px;margin:0 0 10px}p{font-size:14.5px;color:#6E6E73;line-height:1.9;margin:0}</style></head>
<body><div class="c"><h1>هالصفحة محمية 🔒</h1>
<p>المركز المالي يفتح من داخل لوحة عوجا.<br>ارجع للوحة وافتحه من القائمة الجانبية.</p></div></body></html>"""


async def _h_version(request):
    """Ungated build stamp — no business data, just proof of what's deployed."""
    return web.json_response(version_info())


async def _h_erp(request):
    if not api.authed(request):
        return web.Response(text=_GATE_HTML, content_type="text/html", status=401)
    try:
        html = (_DIR / "templates" / "erp.html").read_text("utf-8")
    except Exception as e:
        return web.Response(text="erp.html missing: %r" % (e,), status=500)
    html = (html.replace("__ERP_VERSION__", ERP_VERSION)
                .replace("__ERP_COMMIT__", _COMMIT)
                .replace("__ERP_BUILT__", _BUILT))
    return web.Response(text=html, content_type="text/html")


# ---------------- API handlers (auth enforced here — /erp/* is outside the
# /api/* role middleware in bot.py, so nothing is implicit) ----------------

async def _h_api_work_queue(request):
    if not api.authed(request):
        return api.jres({"error": "unauthorized"}, 401)
    if not api.can_finance(request):
        return api.jres({"error": "forbidden", "detail": "finance role required"}, 403)
    try:
        return api.jres(await api.work_queue(request))
    except Exception as e:
        return api.jres({"error": "work_queue_failed", "detail": str(e)[:300]}, 500)


async def _h_api_approve(request):
    if not api.authed(request):
        return api.jres({"error": "unauthorized"}, 401)
    if not api.can_finance(request):
        return api.jres({"error": "forbidden", "detail": "finance role required"}, 403)
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    try:
        data, status = api.approve(request, body)
        return api.jres(data, status)
    except Exception as e:
        return api.jres({"error": "approve_failed", "detail": str(e)[:300]}, 500)


def _guarded(handler, write=False):
    """Wrap a handler with the standard auth + role gate + error envelope."""
    async def wrapped(request):
        if not api.authed(request):
            return api.jres({"error": "unauthorized"}, 401)
        if not api.can_finance(request):
            return api.jres({"error": "forbidden", "detail": "finance role required"}, 403)
        try:
            return await handler(request)
        except Exception as e:
            return api.jres({"error": "internal", "detail": str(e)[:300]}, 500)
    return wrapped


async def _h_api_bank(request):
    return api.jres(api.bank_register(request.query))


async def _h_api_bank_upload(request):
    # Delegate to bot.py's importer (multipart `file` + `save` field, two-step
    # preview→confirm, dup shield inside). It enforces _fb_can_finance itself too.
    resp = await api.B._api_fb_bank_import(request)
    try:
        payload = json.loads(resp.body)
    except Exception:
        return resp
    # After a confirmed save, auto-apply the stored rules to the new
    # needs_review rows (idempotent — rules only fill unclassified txns).
    if payload.get("ok") and payload.get("saved"):
        applied = api.rules_apply_pending(api.actor(request))
        payload["rules_applied"] = len(applied)
        return api.jres(payload, resp.status)
    return resp


async def _h_api_bank_classify(request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    data, status = api.bank_classify(request, body if isinstance(body, dict) else {})
    return api.jres(data, status)


async def _h_api_accounts(request):
    return api.jres(api.accounts_payload())


_refresh_lock = {"busy": False}


async def _h_api_accounts_refresh(request):
    """Re-pull the chart/cost-centers/etc. from Daftra (idempotent import)."""
    if _refresh_lock["busy"]:
        return api.jres({"error": "busy", "message_ar": "فيه استيراد شغال الحين — انتظره يخلص.",
                         "message_en": "An import is already running."}, 409)
    _refresh_lock["busy"] = True
    try:
        res = await asyncio.to_thread(api.B._daftra_import_all, api.actor(request))
        return api.jres({"ok": True, "result": {
            "imported": res.get("imported"), "updated": res.get("updated"),
            "failed": res.get("failed"),
            "accounts": (res.get("per_object") or {}).get("accounts")},
            "chart": api.accounts_payload()["counts"]})
    finally:
        _refresh_lock["busy"] = False


async def _json_body(request):
    try:
        b = await request.json()
        return b if isinstance(b, dict) else {}
    except Exception:
        return {}


async def _h_api_rules_list(request):
    return api.jres(api.rules_list(request))


async def _h_api_rule_create(request):
    data, status = api.rule_create(request, await _json_body(request))
    return api.jres(data, status)


async def _h_api_rule_toggle(request):
    data, status = api.rule_toggle(request, await _json_body(request))
    return api.jres(data, status)


async def _h_api_rule_delete(request):
    data, status = api.rule_delete(request, await _json_body(request))
    return api.jres(data, status)


async def _h_api_rule_undo(request):
    data, status = api.rule_undo(request, await _json_body(request))
    return api.jres(data, status)


async def _h_api_rules_precision(request):
    return api.jres(api.rules_precision())


async def _h_api_match(request):
    # candidate scoring scans stores and may touch the Hostaway reservation
    # cache (cold cache = one HTTP pull) — keep it off the event loop.
    data = await asyncio.to_thread(api.match_queue, dict(request.query))
    return api.jres(data)


async def _h_api_match_accept(request):
    data, status = api.match_accept(request, await _json_body(request))
    return api.jres(data, status)


async def _h_api_match_reject(request):
    data, status = api.match_reject(request, await _json_body(request))
    return api.jres(data, status)


async def _h_api_match_daftra(request):
    """Delegate to the existing dup machinery (suggestions / journal lines /
    link / link_distributed / not_duplicate / ignore) so verification semantics
    stay byte-identical — then append to the v2 decision log on writes."""
    resp = await api.B._api_fb_daftra_dup(request)
    if request.method == "POST" and resp.status == 200:
        try:
            body = await request.json()
            payload = json.loads(resp.body)
            if payload.get("ok") and body.get("action") in (
                    "link", "link_distributed", "not_duplicate", "ignore"):
                api.match_log_add(request, str(body.get("id") or ""), "daftra",
                                  body.get("action"), {"daftra": body.get("daftra"),
                                                       "reason": body.get("reason") or ""})
        except Exception:
            pass
    return resp


async def _h_api_match_promote(request):
    """«ما له مقابل» — create the missing side as a canonical ledger entry
    (becomes a DRAFT Daftra journal; posts only via migration). Delegates to
    the existing promote action with its dup-shield guard intact."""
    body = await _json_body(request)
    if body.get("action") != "promote":
        return api.jres({"error": "only_promote_allowed"}, 400)
    resp = await api.B._api_fb_entry(request)
    if resp.status == 200:
        try:
            payload = json.loads(resp.body)
            if payload.get("ok"):
                api.match_log_add(request, str(body.get("id") or ""), "ledger", "promote",
                                  {"entry": (payload.get("entry") or {}).get("id")})
        except Exception:
            pass
    return resp


async def _h_api_match_log(request):
    return api.jres({"ok": True, "log": api.match_log_recent()})


async def _h_api_exp(request):
    resp = await api.B._api_exp4_overview(request)
    try:
        payload = json.loads(resp.body)
        if payload.get("ok"):
            return api.jres(api.exp_attach_bank(payload), resp.status)
    except Exception:
        pass
    return resp


async def _h_api_exp_detail(request):
    resp = await api.B._api_exp4_detail(request)
    try:
        payload = json.loads(resp.body)
        if payload.get("ok"):
            ex = api.B._expenses.get(str(request.query.get("id") or ""))
            payload["bank_txn_id"] = (ex or {}).get("bank_txn_id") or ""
            return api.jres(payload, resp.status)
    except Exception:
        pass
    return resp


def _exp_delegate(name):
    async def h(request):
        return await getattr(api.B, name)(request)
    return h


async def _h_api_custody(request):
    return api.jres(api.custody_payload())


async def _h_api_stmts(request):
    data = await asyncio.to_thread(api.stmts_payload, dict(request.query))
    return api.jres(data)


async def _h_api_stmts_account(request):
    data = await asyncio.to_thread(api.stmts_account_lines, dict(request.query))
    return api.jres(data)


async def _h_api_stmts_probe(request):
    return api.jres(api.stmts_type_probe())


async def _h_api_stmts_xlsx(request):
    payload = await asyncio.to_thread(api.stmts_payload, dict(request.query))
    data = await asyncio.to_thread(api.stmts_xlsx, payload)
    return web.Response(body=data,
                        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition":
                                 "attachment; filename=ouja-statements-" + payload["month"] + ".xlsx"})


async def _h_api_stmts_pdf(request):
    payload = await asyncio.to_thread(api.stmts_payload, dict(request.query))
    try:
        data = await asyncio.to_thread(api.stmts_pdf, payload)
    except api.B.PdfFontError:
        return api.jres({"error": "pdf_font_unavailable",
                         "message_ar": "خط الـ PDF العربي غير متاح — جرّب بعد دقيقة.",
                         "message_en": "Arabic PDF font unavailable — try again shortly."}, 503)
    return web.Response(body=data, content_type="application/pdf",
                        headers={"Content-Disposition":
                                 "attachment; filename=ouja-statements-" + payload["month"] + ".pdf"})


async def _h_api_close_get(request):
    data = await asyncio.to_thread(api.close_get, dict(request.query))
    return api.jres(data)


async def _h_api_close_do(request):
    body = await _json_body(request)
    data, status = await asyncio.to_thread(api.close_do, request, body)
    return api.jres(data, status)


async def _h_api_migrate_preview(request):
    data = await asyncio.to_thread(api.migrate_preview, dict(request.query))
    return api.jres(data)


async def _h_api_migrate_run(request):
    body = await _json_body(request)
    data, status = await asyncio.to_thread(api.migrate_run, request, body)
    return api.jres(data, status)


async def _h_api_budget_get(request):
    data = await asyncio.to_thread(api.budget_get, dict(request.query))
    return api.jres(data)


async def _h_api_budget_set(request):
    body = await _json_body(request)
    data, status = api.budget_set(request, body)
    return api.jres(data, status)


async def _h_api_owners(request):
    return api.jres(api.owners_payload())


async def _h_api_owners_diagnose(request):
    """Slice 0b: line-by-line reconciliation of one owner-month (read-only)."""
    owner = (request.query.get("owner") or "").strip()
    if not owner:
        return api.jres({"error": "owner_required"}, 400)
    mkey = api._month_key_or_prev(request.query.get("m"))
    data = await asyncio.to_thread(OW.diagnose, owner, mkey)
    return api.jres(data, 200 if data.get("ok") else 404)


async def _h_api_owner_detail(request):
    owner = (request.query.get("owner") or "").strip()
    if not owner:
        return api.jres({"error": "owner_required"}, 400)
    return api.jres(OW.owner_detail(owner))


async def _h_api_owner_profile(request):
    """v2.2 slice 3: the owner profile — header + chips + 12-month grid."""
    owner = (request.query.get("owner") or "").strip()
    if not owner:
        return api.jres({"error": "owner_required"}, 400)
    data = await asyncio.to_thread(OW.owner_profile, owner)
    return api.jres(data, 200 if data.get("ok") else 404)


async def _h_api_owner_save(request):
    data, status = OW.owner_save(request, await _json_body(request))
    return api.jres(data, status)


async def _h_api_unit_add(request):
    data, status = OW.unit_add(request, await _json_body(request))
    return api.jres(data, status)


async def _h_api_unit_remove(request):
    data, status = OW.unit_remove(request, await _json_body(request))
    return api.jres(data, status)


async def _h_api_unit_terms(request):
    data, status = OW.unit_terms_set(request, await _json_body(request))
    return api.jres(data, status)


async def _h_api_owner_listings_search(request):
    return api.jres(OW.listings_search(request.query.get("q") or ""))


async def _h_api_stmt_get(request):
    owner = (request.query.get("owner") or "").strip()
    if not owner:
        return api.jres({"error": "owner_required"}, 400)
    mkey = api._month_key_or_prev(request.query.get("m"))
    data = await asyncio.to_thread(OW.statement_payload, owner, mkey)
    return api.jres(data, 200 if data.get("ok") else 404)


async def _h_api_stmt_edit(request):
    data, status = await asyncio.to_thread(OW.statement_edit, request, await _json_body(request))
    return api.jres(data, status)


async def _h_api_stmt_publish(request):
    data, status = await asyncio.to_thread(OW.statement_publish, request, await _json_body(request))
    return api.jres(data, status)


async def _h_api_stmt_diff(request):
    owner = (request.query.get("owner") or "").strip()
    mkey = api._month_key_or_prev(request.query.get("m"))
    data = await asyncio.to_thread(OW.statement_recompute_diff, owner, mkey)
    return api.jres(data, 200 if data.get("ok") else 404)


async def _h_api_stmt_tieout(request):
    """v2.2 slice 2: تطابق الكشوف — per-unit subtotals vs aggregate vs PDF fixture."""
    owner = (request.query.get("owner") or "").strip()
    if not owner:
        return api.jres({"error": "owner_required"}, 400)
    mkey = api._month_key_or_prev(request.query.get("m"))
    data = await asyncio.to_thread(OW.statement_tieout, owner, mkey)
    return api.jres(data, 200 if data.get("ok") else 404)


async def _h_api_cycle(request):
    mkey = api._month_key_or_prev(request.query.get("m"))
    data = await asyncio.to_thread(OW.cycle_board, mkey)
    return api.jres(data)


async def _h_api_cycle_status(request):
    data, status = OW.cycle_status_set(request, await _json_body(request))
    return api.jres(data, status)


async def _h_api_cycle_links(request):
    data, status = OW.cycle_links(request, await _json_body(request))
    return api.jres(data, status)


async def _h_api_cycle_template(request):
    body = await _json_body(request)
    return api.jres({"ok": True, "wa_template": OW.wa_template_set(request, body.get("text"))})


async def _h_api_owners_link(request):
    # Delegate to the existing owner-link manager (finance-write gated inside;
    # create/regenerate/revoke + full audit live there).
    return await api.B._api_finance_owner_link(request)


# ---------- /fin/receipt/{expense_id}?t=<owner_token> — the receipt PROXY ----------
# PUBLIC route (owners hold no dashboard session). The owner token IS the auth;
# scope = that owner's apartments only. Fetches the file through the existing
# Google Drive service account so the guest's sharing settings never break it.
# Missing receipt → an honest «بدون فاتورة مرفقة» page — never a dead link.

_RECEIPT_NOTE_HTML = """<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>عوجا — الفاتورة</title><style>body{margin:0;font-family:'IBM Plex Sans Arabic','Tajawal',system-ui,sans-serif;
background:#F7F1E6;color:#2F241B;display:flex;align-items:center;justify-content:center;min-height:100vh}
.c{background:#FFFDF8;border:1px solid #E5D8C4;border-radius:14px;padding:36px 40px;max-width:400px;text-align:center}
h1{font-size:17px;margin:0 0 8px}p{font-size:13.5px;color:#7A6A58;line-height:1.9;margin:0}</style></head>
<body><div class="c"><h1>__T__</h1><p>__P__</p></div></body></html>"""


def _receipt_note(title, sub, status=200):
    return web.Response(text=_RECEIPT_NOTE_HTML.replace("__T__", title).replace("__P__", sub),
                        content_type="text/html", status=status)


async def _h_receipt_proxy(request):
    B = api.B
    token = (request.query.get("t") or "").strip()
    eid = (request.match_info.get("expense_id") or "").strip()
    try:
        owner = B._owner_by_token(token) if token else None
    except Exception:
        owner = None
    if not owner:
        return _receipt_note("هالرابط محمي 🔒", "افتح الفاتورة من داخل كشف حسابك.", 403)
    ex = B._expenses.get(eid) or next(
        (e for e in B._expenses.values() if str(e.get("id")) == eid), None)
    if not ex:
        return _receipt_note("بدون فاتورة مرفقة", "ما لقينا هالمصروف في السجل.", 404)
    apts, lids = api.owner_apartments(owner)
    if not (((ex.get("apartment") or "").strip() in apts)
            or (str(ex.get("listing_id") or "") in lids)):
        return _receipt_note("هالرابط محمي 🔒", "الفاتورة تخص شقة خارج حسابك.", 403)
    link = ex.get("receipt_link") or ""
    import re as _re
    m = _re.search(r"[-\w]{25,}", link)
    if not m:
        return _receipt_note("بدون فاتورة مرفقة", "هالمصروف انسجّل بدون فاتورة.")

    file_id = m.group(0)

    def _download():
        svc = B._cleanproof_get_drive_service()
        if not svc:
            return None, None
        import io as _io
        from googleapiclient.http import MediaIoBaseDownload
        meta = svc.files().get(fileId=file_id, fields="mimeType,name").execute()
        buf = _io.BytesIO()
        dn = MediaIoBaseDownload(buf, svc.files().get_media(fileId=file_id))
        done = False
        while not done:
            _, done = dn.next_chunk()
        return buf.getvalue(), (meta.get("mimeType") or "application/octet-stream")

    try:
        data, mime = await asyncio.to_thread(_download)
    except Exception:
        data, mime = None, None
    if not data:
        return _receipt_note("تعذّر جلب الفاتورة الحين", "حاول بعد دقيقة — أو كلمنا ونرسلها لك مباشرة.")
    return web.Response(body=data, content_type=mime,
                        headers={"Cache-Control": "private, max-age=600",
                                 "X-Robots-Tag": "noindex"})


async def _h_api_contracts(request):
    return api.jres(api.contracts_list())


async def _h_api_contract_link(request):
    data, status = api.contract_link(request, await _json_body(request))
    return api.jres(data, status)


async def _h_api_custody_map(request):
    return api.jres(api.custody_map_data())


async def _h_api_custody_map_set(request):
    data, status = api.custody_map_set(request, await _json_body(request))
    return api.jres(data, status)


def mount(app, botmod):
    """Attach ERP v2 to the running aiohttp app. Called once from bot.py."""
    api.attach(botmod)
    # v2.1: the owner portal/PDF/close-checks read the effective-dated statement
    # through this hook (bot.py falls back to its legacy aggregate on any error).
    # Published snapshot wins; live compute otherwise (slice 2).
    botmod._owner_statement_hook = OW.statement_for_portal
    app.router.add_get("/erp", _h_erp)
    app.router.add_get("/erp/version", _h_version)
    app.router.add_get("/erp/api/work-queue", _h_api_work_queue)
    app.router.add_post("/erp/api/approve", _h_api_approve)
    app.router.add_get("/erp/api/bank", _guarded(_h_api_bank))
    app.router.add_post("/erp/api/bank/upload", _guarded(_h_api_bank_upload, write=True))
    app.router.add_post("/erp/api/bank/classify", _guarded(_h_api_bank_classify, write=True))
    app.router.add_get("/erp/api/accounts", _guarded(_h_api_accounts))
    app.router.add_post("/erp/api/accounts/refresh", _guarded(_h_api_accounts_refresh, write=True))
    app.router.add_get("/erp/api/rules", _guarded(_h_api_rules_list))
    app.router.add_post("/erp/api/rules", _guarded(_h_api_rule_create, write=True))
    app.router.add_post("/erp/api/rules/toggle", _guarded(_h_api_rule_toggle, write=True))
    app.router.add_post("/erp/api/rules/delete", _guarded(_h_api_rule_delete, write=True))
    app.router.add_post("/erp/api/rules/undo", _guarded(_h_api_rule_undo, write=True))
    app.router.add_get("/erp/api/rules/precision", _guarded(_h_api_rules_precision))
    app.router.add_get("/erp/api/contracts", _guarded(_h_api_contracts))
    app.router.add_post("/erp/api/contracts/link", _guarded(_h_api_contract_link, write=True))
    app.router.add_get("/erp/api/custody-map", _guarded(_h_api_custody_map))
    app.router.add_post("/erp/api/custody-map", _guarded(_h_api_custody_map_set, write=True))
    app.router.add_get("/erp/api/match", _guarded(_h_api_match))
    app.router.add_post("/erp/api/match/accept", _guarded(_h_api_match_accept, write=True))
    app.router.add_post("/erp/api/match/reject", _guarded(_h_api_match_reject, write=True))
    app.router.add_get("/erp/api/match/daftra", _guarded(_h_api_match_daftra))
    app.router.add_post("/erp/api/match/daftra", _guarded(_h_api_match_daftra, write=True))
    app.router.add_post("/erp/api/match/promote", _guarded(_h_api_match_promote, write=True))
    app.router.add_get("/erp/api/match/log", _guarded(_h_api_match_log))
    app.router.add_get("/erp/api/exp", _guarded(_h_api_exp))
    app.router.add_get("/erp/api/exp/detail", _guarded(_h_api_exp_detail))
    app.router.add_post("/erp/api/exp/approve", _guarded(_exp_delegate("_api_exp4_approve"), write=True))
    app.router.add_post("/erp/api/exp/reject", _guarded(_exp_delegate("_api_exp4_reject"), write=True))
    app.router.add_post("/erp/api/exp/edit", _guarded(_exp_delegate("_api_exp4_edit"), write=True))
    app.router.add_post("/erp/api/exp/export", _guarded(_exp_delegate("_api_exp4_export"), write=True))
    app.router.add_post("/erp/api/exp/recheck", _guarded(_exp_delegate("_api_exp4_recheck"), write=True))
    app.router.add_get("/erp/api/exp/intake", _guarded(_exp_delegate("_api_exp4_intake_get")))
    app.router.add_post("/erp/api/exp/intake", _guarded(_exp_delegate("_api_exp4_intake_set"), write=True))
    app.router.add_post("/erp/api/exp/pull-preview", _guarded(_exp_delegate("_api_exp4_pull_preview"), write=True))
    app.router.add_post("/erp/api/exp/pull", _guarded(_exp_delegate("_api_exp4_pull_run"), write=True))
    app.router.add_post("/erp/api/exp/delete-all", _guarded(_exp_delegate("_api_exp4_delete_all"), write=True))
    app.router.add_get("/erp/api/daftra/introspect", _guarded(_exp_delegate("_api_daftra_introspect")))
    app.router.add_post("/erp/api/daftra/write-test", _guarded(_exp_delegate("_api_daftra_write_test"), write=True))
    app.router.add_get("/erp/api/custody", _guarded(_h_api_custody))
    app.router.add_get("/erp/api/owners", _guarded(_h_api_owners))
    app.router.add_get("/erp/api/owners/diagnose", _guarded(_h_api_owners_diagnose))
    app.router.add_get("/erp/api/owners/detail", _guarded(_h_api_owner_detail))
    app.router.add_get("/erp/api/owners/profile", _guarded(_h_api_owner_profile))
    app.router.add_post("/erp/api/owners/save", _guarded(_h_api_owner_save, write=True))
    app.router.add_post("/erp/api/owners/unit-add", _guarded(_h_api_unit_add, write=True))
    app.router.add_post("/erp/api/owners/unit-remove", _guarded(_h_api_unit_remove, write=True))
    app.router.add_post("/erp/api/owners/unit-terms", _guarded(_h_api_unit_terms, write=True))
    app.router.add_get("/erp/api/owners/listings-search", _guarded(_h_api_owner_listings_search))
    app.router.add_get("/erp/api/owners/statement", _guarded(_h_api_stmt_get))
    app.router.add_post("/erp/api/owners/statement/edit", _guarded(_h_api_stmt_edit, write=True))
    app.router.add_post("/erp/api/owners/statement/publish", _guarded(_h_api_stmt_publish, write=True))
    app.router.add_get("/erp/api/owners/statement/diff", _guarded(_h_api_stmt_diff))
    app.router.add_get("/erp/api/owners/statement/tieout", _guarded(_h_api_stmt_tieout))
    app.router.add_get("/erp/api/owners/cycle", _guarded(_h_api_cycle))
    app.router.add_post("/erp/api/owners/cycle/status", _guarded(_h_api_cycle_status, write=True))
    app.router.add_post("/erp/api/owners/cycle/links", _guarded(_h_api_cycle_links, write=True))
    app.router.add_post("/erp/api/owners/cycle/template", _guarded(_h_api_cycle_template, write=True))
    app.router.add_get("/erp/api/owners/link", _guarded(_h_api_owners_link))
    app.router.add_post("/erp/api/owners/link", _guarded(_h_api_owners_link, write=True))
    app.router.add_get("/erp/api/stmts", _guarded(_h_api_stmts))
    app.router.add_get("/erp/api/stmts/account", _guarded(_h_api_stmts_account))
    app.router.add_get("/erp/api/stmts/type-probe", _guarded(_h_api_stmts_probe))
    app.router.add_get("/erp/api/stmts/export.xlsx", _guarded(_h_api_stmts_xlsx))
    app.router.add_get("/erp/api/stmts/export.pdf", _guarded(_h_api_stmts_pdf))
    app.router.add_get("/erp/api/close", _guarded(_h_api_close_get))
    app.router.add_post("/erp/api/close", _guarded(_h_api_close_do, write=True))
    app.router.add_get("/erp/api/migrate", _guarded(_h_api_migrate_preview))
    app.router.add_post("/erp/api/migrate", _guarded(_h_api_migrate_run, write=True))
    app.router.add_get("/erp/api/budget", _guarded(_h_api_budget_get))
    app.router.add_post("/erp/api/budget", _guarded(_h_api_budget_set, write=True))
    app.router.add_get("/fin/receipt/{expense_id}", _h_receipt_proxy)   # owner-token scoped (public route)
    app.router.add_static("/erp/static/", path=str(_DIR / "static"), name="erp-static")
    return True
