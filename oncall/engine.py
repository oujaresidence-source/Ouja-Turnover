# -*- coding: utf-8 -*-
"""
oncall.engine — the PURE rules of «المناوبة». No I/O, no clock reads, no database.

Every function takes what it needs and returns plain data, so the tests can feed a fake
week and assert numbers. notify.py is the only caller that touches the world.

The night of date D runs 17:00 -> 24:00 Riyadh time on D. Inside a night, time is counted
in MINUTES AFTER 17:00 (0..420), so a slot is the half-open range [start_min, end_min).
"""

import datetime

WINDOW_START_HOUR = 17          # 5 PM
WINDOW_MINUTES = 7 * 60         # 17:00 -> 24:00
CHECK_EVERY_MIN = 15            # «موجود؟» cadence (owner decision)
ANSWER_WINDOW_MIN = 10          # time to press before it is a miss (owner decision)
CLAIM_WITHIN_MIN = 10           # an escalation must be claimed within this
STALE_AFTER_MIN = 30            # no update this long after the owner's slot ended -> supervisor
PUBLISH_HOUR = 12               # tomorrow's night is published at 12:00
LOCK_HOUR = 15                  # tonight locks at 15:00
REMIND_BEFORE_MIN = 15          # «مناوبتك تبدأ …» DM
SEND_GRACE_MIN = 2              # a check not sent within this of its time is void (bot was down)
DOWNTIME_GAP_SEC = 120          # a tick gap longer than this is recorded as bot downtime
HANDOVER_GRACE_MIN = 5          # handover posted within this after a slot ends, else skipped

MISS_ALERT = "alert"            # 1st miss of the night: employee + supervisor
MISS_WARN = "warn"              # 2nd miss: formal warning (ops_warnings) + supervisor
MISS_ALERT_AGAIN = "alert_again"  # 3rd+: supervisor only, never a second warning


# ----------------------------------------------------------------- time helpers

def sun_weekday(d):
    """Python Monday=0 -> the Employee Calendar's convention, 0=الأحد .. 6=السبت."""
    return (d.weekday() + 1) % 7


def night_start(d, tzinfo):
    """17:00 on date d, tz-aware."""
    return datetime.datetime(d.year, d.month, d.day, WINDOW_START_HOUR, 0, tzinfo=tzinfo)


def at_minute(d, minute, tzinfo):
    return night_start(d, tzinfo) + datetime.timedelta(minutes=int(minute))


def night_minute(now):
    """(night_date, minute 0..419) when `now` is inside 17:00-24:00, else (None, None)."""
    if now.hour < WINDOW_START_HOUR:
        return None, None
    return now.date(), (now.hour - WINDOW_START_HOUR) * 60 + now.minute


def hm(minute):
    """Minutes after 17:00 -> '5:00' .. '12:00' (12-hour clock, the way the team talks)."""
    h = WINDOW_START_HOUR + int(minute) // 60
    m = int(minute) % 60
    h12 = h - 12 if h > 12 else h
    return "%d:%02d" % (h12, m)


# ----------------------------------------------------------------- the rotation

def _rot(available, d):
    """Roster order rotated by the calendar day, so ties never favour the same person."""
    n = len(available)
    k = d.toordinal() % n
    return {p: (i - k) % n for i, p in enumerate(available)}


def build_night(d, available, history):
    """The night of date d, auto-distributed and fair.

    available: names, in roster order, who can work tonight (already filtered for weekly day
               off, recorded leave and a linked Discord account).
    history:   [{date: 'YYYY-MM-DD', slots: [{employee, start_min, end_min}]}] — the
               trailing nights before d (7 is what notify passes).

    Rules:
      * 7 hours split into contiguous whole hours: 7 // n each, the 7 % n remainder hours
        to whoever has the FEWEST trailing hours (ties: fewer long slots, then rotation).
      * the LAST slot (ends 24:00) goes to whoever held it least recently.
      * the rest are rotated so nobody starts at the same time as yesterday when avoidable.
    Deterministic: same inputs -> same night. Returns [{employee, start_min, end_min}]."""
    available = list(dict.fromkeys(available or []))
    n = len(available)
    if n == 0:
        return []
    rot = _rot(available, d)
    hours = {p: 0 for p in available}
    longs = {p: 0 for p in available}
    last_late = {p: "" for p in available}
    yday = {}
    yiso = (d - datetime.timedelta(days=1)).isoformat()
    for night in sorted(history or [], key=lambda h: h["date"]):
        for s in night.get("slots") or []:
            p = s["employee"]
            if p not in hours:
                continue
            ln = (int(s["end_min"]) - int(s["start_min"])) // 60
            hours[p] += ln
            if ln >= 2:
                longs[p] += 1
            if int(s["end_min"]) == WINDOW_MINUTES:
                last_late[p] = night["date"]
            if night["date"] == yiso:
                yday[p] = int(s["start_min"])

    base, extra_n = divmod(WINDOW_MINUTES // 60, n)
    ranked = sorted(available, key=lambda p: (hours[p], longs[p], rot[p]))
    extra = set(ranked[:extra_n])
    length = {p: (base + (1 if p in extra else 0)) * 60 for p in available}

    late = min(available, key=lambda p: (last_late[p], rot[p]))
    rest = [p for p in available if p != late]
    rest.sort(key=lambda p: (yday.get(p, -1), rot[p]))

    best = None
    for shift in list(range(1, len(rest))) + [0]:
        order = rest[shift:] + rest[:shift] + [late]
        out, t = [], 0
        for p in order:
            out.append({"employee": p, "start_min": t, "end_min": t + length[p]})
            t += length[p]
        clashes = sum(1 for s in out if yday.get(s["employee"]) == s["start_min"])
        if best is None or clashes < best[0]:
            best = (clashes, out)
        if clashes == 0:
            break
    return best[1]


def owner_at(slots, minute):
    """Who is on duty at `minute` (0..419) — the slot whose [start,end) contains it."""
    if minute is None:
        return None
    for s in slots or []:
        if int(s["start_min"]) <= minute < int(s["end_min"]):
            return s
    return None


# ----------------------------------------------------------------- presence checks

def check_minutes(start_min, end_min, every=CHECK_EVERY_MIN):
    """The first check fires the moment the slot starts, then every 15 minutes.
    A 2-hour slot from 0 -> [0, 15, 30, 45, 60, 75, 90, 105]."""
    return list(range(int(start_min), int(end_min), int(every)))


def overlaps(a0, a1, b0, b1):
    return a0 < b1 and b0 < a1


def check_verdict(due_at, now, delivered, answered_at, downtimes, window=ANSWER_WINDOW_MIN):
    """('pending'|'answered'|'missed'|'voided', void_reason).

    The employee never pays for the bot: a check that never reached them, or whose
    window was spanned by bot downtime, is VOID — never a miss."""
    deadline = due_at + datetime.timedelta(minutes=window)
    if answered_at is not None and answered_at <= deadline:
        return "answered", ""
    if now < deadline:
        return "pending", ""
    if not delivered:
        return "voided", "not_delivered"
    for d0, d1 in downtimes or []:
        if overlaps(d0, d1, due_at, deadline):
            return "voided", "bot_down"
    return "missed", ""


def miss_decision(nth_miss_tonight):
    """1st -> alert, 2nd -> formal warning, 3rd+ -> alert again (one warning per night)."""
    n = int(nth_miss_tonight or 0)
    if n <= 1:
        return MISS_ALERT
    if n == 2:
        return MISS_WARN
    return MISS_ALERT_AGAIN


# ----------------------------------------------------------------- issue ownership

def claim_overdue(opened_at, claimed_at, now, already_alerted, within=CLAIM_WITHIN_MIN):
    if claimed_at is not None or already_alerted:
        return False
    return now - opened_at >= datetime.timedelta(minutes=within)


def stale_due(slot_end_at, last_update_at, now, alerted_tonight, after=STALE_AFTER_MIN):
    """After the owner's slot has ended, and only while it is still 17:00-24:00, no update for
    30 minutes -> alert the supervisor, at most ONCE per issue per night."""
    if alerted_tonight:
        return False
    nd, _m = night_minute(now)
    if nd is None:
        return False
    if now < slot_end_at:
        return False
    return now - last_update_at >= datetime.timedelta(minutes=after)


# ----------------------------------------------------------------- swaps

def swap_decision(night_status, requester, target_slot, requester_slot, requester_ok,
                  target_ok, pending_exists):
    """(ok, kind, reason_ar). kind: 'exchange' (requester has a slot tonight) or 'takeover'."""
    if night_status not in ("published",):
        return False, "", "الجدول مقفل — التعديل الحين من اسيل بس."
    if not target_slot:
        return False, "", "ما لقيت السلوت."
    if same_person(target_slot["employee"], requester):
        return False, "", "هذا سلوتك أنت."
    if not requester_ok:
        return False, "", "ما تقدر تاخذ مناوبة الليلة (إجازة أو حسابك مو مربوط)."
    if not target_ok:
        return False, "", "صاحب السلوت ما نقدر نوصله الحين."
    if pending_exists:
        return False, "", "فيه طلب تبديل على هذا السلوت ينتظر رد."
    return True, ("exchange" if requester_slot else "takeover"), ""


# ----------------------------------------------------------------- names

def norm(name):
    """Arabic-tolerant key: the escalation picker says «نوره»/«ماثر»/«محمد», the calendar
    says «نورة»/«مآثر»/«محمد اليامي». Same rules as ops.notify._norm."""
    s = (name or "").strip()
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ٱ", "ا"),
                 ("ة", "ه"), ("ى", "ي"), ("ـ", "")):
        s = s.replace(a, b)
    return " ".join("".join(ch for ch in s if ch not in "ًٌٍَُِّْ").split())


def same_person(a, b):
    """Equal after normalising, or one is the other's first name («محمد» ~ «محمد اليامي»)."""
    x, y = norm(a), norm(b)
    if not x or not y:
        return False
    return x == y or x.split(" ")[0] == y or y.split(" ")[0] == x
