# -*- coding: utf-8 -*-
"""
schedule.workload — the BEST-EFFORT bridge from Hostaway to "how much real work is this".

An apartment count is not a workload: nine units with no checkouts is a quiet day, and nine
units that all turn over with same-day arrivals is not. This module turns a date window into
real departures, same-day arrivals, scheduled deep cleans and estimated minutes per unit.

Two absolute rules, both tested:
  1. it NEVER raises. Hostaway being unreachable degrades the answer, it does not break the
     planner. The caller gets source='estimated' and the UI must then say «تقديري» — an honest
     blank beats a confident wrong number.
  2. it is NEVER called from the shared day/week read path. Those endpoints are public and
     must stay instant for the ops team's /team-calendar link; only the period planner pays
     the Hostaway cost, and it pays it ONCE per request for the whole window (two calls), not
     once per day.

CLAUDE.md trap #4 applies: reservations come from the windowed query
(`ha_reservations_window`), never from the truncating full-history cache.
"""

import traceback

from .host import HOST

_DEFAULTS = {"clean_min": 20, "clean_max": 40, "park_buffer": 5}


def _cap(name, fallback=None):
    """A wired host capability, or `fallback` when bot.py did not provide it (tests, or an
    older deploy). Never raises."""
    try:
        fn = getattr(HOST, name, None)
        return fn if fn is not None else fallback
    except Exception:
        return fallback


def _defaults():
    fn = _cap("clean_defaults")
    if not fn:
        return dict(_DEFAULTS)
    try:
        d = fn() or {}
        return {k: (d.get(k) if d.get(k) is not None else v) for k, v in _DEFAULTS.items()}
    except Exception:
        return dict(_DEFAULTS)


def _confirmed():
    fn = _cap("confirmed_statuses")
    try:
        return set(fn() or ()) if fn else {"new", "modified"}
    except Exception:
        return {"new", "modified"}


def unit_config():
    """{listing_id(int): {clean_min, clean_max, park_buffer, district, lat, lng, minutes}} from
    the listings store, falling back to the OujaCT defaults. minutes = midpoint of the cleaning
    estimate + the parking/waiting buffer — the per-turnover cost of that unit."""
    d = _defaults()
    out = {}
    ls = _cap("ls_get")
    store = {}
    if ls:
        try:
            store = (ls() or {}).get("listings") or {}
        except Exception:
            traceback.print_exc()
            store = {}
    for k, rec in (store or {}).items():
        try:
            lid = int(k)
        except (TypeError, ValueError):
            continue
        rec = rec or {}
        cmin = rec.get("clean_min") or d["clean_min"]
        cmax = rec.get("clean_max") or d["clean_max"]
        park = rec.get("park_buffer") if rec.get("park_buffer") is not None else d["park_buffer"]
        out[lid] = {"clean_min": cmin, "clean_max": cmax, "park_buffer": park,
                    "district": (rec.get("group") or rec.get("address") or "") or None,
                    "lat": rec.get("lat"), "lng": rec.get("lng"),
                    "minutes": int(round((cmin + cmax) / 2.0)) + int(park)}
    return out


def default_minutes():
    d = _defaults()
    return int(round((d["clean_min"] + d["clean_max"]) / 2.0)) + int(d["park_buffer"])


def _by_date(rows, field, confirmed):
    """{date_iso: {listing_id, ...}} — one cleaning per (unit, day), confirmed bookings only.
    Mirrors fetch_oujact_turnovers' dedup so the planner and the cleaning board agree."""
    out = {}
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        if (r.get("status") or "").lower() not in confirmed:
            continue          # never owner-stays / blocks / pending / inquiries / cancelled
        lid, day = r.get("listingMapId"), r.get(field)
        if lid is None or not day:
            continue
        out.setdefault(str(day)[:10], set()).add(lid)
    return out


def deep_cleans_by_date():
    """{date_iso: {listing_id, ...}} from the deep-clean scheduler. Best-effort, never raises."""
    out = {}
    fn = _cap("deep_clean_state")
    if not fn:
        return out
    try:
        for lid, s in (fn() or {}).items():
            nxt = (s or {}).get("next_scheduled")
            if nxt:
                out.setdefault(str(nxt)[:10], set()).add(int(lid))
    except Exception:
        traceback.print_exc()
    return out


def fetch_window(start_iso, end_iso, _reservations=None):
    """Real demand for a whole date window in TWO Hostaway calls (departures + arrivals).

    Returns {source, checkouts, checkins, deep_cleans, units, minutes_default} where the three
    date maps are {date_iso: {listing_id}}. source is 'hostaway' when the pull succeeded and
    'estimated' when it did not — the caller must surface that difference to the owner.
    """
    fetch = _reservations or _cap("ha_reservations_window")
    confirmed = _confirmed()
    empty = {"source": "estimated", "checkouts": {}, "checkins": {}, "deep_cleans": {},
             "units": {}, "minutes_default": default_minutes()}
    if not fetch:
        empty["units"] = unit_config()
        empty["deep_cleans"] = deep_cleans_by_date()
        return empty
    try:
        deps = fetch("departureStartDate", "departureEndDate", start_iso, end_iso)
        arrs = fetch("arrivalStartDate", "arrivalEndDate", start_iso, end_iso)
    except Exception:
        traceback.print_exc()          # a Hostaway hiccup degrades, never breaks
        empty["units"] = unit_config()
        empty["deep_cleans"] = deep_cleans_by_date()
        return empty
    return {"source": "hostaway",
            "checkouts": _by_date(deps, "departureDate", confirmed),
            "checkins": _by_date(arrs, "arrivalDate", confirmed),
            "deep_cleans": deep_cleans_by_date(),
            "units": unit_config(),
            "minutes_default": default_minutes()}
