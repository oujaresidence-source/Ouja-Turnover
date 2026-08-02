# -*- coding: utf-8 -*-
"""Pure maths for the cleaning-coverage study. NO network, NO files, NO globals.

Everything the «تغطية التنظيف» tab shows is computed here so it can be tested with
invented numbers before it is ever trusted with real ones
(tests/test_coverage_engine.py).

The one thing to keep in mind while reading this: the system records when a cleaner
FINISHES an apartment, never when they start. So there is no honest "how long did
this flat take" figure anywhere in the data. What we do have is:

  * photo time   — first photo upload -> submit. Real, but it is the photo session
                   at the END of the clean, so it under-reads badly. Never present
                   this as a cleaning duration.
  * cycle time   — one finish to the next finish by the same person. Clean + drive +
                   park + walk up. Fully recorded, and the right unit for staffing.

The capacity model is built on cycle time. Do not quietly switch it to photo time.
"""

import math
from collections import defaultdict
from datetime import datetime

from . import pluscode

UNKNOWN_PERSON = "غير معروف"

# Reference point for recovering SHORT Plus Codes — central Riyadh. A short code drops
# its leading characters and is only meaningful near a reference; every Ouja unit is in
# greater Riyadh, so this is safe.
REF_LAT, REF_LNG = 24.7136, 46.6753


def _load_seed():
    """Coordinates resolved ONCE from the owner's Supabase sheet, keyed by guide slug.

    The sheet always held a Maps link for every apartment; re-resolving those links over
    the network on each deploy is what kept leaving units unlocated. Resolved offline
    and committed, so the map is populated the moment the page opens.
    """
    import json
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed_locations.json")
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except Exception:
        return {}
    out = {}
    for slug, rec in (raw or {}).items():
        try:
            out[str(slug).strip().lower()] = {"lat": float(rec["lat"]),
                                              "lng": float(rec["lng"]),
                                              "src": rec.get("src") or "seed"}
        except (TypeError, ValueError, KeyError):
            continue
    return out


SEED_LOCATIONS = _load_seed()

# A gap longer than this is lunch, a shift change, or a drive across town — not the
# cost of one apartment. Excluded from the median, but always COUNTED and reported.
DEFAULT_MAX_GAP_MIN = 180
# A gap SHORTER than this is a batched submission: the cleaner pressed «تم» for several
# apartments in one burst. Also excluded, also counted. Ignoring this produced a
# 1-minute "cycle time" on live data (2026-08-02).
DEFAULT_MIN_GAP_MIN = 5

# Reports that never reached a submit still count as done if they carry one of these.
DONE_STATUSES = frozenset((
    "submitted_for_review", "pending_manager_review", "manager_approved",
    "manager_rejected", "needs_reshoot", "issue_found",
))


# ------------------------------------------------------------------ time helpers

def parse_ts(value):
    """ISO timestamp -> datetime, or None. Tolerates both the tz-aware stamps the bot
    writes now and the naive ones older records carry."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _minutes_between(start, end):
    """Whole minutes from start to end; None if unknown, unparseable, or negative.
    Mixed naive/aware stamps would raise on subtraction — treated as unknown."""
    a, b = parse_ts(start), parse_ts(end)
    if a is None or b is None:
        return None
    try:
        delta = (b - a).total_seconds() / 60.0
    except TypeError:
        return None
    return int(round(delta)) if delta >= 0 else None


def _day_of(value):
    return str(value or "")[:10]


# ------------------------------------------------------------------ geometry

EARTH_R_M = 6371000.0


def haversine_m(a, b):
    """Great-circle metres between two (lat, lng) pairs. None if either is incomplete."""
    if not a or not b:
        return None
    try:
        lat1, lng1 = float(a[0]), float(a[1])
        lat2, lng2 = float(b[0]), float(b[1])
    except (TypeError, ValueError, IndexError):
        return None
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * EARTH_R_M * math.asin(math.sqrt(h)), 1)


def extract_latlng(url):
    """Best-effort (lat, lng) out of a Google Maps URL. Returns None unless confident.

    Deliberately conservative: a wrong pin puts a cleaner at the wrong building, which
    is worse than an honest blank. Short goo.gl links carry no coordinates at all and
    correctly return None — coverage_study.geo resolves those separately.
    """
    import re
    s = str(url or "").strip()
    if not s:
        return None

    def _ok(lat, lng):
        try:
            lat, lng = float(lat), float(lng)
        except (TypeError, ValueError):
            return None
        if -90 <= lat <= 90 and -180 <= lng <= 180 and not (lat == 0 and lng == 0):
            return (lat, lng)
        return None

    # A bare "24.75,46.70" — what the browser sends as a route start.
    m = re.match(r"^\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)\s*$", s)
    if m:
        return _ok(m.group(1), m.group(2))
    # Coordinates written into an address in words: "N 24.75995° E 46.67103°".
    m = re.search(r"N\s*(\d{1,2}\.\d+)\s*°?\s*[,;]?\s*E\s*(\d{2,3}\.\d+)\s*°?", s, re.I)
    if m:
        return _ok(m.group(1), m.group(2))
    # ?q=lat,lng  /  ?query=lat,lng  /  ll=lat,lng
    m = re.search(r"[?&](?:q|query|ll|daddr|destination)=(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)", s)
    if m:
        return _ok(m.group(1), m.group(2))
    # /@lat,lng,17z
    m = re.search(r"/@(-?\d+\.\d+),(-?\d+\.\d+)", s)
    if m:
        return _ok(m.group(1), m.group(2))
    # !3dLAT!4dLNG (place links)
    m = re.search(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)", s)
    if m:
        return _ok(m.group(1), m.group(2))
    return None


def cluster_units(units, radius_m=120):
    """Group units that sit on the same pin / same building.

    Greedy single-pass in listing-id order, so the result never depends on the order
    the caller happened to hand them over. Units with no coordinates are each their
    own cluster and flagged `has_location: False` — never silently lumped together.
    """
    ordered = sorted(units, key=lambda u: (u.get("lid") is None, u.get("lid")))
    clusters = []
    for u in ordered:
        lat, lng = u.get("lat"), u.get("lng")
        here = (lat, lng) if (lat is not None and lng is not None) else None
        placed = False
        if here:
            for c in clusters:
                if not c["has_location"]:
                    continue
                d = haversine_m((c["lat"], c["lng"]), here)
                if d is not None and d <= radius_m:
                    c["lids"].append(u.get("lid"))
                    c["units"].append(u)
                    c["district"] = c["district"] or (u.get("district") or "")
                    placed = True
                    break
        if not placed:
            clusters.append({
                "key": "c%d" % (len(clusters) + 1),
                "lat": lat, "lng": lng,
                "has_location": here is not None,
                "district": u.get("district") or "",
                "lids": [u.get("lid")],
                "units": [u],
            })
    for c in clusters:
        c["size"] = len(c["lids"])
        c["label"] = c["district"] or (c["units"][0].get("name") or "")
    clusters.sort(key=lambda c: (-c["size"], c["lids"][0] if c["lids"] else 0))
    return clusters


# ------------------------------------------------------------------ timings

def photo_timing(report, photos):
    """(started, ended, minutes, photo_count) for one report.

    Mirrors bot.py's _cleanproof_timing exactly — same fallbacks — so the tab and the
    Discord approval card can never disagree with each other.
    """
    rid = report.get("report_id")
    mine = [p for p in (photos or [])
            if p.get("report_id") == rid and p.get("status") == "uploaded"]
    ups = sorted(p.get("uploaded_at") for p in mine if p.get("uploaded_at"))
    started = (ups[0] if ups else "") or report.get("created_at") or ""
    ended = (report.get("submitted_at") or (ups[-1] if ups else "")
             or report.get("updated_at") or "")
    minutes = _minutes_between(started, ended) if (started and ended) else None
    if not mine:
        minutes = None            # no photos = no evidence, not "0 minutes"
    return started, ended, minutes, len(mine)


def done_events(status_log, reports, photos=None):
    """Every apartment-finished event, newest last.

    Two sources, deliberately:
      * oujact_status.json — the real spine, but it is trimmed to the last 5000 events,
        so the earliest days eventually fall out of it.
      * cleaning_reports.json — never pruned, so it still remembers the first week.
    Where both know about the same apartment-day the status log wins (it is the actual
    button press). Unparseable stamps are dropped rather than guessed at.
    """
    out = {}
    for e in status_log or []:
        if (e.get("action") or "") != "done":
            continue
        ts = e.get("ts")
        if parse_ts(ts) is None:
            continue
        lid, day = e.get("lid"), _day_of(e.get("date") or ts)
        out[(lid, day)] = {"lid": lid, "date": day, "ts": ts,
                           "by": e.get("by") or "", "source": "status"}
    for r in reports or []:
        submitted = r.get("submitted_at")
        if not submitted and (r.get("status") or "") not in DONE_STATUSES:
            continue
        ts = submitted
        if not ts:
            mine = sorted(p.get("uploaded_at") for p in (photos or [])
                          if p.get("report_id") == r.get("report_id")
                          and p.get("status") == "uploaded" and p.get("uploaded_at"))
            ts = (mine[-1] if mine else "") or r.get("updated_at")
        if parse_ts(ts) is None:
            continue
        lid, day = r.get("apartment_id"), _day_of(r.get("date") or ts)
        if (lid, day) in out:
            continue                      # the status log already has it
        out[(lid, day)] = {"lid": lid, "date": day, "ts": ts,
                           "by": r.get("cleaner_name") or "", "source": "report"}
    return sorted(out.values(), key=lambda e: (parse_ts(e["ts"]), e["lid"]))


def work_days(events):
    """One row per person per day: what they finished, when, and the gaps between."""
    groups = defaultdict(list)
    for e in events or []:
        groups[(e.get("date"), (e.get("by") or "").strip() or UNKNOWN_PERSON)].append(e)
    rows = []
    for (day, person), evs in groups.items():
        evs = sorted(evs, key=lambda e: parse_ts(e["ts"]))
        gaps = []
        for prev, cur in zip(evs, evs[1:]):
            m = _minutes_between(prev["ts"], cur["ts"])
            if m is not None:
                gaps.append(m)
        first, last = evs[0]["ts"], evs[-1]["ts"]
        rows.append({
            "date": day, "person": person, "count": len(evs),
            "first_ts": first, "last_ts": last,
            "span_min": _minutes_between(first, last) or 0,
            "gaps": gaps,
            "lids": [e["lid"] for e in evs],
        })
    rows.sort(key=lambda r: (r["date"], r["person"]))
    return rows


def _median(xs):
    if not xs:
        return None
    s = sorted(xs)
    n = len(s)
    mid = n // 2
    return round(s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0, 1)


def cycle_stats(rows, max_gap_min=DEFAULT_MAX_GAP_MIN, min_gap_min=DEFAULT_MIN_GAP_MIN):
    """Pooled cycle time across every work day.

    Two exclusions, both counted and reported — a silently trimmed sample is how you
    end up under-hiring:

      * gaps ABOVE max_gap_min  — lunch, a shift change, a drive across town.
      * gaps BELOW min_gap_min  — BATCHED submissions. Cleaners press «تم» for several
        apartments in one burst, so those records are seconds apart. They are two rows
        written together, not two apartments cleaned back to back. Counting them made
        the live page report a 1-minute cycle and 480 apartments per person per day.

    When most of the sample is batched this returns median_min=None rather than a
    tidy-looking fiction. Capacity should then come from observed day rates instead
    (throughput_stats) — see capacity_model.
    """
    kept, excluded, batched = [], 0, 0
    for r in rows or []:
        for g in r.get("gaps") or []:
            if g is None:
                continue
            if g < min_gap_min:
                batched += 1
            elif g > max_gap_min:
                excluded += 1
            else:
                kept.append(g)
    total = len(kept) + excluded + batched
    base = {"excluded": excluded, "batched": batched,
            "batched_pct": round(batched * 100.0 / total, 1) if total else 0.0,
            "max_gap_min": max_gap_min, "min_gap_min": min_gap_min}
    if not kept:
        base.update({"median_min": None, "mean_min": None, "p25_min": None,
                     "p75_min": None, "n": 0})
        return base
    s = sorted(kept)
    half = len(s) // 2
    base.update({
        "median_min": _median(s),
        "mean_min": round(sum(s) / float(len(s)), 1),
        "p25_min": _median(s[:half]) if half else _median(s),
        "p75_min": _median(s[-half:]) if half else _median(s),
        "n": len(s),
    })
    return base


def throughput_stats(rows):
    """Apartments finished per person per DAY, straight from the work-day rows.

    This is the honest basis for a head count on this data. Batched button presses
    distort every gap-based measure, but they cannot distort a whole-day total — the
    apartments still got cleaned that day, whenever the button was pressed.

    Median (not mean, not peak) so one heroic day cannot inflate the plan.
    """
    counts = sorted(int(r.get("count") or 0) for r in (rows or []) if r.get("count"))
    if not counts:
        return {"median": None, "p75": None, "mean": None, "n": 0}
    half = len(counts) // 2
    return {
        "median": _median(counts),
        "p75": _median(counts[-half:]) if half else _median(counts),
        "mean": round(sum(counts) / float(len(counts)), 1),
        "n": len(counts),
    }


# ------------------------------------------------------------------ capacity

def capacity_model(units_per_person_day=None, cycle_median_min=None, workday_min=480,
                   demand_per_day=0, current_people=0, cluster_saving_pct=0):
    """How many cleaners it takes to cover `demand_per_day` apartments.

    PREFERS the OBSERVED apartments-per-person-per-day rate. That is what this log can
    actually measure: cleaners submit in batches, so every gap-based figure is corrupted,
    but a whole-day total is not (2026-08-02 — a 1-minute "cycle" produced a nonsense
    480 apartments per person per day on live data).

    Falls back to deriving a rate from cycle time only when no observed rate exists, and
    says which basis it used. Head count always rounds UP — you cannot hire 3.1 people.
    """
    saving = max(0.0, min(60.0, float(cluster_saving_pct or 0)))
    base = {"workday_min": workday_min, "demand_per_day": demand_per_day,
            "current_people": current_people, "cluster_saving_pct": saving,
            "cycle_used_min": None, "basis": "", "reason": ""}

    per_person, basis, cycle_used = 0, "", None
    if units_per_person_day and float(units_per_person_day) > 0:
        per_person = int(math.floor(float(units_per_person_day) * (1.0 + saving / 100.0)))
        basis, cycle_used = "observed", None
    elif cycle_median_min and float(cycle_median_min) > 0:
        cycle = float(cycle_median_min) * (1.0 - saving / 100.0)
        per_person = int(workday_min // cycle) if cycle > 0 else 0
        basis, cycle_used = "cycle", round(cycle, 1)
    else:
        base.update({"units_per_person_day": None, "people_needed": None, "hire": None,
                     "reason": ("لا يوجد أساس كافٍ للحساب — لا معدل يومي ولا زمن دورة سليم / "
                                "no basis yet — neither an observed day rate nor a usable cycle time")})
        return base

    base.update({"basis": basis, "cycle_used_min": cycle_used})
    if per_person <= 0:
        base.update({"units_per_person_day": 0, "people_needed": None, "hire": None,
                     "reason": ("المعدل المقاس أقل من شقة في اليوم / "
                                "the measured rate is under one apartment a day")})
        return base
    needed = int(math.ceil(float(demand_per_day) / per_person)) if demand_per_day else 0
    base.update({
        "units_per_person_day": per_person,
        "people_needed": needed,
        "hire": max(0, needed - int(current_people or 0)),
    })
    return base


# ------------------------------------------------------------------ units

def norm_code(s):
    """Apartment code normaliser: lowercase, punctuation out, tokens SORTED.

    Sorted because the two systems write the same unit in different orders —
    the sheet says `101-qur`, Hostaway says `QUR 101`. Dropping the brand word keeps
    `Ouja | 3BMJ` and `3bmj` together.
    """
    import re
    s = re.sub(r"[^a-z0-9]+", " ", (s or "").lower())
    return " ".join(sorted(t for t in s.split() if t not in ("ouja",)))


def build_units(listings, guide_units, teams, in_house_team_ids=None):
    """One row per live apartment: where it is, who cleans it, and how we know.

    Coordinates prefer the listings store — that is what the dispatch/ETA code already
    trusts — and fall back to the pin in the guest guide. `coord_source` records which,
    so a wrong pin can be traced to the sheet it came from.
    """
    in_house = set(in_house_team_ids or ())
    team_name = {str(t.get("id")): (t.get("name") or "") for t in (teams or [])}
    guide_by_lid, by_code, ambiguous = {}, {}, set()
    for g in guide_units or []:
        lid = g.get("listing_id")
        if lid is not None:
            try:
                guide_by_lid[int(lid)] = g
            except (TypeError, ValueError):
                pass
        # Second index on the SHEET CODE (the slug). The guide's importer only ever
        # matched marketing names against Hostaway internal names, which scored 0/17
        # on live data and left 63 of 71 apartments with no pin.
        code = norm_code(g.get("slug"))
        if not code:
            continue
        if code in by_code and by_code[code] is not g:
            ambiguous.add(code)          # never guess between two sheet rows
        by_code[code] = g

    out = []
    for rec in listings or []:
        if rec.get("active") is False:
            continue
        try:
            lid = int(rec.get("id"))
        except (TypeError, ValueError):
            continue
        g = guide_by_lid.get(lid)
        if g is None:
            code = norm_code(rec.get("internal_name"))
            g = by_code.get(code) if code and code not in ambiguous else None
        g = g or {}
        lat, lng, src = rec.get("lat"), rec.get("lng"), "listing"
        if lat is None or lng is None:
            lat, lng, src = None, None, ""
            for link, tag in ((rec.get("maps_link"), "listing_link"),
                              (g.get("map_link"), "guide")):
                ll = extract_latlng(link)
                if ll:
                    lat, lng, src = ll[0], ll[1], tag
                    break
            if lat is None:
                # A Plus Code in the Hostaway address IS a coordinate written as text —
                # exact, offline, no geocoder and no API key. Several Ouja units carry
                # one ("QJVM+4MM, King Fahd Rd, As Sahafah, Riyadh").
                ll = pluscode.from_address(rec.get("address"), REF_LAT, REF_LNG)
                if ll:
                    lat, lng, src = ll[0], ll[1], "pluscode"
            if lat is None and g.get("slug"):
                # Pre-resolved once from the owner's own Supabase sheet (seed_locations
                # .json). The sheet already held every pin; resolving it on every
                # deployment over the network was the reason apartments kept reading
                # "no location" while the answer sat in the repo.
                seeded = SEED_LOCATIONS.get(str(g.get("slug")).strip().lower())
                if seeded:
                    lat, lng, src = seeded["lat"], seeded["lng"], "sheet:" + seeded.get("src", "seed")
        tid = str(rec.get("cleaning_team") or "")
        link = (rec.get("maps_link") or g.get("map_link") or "")
        out.append({
            "lid": lid,
            "name": rec.get("internal_name") or rec.get("public_name") or ("unit-%d" % lid),
            "district": rec.get("group") or rec.get("address") or "",
            "bedrooms": rec.get("bedrooms"),
            "lat": lat, "lng": lng,
            "coord_source": src,
            "has_location": lat is not None and lng is not None,
            "map_link": link,
            # What the geocoder should look up. Most live units have a street address but
            # NO map pin, so without this fallback there is nothing to resolve for them.
            "geo_key": link or (rec.get("address") or ""),
            "guide_slug": g.get("slug") or "",
            "team_id": tid,
            "team_name": team_name.get(tid, ""),
            "in_house": tid in in_house,
            "oujact_flag": bool(rec.get("oujact")),
            "active": True,
        })
    out.sort(key=lambda u: u["lid"])
    return out


# ------------------------------------------------------------------ the study

def study(listings, guide_units, teams, status_log, reports, photos,
          since=None, in_house_team_ids=None, workday_min=480,
          cluster_radius_m=120, max_gap_min=DEFAULT_MAX_GAP_MIN,
          demand_per_day=None, current_people=None, units=None, non_cleaners=None):
    """The whole snapshot the coverage tab renders. Pure — hand it dicts, get a dict.

    `units` lets the caller pass rows that have already been through the geo cache, so
    coordinates filled in from a resolved short link are not thrown away and rebuilt.
    """
    in_house = set(in_house_team_ids or ())
    if units is None:
        units = build_units(listings, guide_units, teams, in_house)
    clusters = cluster_units(units, radius_m=cluster_radius_m)

    all_events = done_events(status_log, reports, photos)
    started_on = all_events[0]["date"] if all_events else None   # never moves with `since`
    events = [e for e in all_events if not since or e["date"] >= since]

    # Actors the owner has said are not cleaning staff (themselves, a shared crew link).
    # Their cleans still HAPPENED — demand keeps them — but they must not dilute the
    # per-person rate or inflate the count of people already working.
    excluded_people = set(non_cleaners or ())
    rows = work_days(events)
    counted_rows = [r for r in rows if r["person"] not in excluded_people]
    cyc = cycle_stats(counted_rows, max_gap_min=max_gap_min)

    by_day = defaultdict(lambda: {"date": "", "count": 0, "people": set()})
    for e in events:
        d = by_day[e["date"]]
        d["date"] = e["date"]
        d["count"] += 1
        who = (e.get("by") or "").strip() or UNKNOWN_PERSON
        if who not in excluded_people:
            d["people"].add(who)
    daily = [{"date": d["date"], "count": d["count"], "people": len(d["people"])}
             for d in sorted(by_day.values(), key=lambda x: x["date"])]

    # Photo-session times, kept clearly separate from cycle time.
    photo_mins = []
    for r in reports or []:
        if since and _day_of(r.get("date")) < since:
            continue
        _, _, m, n = photo_timing(r, photos)
        if m is not None and n:
            photo_mins.append(m)

    per_person = defaultdict(lambda: {"days": 0, "cleans": 0})
    for r in rows:
        p = per_person[r["person"]]
        p["days"] += 1
        p["cleans"] += r["count"]
    people = [{"person": k, "days": v["days"], "cleans": v["cleans"],
               "counted": k not in excluded_people,
               "per_day": round(v["cleans"] / float(v["days"]), 1) if v["days"] else 0}
              for k, v in sorted(per_person.items(), key=lambda kv: -kv[1]["cleans"])]

    days_worked = len({e["date"] for e in events})
    active_people = len(per_person) if per_person else 0
    if current_people is None:
        # TYPICAL day, not the busiest — one all-hands day should not become the baseline.
        current_people = int(_median([d["people"] for d in daily]) or 0)

    thr = throughput_stats(counted_rows)

    if demand_per_day is None:
        # Fallback only — routes.py passes the real Hostaway checkout rate instead.
        # HARD CAP at the apartment count: an estimate of 94.8 cleans/day against 71
        # apartments is impossible, and scaling the observed rate up by
        # total/in-house produced exactly that on live data (2026-08-02).
        obs = round(len(events) / float(days_worked), 1) if days_worked else 0
        demand_per_day = min(obs, float(len(units))) if units else obs

    cap = capacity_model(units_per_person_day=thr["median"],
                         cycle_median_min=cyc["median_min"],
                         workday_min=workday_min,
                         demand_per_day=demand_per_day, current_people=current_people)

    stacked = sum(c["size"] for c in clusters if c["size"] > 1)
    return {
        "units": {
            "total": len(units),
            "in_house": sum(1 for u in units if u["in_house"]),
            "third_party": sum(1 for u in units if u["team_id"] and not u["in_house"]),
            "unassigned": sum(1 for u in units if not u["team_id"]),
            "located": sum(1 for u in units if u["has_location"]),
            "missing_location": sum(1 for u in units if not u["has_location"]),
            "rows": units,
        },
        "clusters": {
            "total": len(clusters),
            "multi": sum(1 for c in clusters if c["size"] > 1),
            "stacked_units": stacked,
            "biggest": clusters[0]["size"] if clusters else 0,
            "rows": [{k: v for k, v in c.items() if k != "units"} for c in clusters],
        },
        "teams": _team_rollup(units, teams, in_house),
        "oujact": {
            "started_on": started_on,
            "since": since or started_on,
            "days_worked": days_worked,
            "total_cleans": len(events),
            "per_day_avg": round(len(events) / float(days_worked), 1) if days_worked else 0,
            "active_people": active_people,
            "daily": daily,
            "people": people,
            "work_days": rows,
        },
        "cycle": cyc,
        "throughput": thr,
        "photo_time": {
            "median_min": _median(photo_mins),
            "n": len(photo_mins),
            "warning": ("هذا زمن التصوير وليس زمن التنظيف / this is the photo session, "
                        "not the cleaning time"),
        },
        "capacity": cap,
    }


# ------------------------------------------------------------------ turn deadlines

DEFAULT_CHECKIN_HOUR = 15
DEFAULT_CHECKOUT_HOUR = 11
CONFIRMED = ("new", "modified")           # Hostaway's confirmed statuses

SKIP_UNLINKED = "الشقة غير مرتبطة بـ Hostaway"
SKIP_INACTIVE = "الشقة غير مفعّلة في Hostaway"

TURN_KINDS = ("T0", "T1", "T2")


def _hour(value, default):
    """'16:00' -> 16. Anything unreadable falls back, rather than dropping the turn."""
    try:
        return max(0, min(23, int(str(value).split(":")[0])))
    except (TypeError, ValueError, IndexError, AttributeError):
        return default


def _dt(date_iso, hour):
    d = str(date_iso or "")[:10]
    if len(d) != 10:
        return None
    try:
        return datetime.strptime(d, "%Y-%m-%d").replace(hour=hour)
    except ValueError:
        return None


def classify_turns(reservations, units, all_lids=None, since=None, until=None,
                   checkin_hour=DEFAULT_CHECKIN_HOUR, checkout_hour=DEFAULT_CHECKOUT_HOUR):
    """Every checkout, joined to the NEXT check-in for the same apartment.

        T0  next check-in the SAME day   — hard deadline, the guest is arriving
        T1  next check-in the NEXT day   — due by end of tomorrow
        T2  later, or nothing booked     — deferrable

    This is the difference between a day with 19 relaxed turns and a day with 12 that
    must happen inside a few hours. Both look identical on a count alone.

    It comes entirely from the reservations, so it needs NO new button and no change to
    how cleaners work — unlike a true cleaning duration, which the data cannot give.
    Cancelled bookings are ignored on both sides: a cancelled same-day arrival must not
    manufacture a hard deadline that does not exist.

    Skips are returned explicitly with an Arabic reason — never a silently shorter list.
    """
    active = {}
    for u in units or []:
        try:
            active[int(u.get("lid"))] = u
        except (TypeError, ValueError):
            continue
    known = set(all_lids) if all_lids is not None else None

    arrivals, departures, skipped, seen_skips = {}, {}, [], set()

    def _skip(lid, reason):
        if (lid, reason) in seen_skips:
            return
        seen_skips.add((lid, reason))
        skipped.append({"lid": lid, "reason": reason})

    for r in reservations or []:
        if str(r.get("status") or "") not in CONFIRMED:
            continue
        try:
            lid = int(r.get("listingMapId"))
        except (TypeError, ValueError):
            continue
        if lid not in active:
            _skip(lid, SKIP_INACTIVE if (known and lid in known) else SKIP_UNLINKED)
            continue
        a = _dt(r.get("arrivalDate"), _hour(r.get("checkInTime"), checkin_hour))
        if a:
            arrivals.setdefault(lid, []).append(a)
        d = _dt(r.get("departureDate"), _hour(r.get("checkOutTime"), checkout_hour))
        if d:
            departures.setdefault(lid, []).append(d)

    for v in arrivals.values():
        v.sort()

    rows = []
    for lid, deps in departures.items():
        ars = arrivals.get(lid, [])
        for dep in sorted(deps):
            day = dep.date().isoformat()
            if since and day < since:
                continue
            if until and day > until:
                continue
            nxt = next((a for a in ars if a > dep), None)
            if nxt is None:
                kind, deadline = "T2", None
            elif nxt.date() == dep.date():
                kind, deadline = "T0", nxt.isoformat(timespec="minutes")
            elif (nxt.date() - dep.date()).days == 1:
                kind = "T1"
                deadline = nxt.replace(hour=23, minute=59).isoformat(timespec="minutes")
            else:
                kind, deadline = "T2", None
            rows.append({"lid": lid, "name": (active[lid].get("name") or str(lid)),
                         "date": day, "kind": kind, "deadline": deadline,
                         "checkout": dep.isoformat(timespec="minutes"),
                         "next_checkin": nxt.isoformat(timespec="minutes") if nxt else None})

    rows.sort(key=lambda r: (r["date"], r["lid"]))
    by_date = {}
    for r in rows:
        d = by_date.setdefault(r["date"], {"date": r["date"], "T0": 0, "T1": 0,
                                           "T2": 0, "total": 0})
        d[r["kind"]] += 1
        d["total"] += 1
    return {"rows": rows, "by_date": by_date, "skipped": skipped,
            "counts": {k: sum(1 for r in rows if r["kind"] == k) for k in TURN_KINDS}}


# ------------------------------------------------------------------ shape of the week

WEEKDAY_AR = ("الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد")
WEEKDAY_EN = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
# Saudi week reads Sunday-first; Python's weekday() is Monday=0.
_WEEK_ORDER = (6, 0, 1, 2, 3, 4, 5)


def week_shape(turns, weeks_back=None):
    """Turns by weekday, with the same-day (T0) portion broken out.

    Answers the question the head count actually hinges on: is the busiest day 1.2x an
    average day or 2x? Staffing the mean and hoping is how Thursday goes wrong.
    """
    per_day = {}
    for t in turns or []:
        d = per_day.setdefault(t.get("date"), {"total": 0, "T0": 0})
        d["total"] += 1
        if t.get("kind") == "T0":
            d["T0"] += 1

    buckets = {i: {"total": 0, "T0": 0, "days": 0} for i in range(7)}
    for date_iso, v in per_day.items():
        dt = _dt(date_iso, 12)
        if not dt:
            continue
        b = buckets[dt.weekday()]
        b["total"] += v["total"]
        b["T0"] += v["T0"]
        b["days"] += 1

    days = []
    for wd in _WEEK_ORDER:
        b = buckets[wd]
        n = b["days"] or 1
        days.append({"weekday": wd, "ar": WEEKDAY_AR[wd], "en": WEEKDAY_EN[wd],
                     "total": round(b["total"] / float(n), 1) if b["days"] else 0,
                     "T0": round(b["T0"] / float(n), 1) if b["days"] else 0,
                     "observed_days": b["days"]})

    totals = sorted(v["total"] for v in per_day.values())
    mean = round(sum(totals) / float(len(totals)), 1) if totals else 0
    busiest = max(days, key=lambda d: d["total"]) if days else None
    return {"days": days, "mean_per_day": mean,
            "p70_per_day": _percentile(totals, 70),
            "busiest": busiest,
            "peak_ratio": round(busiest["total"] / mean, 2) if (busiest and mean) else None,
            "observed_days": len(totals)}


def _percentile(values, pct):
    """Nearest-rank percentile — no interpolation, so it always lands on a real day."""
    if not values:
        return 0
    s = sorted(values)
    k = int(math.ceil(pct / 100.0 * len(s))) - 1
    return s[max(0, min(len(s) - 1, k))]


# ------------------------------------------------------------------ head count

DEFAULT_ROSTER_FACTOR = 30 / 26.0     # six-day week: 26 worked days in 30
DEFAULT_ABSENCE_FACTOR = 0.08         # leave + sickness


def headcount(demand_per_day, rate, current_people=0, peak_per_day=None,
              roster_factor=DEFAULT_ROSTER_FACTOR, absence_factor=DEFAULT_ABSENCE_FACTOR):
    """Four numbers, not one — because "on shift" and "on payroll" are not the same thing.

    The previous single figure staffed the average day and quietly assumed everyone works
    every day. To keep N people on shift daily across a six-day week you need N × 30/26 on
    payroll, and more again once leave and sickness are allowed for.
    """
    base = {"demand_per_day": demand_per_day, "rate": rate,
            "current_people": current_people, "peak_per_day": peak_per_day,
            "roster_factor": round(roster_factor, 3),
            "absence_factor": absence_factor, "reason": ""}
    if not rate or float(rate) <= 0:
        base.update({"on_shift_avg": None, "payroll": None, "on_shift_peak": None,
                     "gap": None,
                     "reason": "ما فيه معدل يومي مقاس بعد / no measured day rate yet"})
        return base
    on_shift = int(math.ceil(float(demand_per_day) / float(rate))) if demand_per_day else 0
    payroll = int(math.ceil(on_shift * float(roster_factor) * (1.0 + float(absence_factor))))
    peak = (int(math.ceil(float(peak_per_day) / float(rate)))
            if peak_per_day else None)
    base.update({"on_shift_avg": on_shift, "payroll": payroll, "on_shift_peak": peak,
                 "gap": max(0, payroll - int(current_people or 0))})
    return base


# ------------------------------------------------------------------ reconciliation

def reconcile(logged_per_day, checkouts_per_day, units, events, implausible_ratio=2.0):
    """Two checks that can be wrong today without anyone noticing.

    1. Cleans logged vs real checkouts. If Hostaway shows more checkouts than the system
       logged cleans, cleaning is happening that we never see — almost certainly the
       third-party crews — and the head count is understated by exactly that gap.
    2. Crew tags vs the work actually logged on their apartments. OujaCT is tagged to 14
       units yet logged over a thousand cleans; 14 units cannot produce that. So the
       tags describe paperwork, not work, and any plan sized off them is sized wrong.

    Note this counts cleans by the APARTMENT's crew tag, not by who pressed the button —
    a done event records a person, and there is no person-to-crew mapping anywhere.
    """
    gap = round(max(0.0, float(checkouts_per_day or 0) - float(logged_per_day or 0)), 1)

    team_of, names = {}, {}
    for u in units or []:
        team_of[u.get("lid")] = u.get("team_id") or ""
        names[u.get("team_id") or ""] = u.get("team_name") or ""

    cleans, untagged = defaultdict(int), 0
    for e in events or []:
        tid = team_of.get(e.get("lid"))
        if tid is None:
            continue                      # apartment not in the active list at all
        cleans[tid] += 1
        if not tid:
            untagged += 1

    crews = []
    for tid, name in names.items():
        n_units = sum(1 for u in units if (u.get("team_id") or "") == tid)
        n_cleans = cleans.get(tid, 0)
        # A unit turns over at most ~once every other day; well beyond that and the tag
        # cannot be describing who really cleans it.
        ceiling = max(1, n_units) * implausible_ratio * 15
        crews.append({"team_id": tid, "name": name or "—", "units": n_units,
                      "cleans": n_cleans,
                      "implausible": bool(n_units and n_cleans > ceiling)})
    crews.sort(key=lambda c: -c["cleans"])
    return {"logged_per_day": round(float(logged_per_day or 0), 1),
            "checkouts_per_day": round(float(checkouts_per_day or 0), 1),
            "unlogged_per_day": gap, "has_gap": gap > 0.5,
            "crews": crews, "untagged_cleans": untagged}


def _team_rollup(units, teams, in_house_ids):
    known = {str(t.get("id")): (t.get("name") or "") for t in (teams or [])}
    counts = defaultdict(int)
    located = defaultdict(int)
    for u in units:
        counts[u["team_id"]] += 1
        if u["has_location"]:
            located[u["team_id"]] += 1
    rows = []
    for tid, name in known.items():
        rows.append({"team_id": tid, "name": name, "apartments": counts.get(tid, 0),
                     "located": located.get(tid, 0), "in_house": tid in in_house_ids})
    if counts.get(""):
        rows.append({"team_id": "", "name": "", "apartments": counts[""],
                     "located": located.get("", 0), "in_house": False})
    rows.sort(key=lambda r: (not r["in_house"], -r["apartments"]))
    return rows
