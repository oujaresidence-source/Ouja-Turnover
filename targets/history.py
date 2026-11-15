# -*- coding: utf-8 -*-
"""
targets.history — where the booking history comes from.

  1. ONE-TIME seed: a Hostaway reservations export (CSV) uploaded on the admin screen. It is
     the only source for listings Hostaway has deleted — the API no longer returns them.
     The file holds guest names and phones: it is kept under STATE_DIR, never in the repo.
  2. EVERY NIGHT: month by month through HOST.fetch_window (bot.fetch_reservations_window —
     never the truncated history cache), plus the calendar for owner/maintenance blocks.

A seed listing NAME is matched to a live Hostaway listing by exact (normalised) name only.
A name that does not match is NEVER guessed: its rows stay as history under 'n:<name>' and
the name is reported to the owner, who either points it at a listing or leaves it as history.
"""

import csv
import datetime as dt
import io
import os

from . import db, engine
from .host import HOST

KEEP_STATUS = ("new", "modified", "cancelled")
SEED_NAME = "reservations_seed.csv"


def norm_name(s):
    return " ".join(str(s or "").split()).casefold()


def channel_of(raw):
    c = str(raw or "").strip().lower()
    if "direct" in c or "bookingengine" in c or "website" in c:
        return "direct"
    if "airbnb" in c:
        return "airbnb"
    return c or "other"


def _iso(x):
    s = str(x or "").strip()[:10]
    try:
        return dt.date.fromisoformat(s).isoformat()
    except ValueError:
        return ""


def _now_iso():
    return HOST.require("now")().isoformat(timespec="seconds")


def _nights(arrival, departure):
    a, b = dt.date.fromisoformat(arrival), dt.date.fromisoformat(departure)
    return [(a + dt.timedelta(days=i)).isoformat() for i in range(max(0, min((b - a).days, 400)))]


# ------------------------------------------------------------------ name -> unit

def _live_by_name():
    out = {}
    for lid, name in (HOST.call("listings", {}) or {}).items():
        out.setdefault(norm_name(name), str(lid))
    return out


def unit_for_name(shown, live=None, known=None):
    """(unit key, status). Manual decisions win; then an exact live-name match; else history."""
    n = norm_name(shown)
    if not n:
        return "n:?", "unmapped"
    known = known if known is not None else {r["name"]: r for r in db.names()}
    row = known.get(n)
    if row and row["status"] == "manual" and row["listing_id"]:
        return str(row["listing_id"]), "manual"
    if row and row["status"] == "history":
        return "n:" + n, "history"
    live = live if live is not None else _live_by_name()
    if n in live:
        return live[n], "auto"
    return "n:" + n, "unmapped"


def unit_names():
    """{unit key: display name} for every unit this package has ever seen."""
    out = {}
    for lid, name in (HOST.call("listings", {}) or {}).items():
        out[str(lid)] = name
    for r in db.names():
        out.setdefault("n:" + r["name"], r["shown"] or r["name"])
        if r["listing_id"]:
            out.setdefault(str(r["listing_id"]), r["shown"] or r["name"])
    return out


def unmapped():
    return [{"name": r["name"], "shown": r["shown"]} for r in db.names() if r["status"] == "unmapped"]


def map_name(name, listing_id, by):
    """Owner's decision for one seed name: a live listing id, or '' = «شقة محذوفة، تاريخ فقط»."""
    n = norm_name(name)
    row = db.name_row(n)
    if not row:
        return False, "الاسم غير موجود"
    live = HOST.call("listings", {}) or {}
    if listing_id:
        if str(listing_id) not in {str(k) for k in live}:
            return False, "رقم الشقة غير موجود في Hostaway"
        unit, status = str(listing_id), "manual"
    else:
        unit, status = "n:" + n, "history"
    db.set_name(n, row["shown"], str(listing_id or ""), status, by, _now_iso())
    spellings = {r["listing_name"] for r in db.q("SELECT DISTINCT listing_name FROM tg_res")
                 if norm_name(r["listing_name"]) == n}
    db.remap_unit(sorted(spellings), unit)
    old = "n:" + n
    if unit != old:
        moved = [(unit, d) for d in db.blocked_dates(old, "0000", "9999")]
        if moved:
            db.add_blocked(moved, "seed")
            db.execute("DELETE FROM tg_blocked WHERE unit=?", (old,))
    db.log("map_name", _now_iso(), by, {"name": n, "listing_id": str(listing_id or "")})
    return True, ""


# ------------------------------------------------------------------ the one-time seed

def seed_path():
    return os.path.join(HOST.state_dir or ".", "targets", SEED_NAME)


def import_seed_text(text, by=""):
    """Parse a Hostaway reservations export and store it. Safe to run twice (upsert)."""
    live = _live_by_name()
    known = {r["name"]: r for r in db.names()}
    now = _now_iso()
    rows, blocked, seen_names, skipped = [], [], {}, 0
    reader = csv.DictReader(io.StringIO(text))
    for x in reader:
        shown = (x.get("Listing") or "").strip()
        arrival, departure = _iso(x.get("Check-in date")), _iso(x.get("Check-out date"))
        if not shown or not arrival or not departure or departure <= arrival:
            skipped += 1
            continue
        n = norm_name(shown)
        if n not in seen_names:
            seen_names[n] = (shown,) + unit_for_name(shown, live, known)
        unit = seen_names[n][1]
        status = (x.get("Status") or "").strip()
        guest = (x.get("Guest name") or "").strip()
        chan_raw = (x.get("Channel") or "").strip()
        if status == "ownerStay" or chan_raw == "customIcal" or "CLOSED" in guest.upper():
            if status in ("ownerStay", "new", "modified"):
                blocked.extend((unit, d) for d in _nights(arrival, departure))
            continue
        if status not in KEEP_STATUS:
            continue
        rid = (x.get("Hostaway reservation ID") or "").strip()
        if not rid:
            skipped += 1
            continue
        try:
            total = float(x.get("Total price") or 0)
        except ValueError:
            total = 0.0
        phone = (x.get("Phone") or "").strip()
        rows.append({"res_id": rid, "unit": unit, "listing_name": shown,
                     "phone_key": engine.phone_key(phone), "phone": phone, "guest_name": guest,
                     "channel": channel_of(chan_raw), "status": status, "arrival": arrival,
                     "departure": departure,
                     "created": _iso(x.get("Reservation date")) or arrival, "total": total,
                     "source": "seed", "updated_at": now})
    # an API row already stored for the same reservation is newer than the export: keep it
    have_api = {r["res_id"] for r in db.q("SELECT res_id FROM tg_res WHERE source='api'")}
    rows = [r for r in rows if r["res_id"] not in have_api]
    db.upsert_res(rows)
    db.add_blocked(blocked, "seed")
    for n, (shown, unit, status) in seen_names.items():
        row = known.get(n)
        if row and row["status"] in ("manual", "history"):
            continue
        db.set_name(n, shown, unit if not unit.startswith("n:") else "", status, by, now)
    report = {"rows": len(rows), "blocked_nights": len(blocked), "skipped": skipped,
              "listings": len(seen_names),
              "unmapped": sorted(s for s, _u, st in seen_names.values() if st == "unmapped")}
    db.set_setting("seed_imported_at", now, by, now)
    db.log("seed_import", now, by, {k: (v if k != "unmapped" else len(v)) for k, v in report.items()})
    return report


def import_seed_file(path=None, by=""):
    path = path or seed_path()
    with open(path, encoding="utf-8-sig", newline="") as f:
        return import_seed_text(f.read(), by)


# ------------------------------------------------------------------ nightly sync

def _api_row(r, names, now):
    lid = r.get("listingMapId")
    arrival, departure = _iso(r.get("arrivalDate")), _iso(r.get("departureDate"))
    if lid in (None, "") or not r.get("id") or not arrival or not departure or departure <= arrival:
        return None
    phone = str(r.get("phone") or r.get("guestPhone") or "").strip()
    try:
        total = float(r.get("totalPrice") or 0)
    except (TypeError, ValueError):
        total = 0.0
    return {"res_id": str(r["id"]), "unit": str(lid),
            "listing_name": names.get(str(lid)) or ("unit-%s" % lid),
            "phone_key": engine.phone_key(phone), "phone": phone,
            "guest_name": str(r.get("guestName") or "").strip(),
            "channel": channel_of(r.get("channelName") or r.get("channel")),
            "status": str(r.get("status") or ""), "arrival": arrival, "departure": departure,
            "created": _iso(r.get("reservationDate") or r.get("insertedOn")) or arrival,
            "total": total, "source": "api", "updated_at": now}


def month_keys(first, count):
    y, m = int(first[:4]), int(first[5:7])
    out = []
    for _ in range(count):
        out.append("%04d-%02d" % (y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def shift_month(month_key, by):
    y, m = int(month_key[:4]), int(month_key[5:7])
    idx = y * 12 + (m - 1) + by
    return "%04d-%02d" % (idx // 12, idx % 12 + 1)


def sync_month(month_key, names=None):
    """Pull one month through the targeted window fetch and store it."""
    start, end = engine.month_bounds(month_key)
    raw = HOST.require("fetch_window")(start, end - dt.timedelta(days=1)) or []
    names = names if names is not None else {str(k): v for k, v in (HOST.call("listings", {}) or {}).items()}
    now = _now_iso()
    rows, blocked = [], []
    for r in raw:
        row = _api_row(r, names, now)
        if row is None:
            continue
        if row["status"] == "ownerStay":
            blocked.extend((row["unit"], d) for d in _nights(row["arrival"], row["departure"]))
        elif row["status"] in KEEP_STATUS:
            rows.append(row)
    db.upsert_res(rows)
    db.add_blocked(blocked, "api_owner")
    return len(rows)


def sync_blocked(start, end):
    """Owner/maintenance blocks from the calendar, for units that have an owner in the
    Employee Calendar. One call per unit; a failed call leaves that unit's nights as they were."""
    cal = HOST.calendar_days
    if cal is None:
        return 0
    booked = {}
    for r in db.q("SELECT unit, arrival, departure FROM tg_res WHERE status IN ('new','modified') "
                  "AND departure>? AND arrival<?", (start.isoformat(), end.isoformat())):
        booked.setdefault(r["unit"], set()).update(_nights(r["arrival"], r["departure"]))
    done = 0
    for o in HOST.call("ownership", []) or []:
        lid = o.get("listing_id")
        if lid in (None, ""):
            continue
        try:
            days = cal(lid, start, end - dt.timedelta(days=1)) or []
        except Exception as e:
            print("[targets] calendar failed for %s: %s" % (lid, e))
            continue
        if not days:
            continue
        unit = str(lid)
        dates = []
        for d in days:
            day = _iso(d.get("date"))
            if not day or day in booked.get(unit, ()):
                continue
            if d.get("reservationId") or d.get("reservations"):
                continue
            if not d.get("isAvailable") and str(d.get("status") or "").lower() != "reserved":
                dates.append(day)
        db.set_blocked(unit, dates, "api_cal", start.isoformat(), end.isoformat())
        done += 1
    return done


def nightly(today=None):
    """The whole nightly job: last month, this month and the next two; blocks for this month
    and next. Returns a small report. Never raises past the caller's log line."""
    today = today or HOST.require("now")().date()
    this = "%04d-%02d" % (today.year, today.month)
    names = {str(k): v for k, v in (HOST.call("listings", {}) or {}).items()}
    report = {"months": {}, "calendars": 0}
    for mk in month_keys(shift_month(this, -1), 4):
        try:
            report["months"][mk] = sync_month(mk, names)
        except Exception as e:
            report["months"][mk] = "failed: %s" % e
    try:
        start, _ = engine.month_bounds(this)
        _, end = engine.month_bounds(shift_month(this, 1))
        report["calendars"] = sync_blocked(start, end)
    except Exception as e:
        report["calendars"] = "failed: %s" % e
    now = _now_iso()
    db.set_setting("synced_at", now, "system", now)
    db.log("sync", now, "system", report)
    return report
