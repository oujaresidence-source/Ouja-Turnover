# -*- coding: utf-8 -*-
"""aiohttp handlers for the coverage study.

  GET /api/coverage/study   → the whole computed snapshot (login + `coverage` read perm)
  GET /api/coverage/geo     → resolve a batch of un-located map links (admin/ops only)

Both are read-only. Nothing here writes to the listings store, the cleaning log, or
anything else the live operation depends on — the only thing it ever writes is its own
geo cache.
"""

import asyncio
import datetime
import json
import time
import traceback

from . import brief, engine, geo, pluscode, tiles
from .host import HOST, call

EDIT_ROLES = ("admin", "ops")
SETTINGS_FILE = "coverage_settings.json"

# Actors who press «تم» but are not cleaning staff — the owner named these on
# 2026-08-02. Seeded once into the settings file so it can be changed later without
# a deploy. Their cleans still count as demand; they just do not dilute the
# per-person rate or inflate the count of people already working.
DEFAULT_NON_CLEANERS = ("faisalouja", "route-link", "_hmdkhdyr")

# How many trailing weeks of checkouts the week-shape and peak factor are measured over.
TURNS_WEEKS_BACK = 8
_TURNS_CACHE = {}          # (start, end) -> (payload, fetched_at). Hostaway is slow.
_TURNS_TTL_S = 900

# Owner-editable without a deploy, exactly like the non-cleaner list.
# Owner-supplied, 2026-08-02: 3 cleaners, 1 supervisor, 6-day week, 21 days off a year,
# 1,300 SAR/month per cleaner, 6,000 SAR/month for the supervisor (with car, housing,
# transport and petrol). Editable on the page — no deploy needed to change any of them.
SETTING_DEFAULTS = {
    "cleaners_count": 3,
    "supervisors_count": 1,
    "cleaner_cost_sar": 1300,
    "supervisor_cost_sar": 6000,
    "days_per_week": 6,
    "days_off_per_year": 21,
    "apartment_price_sar": {},              # {listing_id: SAR per month, per apartment}
}
NUMERIC_SETTINGS = ("cleaners_count", "supervisors_count", "cleaner_cost_sar",
                    "supervisor_cost_sar", "days_per_week", "days_off_per_year")


def _factors(cfg):
    """Roster and absence factors derived from the real working pattern.

    A 6-day week needs 7/6 people on payroll to keep one on shift every day; 21 days off
    against 312 working days is ~6.7%. Derived rather than typed so the two can never
    drift apart from the pattern they describe.
    """
    try:
        dpw = max(1.0, min(7.0, float(cfg.get("days_per_week") or 6)))
    except (TypeError, ValueError):
        dpw = 6.0
    try:
        off = max(0.0, float(cfg.get("days_off_per_year") or 0))
    except (TypeError, ValueError):
        off = 0.0
    worked = max(1.0, 52.0 * dpw)
    return 7.0 / dpw, min(0.5, off / worked)


def _settings():
    load = getattr(HOST, "load_json", None)
    if not callable(load):
        return {"non_cleaners": list(DEFAULT_NON_CLEANERS)}
    cfg = load(SETTINGS_FILE, None)
    if not isinstance(cfg, dict):
        cfg = {"non_cleaners": list(DEFAULT_NON_CLEANERS)}
        save = getattr(HOST, "save_json", None)
        if callable(save):
            save(SETTINGS_FILE, cfg)
    cfg.setdefault("non_cleaners", list(DEFAULT_NON_CLEANERS))
    for k, v in SETTING_DEFAULTS.items():
        cfg.setdefault(k, v)
    return cfg


def _turns_payload(units, all_lids, weeks_back=TURNS_WEEKS_BACK):
    """Turn deadlines + the shape of the week, over the trailing `weeks_back` weeks.

    Cached: this is a live Hostaway window query and the page must not wait on it twice.
    Returns None when reservations are unavailable, so the page can say the deadline view
    is missing rather than silently showing zero same-day turns — which would read as
    'no pressure' and is the most dangerous possible wrong answer here.
    """
    if not callable(getattr(HOST, "reservations", None)):
        return None
    end = datetime.date.today()
    start = end - datetime.timedelta(days=weeks_back * 7)
    key = (start.isoformat(), end.isoformat())
    hit = _TURNS_CACHE.get(key)
    if hit and (time.time() - hit[1]) < _TURNS_TTL_S:
        res = hit[0]
    else:
        try:
            res = HOST.reservations(start.isoformat(), end.isoformat())
        except Exception as e:
            print("[coverage] reservations unavailable:", e)
            return None
        _TURNS_CACHE.clear()
        _TURNS_CACHE[key] = (res, time.time())
    turns = engine.classify_turns(res, units, all_lids,
                                  since=start.isoformat(), until=end.isoformat())
    shape = engine.week_shape(turns["rows"])
    checkouts = len(turns["rows"])
    days = max(1, (end - start).days)
    turns["window"] = {"start": start.isoformat(), "end": end.isoformat(),
                       "weeks": weeks_back}
    turns["checkouts_per_day"] = round(checkouts / float(days), 1)
    return {"turns": turns, "week": shape}


def _json(obj, status=200):
    return HOST.json_response(obj, status)


def _safe(fn):
    async def _w(request):
        try:
            if HOST.dash_auth and not HOST.dash_auth(request):
                return _json({"error": "unauthorized"}, 401)
            return await fn(request)
        except Exception as e:
            traceback.print_exc()
            return _json({"error": "server_error", "detail": str(e)[:300]}, 500)
    _w.__name__ = getattr(fn, "__name__", "coverage_handler")
    return _w


def _int(request, name, default, lo, hi):
    try:
        v = int(request.query.get(name, default))
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def _collect():
    """Pull every input the study needs. Blocking (file reads) — run in a thread."""
    return {
        "listings": call("listings") or [],
        "guide_units": call("guide_units") or [],
        "teams": call("teams") or [],
        "status_log": call("status_log") or [],
        "reports": call("reports") or [],
        "photos": call("photos") or [],
    }


def _events_for_reconcile(study):
    """Every logged clean as {lid, date} — the crew-tag check counts by the APARTMENT's
    tag, since a done event records a person and no person-to-crew mapping exists."""
    out = []
    for row in (study.get("oujact") or {}).get("work_days") or []:
        for lid in row.get("lids") or []:
            out.append({"lid": lid, "date": row.get("date")})
    return out


def _in_house_ids(teams):
    """OujaCT is ours; every other crew is a third-party company (owner, 2026-08-02).

    Identified by team id `team-1` (the migrated in-house team) or by an OujaCT-ish
    name, so renaming the team in the dashboard does not silently reclassify 40
    apartments as outsourced.
    """
    out = set()
    for t in teams or []:
        tid = str(t.get("id") or "")
        name = (t.get("name") or "").strip().lower()
        if tid == "team-1" or "oujact" in name.replace(" ", "") or "أوجا" in name:
            out.add(tid)
    return out


def _build(request_params):
    data = _collect()
    teams = data["teams"]
    in_house = _in_house_ids(teams)

    units = engine.build_units(data["listings"], data["guide_units"], teams, in_house)
    cache = geo.load_cache()
    filled = geo.apply_to_units(units, cache)

    s = engine.study(
        listings=data["listings"], guide_units=data["guide_units"], teams=teams,
        status_log=data["status_log"], reports=data["reports"], photos=data["photos"],
        since=request_params.get("since"), in_house_team_ids=in_house,
        workday_min=request_params["workday_min"],
        cluster_radius_m=request_params["radius"],
        max_gap_min=request_params["max_gap"],
        demand_per_day=request_params.get("demand"),
        current_people=request_params.get("people"),
        units=units,
        non_cleaners=set(_settings().get("non_cleaners") or ()),
    )
    # have_key decides whether locating can work AT ALL: without it we can follow a short
    # link to a street address but never turn that address into coordinates, and the map
    # image cannot be fetched either. The page must say so outright rather than showing a
    # blank box and a vague failure (seen live 2026-08-02).
    # ---- v2: turn deadlines, the shape of the week, and the corrected head count ----
    cfg = _settings()
    roster_f, absence_f = _factors(cfg)
    all_lids = call("all_listing_ids") or None
    tp = _turns_payload(units, all_lids)
    if tp:
        rows = tp["turns"]["rows"]
        wdays = max(1, TURNS_WEEKS_BACK * 7)
        s["turns"] = tp["turns"]
        s["week"] = tp["week"]

        # The rate that decides hiring is per CLEANER, and the log only records the
        # SUPERVISOR who pressed done — so it is derived from checkouts on our own
        # apartments (owner's own suggestion, 2026-08-02).
        cleaners = int(cfg.get("cleaners_count") or 0)
        cap = engine.cleaner_capacity(rows, units, cleaners, wdays)
        s["cleaner"] = cap

        demand = s["capacity"].get("demand_per_day") or tp["turns"].get("checkouts_per_day") or 0
        # Their BEST observed day, not their typical one: a team that is not busy would
        # otherwise look incapable, and every hiring number built on it would be inflated.
        rate = cap.get("per_cleaner_best") or cap.get("per_cleaner_typical")
        peak = (tp["week"].get("busiest") or {}).get("total")
        s["capacity"]["headcount"] = engine.headcount(
            demand_per_day=demand, rate=rate, current_people=cleaners,
            peak_per_day=peak, roster_factor=roster_f, absence_factor=absence_f)

        vm = engine.vendor_monthly(rows, units, cfg.get("apartment_price_sar") or {},
                                   window_days=wdays)
        s["vendors"] = vm
        s["cost"] = engine.cost_compare(
            demand_per_day=demand, per_cleaner_day=rate,
            cleaner_cost=cfg.get("cleaner_cost_sar"),
            supervisor_cost=cfg.get("supervisor_cost_sar"),
            supervisors=int(cfg.get("supervisors_count") or 0),
            current_cleaners=cleaners,
            vendor_monthly=(vm["total_monthly"] if vm["total_monthly"] else None),
            roster_factor=roster_f, absence_factor=absence_f)

        s["reconcile"] = engine.reconcile(
            logged_per_day=(s.get("oujact") or {}).get("per_day_avg") or 0,
            checkouts_per_day=tp["turns"].get("checkouts_per_day") or 0,
            units=units, events=_events_for_reconcile(s))
    else:
        for k in ("turns", "week", "cleaner", "vendors", "cost", "reconcile"):
            s[k] = None
        s["capacity"]["headcount"] = None
    s["settings"] = dict(cfg)
    s["settings"]["roster_factor"] = round(roster_f, 3)
    s["settings"]["absence_factor"] = round(absence_f, 4)

    s["geo"] = {"have_key": bool(call("maps_key")),
                "filled_from_cache": filled, "cached_total": len(cache),
                "pending": len([u for u in units
                                if not u["has_location"] and u.get("geo_key")]),
                "nothing_to_resolve": len([u for u in units
                                           if not u["has_location"] and not u.get("geo_key")])}
    return s


async def _snapshot(request):
    """The one snapshot both the page and the export are built from.

    Deliberately shared: an export that recomputed its own numbers could disagree with
    the screen the owner is looking at, and a file that quietly says something different
    from the dashboard is worse than no file.
    """
    since = (request.query.get("since") or "").strip()[:10] or None
    demand = request.query.get("demand")
    people = request.query.get("people")
    params = {
        "since": since,
        "workday_min": _int(request, "workday", 480, 60, 1440),
        "radius": _int(request, "radius", 120, 20, 2000),
        "max_gap": _int(request, "maxgap", engine.DEFAULT_MAX_GAP_MIN, 30, 720),
        "demand": float(demand) if _num(demand) else None,
        "people": int(float(people)) if _num(people) else None,
    }
    # Fetch the real Hostaway demand BEFORE building, and hand it in.
    #
    # This used to run afterwards and REPLACED s["capacity"] wholesale, which silently
    # destroyed the head count computed inside _build. The page then showed two different
    # hiring answers at once: a KPI reading from the leftover old model, and the main card
    # reading a key that no longer existed, so it rendered "not enough data" directly
    # underneath a filled-in KPI (owner screenshot, 2026-08-02). Computing demand first
    # means everything downstream is derived once, from one number.
    params["demand_source"] = "estimated_from_log"
    params["demand_note"] = ""
    if params["demand"] is None and callable(getattr(HOST, "turnovers", None)):
        try:
            end = datetime.date.today()
            start = end - datetime.timedelta(days=29)
            n = await asyncio.to_thread(HOST.turnovers, start.isoformat(), end.isoformat())
            if n:
                params["demand"] = round(float(n) / 30.0, 1)
                params["demand_source"] = "hostaway_30d"
                params["demand_note"] = "%d checkouts in 30 days" % n
            else:
                params["demand_note"] = "Hostaway returned no checkouts for the window"
        except Exception as e:
            params["demand_note"] = "Hostaway demand unavailable: %s" % str(e)[:160]

    s = await asyncio.to_thread(_build, params)
    s["capacity"]["demand_source"] = params["demand_source"]
    s["capacity"]["demand_note"] = params["demand_note"]
    s["generated_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    return s


async def api_study(request):
    return _json({"ok": True, "study": await _snapshot(request)})


async def api_brief(request):
    """«نزّل كل البيانات» — the same snapshot as a file you can hand to someone else.

    `?format=md`   a readable briefing where every number carries its source
    `?format=json` the complete raw snapshot, nothing summarised
    `?format=both` both of them, built from ONE computation, for the page's button

    `both` exists for a reason: fetching the two files separately would run the study
    twice, and the reservation cache can turn over between the two runs — leaving the
    owner holding a briefing and a data file that quietly disagree.

    Read-only, like everything else in this module: it renders what the page already
    computed and writes nothing anywhere.
    """
    s = await _snapshot(request)
    fmt = (request.query.get("format") or "md").strip().lower()
    day = str(s.get("generated_at") or "")[:10]
    if fmt == "both":
        return _json({"ok": True,
                      "md": brief.render_markdown(s),
                      "data": brief.render_payload(s),
                      "md_name": brief.filename("md", day),
                      "json_name": brief.filename("json", day)})
    if fmt == "json":
        body = json.dumps(brief.render_payload(s), ensure_ascii=False, indent=1)
        ctype = "application/json"
    else:
        body = brief.render_markdown(s)
        ctype = "text/markdown"
    name = brief.filename("json" if fmt == "json" else "md", day)
    web = getattr(HOST, "web", None)
    if web is None:
        return _json({"ok": False, "error": "no_web"}, 500)
    return web.Response(text=body, content_type=ctype, charset="utf-8",
                        headers={"Content-Disposition": 'attachment; filename="%s"' % name,
                                 "Cache-Control": "no-store"})


def _num(v):
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


async def api_geo(request):
    """Resolve un-located map links in bounded batches. Admin/ops only — it calls out
    to Google, so it is not something a viewer should be able to trigger on a loop."""
    role = HOST.req_role(request) if callable(getattr(HOST, "req_role", None)) else "viewer"
    if role not in EDIT_ROLES:
        return _json({"ok": False, "error": "غير مصرّح لك بتشغيل هذا / not allowed"}, 403)

    def _work():
        data = _collect()
        teams = data["teams"]
        units = engine.build_units(data["listings"], data["guide_units"], teams,
                                   _in_house_ids(teams))
        cache = geo.load_cache()
        geo.apply_to_units(units, cache)
        links = [u["geo_key"] for u in units if not u["has_location"] and u.get("geo_key")]
        key = call("maps_key") or ""
        return geo.resolve_missing(links, api_key=key,
                                   batch=_int(request, "batch", geo.DEFAULT_BATCH, 1, 60))

    _cache, report = await asyncio.to_thread(_work)
    return _json({"ok": True, "geo": report})


_MAP_CACHE = {}          # (params) -> png bytes. Static tiles for fixed views never change.
_MAP_CACHE_MAX = 24


async def api_map(request):
    """A real street map, stitched from OpenStreetMap tiles on OUR server.

    NO API key — the owner does not want to register one (2026-08-02), so this replaced
    Google Static Maps outright. Fetching server-side also means the page makes no
    third-party requests and the tiles can be cached hard. The dashboard draws its own
    coloured dots on top using the same Web Mercator projection these tiles use.
    """
    try:
        lat = float(request.query.get("lat"))
        lng = float(request.query.get("lng"))
    except (TypeError, ValueError):
        return _json({"ok": False, "error": "bad_center"}, 400)
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return _json({"ok": False, "error": "bad_center"}, 400)
    z = _int(request, "z", 11, 1, 19)
    w = _int(request, "w", 700, 100, 1024)
    h = _int(request, "h", 440, 100, 1024)
    ck = (round(lat, 5), round(lng, 5), z, w, h)
    png = _MAP_CACHE.get(ck)
    if png is None:
        try:
            png = await asyncio.to_thread(tiles.render, lat, lng, z, w, h)
        except Exception as e:
            return _json({"ok": False, "error": "map_fetch_failed",
                          "message": str(e)[:200]}, 502)
        if len(_MAP_CACHE) >= _MAP_CACHE_MAX:
            _MAP_CACHE.clear()
        _MAP_CACHE[ck] = png
    web = getattr(HOST, "web", None)
    if web is None:
        return _json({"ok": False, "error": "no_web"}, 500)
    return web.Response(body=png, content_type="image/png",
                        headers={"Cache-Control": "private, max-age=86400"})


async def api_pin(request):
    """Owner pastes a Google Maps link for one apartment: save it AND locate it, now.

    One step on purpose. /api/listings/update already stores a maps_link, but it can
    only read coordinates that are literally inside the URL — a shortened
    maps.app.goo.gl link has none, so the apartment would still read "no location" and
    the owner would have to go press Locate again. This follows the redirect, reads a
    Plus Code if that is what the link resolves to, and writes the coordinates straight
    onto the listing, so the pin appears on the map immediately.
    """
    role = HOST.req_role(request) if callable(getattr(HOST, "req_role", None)) else "viewer"
    if role not in EDIT_ROLES:
        return _json({"ok": False, "error": "غير مصرّح لك بالتعديل / not allowed"}, 403)
    body = await request.json()
    try:
        lid = int(body.get("lid"))
    except (TypeError, ValueError):
        return _json({"ok": False, "error": "bad_lid"}, 400)
    link = str(body.get("link") or "").strip()[:600]
    if not link:
        return _json({"ok": False, "error": "empty_link",
                      "message": "الصق رابط قوقل ماب أول / paste a Google Maps link first"}, 400)

    def _work():
        ll = engine.extract_latlng(link)
        if not ll:
            rec = geo.resolve_link(link, api_key=call("maps_key") or "")
            if rec.get("lat") is not None:
                ll = (rec["lat"], rec["lng"])
            else:
                ll = pluscode.from_address(rec.get("address") or link,
                                           engine.REF_LAT, engine.REF_LNG)
        if not ll:
            return None
        # Sanity-gate to greater Riyadh: a link pasted from the wrong tab should be
        # refused, not silently dropped onto the map hundreds of km away.
        if not (23.0 <= ll[0] <= 26.5 and 45.0 <= ll[1] <= 48.5):
            return "out_of_range"
        saver = getattr(HOST, "set_pin", None)
        if not callable(saver):
            return "no_saver"
        return saver(lid, link, ll[0], ll[1])

    res = await asyncio.to_thread(_work)
    if res is None:
        return _json({"ok": False, "error": "unresolvable",
                      "message": "ما قدرنا نطلع موقع من هذا الرابط — جرّب «مشاركة» من تطبيق قوقل ماب."
                                 " / could not read a location from that link"}, 422)
    if res == "out_of_range":
        return _json({"ok": False, "error": "out_of_range",
                      "message": "الموقع طالع برّه الرياض — تأكد من الرابط."
                                 " / that location is outside Riyadh"}, 422)
    if res == "no_saver":
        return _json({"ok": False, "error": "not_wired"}, 500)
    return _json({"ok": True, "lid": lid, "saved": res})


async def api_settings(request):
    """Save the numbers the model runs on: how many cleaners, what they cost, and each
    company's price per clean. Whitelisted keys only — this endpoint can never be talked
    into writing anything else into the settings file."""
    role = HOST.req_role(request) if callable(getattr(HOST, "req_role", None)) else "viewer"
    if role not in EDIT_ROLES:
        return _json({"ok": False, "error": "غير مصرّح لك بالتعديل / not allowed"}, 403)
    body = await request.json()
    cfg = _settings()

    for k in NUMERIC_SETTINGS:
        if k in body:
            try:
                v = float(body.get(k))
            except (TypeError, ValueError):
                return _json({"ok": False, "error": "bad_number", "field": k}, 400)
            if v < 0 or v > 1e7:
                return _json({"ok": False, "error": "out_of_range", "field": k}, 400)
            cfg[k] = int(v) if float(v).is_integer() else v

    if "apartment_price_sar" in body:
        rates = body.get("apartment_price_sar") or {}
        if not isinstance(rates, dict):
            return _json({"ok": False, "error": "bad_rates"}, 400)
        clean = {}
        for tid, val in list(rates.items())[:200]:   # one entry per apartment
            tid = str(tid)[:40]
            if val in (None, ""):
                continue
            try:
                f = float(val)
            except (TypeError, ValueError):
                return _json({"ok": False, "error": "bad_rate", "field": tid}, 400)
            if 0 <= f <= 100000:
                clean[tid] = f
        cfg["apartment_price_sar"] = clean

    save = getattr(HOST, "save_json", None)
    if callable(save):
        save(SETTINGS_FILE, cfg)
    return _json({"ok": True, "settings": cfg})


def register(app):
    app.router.add_post("/api/coverage/settings", _safe(api_settings))
    app.router.add_post("/api/coverage/pin", _safe(api_pin))
    app.router.add_get("/api/coverage/study", _safe(api_study))
    app.router.add_get("/api/coverage/brief", _safe(api_brief))
    app.router.add_get("/api/coverage/geo", _safe(api_geo))
    app.router.add_get("/api/coverage/map.png", _safe(api_map))
