# -*- coding: utf-8 -*-
"""
stayhub.probe — the answer to StayHub's sync probe (guide slide 11, the ONE endpoint we must
host; certification checks drift on it). StayHub asks "what do you hold for property X in this
window?" and compares it with its own state. We answer from the local cache and the ledger,
within 10 seconds, without calling StayHub or Hostaway.

    scope = properties | availability | rates | bookings | holds | all
"""
import datetime

from . import db, engine

SCOPES = ("properties", "availability", "rates", "bookings", "holds")
MAX_WINDOW_DAYS = 400


def _window(win, today):
    a = engine.parse_date((win or {}).get("from")) or today
    b = engine.parse_date((win or {}).get("to")) or (a + datetime.timedelta(days=90))
    if b < a:
        a, b = b, a
    if (b - a).days > MAX_WINDOW_DAYS:
        b = a + datetime.timedelta(days=MAX_WINDOW_DAYS)
    return a.isoformat(), b.isoformat()


def _num(v):
    if v is None:
        return None
    try:
        f = float(v)
        return int(f) if f == int(f) else f
    except (TypeError, ValueError):
        return None


def answer(req, now_iso, today):
    """req = the probe body. Returns the response dict (always — an unknown property simply has
    empty lists, which is the truthful answer)."""
    req = req or {}
    pid = str(req.get("propertyId") or "").strip()
    scope = str(req.get("scope") or "all").strip().lower()
    want = set(SCOPES) if scope == "all" else ({scope} & set(SCOPES))
    d_from, d_to = _window(req.get("window"), today)
    out = {"probeId": req.get("probeId"), "propertyId": pid, "respondedAt": now_iso + "Z"}
    prop = db.property_row(pid) if pid else None
    if "properties" in want:
        out["properties"] = {"lastSyncedAt": (db.setting_get("last_sync_at") or "") + ("Z" if db.setting_get("last_sync_at") else ""),
                             "version": (prop or {}).get("version"),
                             "status": (prop or {}).get("status") or ("unknown" if not prop else "active")}
    rows = db.days(pid, d_from, d_to) if pid and want & {"availability", "rates"} else []
    if "availability" in want:
        seen, days = set(), []
        for r in rows:
            if r["date"] in seen or r.get("rooms") is None:
                continue
            seen.add(r["date"])
            days.append({"date": r["date"], "roomsAvailable": r["rooms"]})
        out["availability"] = {"days": days}
    if "rates" in want:
        out["rates"] = {"days": [{"date": r["date"], "ratePlanId": r["rate_plan_id"] or None, "rate": _num(r["rate"])}
                                 for r in rows if r.get("rate") is not None]}
    if "bookings" in want:
        bk = db.bookings_for_property(pid, d_from, d_to, statuses=[engine.CONFIRMED, engine.CANCELLED]) if pid else []
        out["bookings"] = [{"reservationId": b.get("sh_reservation_id"), "externalReservationId": b.get("external_id"),
                            "checkIn": b.get("pushed_check_in"), "checkOut": b.get("pushed_check_out"),
                            "status": b.get("status"), "externalRevision": b.get("revision"),
                            "total": _num(b.get("pushed_total"))}
                           for b in bk if b.get("sh_reservation_id")]
    if "holds" in want:
        hs = db.active_holds(pid, now_iso) if pid else []
        out["holds"] = [{"holdId": h.get("hold_id"), "externalReservationId": h.get("external_id"),
                         "checkIn": h.get("check_in"), "checkOut": h.get("check_out"),
                         "expiresAt": (h.get("hold_expires") or "") + "Z"} for h in hs]
    return out
