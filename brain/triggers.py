# -*- coding: utf-8 -*-
"""
brain.triggers — the explicit, editable trigger calendar for the Elite v5 campaigns.

One table says WHEN each campaign may fire (calendar-only — the audience/segment gate lives in
brain.cards.recommend_today, which has the guest data). Nothing here is scattered across ifs:
every campaign has one CAMPAIGN_TRIGGERS entry, and the Saudi holiday dates live in one table
(BASE_HOLIDAYS) that the owner can override from the dashboard when Saudi announces exact
Eid / Hijri dates (settings key "gap_holidays").

Everything is a PURE function of (date, holiday-overrides) so the tests feed fixed dates and
assert the eligibility without any clock, network or DB.

Python weekday(): Mon=0 … Sun=6. Midweek (Sun–Wed) = {6,0,1,2}; the weekend (Thu/Fri/Sat) is
never a midweek day, so no evergreen campaign fires on it.
"""

from datetime import date

MIDWEEK = frozenset({6, 0, 1, 2})            # Sun, Mon, Tue, Wed

# Default send window per campaign: 'morning' ≈ 11:00, 'evening' ≈ 19:00 (Riyadh). Editable here.
HOUR_MORNING = 11
HOUR_EVENING = 19

# --------------------------------------------------------------------------
# Saudi holiday table — ONE place to edit. Fixed-Gregorian holidays carry MM-DD; the lunar ones
# (Ramadan / Eid / Hijri New Year) carry the 2026 approximations from the build spec and SHOULD be
# overridden each year from the dashboard (settings "gap_holidays": {"EID-FITR":"2026-03-20", …}).
# --------------------------------------------------------------------------
BASE_HOLIDAYS = {
    "GREG-NEW-YEAR":  "01-01",
    "FOUNDING-DAY":   "02-22",
    "RAMADAN-START":  "02-18",   # lunar — override yearly
    "EID-FITR":       "03-20",   # lunar — override yearly
    "EID-ADHA":       "05-27",   # lunar — override yearly
    "HIJRI-NEW-YEAR": "06-16",   # lunar — override yearly
    "NATIONAL-DAY":   "09-23",
}
HOLIDAY_NAMES_AR = {
    "GREG-NEW-YEAR": "رأس السنة الميلادية", "FOUNDING-DAY": "يوم التأسيس",
    "RAMADAN-START": "بداية رمضان", "EID-FITR": "عيد الفطر", "EID-ADHA": "عيد الأضحى",
    "HIJRI-NEW-YEAR": "رأس السنة الهجرية", "NATIONAL-DAY": "اليوم الوطني",
}
# Holidays that create a "long weekend" (the LONG-WEEKEND campaign looks 3–7 days ahead of these).
LONG_WEEKEND_HOLIDAYS = ("FOUNDING-DAY", "NATIONAL-DAY", "EID-FITR", "EID-ADHA",
                         "HIJRI-NEW-YEAR", "GREG-NEW-YEAR")


def _parse_md(s, year):
    """'MM-DD' or 'YYYY-MM-DD' -> date in `year` (full dates keep their own year)."""
    s = str(s or "").strip()
    parts = s.split("-")
    try:
        if len(parts) == 3:
            return date(int(parts[0]), int(parts[1]), int(parts[2]))
        if len(parts) == 2:
            return date(year, int(parts[0]), int(parts[1]))
    except (ValueError, TypeError):
        return None
    return None


def holiday_dates(year, overrides=None):
    """{name: date} for `year`, merging BASE_HOLIDAYS with any dashboard overrides. An override may
    be a full ISO date (used verbatim, re-homed to `year` if it's MM-DD) or a MM-DD string."""
    overrides = overrides or {}
    out = {}
    for name, md in BASE_HOLIDAYS.items():
        ov = overrides.get(name)
        d = None
        if ov:
            d = _parse_md(ov, year)
            # a full override dated to another year: keep month/day, home it to `year`
            if d and len(str(ov).split("-")) == 3 and d.year != year:
                try:
                    d = date(year, d.month, d.day)
                except ValueError:
                    d = None
        if d is None:
            d = _parse_md(md, year)
        if d:
            out[name] = d
    return out


def next_holiday_within(d, max_days, overrides=None, names=None):
    """The soonest holiday strictly ahead of `d` within `max_days` (searching this year + next, so
    a January holiday is found from December). Returns (name, holiday_date, days_until) or None."""
    names = set(names or LONG_WEEKEND_HOLIDAYS)
    best = None
    for yr in (d.year, d.year + 1):
        for name, hd in holiday_dates(yr, overrides).items():
            if name not in names:
                continue
            delta = (hd - d).days
            if 0 <= delta <= max_days:
                if best is None or delta < best[2]:
                    best = (name, hd, delta)
    return best


def _in_dom_range(day, start, end):
    """Day-of-month in [start,end] inclusive, with month wrap (e.g. 27..1 spans month-end)."""
    if start <= end:
        return start <= day <= end
    return day >= start or day <= end


# --------------------------------------------------------------------------
# The trigger table: one row per campaign. `kind` + params decide WHEN it may fire; `priority`
# ranks competing campaigns (higher first); `time` picks the default send window.
# kinds: dom_range | month_range | holiday_window | long_weekend | evergreen_midweek | segment
# --------------------------------------------------------------------------
CAMPAIGN_TRIGGERS = {
    # calendar-urgent
    "PAYDAY-DROPPED":  {"kind": "dom_range", "start": 27, "end": 1, "priority": 80, "time": "evening"},
    "END-OF-MONTH":    {"kind": "dom_range", "start": 20, "end": 26, "priority": 70, "time": "evening"},
    "LONG-WEEKEND":    {"kind": "long_weekend", "min_days": 3, "max_days": 7, "priority": 78, "time": "evening"},
    # holidays / seasons
    "EID":             {"kind": "holiday_window", "names": ["EID-FITR", "EID-ADHA"], "before": 3, "after": 3, "priority": 92, "time": "morning"},
    "NATIONAL-DAY":    {"kind": "holiday_window", "names": ["NATIONAL-DAY"], "before": 4, "after": 1, "priority": 90, "time": "evening"},
    "FOUNDING-DAY":    {"kind": "holiday_window", "names": ["FOUNDING-DAY"], "before": 4, "after": 1, "priority": 90, "time": "evening"},
    "RAMADAN":         {"kind": "holiday_window", "names": ["RAMADAN-START"], "before": 2, "after": 28, "priority": 85, "time": "evening"},
    "NEW-YEAR":        {"kind": "holiday_window", "names": ["GREG-NEW-YEAR", "HIJRI-NEW-YEAR"], "before": 3, "after": 3, "priority": 84, "time": "evening"},
    "HEATWAVE":        {"kind": "month_range", "months": [6, 7, 8, 9], "priority": 50, "time": "morning"},
    "PERFECT-WEATHER": {"kind": "month_range", "months": [12, 1, 2], "priority": 50, "time": "morning"},
    "SCHOOL-BREAK":    {"kind": "month_range", "months": [6, 7, 8], "priority": 55, "time": "morning"},
    # behavioral / segment (calendar-always; the audience gate decides if there's anyone to send to)
    "DORMANT-COMEBACK": {"kind": "segment", "priority": 62, "time": "evening"},
    "WIN-BACK-ALIAS":   None,  # reserved (kept out of the table)
    "FIRST-TIMER":      {"kind": "segment", "priority": 60, "time": "evening"},
    "LOYAL-THANKS":     {"kind": "segment", "priority": 58, "time": "evening"},
    "LAST-MINUTE":      {"kind": "segment", "priority": 64, "time": "evening"},
    "POST-STAY":        {"kind": "segment", "priority": 66, "time": "morning"},
    "BIRTHDAY":         {"kind": "segment", "priority": 68, "time": "morning"},
    # evergreen — always available any midweek, lowest priority (the filler)
    "MIDWEEK-RESET":       {"kind": "evergreen_midweek", "priority": 20, "time": "evening"},
    "WORK-FROM-ELSEWHERE": {"kind": "evergreen_midweek", "priority": 18, "time": "morning"},
    "GIFT-SOMEONE":        {"kind": "evergreen_midweek", "priority": 16, "time": "evening"},
}
CAMPAIGN_TRIGGERS = {k: v for k, v in CAMPAIGN_TRIGGERS.items() if v}   # drop reserved Nones


def send_hour(code):
    t = (CAMPAIGN_TRIGGERS.get(code) or {}).get("time", "evening")
    return HOUR_MORNING if t == "morning" else HOUR_EVENING


def time_label(code):
    h = send_hour(code)
    h12 = h % 12 or 12
    suffix_en = "AM" if h < 12 else "PM"
    suffix_ar = "صباحاً" if h < 12 else "مساءً"
    return {"hour": h, "ar": "الساعة %d %s" % (h12, suffix_ar), "en": "%d:00 %s" % (h12, suffix_en)}


def _fires(code, trig, d, overrides):
    """Return (fires: bool, reason_ar, reason_en) for one campaign on date `d`."""
    kind = trig.get("kind")
    if kind == "dom_range":
        ok = _in_dom_range(d.day, trig["start"], trig["end"])
        if code == "PAYDAY-DROPPED":
            return ok, "نزل الراتب (أيام %d–%d)" % (trig["start"], trig["end"]), "Payday window (days %d–%d)" % (trig["start"], trig["end"])
        return ok, "قبيل الراتب (أيام %d–%d)" % (trig["start"], trig["end"]), "Pre-payday (days %d–%d)" % (trig["start"], trig["end"])
    if kind == "month_range":
        ok = d.month in set(trig["months"])
        return ok, "الموسم مناسب", "In-season"
    if kind == "evergreen_midweek":
        ok = d.weekday() in MIDWEEK
        return ok, "وسط الأسبوع", "Midweek"
    if kind == "segment":
        return True, "الشريحة متاحة", "Segment available"     # calendar-always; audience gates later
    if kind == "holiday_window":
        for name in trig["names"]:
            for yr in (d.year, d.year + 1, d.year - 1):
                hd = holiday_dates(yr, overrides).get(name)
                if not hd:
                    continue
                delta = (hd - d).days                          # >0 = ahead, <0 = past
                if -int(trig.get("after", 0)) <= delta <= int(trig.get("before", 0)):
                    return True, "قرب %s" % HOLIDAY_NAMES_AR.get(name, name), "Near %s" % name.replace("-", " ").title()
        return False, "", ""
    if kind == "long_weekend":
        hit = next_holiday_within(d, int(trig.get("max_days", 7)), overrides, LONG_WEEKEND_HOLIDAYS)
        if hit and hit[2] >= int(trig.get("min_days", 3)):
            return True, "إجازة طويلة بعد %d أيام (%s)" % (hit[2], HOLIDAY_NAMES_AR.get(hit[0], hit[0])), \
                   "Long weekend in %d days (%s)" % (hit[2], hit[0].replace("-", " ").title())
        return False, "", ""
    return False, "", ""


def eligible_campaigns(d, overrides=None):
    """All campaigns whose trigger window is live on date `d`, highest priority first. PURE — the
    audience/segment availability is applied later by recommend_today. Each item:
        {code, priority, time, time_label, reason_ar, reason_en}"""
    overrides = overrides or {}
    out = []
    for code, trig in CAMPAIGN_TRIGGERS.items():
        fires, r_ar, r_en = _fires(code, trig, d, overrides)
        if not fires:
            continue
        out.append({
            "code": code, "priority": int(trig.get("priority", 0)),
            "time": trig.get("time", "evening"), "time_label": time_label(code),
            "reason_ar": r_ar, "reason_en": r_en,
        })
    out.sort(key=lambda x: -x["priority"])
    return out


def calendar_table(year, overrides=None):
    """The dashboard's editable view: each holiday with its resolved date for `year` (so the owner
    can see and override), plus a plain description of every campaign's trigger window."""
    hd = holiday_dates(year, overrides)
    holidays = [{"name": n, "name_ar": HOLIDAY_NAMES_AR.get(n, n),
                 "date": hd.get(n).isoformat() if hd.get(n) else None,
                 "lunar": n in ("RAMADAN-START", "EID-FITR", "EID-ADHA", "HIJRI-NEW-YEAR")}
                for n in BASE_HOLIDAYS]
    rules = []
    for code, t in CAMPAIGN_TRIGGERS.items():
        rules.append({"code": code, "kind": t.get("kind"), "priority": t.get("priority"),
                      "time": t.get("time")})
    return {"year": year, "holidays": holidays, "rules": rules}
