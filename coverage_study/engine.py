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

UNKNOWN_PERSON = "غير معروف"

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

def build_units(listings, guide_units, teams, in_house_team_ids=None):
    """One row per live apartment: where it is, who cleans it, and how we know.

    Coordinates prefer the listings store — that is what the dispatch/ETA code already
    trusts — and fall back to the pin in the guest guide. `coord_source` records which,
    so a wrong pin can be traced to the sheet it came from.
    """
    in_house = set(in_house_team_ids or ())
    team_name = {str(t.get("id")): (t.get("name") or "") for t in (teams or [])}
    guide_by_lid = {}
    for g in guide_units or []:
        lid = g.get("listing_id")
        if lid is None:
            continue
        try:
            guide_by_lid[int(lid)] = g
        except (TypeError, ValueError):
            continue

    out = []
    for rec in listings or []:
        if rec.get("active") is False:
            continue
        try:
            lid = int(rec.get("id"))
        except (TypeError, ValueError):
            continue
        g = guide_by_lid.get(lid) or {}
        lat, lng, src = rec.get("lat"), rec.get("lng"), "listing"
        if lat is None or lng is None:
            lat, lng, src = None, None, ""
            for link, tag in ((rec.get("maps_link"), "listing_link"),
                              (g.get("map_link"), "guide")):
                ll = extract_latlng(link)
                if ll:
                    lat, lng, src = ll[0], ll[1], tag
                    break
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
          demand_per_day=None, current_people=None, units=None):
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

    rows = work_days(events)
    cyc = cycle_stats(rows, max_gap_min=max_gap_min)

    by_day = defaultdict(lambda: {"date": "", "count": 0, "people": set()})
    for e in events:
        d = by_day[e["date"]]
        d["date"] = e["date"]
        d["count"] += 1
        d["people"].add((e.get("by") or "").strip() or UNKNOWN_PERSON)
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
               "per_day": round(v["cleans"] / float(v["days"]), 1) if v["days"] else 0}
              for k, v in sorted(per_person.items(), key=lambda kv: -kv[1]["cleans"])]

    days_worked = len({e["date"] for e in events})
    active_people = len(per_person) if per_person else 0
    if current_people is None:
        # TYPICAL day, not the busiest — one all-hands day should not become the baseline.
        current_people = int(_median([d["people"] for d in daily]) or 0)

    thr = throughput_stats(rows)

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
