# -*- coding: utf-8 -*-
"""
staff.engine — PURE: one employee's day, built from data bot.py already holds.

Inputs are plain dicts handed over by the bot.py bridge (see staff.host), so this module never
touches Hostaway, Discord or the disk:
    day        schedule.routes.schedule_day(date)      who works, who is off, who covers what
    snap       the cached «اليوم» snapshot              arrivals / departures / empty tonight
    tickets    maintenance tickets                      lid, status, priority, title, due_date
    promises   open promise_ledger rows                 listing_id, promise_text, due_at
    cleaning   {lid: {"report": status, "action": last route ping}}   today only
    oncall     {"now": {...} | None, "tonight": [{employee, from, to}]}

Owner rules this module enforces:
    * never state how many apartments there are: no totals, loads or counts in the payload
    * a guest is shown by first name only (no surname, no phone)
"""

OPEN_TICKET = ("open", "in_progress")
URGENT = ("urgent", "high")

# key, Arabic label, tone (danger | warn | ok | info | quiet)
_CLEAN = {
    "none":     ("ما بدأ التنظيف", "quiet"),
    "arrived":  ("فريق التنظيف وصل", "info"),
    "cleaning": ("جاري التنظيف", "info"),
    "done":     ("خلص التنظيف", "ok"),
    "review":   ("الصور تنتظر المراجعة", "info"),
    "approved": ("التنظيف معتمد", "ok"),
    "reshoot":  ("يبي إعادة تصوير", "warn"),
    "issue":    ("فيه ملاحظة بالتنظيف", "danger"),
}
_REPORT = {
    "submitted_for_review": "review", "pending_manager_review": "review",
    "approved": "approved", "needs_reshoot": "reshoot", "issue_found": "issue",
    "rejected": "reshoot",
}
_ACTION = {"arrived": "arrived", "started": "cleaning", "done": "done"}
CLEANED = ("done", "review", "approved")

EVENT_AR = {
    "turnover": "خروج ودخول اليوم",
    "checkout": "خروج اليوم",
    "checkin":  "دخول اليوم",
    "inhouse":  "فيها ضيف",
    "vacant":   "فاضية الليلة",
    "unknown":  "ما وصلت بيانات اليوم",
}


def first_name(full):
    parts = str(full or "").strip().split()
    return parts[0] if parts else ""


def cleaning_state(report_status, action):
    key = _REPORT.get(str(report_status or ""))
    if not key:
        key = _ACTION.get(str(action or ""), "none")
    label, tone = _CLEAN[key]
    return {"key": key, "label": label, "tone": tone}


def _events(snap, name_to_lid):
    """{lid: {"event", "guest", "nights", "checkout"}} — {} when there is no snapshot."""
    if not snap:
        return None
    out = {}

    def lid_of(row):
        v = row.get("lid")
        if v is None:
            v = (name_to_lid or {}).get(row.get("unit"))
        return v

    arr = {}
    for r in snap.get("arrivals") or []:
        lid = lid_of(r)
        if lid is not None:
            arr[lid] = r
    dep = {lid_of(r) for r in snap.get("departures") or []} - {None}
    empty = {lid_of(r) for r in snap.get("empty") or []} - {None}
    for lid in set(arr) | dep | empty:
        a = arr.get(lid)
        if a and lid in dep:
            ev = "turnover"
        elif a:
            ev = "checkin"
        elif lid in dep:
            ev = "checkout"
        else:
            ev = "vacant"
        out[lid] = {"event": ev,
                    "guest": first_name((a or {}).get("guest")),
                    "nights": (a or {}).get("nights") or 0,
                    "checkout": (a or {}).get("checkout") or ""}
    return out


def _find(day, employee):
    for w in day.get("working") or []:
        if w.get("name") == employee:
            return "working", w
    for o in day.get("off") or []:
        if o.get("name") == employee:
            return ("leave" if o.get("reason") == "leave" else "off"), o
    return "unknown", None


def _ticket_late(t, today_iso):
    d = str(t.get("due_date") or "")[:10]
    return bool(d) and d < today_iso


def _promise_late(p, now_iso):
    d = str(p.get("due_at") or "")[:19]
    return bool(d) and d < str(now_iso)[:19]


def _apartment_card(apt, mine, owner_name, events, cleaning, tickets, promises, today_iso,
                    now_iso):
    lid = apt.get("listing_id")
    if events is None:
        ev = {"event": "unknown", "guest": "", "nights": 0, "checkout": ""}
    else:
        ev = events.get(lid) or {"event": "inhouse", "guest": "", "nights": 0, "checkout": ""}
    c = (cleaning or {}).get(lid) or {}
    tks = [{"id": t.get("id"), "title": t.get("title") or "", "priority": t.get("priority") or "med",
            "status": t.get("status"), "late": _ticket_late(t, today_iso)}
           for t in tickets if t.get("lid") == lid and t.get("status") in OPEN_TICKET]
    prs = [{"id": p.get("id"), "text": p.get("promise_text") or "", "due_at": p.get("due_at") or "",
            "late": _promise_late(p, now_iso)}
           for p in promises
           if str(p.get("listing_id") or "") == str(lid) and (p.get("status") or "open") == "open"]
    return {"lid": lid, "name": apt.get("name") or "", "mine": mine,
            "owner_name": "" if mine else (owner_name or ""),
            "event": ev["event"], "event_ar": EVENT_AR[ev["event"]], "guest": ev["guest"],
            "nights": ev["nights"], "checkout": ev["checkout"],
            "cleaning": cleaning_state(c.get("report"), c.get("action")),
            "tickets": tks, "promises": prs}


def _tasks(apartments):
    """Everything waiting on this employee, most urgent first. rank: lower = sooner."""
    out = []

    def add(rank, kind, tone, a, title, ref=None):
        out.append({"rank": rank, "kind": kind, "tone": tone, "lid": a["lid"], "unit": a["name"],
                    "title": title, "ref": ref})

    for a in apartments:
        ev, cl = a["event"], a["cleaning"]["key"]
        if ev in ("checkin", "turnover") and a["tickets"]:
            add(0, "arrival_ticket", "danger", a, "ضيف داخل اليوم والتذكرة مفتوحة",
                a["tickets"][0]["id"])
        if ev == "turnover" and cl not in CLEANED:
            add(1, "turnover_clean", "danger", a, "خروج ودخول اليوم · التنظيف قبل الدخول")
        for p in a["promises"]:
            if p["late"]:
                add(2, "promise_late", "danger", a, "وعد متأخر · " + p["text"], p["id"])
        for t in a["tickets"]:
            if t["late"]:
                add(3, "ticket_late", "warn", a, "تذكرة متأخرة · " + t["title"], t["id"])
            elif t["priority"] in URGENT:
                add(3, "ticket_urgent", "warn", a, "تذكرة عاجلة · " + t["title"], t["id"])
        if ev == "checkout" and cl not in CLEANED:
            add(4, "checkout_clean", "warn", a, "خروج اليوم · يحتاج تنظيف")
        if cl in ("reshoot", "issue"):
            add(5, "cleaning_fix", "warn", a, a["cleaning"]["label"])
        if ev == "checkin":
            add(6, "checkin", "info", a, "دخول اليوم" + (" · " + a["guest"] if a["guest"] else ""))
        for p in a["promises"]:
            if not p["late"]:
                add(7, "promise", "info", a, "وعد للضيف · " + p["text"], p["id"])
        for t in a["tickets"]:
            if not t["late"] and t["priority"] not in URGENT:
                add(8, "ticket", "info", a, "تذكرة مفتوحة · " + t["title"], t["id"])
    out.sort(key=lambda x: (x["rank"], x["unit"]))
    return out


def team(day, employee):
    working = []
    for w in day.get("working") or []:
        cov = []
        for c in w.get("coverage") or []:
            n = c.get("owner_name") or ""
            if n and n not in cov:
                cov.append(n)
        working.append({"name": w.get("name") or "", "emoji": w.get("emoji") or "",
                        "color": w.get("color") or "", "covering_for": cov,
                        "me": w.get("name") == employee})
    off = []
    for o in day.get("off") or []:
        by = []
        for a in o.get("apartments") or []:
            n = a.get("covering_name") or ""
            if n and n not in by:
                by.append(n)
        off.append({"name": o.get("name") or "", "emoji": o.get("emoji") or "",
                    "reason": o.get("reason") or "off", "covered_by": by,
                    "me": o.get("name") == employee})
    return {"working": working, "off": off}


def build_today(employee, day, snap, tickets, promises, cleaning, oncall, today_iso, now_iso,
                name_to_lid=None):
    day = day or {}
    tickets = tickets or []
    promises = promises or []
    status, row = _find(day, employee)
    events = _events(snap, name_to_lid)
    apartments, covering_for, covered_by = [], [], []
    if status == "working":
        for apt in row.get("own") or []:
            apartments.append(_apartment_card(apt, True, "", events, cleaning, tickets, promises,
                                              today_iso, now_iso))
        for c in row.get("coverage") or []:
            n = c.get("owner_name") or ""
            if n and n not in covering_for:
                covering_for.append(n)
            apartments.append(_apartment_card(c.get("apartment") or {}, False, n, events,
                                              cleaning, tickets, promises, today_iso, now_iso))
    elif row is not None:
        covered_by = [{"name": (a.get("apartment") or {}).get("name") or "",
                       "by": a.get("covering_name") or ""}
                      for a in row.get("apartments") or []]
    tasks = _tasks(apartments)
    oc = oncall or {}
    return {
        "employee": employee, "date": day.get("date") or today_iso,
        "weekday_ar": day.get("weekday_ar") or "", "status": status,
        "covering_for": covering_for, "covered_by": covered_by,
        "apartments": apartments, "tasks": tasks, "next": tasks[:3],
        "team": team(day, employee),
        "oncall": {"now": oc.get("now"), "tonight": list(oc.get("tonight") or [])},
        "has_snapshot": events is not None,
    }


def supervisor_items(review_rows, replies, escalations):
    """What waits on a supervisor across the whole team today. Each item deep-links into the
    dashboard page that already does the job (and already checks the permission)."""
    out = []
    for r in review_rows or []:
        if _REPORT.get(str(r.get("status") or "")) == "review":
            out.append({"kind": "review", "tone": "info", "lid": r.get("lid"),
                        "unit": r.get("name") or "", "title": "صور تنظيف تنتظر مراجعتك",
                        "href": "/dashboard#clean_center"})
    if replies:
        out.append({"kind": "replies", "tone": "warn", "lid": None, "unit": "",
                    "title": "ردود مساعد تنتظر موافقتك", "href": "/dashboard#inbox"})
    if escalations:
        out.append({"kind": "escalations", "tone": "danger", "lid": None, "unit": "",
                    "title": "ضيوف ينتظرون أحد يمسك موضوعهم", "href": "/dashboard#inbox"})
    return out


def my_week(days, employee):
    """[{date, weekday_ar, status}] for the coming days — working | off | leave | unknown."""
    out = []
    for d in days or []:
        st, _ = _find(d or {}, employee)
        out.append({"date": (d or {}).get("date") or "", "weekday_ar": (d or {}).get("weekday_ar") or "",
                    "status": st})
    return out
