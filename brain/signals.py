"""
brain.signals — the signal engine. Reads bot.py's CACHED units x nights calendar grid
(_compute_calendar_grid, cache key 'calendar_grid') plus the pricing engine's discount
state/diagnostics, and derives the inventory-softness signals the campaign selector and
the dashboard need. 100% read-only; it never re-fetches Hostaway when the cache is warm.

Weekday-night convention (build spec): low-demand nights = Sun–Wed. In Python weekday()
that's {6,0,1,2}. The local WEEKEND (Thu/Fri here) is used only for the 'weekend freed'
premium signal.
"""

from . import settings
from .host import HOST
from .util import parse_date, now_dt

SUN_WED = {6, 0, 1, 2}          # Sun, Mon, Tue, Wed  (low-demand weekday nights)


def _grid(days=45):
    """The cached calendar grid, computed live only if the cache is cold."""
    g = None
    try:
        g = HOST.cache_get("calendar_grid") if HOST.cache_get else None
    except Exception:
        g = None
    if g and isinstance(g, dict) and g.get("units"):
        return g
    # cold cache: warm it for next time AND compute now so the Brain still answers
    try:
        if HOST.kick_compute and HOST.compute_calendar_grid:
            HOST.kick_compute("calendar_grid", HOST.compute_calendar_grid)
    except Exception:
        pass
    try:
        if HOST.compute_calendar_grid:
            return HOST.compute_calendar_grid(days=max(days, 30))
    except Exception:
        pass
    return {"days": [], "units": [], "days_count": 0}


def _discounted_set():
    """Set of (lid, 'YYYY-MM-DD') the pricing engine already softened — the strongest
    flash candidates. Sourced from discount_state (confirmed {date:{lid:{...}}}) and,
    best-effort, from recent last-minute diagnostics runs."""
    out = set()
    # 1) discount_state — presence of (date, lid) = price moved off baseline for that night
    try:
        st = HOST.load_discount_state() if HOST.load_discount_state else {}
        if isinstance(st, dict):
            for date_iso, per_lid in st.items():
                if isinstance(per_lid, dict):
                    for lid in per_lid.keys():
                        out.add((str(lid), str(date_iso)[:10]))
    except Exception:
        pass
    # 2) diagnostics runs — items that were actually softened
    try:
        runs = HOST.latest_last_minute_diagnostics(20) if HOST.latest_last_minute_diagnostics else []
        for run in runs or []:
            td = str(run.get("target_date") or "")[:10]
            for it in (run.get("items") or []):
                lid = it.get("lid")
                status = (it.get("status") or "").lower()
                cur = it.get("current_price")
                fin = it.get("final_price")
                softened = status == "applied" or (
                    status == "evaluated" and isinstance(fin, (int, float))
                    and isinstance(cur, (int, float)) and fin < cur)
                if lid is not None and td and softened:
                    out.add((str(lid), td))
    except Exception:
        pass
    return out


def _listing_meta():
    """lid(str) -> {beds, group, name}."""
    meta = {}
    try:
        store = HOST.ls_get()["listings"] if HOST.ls_get else {}
        for k, rec in (store or {}).items():
            meta[str(k)] = {
                "beds": rec.get("bedrooms"),
                "group": rec.get("group") or "",
                "name": rec.get("internal_name") or rec.get("public_name") or str(k),
            }
    except Exception:
        pass
    return meta


def _is_premium(m):
    beds = m.get("beds")
    grp = (m.get("group") or "").lower()
    try:
        beds = int(beds) if beds is not None else 0
    except (ValueError, TypeError):
        beds = 0
    return beds >= 3 or any(w in grp for w in ("premium", "luxury", "تريف", "تُرَيف", "vip"))


def compute_signals():
    horizon = settings.get_int("signal_horizon_days")
    imminent_hours = settings.get_int("imminent_hours")
    gap_long = settings.get_int("gap_long_nights")
    imminent_days = max(1, imminent_hours // 24)   # 72h -> first ~3 day-indices

    grid = _grid(days=max(horizon, 30))
    days = grid.get("days", [])
    units = grid.get("units", [])
    disc = _discounted_set()
    meta = _listing_meta()
    weekend_days = HOST.weekend_days or {3, 4}

    # date index -> weekday int + weekend flag (from grid days)
    day_meta = []
    for d in days:
        wd = d.get("weekday")
        if wd is None:
            pd = parse_date(d.get("date"))
            wd = pd.weekday() if pd else 0
        day_meta.append({"date": d.get("date"), "weekday": wd,
                         "weekend": bool(d.get("weekend")) or (wd in weekend_days),
                         "at_risk": d.get("at_risk") or 0})

    n = min(horizon, len(day_meta))
    open_total = open_weekday = 0
    imminent_open = imminent_disc = disc_soft = 0
    long_gap_units = []
    large_units_empty = []
    new_premium_units = []
    per_unit = {}

    for u in units:
        lid = str(u.get("lid"))
        cells = u.get("cells", [])
        name = u.get("name") or meta.get(lid, {}).get("name") or lid
        m = meta.get(lid, {"beds": None, "group": "", "name": name})
        u_open = u_weekday = u_soft = 0
        run = 0
        max_gap = 0
        gap_weekday_in_long = 0
        empty_weekend_soon = False
        for i in range(n):
            cell = cells[i] if i < len(cells) else {"status": "none"}
            dm = day_meta[i]
            is_empty = cell.get("status") == "empty"
            if is_empty:
                u_open += 1
                run += 1
                max_gap = max(max_gap, run)
                softened = (lid, dm["date"]) in disc
                if softened:
                    u_soft += 1
                    disc_soft += 1
                if dm["weekday"] in SUN_WED:
                    u_weekday += 1
                    open_weekday += 1
                    if run >= gap_long:
                        gap_weekday_in_long += 1
                if i <= imminent_days:
                    imminent_open += 1
                    if softened:
                        imminent_disc += 1
                if dm["weekend"] and i <= 10:
                    empty_weekend_soon = True
                open_total += 1
            else:
                run = 0
        per_unit[lid] = {"name": name, "open_total": u_open, "open_weekday": u_weekday,
                         "soft": u_soft, "max_gap": max_gap, "beds": m.get("beds"),
                         "premium": _is_premium(m)}
        if max_gap >= gap_long:
            long_gap_units.append({"lid": lid, "name": name, "gap": max_gap,
                                   "weekday_nights": gap_weekday_in_long or 1})
        if u_open >= 2 and _is_premium(m) and (m.get("beds") or 0) and int(m.get("beds") or 0) >= 3:
            large_units_empty.append({"lid": lid, "name": name, "beds": m.get("beds")})
        if u_open >= 2 and _is_premium(m) and empty_weekend_soon:
            new_premium_units.append({"lid": lid, "name": name})

    # near-term occupancy (next 7 days) from the grid
    occ_pct = 0
    if units and n:
        wnd = min(7, n)
        booked = 0
        for u in units:
            for i in range(wnd):
                c = u.get("cells", [])
                if i < len(c) and c[i].get("status") == "booked":
                    booked += 1
        denom = len(units) * wnd
        occ_pct = round(booked / denom * 100) if denom else 0

    # checkouts today/tomorrow
    checkouts_today = 0
    try:
        checkouts_today = len(HOST.fetch_upcoming_checkouts() or []) if HOST.fetch_upcoming_checkouts else 0
    except Exception:
        checkouts_today = 0

    # far-out at-risk dates (beyond the imminent window), top by revenue at risk
    far_out = []
    for i in range(min(imminent_days + 1, n), n):
        dm = day_meta[i]
        if dm["at_risk"] and dm["at_risk"] > 0:
            far_out.append({"date": dm["date"], "at_risk": round(dm["at_risk"])})
    far_out.sort(key=lambda x: x["at_risk"], reverse=True)
    far_out = far_out[:8]

    # month close = within last 3 days of the month
    nowd = now_dt().date()
    try:
        from calendar import monthrange
        last_day = monthrange(nowd.year, nowd.month)[1]
        is_month_close = (last_day - nowd.day) <= 3
    except Exception:
        is_month_close = False

    long_gap_units.sort(key=lambda x: x["gap"], reverse=True)

    return {
        "today": nowd.isoformat(),
        "horizon_days": horizon,
        "open_nights_total": open_total,
        "open_weekday_nights": open_weekday,
        "imminent_open_nights": imminent_open,
        "imminent_discounted_nights": imminent_disc,
        "discounted_soft_nights": disc_soft,
        "long_gap_units": long_gap_units,
        "checkouts_today": checkouts_today,
        "new_premium_units": new_premium_units,
        "large_units_empty": large_units_empty,
        "far_out_at_risk_dates": far_out,
        "occupancy_pct": occ_pct,
        "is_month_close": is_month_close,
        "units_count": len(units),
        "per_unit": per_unit,
    }


def build_heatmap(days=30):
    """Units x nights tape for the dashboard heatmap, straight from the cached grid."""
    grid = _grid(days=max(days, 30))
    gdays = grid.get("days", [])[:days]
    disc = _discounted_set()
    out_days = [{"date": d.get("date"), "weekday": d.get("weekday"),
                 "weekend": bool(d.get("weekend")), "at_risk": round(d.get("at_risk") or 0),
                 "events": d.get("events") or []} for d in gdays]
    out_units = []
    for u in grid.get("units", []):
        lid = str(u.get("lid"))
        cells = []
        for i, c in enumerate(u.get("cells", [])[:days]):
            date_iso = gdays[i]["date"] if i < len(gdays) else None
            cells.append({"s": c.get("status"), "p": c.get("price"),
                          "soft": 1 if (lid, date_iso) in disc else 0,
                          "orphan": c.get("orphan", 0)})
        out_units.append({"lid": lid, "name": u.get("name"), "cells": cells})
    out_units.sort(key=lambda x: (x["name"] or ""))
    return {"days": out_days, "units": out_units, "days_count": len(out_days)}
