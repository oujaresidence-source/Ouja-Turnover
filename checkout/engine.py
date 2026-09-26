# -*- coding: utf-8 -*-
"""
checkout.engine — the PURE rules of «متابعة الخروج». No I/O, no discord, no bot import.

Everything that decides WHEN something happens lives here, so it can be tested with an
injected clock and nothing else:

    state machine   waiting → asking → out | no_answer | inside → cleaned_pending → approved
    the clock       ping at checkout, reminder every 30 min, re-ask at the promised exit time,
                    silence 23:00–08:00
    the cap         the latest exit we can still clean after before check-in / 17:00
    the risk        🔴 / 🟠 / 🟢 / ✅ per apartment, with ONE reason code

The hotel precedent this copies is front-desk "due-out" control: a room is Due Out until the
desk confirms Checked Out, housekeeping only enters after that, and a room reported vacant that
turns out occupied is logged against whoever reported it.
"""

import datetime
import statistics
from zoneinfo import ZoneInfo

RIYADH = "Asia/Riyadh"

# ------------------------------------------------------------------ states

WAITING = "waiting"            # card posted, checkout time still ahead
ASKING = "asking"              # checkout time reached (or re-asked) — nobody answered yet
OUT = "out"                    # ✅ someone confirmed the guest left
NO_ANSWER = "no_answer"        # 📵 the guest is not answering
INSIDE = "inside"              # ⛔ still inside (with a reason and an expected exit) / 🚨 surprise
CLEANED = "cleaned_pending"    # cleaning submitted for review
APPROVED = "approved"          # cleaning report approved

STATES = (WAITING, ASKING, OUT, NO_ANSWER, INSIDE, CLEANED, APPROVED)
OPEN = (WAITING, ASKING, NO_ANSWER, INSIDE)          # still waiting on the guest
QUIET_STATES = (OUT, CLEANED, APPROVED)              # the bot has nothing to chase

# Which answer may move the row from which state. «First final wins for the same step»:
# a second press after the state moved is refused and told who answered first.
ALLOWED_FROM = {
    "yes":      (WAITING, ASKING, NO_ANSWER, INSIDE),   # inside → out is the guest finally leaving
    "noanswer": (WAITING, ASKING),
    "no":       (WAITING, ASKING, NO_ANSWER),
    "surprise": (WAITING, ASKING, NO_ANSWER, OUT),
}

# ⛔ reasons: code -> oujact checkout state it writes (the cleaner's warning)
REASON_CODES = ("late_ok", "late_ask", "packing", "unaware", "refuse", "other")
LATE_REASONS = ("late_ok", "late_ask")

# ⛔ expected-exit choices: code -> minutes from now (None = typed HH:MM)
EXPECT_CHOICES = (("30m", 30), ("1h", 60), ("2h", 120), ("3h", 180), ("custom", None))

AIRBNB_MAX = 2                 # never more than two Airbnb chat messages per turnover
AIRBNB_SECOND_AT = 3           # …the second one goes out with the third reminder (+90 min)


def tz():
    return ZoneInfo(RIYADH)


def oujact_state_for(answer, reason_code=None):
    """The state written into oujact_checkout.json — what the cleaners' route page reads."""
    if answer == "yes":
        return "guest_confirmed"
    if answer == "noanswer":
        return "no_answer"
    if answer == "surprise":
        return "inside"
    if answer == "no":
        return "late_checkout" if reason_code in LATE_REASONS else "inside"
    return None


# ------------------------------------------------------------------ time helpers

def parse_dt(v):
    if not v:
        return None
    if isinstance(v, datetime.datetime):
        return v if v.tzinfo else v.replace(tzinfo=tz())
    try:
        d = datetime.datetime.fromisoformat(str(v))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=tz())


def iso(d):
    return d.isoformat(timespec="seconds") if d else None


def parse_hhmm(s):
    """'17:00' / '٥:٣٠' → (17, 0). None when it is not a real clock time. Never guesses."""
    if s is None:
        return None
    t = str(s).strip().translate(str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"))
    t = t.replace("٫", ":").replace(".", ":").replace("：", ":")
    parts = t.split(":")
    if len(parts) != 2 or not all(p.strip().isdigit() for p in parts):
        return None
    h, m = int(parts[0]), int(parts[1])
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return h, m


def at_clock(day, hhmm, zone=None):
    """The datetime of clock time 'HH:MM' on `day` (date or 'YYYY-MM-DD')."""
    if isinstance(day, str):
        day = datetime.date.fromisoformat(day[:10])
    h, m = parse_hhmm(hhmm) or (0, 0)
    return datetime.datetime(day.year, day.month, day.day, h, m, tzinfo=zone or tz())


def in_quiet(now, quiet_from="23:00", quiet_to="08:00"):
    """True inside the silent window. The window wraps midnight (23:00 → 08:00)."""
    a = parse_hhmm(quiet_from) or (23, 0)
    b = parse_hhmm(quiet_to) or (8, 0)
    cur = (now.hour, now.minute)
    if a == b:
        return False
    if a < b:
        return a <= cur < b
    return cur >= a or cur < b


def deadline_at(day, deadline="17:00", zone=None):
    return at_clock(day, deadline, zone)


# ------------------------------------------------------------------ the late-exit cap (§5a)

def cap_anchor(checkin_at, deadline):
    """What the apartment must be ready by: the check-in, but never later than 17:00."""
    ci = parse_dt(checkin_at)
    return min(ci, deadline) if ci else deadline


def latest_ok_exit(checkin_at, deadline, clean_minutes):
    """The latest the guest can leave and we still finish cleaning in time."""
    return cap_anchor(checkin_at, deadline) - datetime.timedelta(minutes=int(clean_minutes or 0))


def red_cap(expected_out_at, checkin_at, deadline, clean_minutes):
    exp = parse_dt(expected_out_at)
    if not exp:
        return False
    return exp > latest_ok_exit(checkin_at, deadline, clean_minutes)


def expected_from_choice(choice, now, typed=None):
    """(datetime | None, error_code | None). The typed time must be later than now and today —
    an impossible answer is sent back to the person, never rounded into something plausible."""
    minutes = dict(EXPECT_CHOICES).get(choice, "missing")
    if minutes == "missing":
        return None, "choice"
    if minutes is None:
        hm = parse_hhmm(typed)
        if not hm:
            return None, "format"
        exp = now.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
    else:
        exp = (now + datetime.timedelta(minutes=minutes)).replace(second=0, microsecond=0)
    if exp <= now:
        return None, "past"
    if exp.date() != now.date():
        return None, "tomorrow"
    return exp, None


# ------------------------------------------------------------------ the clock (§5)

def initial_state(checkout_at, now):
    co = parse_dt(checkout_at)
    return WAITING if (co and now < co) else ASKING


def due_action(row, now, quiet_from="23:00", quiet_to="08:00", demo=False):
    """What the tick owes this turnover right now: 'ping' | 'remind' | 'reask' | None.

    ping    once, at checkout time (the first mention of the responsible person)
    remind  every 30 min while nobody has settled it (after «ما رد», or an unanswered ping)
    reask   at the exit time the person promised under ⛔
    Nothing during quiet hours; the demo ignores quiet hours so a video can be recorded at night.
    """
    st = row.get("state")
    if st not in OPEN:
        return None
    if not demo and in_quiet(now, quiet_from, quiet_to):
        return None
    if st in (WAITING, ASKING) and not row.get("pinged_at"):
        co = parse_dt(row.get("checkout_at"))
        return "ping" if (co and now >= co) else None
    if st == INSIDE:
        exp = parse_dt(row.get("expected_out_at"))
        if exp:
            return "reask" if now >= exp else None
    nxt = parse_dt(row.get("next_action_at"))
    if nxt and now >= nxt:
        return "remind"
    return None


def next_due_at(row):
    """When due_action would next fire (ignoring quiet hours) — the demo's ⏩ jumps to it."""
    st = row.get("state")
    if st not in OPEN:
        return None
    if st in (WAITING, ASKING) and not row.get("pinged_at"):
        return parse_dt(row.get("checkout_at"))
    if st == INSIDE and row.get("expected_out_at"):
        return parse_dt(row.get("expected_out_at"))
    return parse_dt(row.get("next_action_at"))


def airbnb_due(row, on_noanswer=False, next_remind_count=None):
    """First send on the first «ما رد», second with the third reminder, never a third."""
    sent = int(row.get("airbnb_sent") or 0)
    if sent >= AIRBNB_MAX:
        return False
    if on_noanswer:
        return sent == 0
    return next_remind_count == AIRBNB_SECOND_AT and sent == 1


# ------------------------------------------------------------------ risk (§8.3)

RED, ORANGE, GREEN, DONE = "red", "orange", "green", "done"
RISK_ORDER = {RED: 0, ORANGE: 1, GREEN: 2, DONE: 3}


def slack_minutes(row, now, deadline):
    """Minutes to spare = (check-in or 17:00) − when the guest is out − cleaning time."""
    anchor = parse_dt(row.get("checkin_at")) or deadline
    st = row.get("state")
    clean = 0 if st in (CLEANED, APPROVED) else int(row.get("clean_minutes") or 0)
    if st in (OUT, CLEANED, APPROVED):
        start = now                                   # already out — the clock is running now
    else:
        exit_at = parse_dt(row.get("expected_out_at")) or parse_dt(row.get("checkout_at")) or now
        start = max(now, exit_at)
    return int((anchor - start).total_seconds() // 60) - clean


def risk(row, now, deadline, surprise_today=False, early_checkin=False):
    """(level, reason_code). ONE reason — the most urgent one — so the next step is obvious."""
    st = row.get("state")
    if st == APPROVED:
        return DONE, "done"
    has_ci = bool(row.get("checkin_at"))
    slack = slack_minutes(row, now, deadline)
    co = parse_dt(row.get("checkout_at"))
    if has_ci and st == INSIDE:
        return RED, "inside_checkin"
    if has_ci and st == NO_ANSWER:
        return RED, "noanswer_checkin"
    if has_ci and slack < 0:
        return RED, "slack_negative"
    if surprise_today:
        return RED, "surprise"
    if now >= deadline:
        return RED, "past_deadline"
    if has_ci and st in (WAITING, ASKING) and co and now >= co:
        return ORANGE, "unconfirmed_checkin"
    if slack < 60:
        return ORANGE, "slack_low"
    if early_checkin:
        return ORANGE, "early_checkin"
    return GREEN, "ok"


# ------------------------------------------------------------------ the report (§8.6)

def _median(xs):
    return int(round(statistics.median(xs))) if xs else None


def person_report(items, events, deadline_for):
    """Per person: turnovers, median minutes checkout→first answer, «ما رد» count, reminders,
    surprises attributed to a ✅ they pressed, % approved before 17:00.

    `deadline_for(day)` → the day's deadline datetime. Pure: rows and events in, dict out."""
    by_key = {}
    for e in events:
        by_key.setdefault(e["work_key"], []).append(e)
    people = {}

    def slot(name):
        return people.setdefault(name or "—", {"name": name or "—", "turnovers": 0,
                                               "answer_minutes": [], "noanswer": 0,
                                               "reminders": 0, "surprises": 0,
                                               "approved_on_time": 0})

    for it in items:
        p = slot(it.get("responsible"))
        p["turnovers"] += 1
        evs = sorted(by_key.get(it["work_key"], []), key=lambda e: e["at"])
        co = parse_dt(it.get("checkout_at"))
        first = next((e for e in evs if e["kind"] in ("yes", "no", "noanswer")), None)
        if first and co:
            p["answer_minutes"].append(max(0, int((parse_dt(first["at"]) - co).total_seconds() // 60)))
        p["noanswer"] += sum(1 for e in evs if e["kind"] == "noanswer")
        p["reminders"] += sum(1 for e in evs if e["kind"] == "remind")
        appr = next((e for e in evs if e["kind"] == "approved"), None)
        if appr and parse_dt(appr["at"]) < deadline_for(it["day"]):
            p["approved_on_time"] += 1
        for e in evs:
            if e["kind"] == "surprise" and e.get("detail"):
                slot(e["detail"])["surprises"] += 1          # detail = who pressed ✅ before it
    out = []
    for p in people.values():
        n = p["turnovers"]
        out.append({"name": p["name"], "turnovers": n,
                    "median_answer_min": _median(p["answer_minutes"]),
                    "noanswer": p["noanswer"], "reminders": p["reminders"],
                    "surprises": p["surprises"],
                    "on_time_pct": (int(round(100.0 * p["approved_on_time"] / n)) if n else None)})
    out.sort(key=lambda r: (-r["turnovers"], r["name"]))
    return out
