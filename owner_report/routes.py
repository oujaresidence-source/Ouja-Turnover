# -*- coding: utf-8 -*-
"""
owner_report.routes — aiohttp handlers for the Owner Report wizard.

Auth model (mirrors schedule): every endpoint needs dashboard auth; writes + preview +
export additionally require an editor role (admin/ops). The gated wizard cannot be skipped
— export runs the full build_report gate chain and refuses on any violation.

Flow: pick unit -> wizard (prefilled, every field re-confirmed) -> reconcile (sign-off) ->
preview -> export (immutable snapshot).
"""
from __future__ import annotations

import asyncio
import datetime
import pathlib
import traceback

from . import live, questions, page
from .host import HOST
from .assumptions import AssumptionStore
from .audit_log import AuditLog
from .errors import BuildError, ValidationError

EDIT_ROLES = ("admin", "ops")


def _store():
    return AssumptionStore(HOST.require("load_json"), HOST.require("save_json"))


def _audit():
    return AuditLog(HOST.require("load_json"), HOST.require("save_json"))


def _reports_dir():
    d = pathlib.Path(HOST.require("state_path")("owner_reports"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _now_iso():
    try:
        return HOST.now().isoformat()
    except Exception:
        return datetime.datetime.utcnow().isoformat()


def can_edit(request):
    try:
        return (HOST.req_role(request) if HOST.req_role else "viewer") in EDIT_ROLES
    except Exception:
        return False


def _guard(request):
    if not HOST.dash_auth(request):
        return HOST.json_response({"ok": False, "error": "unauthorized"}, 401)
    return None


def _deny():
    return HOST.json_response({"ok": False, "error": "غير مصرّح لك بإصدار التقارير"}, 403)


def _safe(fn):
    async def _w(request):
        g = _guard(request)
        if g:
            return g
        try:
            return await fn(request)
        except (BuildError, ValidationError) as e:
            return HOST.json_response({"ok": False, "error": str(e),
                                       "violations": getattr(e, "violations", None)}, 200)
        except Exception as e:
            traceback.print_exc()
            return HOST.json_response({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}, 200)
    _w.__name__ = getattr(fn, "__name__", "w")
    return _w


async def _body(request):
    try:
        d = await request.json()
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _actor(request):
    try:
        return HOST.actor(request) if HOST.actor else "operator"
    except Exception:
        return "operator"


# ─────────────────────────── wizard data ───────────────────────────
async def api_units(request):
    return HOST.json_response({"ok": True, "units": live.list_units()})


async def api_question_bank(request):
    bank = {s: [{"id": q.id, "kind": q.kind, "en": q.en, "ar": q.ar, "required": q.required,
                 "options": [{"value": v, "en": e, "ar": a} for (v, e, a) in q.options],
                 "note_en": q.note_en, "note_ar": q.note_ar, "maps_to": q.maps_to}
                for q in questions.BY_SECTION[s]]
            for s in questions.SECTIONS}
    sections = [{"key": k, "en": v[0], "ar": v[1]} for k, v in questions.SECTIONS.items()]
    return HOST.json_response({"ok": True, "sections": sections, "bank": bank})


async def api_wizard_load(request):
    lid = request.query.get("lid", "")
    store = _store()
    stored = store.stored(lid)
    if not stored:
        # first run for this unit: seed the editable operator template with the unit name
        units = {u["lid"]: u["name"] for u in live.list_units()}
        stored = live.operator_template({"listing_name_en": units.get(lid, "")})
    prefill = {"values": stored, "prefill_meta": store.prefill(lid)}
    return HOST.json_response({"ok": True, "lid": lid, **prefill})


async def api_wizard_save(request):
    if not can_edit(request):
        return _deny()
    b = await _body(request)
    lid = b.get("lid", "")
    values = b.get("values") or {}
    _store().record(lid, values, _actor(request), _now_iso())
    return HOST.json_response({"ok": True})


# ─────────────────────────── build steps ───────────────────────────
def _build_meta(b, disclosures=None):
    """Assemble the validation meta from the wizard's confirmation payload."""
    m = {
        "vat_resolved": bool(b.get("vat_resolved")),
        "vat_reconciled_against_payout": bool(b.get("vat_reconciled_against_payout")),
        "reconciliation_signed": bool(b.get("reconciliation_signed")),
        "cancelled_in_revenue": int(b.get("cancelled_in_revenue", 0) or 0),
        "lease_sections_enabled": bool(b.get("lease_sections_enabled", True)),
        "owner_blocked_nights": int(b.get("owner_blocked_nights", 0) or 0),
        "owner_blocked_treatment": b.get("owner_blocked_treatment", "exclude"),
        "ejar_is_single_contract": bool(b.get("ejar_is_single_contract")),
        "ejar_unfurnished_no_uplift": bool(b.get("ejar_unfurnished_no_uplift")),
        "comp_stale": bool(b.get("comp_stale")),
        "manual_bookings": int(b.get("manual_bookings", 0) or 0),
        "acknowledged": list(b.get("acknowledged") or []),
        "required_fields_confirmed": bool(b.get("required_fields_confirmed")),
    }
    if disclosures is not None:
        m["disclosures"] = list(disclosures)
    return m


def _prepare(b):
    """Gather Hostaway H + assemble inputs + build cfg. Returns (inputs, cfg, manifest, disc)."""
    from .model import build_cfg
    lid = b.get("lid", "")
    answers = b.get("values") or _store().stored(lid)
    start = b["period_start"]
    end = b["period_end"]
    months = int(b.get("months", 6))
    ha = live.gather_hostaway(lid, start, end, months, answers.get("vat_basis", "net"))
    inputs = live.assemble_inputs(answers, ha)
    inputs["lid"] = lid
    if not inputs["costs"].get("channel_fees") and b.get("channel_fees"):
        inputs["costs"]["channel_fees"] = float(b["channel_fees"])
    cfg, manifest, disc = build_cfg(inputs)
    return inputs, cfg, manifest, disc, ha


# The Hostaway pulls and the frozen renderer are BLOCKING and the renderer uses the
# Playwright SYNC API, which cannot run inside the aiohttp event loop. Every handler that
# touches them runs the work in a worker thread via asyncio.to_thread.
def _reconcile_sync(b):
    from .build import reconciliation
    from .validate import validate
    inputs, cfg, manifest, disc, ha = _prepare(b)
    recon = reconciliation(cfg)
    meta = _build_meta(b, disclosures=disc)
    meta.setdefault("reservation_revenue_total", ha["reservation_revenue_total"])
    res = validate(cfg, meta)
    return {
        "ok": True, "reconciliation": recon, "hostaway_revenue_total": ha["reservation_revenue_total"],
        "degraded": ha.get("degraded"), "disclosures": list(disc),
        "hard": res.hard, "soft": [{"code": c, "msg": m} for c, m in res.soft],
        "can_render": res.ok, "tags": {t: sum(1 for e in manifest if e.tag == t) for t in "HOMC"},
    }


async def api_reconcile(request):
    """Compute the reconciliation chain + validation result WITHOUT rendering."""
    b = await _body(request)
    return HOST.json_response(await asyncio.to_thread(_reconcile_sync, b))


def _preview_sync(b, actor, now):
    from .build import build_report
    inputs, cfg, manifest, disc, ha = _prepare(b)
    meta = _build_meta(b, disclosures=disc)
    meta["reconciliation_signed"] = True   # preview is the pre-sign review; not an issued report
    meta.setdefault("reservation_revenue_total", ha["reservation_revenue_total"])
    out = _reports_dir() / ("_preview_%s.pdf" % (cfg["REPORT"].get("doc_ref") or "draft"))
    res = build_report(inputs, meta, out, generated_by=actor, created_at=now, audit_log=None)
    return {"ok": True, "pdf": "/owner-report/pdf/" + out.name,
            "doc_ref": res["doc_ref"], "draft": True}


async def api_preview(request):
    """Render a DRAFT for review (pre-sign). All data gates enforced; no snapshot issued."""
    if not can_edit(request):
        return _deny()
    b = await _body(request)
    return HOST.json_response(await asyncio.to_thread(_preview_sync, b, _actor(request), _now_iso()))


def _export_sync(b, actor, now):
    from .build import build_report
    inputs, cfg, manifest, disc, ha = _prepare(b)
    meta = _build_meta(b, disclosures=disc)
    meta.setdefault("reservation_revenue_total", ha["reservation_revenue_total"])
    out = _reports_dir() / (cfg["REPORT"]["doc_ref"] + ".pdf")
    res = build_report(inputs, meta, out, generated_by=actor, created_at=now,
                       audit_log=_audit(), supersedes=b.get("supersedes") or None)
    try:
        if HOST.notify:
            HOST.notify({"doc_ref": res["doc_ref"], "unit": cfg["UNIT"].get("unit_ref"),
                         "owner_net": res["reconciliation"]["owner_net"]})
    except Exception:
        pass
    return {"ok": True, "doc_ref": res["doc_ref"], "pdf": "/owner-report/pdf/" + out.name,
            "reconciliation": res["reconciliation"]}


async def api_export(request):
    """Issue the report: full gate chain + immutable snapshot. Requires a signed reconciliation."""
    if not can_edit(request):
        return _deny()
    b = await _body(request)
    return HOST.json_response(await asyncio.to_thread(_export_sync, b, _actor(request), _now_iso()))


async def api_history(request):
    return HOST.json_response({"ok": True, "history": _audit().history()})


async def handle_pdf(request):
    name = request.match_info.get("name", "")
    if "/" in name or ".." in name or not name.endswith(".pdf"):
        return HOST.web.Response(status=400, text="bad name")
    f = _reports_dir() / name
    if not f.exists():
        return HOST.web.Response(status=404, text="not found")
    return HOST.web.Response(body=f.read_bytes(), content_type="application/pdf")


async def handle_page(request):
    return HOST.web.Response(text=page.OWNER_REPORT_PAGE_HTML, content_type="text/html")


def register(app):
    g = app.router.add_get
    p = app.router.add_post
    g("/owner-report", handle_page)
    g("/api/owner-report/units", _safe(api_units))
    g("/api/owner-report/questions", _safe(api_question_bank))
    g("/api/owner-report/wizard", _safe(api_wizard_load))
    p("/api/owner-report/wizard", _safe(api_wizard_save))
    p("/api/owner-report/reconcile", _safe(api_reconcile))
    p("/api/owner-report/preview", _safe(api_preview))
    p("/api/owner-report/export", _safe(api_export))
    g("/api/owner-report/history", _safe(api_history))
    g("/owner-report/pdf/{name}", _safe(handle_pdf))
