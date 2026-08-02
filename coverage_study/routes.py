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
import traceback

from . import engine, geo
from .host import HOST, call

EDIT_ROLES = ("admin", "ops")
SETTINGS_FILE = "coverage_settings.json"

# Actors who press «تم» but are not cleaning staff — the owner named these on
# 2026-08-02. Seeded once into the settings file so it can be changed later without
# a deploy. Their cleans still count as demand; they just do not dilute the
# per-person rate or inflate the count of people already working.
DEFAULT_NON_CLEANERS = ("faisalouja", "route-link", "_hmdkhdyr")


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
    return cfg


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
    s["geo"] = {"filled_from_cache": filled, "cached_total": len(cache),
                "pending": len([u for u in units
                                if not u["has_location"] and u.get("geo_key")]),
                "nothing_to_resolve": len([u for u in units
                                           if not u["has_location"] and not u.get("geo_key")])}
    return s


async def api_study(request):
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
    s = await asyncio.to_thread(_build, params)

    # Real checkout demand from Hostaway beats the engine's capped fallback estimate.
    # Whatever happens is REPORTED — a silent fallback to the estimate is how the page
    # ended up showing an impossible 94.8 cleans/day (2026-08-02).
    if params["demand"] is None and callable(getattr(HOST, "turnovers", None)):
        try:
            end = datetime.date.today()
            start = end - datetime.timedelta(days=29)
            n = await asyncio.to_thread(HOST.turnovers, start.isoformat(), end.isoformat())
            if n:
                s["capacity"] = engine.capacity_model(
                    units_per_person_day=(s.get("throughput") or {}).get("median"),
                    cycle_median_min=s["cycle"]["median_min"],
                    workday_min=params["workday_min"],
                    demand_per_day=round(float(n) / 30.0, 1),
                    current_people=s["capacity"].get("current_people") or 0)
                s["capacity"]["demand_source"] = "hostaway_30d"
                s["capacity"]["demand_note"] = "%d checkouts in 30 days" % n
            else:
                s["capacity"]["demand_note"] = "Hostaway returned no checkouts for the window"
        except Exception as e:
            s["capacity"]["demand_note"] = "Hostaway demand unavailable: %s" % str(e)[:160]
    s["capacity"].setdefault("demand_source", "estimated_from_log")
    s["capacity"].setdefault("demand_note", "")
    s["generated_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    return _json({"ok": True, "study": s})


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
    """Real Google map imagery, fetched BY US so the Maps key never reaches the browser.

    The owner chose this over the interactive JS map precisely to avoid putting a key
    in the page (2026-08-02): nothing to configure in Google Cloud, and no key to steal.
    The page draws its own coloured dots on top using the same Mercator projection.
    """
    key = call("maps_key") or ""
    if not key:
        return _json({"ok": False, "error": "no_maps_key",
                      "message": "ما فيه مفتاح خرائط في الإعدادات / GOOGLE_MAPS_API_KEY is not set"}, 503)
    try:
        lat = float(request.query.get("lat"))
        lng = float(request.query.get("lng"))
    except (TypeError, ValueError):
        return _json({"ok": False, "error": "bad_center"}, 400)
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return _json({"ok": False, "error": "bad_center"}, 400)
    z = _int(request, "z", 11, 1, 20)
    w = _int(request, "w", 640, 100, 640)          # Static Maps caps a side at 640
    h = _int(request, "h", 420, 100, 640)
    ck = (round(lat, 5), round(lng, 5), z, w, h)
    png = _MAP_CACHE.get(ck)
    if png is None:
        def _fetch():
            import requests
            r = requests.get("https://maps.googleapis.com/maps/api/staticmap",
                             params={"center": "%s,%s" % (lat, lng), "zoom": z,
                                     "size": "%dx%d" % (w, h), "scale": 2,
                                     "maptype": "roadmap", "language": "ar",
                                     "region": "sa", "key": key},
                             timeout=20)
            r.raise_for_status()
            if not (r.headers.get("Content-Type") or "").startswith("image/"):
                raise ValueError("Google returned %s" % (r.text or "")[:120])
            return r.content
        try:
            png = await asyncio.to_thread(_fetch)
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


def register(app):
    app.router.add_get("/api/coverage/study", _safe(api_study))
    app.router.add_get("/api/coverage/geo", _safe(api_geo))
    app.router.add_get("/api/coverage/map.png", _safe(api_map))
