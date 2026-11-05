# -*- coding: utf-8 -*-
"""
stayhub.recon — the daily reconciliation StayHub asked for (answer §4): for every mapped unit we
send our view of the bookings (POST /reconciliation/report), log StayHub's diff, and post ONE
Discord summary that lists every booking StayHub refused, so each case can be resolved with them.

Latched on a persisted date (stayhub_settings.recon_date) — a time-based loop re-runs its first
iteration on every Railway redeploy, the latch stops a second report the same day.
"""
import datetime
import json

from . import client, config, db, engine, notify
from .client import StayHubError


def _num(v):
    try:
        f = float(v)
        return int(f) if f == int(f) else f
    except (TypeError, ValueError):
        return None


def report_body(property_id, d_from, d_to):
    rows = db.bookings_for_property(property_id, d_from, d_to)
    res = []
    for b in rows:
        if b.get("status") not in (engine.CONFIRMED, engine.CANCELLED, engine.REJECTED, engine.FAILED):
            continue
        res.append({"externalReservationId": b.get("external_id"),
                    "reservationId": b.get("sh_reservation_id"),
                    "checkIn": b.get("pushed_check_in") or b.get("check_in"),
                    "checkOut": b.get("pushed_check_out") or b.get("check_out"),
                    "status": b.get("status"),
                    "externalRevision": b.get("revision"),
                    "total": _num(b.get("pushed_total") if b.get("pushed_total") is not None else b.get("total")),
                    "rejectionCode": b.get("last_code") if b.get("status") in (engine.REJECTED, engine.FAILED) else None})
    return {"propertyId": property_id, "window": {"from": d_from, "to": d_to},
            "reservations": res, "availability": []}


def run(today, force=False):
    """Once a day (or force). Returns the summary dict."""
    if not config.configured():
        return {"skipped": "not_configured"}
    if not force and db.setting_get("recon_date") == today.isoformat():
        return {"skipped": "already_today"}
    d_from = (today - datetime.timedelta(days=1)).isoformat()
    d_to = (today + datetime.timedelta(days=config.recon_days_ahead())).isoformat()
    mismatches, errors = 0, 0
    for m in db.maps():
        body = report_body(m["property_id"], d_from, d_to)
        try:
            data, trace = client.recon_report(body)
        except StayHubError as e:
            errors += 1
            db.add_event("", "recon_error", "property=%s %s" % (m["property_id"], e.code), e.trace_id)
            continue
        s = (data or {}).get("summary") or {}
        det = (data or {}).get("details") or {}
        n = int(s.get("statusMismatches") or 0) + int(s.get("availabilityMismatches") or 0) \
            + len(det.get("missingOnPartner") or []) + len(det.get("missingOnUs") or [])
        mismatches += n
        db.add_event("", "recon", "property=%s checked=%s mismatches=%s detail=%s"
                     % (m["property_id"], s.get("reservationsChecked"), n,
                        json.dumps(det, ensure_ascii=False)[:600]), trace)
    c = db.counts()
    summary = {
        "confirmed": c.get(engine.CONFIRMED, 0), "pending": c.get(engine.PENDING, 0) + c.get(engine.RETRY, 0),
        "rejected": c.get(engine.REJECTED, 0), "failed": c.get(engine.FAILED, 0),
        "mismatches": mismatches, "errors": errors,
        "rejected_rows": db.bookings(engine.REJECTED, 20) + db.bookings(engine.FAILED, 20),
    }
    db.setting_set("recon_date", today.isoformat())
    if db.maps():
        notify.send(notify.daily_text(summary))
    return summary
