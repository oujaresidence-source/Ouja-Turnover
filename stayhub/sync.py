# -*- coding: utf-8 -*-
"""
stayhub.sync — the /sync loop (guide slides 5–6). /sync is StayHub's source of truth; webhooks
only make us call it sooner.

    run_sync()      pull every page since the saved cursor (hasMore ⇒ call again at once),
                    apply the eight arrays to the local cache, save nextCursor.
    CURSOR_EXPIRED  ⇒ discard the cached catalog and bootstrap with since=null (the unit map
                    and the bookings ledger are ours and are kept).

StayHub's exact item shapes inside the arrays are not fully documented, so every reader below
is defensive (propertyId | property.id | property._id | id) and a malformed item is skipped
and counted, never fatal.
"""
import datetime
import json

from . import client, config, db
from .client import StayHubError
from .host import HOST

MAX_PAGES = 25
ARRAYS = ("newAuthorizations", "deauthorizations", "propertyChanges", "rateChanges",
          "availabilityChanges", "restrictionChanges", "suspensions", "resumptions")


def _today():
    fn = getattr(HOST, "now", None)
    d = fn() if fn else datetime.datetime.utcnow()
    return d.date() if isinstance(d, datetime.datetime) else d


def _pid(o):
    if not isinstance(o, dict):
        return None
    v = o.get("propertyId")
    if not v and isinstance(o.get("property"), dict):
        p = o["property"]
        v = p.get("id") or p.get("_id") or p.get("propertyId")
    if not v:
        v = o.get("id") or o.get("_id")
    return str(v).strip() if v else None


def _prop(o):
    return o.get("property") if isinstance(o.get("property"), dict) else o


def _version(o):
    p = _prop(o)
    for k in ("connectivityVersion", "propertyVersion", "version", "newVersion"):
        v = p.get(k) if isinstance(p, dict) else None
        if v is None:
            v = o.get(k)
        if v is not None:
            try:
                return int(str(v).lstrip("v"))
            except (TypeError, ValueError):
                continue
    return None


def _title(o):
    p = _prop(o)
    for k in ("title", "name", "propertyName", "nameEn", "nameAr"):
        v = p.get(k) if isinstance(p, dict) else None
        if isinstance(v, dict):
            v = v.get("en") or v.get("ar")
        if v:
            return str(v)
    return None


def _rate_plans(o):
    plans = o.get("ratePlans")
    if plans is None and isinstance(o.get("property"), dict):
        plans = o["property"].get("ratePlans")
    out = []
    for rp in plans or []:
        if isinstance(rp, dict):
            v = rp.get("id") or rp.get("_id") or rp.get("ratePlanId")
            if v:
                out.append(str(v))
        elif rp:
            out.append(str(rp))
    return out


def _day_list(o):
    """The per-day list inside a change item, wherever StayHub put it."""
    for k in ("days", "dates", "availability", "rates", "restrictions", "changes", "calendar"):
        v = o.get(k)
        if isinstance(v, dict):
            v = v.get("days")
        if isinstance(v, list):
            return v
    return []


def _norm_day(d):
    if not isinstance(d, dict):
        return None
    date = str(d.get("date") or d.get("day") or "")[:10]
    if len(date) != 10:
        return None
    rooms = d.get("roomsAvailable", d.get("available", d.get("rooms")))
    if isinstance(rooms, bool):
        rooms = 1 if rooms else 0
    rate = d.get("rate", d.get("price", d.get("amount")))
    restr = {k: d[k] for k in ("minStay", "maxStay", "closedToArrival", "closedToDeparture", "cta", "ctd", "stopSell")
             if k in d}
    return {"date": date, "rooms": rooms, "rate": rate, "restrictions": restr or None}


def _apply_days(o, kind, at):
    pid = _pid(o)
    if not pid:
        return 0
    rp = o.get("ratePlanId") or ""
    rows = []
    for d in _day_list(o):
        nd = _norm_day(d)
        if not nd:
            continue
        r_rp = d.get("ratePlanId") or rp
        if kind == "availability":
            nd["restrictions"] = None
        elif kind == "rate":
            nd["rooms"], nd["restrictions"] = None, None
        elif kind == "restriction":
            nd["rooms"], nd["rate"] = None, None
        rows.append((r_rp, nd))
    n = 0
    by_rp = {}
    for r_rp, nd in rows:
        by_rp.setdefault(r_rp or "", []).append(nd)
    for r_rp, lst in by_rp.items():
        n += db.put_days(pid, r_rp, lst, at)
    return n


def apply(envelope, at=None):
    """Apply one /sync page to the cache. Returns per-array counts (+ 'bad' for skipped items)."""
    at = at or db.now_iso()
    env = envelope or {}
    out = {k: 0 for k in ARRAYS}
    out["bad"] = 0
    fresh = []
    for o in env.get("newAuthorizations") or []:
        pid = _pid(o)
        if not pid:
            out["bad"] += 1
            continue
        db.upsert_property(pid, _title(o), _version(o), _rate_plans(o), "active", at)
        if _day_list(o):
            _apply_days(o, "availability", at)
        else:
            fresh.append(pid)
        db.add_event("", "authorized", "property=%s" % pid, at=at)
        out["newAuthorizations"] += 1
    for o in env.get("deauthorizations") or []:
        pid = _pid(o)
        if not pid:
            out["bad"] += 1
            continue
        db.set_property_status(pid, "deauthorized", at)
        db.add_event("", "deauthorized", "property=%s" % pid, at=at)
        _notify_property(pid, "deauthorized")
        out["deauthorizations"] += 1
    for o in env.get("propertyChanges") or []:
        pid = _pid(o)
        if not pid:
            out["bad"] += 1
            continue
        plans = _rate_plans(o)
        db.upsert_property(pid, _title(o), _version(o), plans or None, None, at)
        out["propertyChanges"] += 1
    for key, kind in (("rateChanges", "rate"), ("availabilityChanges", "availability"),
                      ("restrictionChanges", "restriction")):
        for o in env.get(key) or []:
            if not _pid(o):
                out["bad"] += 1
                continue
            _apply_days(o, kind, at)
            out[key] += 1
    for key, st in (("suspensions", "suspended"), ("resumptions", "active")):
        for o in env.get(key) or []:
            pid = _pid(o)
            if not pid:
                out["bad"] += 1
                continue
            db.set_property_status(pid, st, at)
            db.add_event("", st, "property=%s reason=%s" % (pid, o.get("reason") or ""), at=at)
            if st == "suspended":
                _notify_property(pid, "suspended")
            out[key] += 1
    out["_fresh"] = fresh
    return out


def _notify_property(pid, what):
    from . import notify
    m = db.map_for_property(pid)
    notify.send(notify.property_text(pid, what, m))


def _fill_fresh(pids):
    """A new authorisation without inline days: pull 90 days once so the sync probe has data."""
    a = _today()
    b = a + datetime.timedelta(days=90)
    for pid in pids:
        try:
            av = client.availability(pid, a.isoformat(), b.isoformat())
            db.put_days(pid, av.get("ratePlanId") or "", [
                x for x in (_norm_day(d) for d in av.get("days") or []) if x])
            if av.get("propertyVersion") is not None:
                db.upsert_property(pid, version=av.get("propertyVersion"))
        except StayHubError as e:
            print("[stayhub] availability fill failed for %s: %s" % (pid, e.code))


def run_sync(_rebootstrapped=False):
    """One full sync (all pages). Never raises for StayHub errors — returns a summary dict."""
    if not config.configured():
        return {"skipped": "not_configured"}
    cursor = db.setting_get("cursor")
    totals = {k: 0 for k in ARRAYS}
    totals["bad"] = 0
    pages, fresh = 0, []
    try:
        while pages < MAX_PAGES:
            env = client.sync(cursor)
            got = apply(env)
            fresh.extend(got.pop("_fresh", []))
            for k, v in got.items():
                totals[k] = totals.get(k, 0) + v
            nxt = env.get("nextCursor") or env.get("cursor")
            if nxt:
                cursor = nxt
                db.setting_set("cursor", cursor)
            pages += 1
            if not env.get("hasMore"):
                break
    except StayHubError as e:
        if e.code == "CURSOR_EXPIRED" and not _rebootstrapped:
            print("[stayhub] cursor expired — discarding the catalog cache and bootstrapping")
            db.clear_catalog()
            db.setting_set("cursor", None)
            db.add_event("", "cursor_expired", "rebootstrap", e.trace_id)
            return run_sync(_rebootstrapped=True)
        db.setting_set("last_sync_error", "%s %s" % (e.code, e.status))
        print("[stayhub] sync failed: %s (%s) trace=%s" % (e.code, e.status, e.trace_id))
        return {"error": e.code, "pages": pages, **totals}
    if fresh:
        _fill_fresh(fresh)
    db.setting_set("last_sync_at", db.now_iso())
    db.setting_set("last_sync_error", "")
    totals["pages"] = pages
    if any(totals.get(k) for k in ARRAYS):
        print("[stayhub] sync · %s" % json.dumps({k: v for k, v in totals.items() if v}, ensure_ascii=False))
    return totals
