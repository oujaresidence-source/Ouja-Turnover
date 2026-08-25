# -*- coding: utf-8 -*-
"""
ops.engine — «نظام الالتزام» PURE rules. No Discord, no database, no network, no ambient
clock: every function takes what it needs and gives back a value, so the whole accusation
model is testable with nothing running.

THE PRINCIPLE THIS FILE ENCODES
    The system accuses. Humans only forgive.
There is no function here that lets a person issue a warning. `deadline_decision` is the
ONLY producer of a 'missed' verdict, and every other verdict it can return is a form of
mercy (done, leave, excuse, free pass, unreachable).

THE LADDER CLOCK
    due  = Monday 23:59 Riyadh
    L1   = due - 30h  -> Sunday 17:59
    L2   = due - 14h  -> Monday 09:59
    L3   = due -  8h  -> Monday 15:59
    L4   = due -  4h  -> Monday 19:59
The spec names these 18:00 / 10:00 / 16:00 / 20:00, and that is exactly what the team sees:
the tick runs every 5 minutes and fires a step at the first tick at-or-after its time, so a
17:59 step is delivered at 18:00. The offsets stay the definition because they survive any
change to the due hour; the round clock times are the consequence.
"""

import datetime

TZ_NAME = "Asia/Riyadh"

# level -> hours BEFORE the deadline. Order matters: escalating.
LADDER = (("L1", 30), ("L2", 14), ("L3", 8), ("L4", 4))
LADDER_LEVELS = tuple(l for l, _ in LADDER) + ("issue",)

# active warnings -> what fraction of commission survives.
MULTIPLIER_TABLE = {0: 1.0, 1: 0.9, 2: 0.75}
MULTIPLIER_FLOOR = 0.0            # 3 or more

RETIREMENT_WEEKS = 4              # consecutive clean weeks that retire the OLDEST warning

APPEAL_STAGES = ("s1", "s2", "s3")        # أصيل -> ريم -> فيصل (final)
APPEAL_FINAL = "s3"


# ----------------------------------------------------------------- time helpers

def tz():
    """The Riyadh zone. tzdata is a declared dependency; a bare UTC+3 offset is the
    fallback so a broken tz database can never stop the ladder (Riyadh has no DST, so
    the fallback is exact, not an approximation)."""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(TZ_NAME)
    except Exception:
        return datetime.timezone(datetime.timedelta(hours=3), TZ_NAME)


def as_date(d):
    """date | datetime | 'YYYY-MM-DD...' -> date."""
    if isinstance(d, str):
        return datetime.date.fromisoformat(d[:10])
    if isinstance(d, datetime.datetime):
        return d.date()
    return d


def iso_week_key(d):
    """date/datetime/ISO-string -> '2026-W30' (ISO week, zero-padded)."""
    y, w, _ = as_date(d).isocalendar()
    return "%04d-W%02d" % (y, w)


def parse_week_key(iso_week):
    """'2026-W30' -> (2026, 30). Raises ValueError on anything else — a malformed period
    key must never silently become week 1 of year 0."""
    s = (iso_week or "").strip().upper()
    if len(s) != 8 or s[4] != "-" or s[5] != "W":
        raise ValueError("bad iso week key: %r" % (iso_week,))
    return int(s[:4]), int(s[6:])


def week_monday(iso_week):
    """'2026-W30' -> the date of that ISO week's Monday."""
    y, w = parse_week_key(iso_week)
    return datetime.date.fromisocalendar(y, w, 1)


def due_at_for_week(iso_week, hour=23, minute=59, tz_name=TZ_NAME):
    """'2026-W30' -> Monday 23:59 Riyadh, timezone-aware.

    hour/minute exist so OPS_WEEKLY_DUE_HOUR can move the deadline without touching code;
    the default IS the spec. tz_name is accepted for symmetry with the spec signature."""
    mon = week_monday(iso_week)
    zone = tz() if tz_name == TZ_NAME else _zone(tz_name)
    return datetime.datetime(mon.year, mon.month, mon.day, hour, minute, tzinfo=zone)


def _zone(name):
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:
        return tz()


def quarter_key(d):
    """date/datetime/ISO-string -> '2026-Q3'."""
    dt = as_date(d)
    return "%04d-Q%d" % (dt.year, (dt.month - 1) // 3 + 1)


def month_key(d):
    """date/datetime/ISO-string -> '2026-07'."""
    dt = as_date(d)
    return "%04d-%02d" % (dt.year, dt.month)


# ----------------------------------------------------------------- the ladder

def ladder_steps(due_at):
    """The full escalation timetable for one deadline.

    Returns [{level, at, hours_before}] in order, ending with the 'issue' step AT the
    deadline itself. Pure: no clock is read, so a test can place `now` anywhere."""
    out = []
    for level, hours in LADDER:
        out.append({"level": level, "at": due_at - datetime.timedelta(hours=hours),
                    "hours_before": hours})
    out.append({"level": "issue", "at": due_at, "hours_before": 0})
    return out


def due_step(due_at, now, sent_levels=()):
    """The single step that should fire RIGHT NOW, or None.

    Returns the LATEST step whose time has arrived and that has not been sent yet, so a
    bot that was asleep through L1 and L2 wakes up and sends only L3 — it never machine-guns
    the backlog at somebody's phone.
    """
    sent = set(sent_levels or ())
    pending = [s for s in ladder_steps(due_at) if s["at"] <= now and s["level"] not in sent]
    return pending[-1] if pending else None


# ----------------------------------------------------------------- money

def compute_multiplier(active_warning_count):
    """Active warnings -> the fraction of commission that survives.
    0 -> 1.0 | 1 -> 0.9 | 2 -> 0.75 | 3+ -> 0.0
    Voided and retired warnings are not active, so they are not counted — see active_count."""
    n = max(0, int(active_warning_count or 0))
    return MULTIPLIER_TABLE.get(n, MULTIPLIER_FLOOR)


def active_count(warnings):
    """How many of these warnings still bite. status 'voided' (won an appeal) and 'retired'
    (earned back with 4 clean weeks) are history, not debt."""
    return sum(1 for w in (warnings or []) if (w.get("status") or "") == "active")


# ----------------------------------------------------------------- forgiveness

def retirement_check(employee, weeks, needed=RETIREMENT_WEEKS):
    """4 consecutive clean weeks retire the OLDEST active warning.

    Args:
      employee: name (carried through to the result so a caller looping over people can
                keep the answers straight)
      weeks:    [{period_key, clean}] oldest -> newest. 'clean' means the obligation for
                that week was met (done/waived/excused all count as clean — being on
                approved leave must not cost somebody their streak).
      needed:   consecutive clean weeks required.

    Returns {employee, streak, retire, through}. It does NOT retire anything: it reports.
    The database layer picks the oldest active warning and marks it retired."""
    streak, through = 0, None
    for w in (weeks or []):
        if w.get("clean"):
            streak += 1
            through = w.get("period_key")
        else:
            streak, through = 0, None
    return {"employee": employee, "streak": streak,
            "retire": streak >= needed, "through": through}


def free_pass_decision(used_this_quarter, prior_misses_this_quarter):
    """One free pass per employee per quarter, spent AUTOMATICALLY on a FIRST miss.

    prior_misses counts real misses only (obligations that produced a warning). A week
    covered by leave or an excuse is not a miss, so it never uses up somebody's first-miss
    mercy."""
    return (not used_this_quarter) and int(prior_misses_this_quarter or 0) == 0


# ----------------------------------------------------------------- THE verdict

# Every verdict except 'missed' is a form of mercy. 'missed' is the only one that costs money.
VERDICTS = ("done", "waived", "excused", "free_pass", "unreachable", "missed")


def deadline_decision(done=False, on_leave=False, excused=False,
                      free_pass_available=False, prior_misses=0, reachable=True):
    """What happens to ONE obligation at its deadline. The only place a miss is decided.

    Order is deliberate:
      1. done          — they filed it.
      2. waived        — approved leave. Silent, zero messages, and it does NOT burn the
                         quarterly free pass (checked before free_pass on purpose).
      3. excused       — a leader pressed «عذر مسبق» before the deadline.
      4. free_pass     — first miss of the quarter, forgiven automatically.
      5. unreachable   — we never actually got a message to this person. NOT their fault.
                         Warning a person the system could not reach is the fastest way to
                         make the whole thing illegitimate, so it is refused structurally.
      6. missed        — a warning is issued.

    Returns (verdict, reason_ar)."""
    if done:
        return "done", "تم تسليم التقرير"
    if on_leave:
        return "waived", "إجازة معتمدة"
    if excused:
        return "excused", "عذر مسبق من المسؤول"
    if free_pass_decision(not free_pass_available, prior_misses):
        return "free_pass", "استخدمنا لك السماح الفصلي — ما انسجل إنذار"
    if not reachable:
        return "unreachable", "ما وصلتنا طريقة للتواصل — ما ينسجل إنذار"
    return "missed", "ما تم تسليم التقرير الأسبوعي قبل الموعد"


# ----------------------------------------------------------------- appeals

def next_stage(stage):
    """s1 -> s2 -> s3 -> closed. An appeal never stalls: the 24h timer moves it on its own."""
    try:
        i = APPEAL_STAGES.index(stage)
    except ValueError:
        return "closed"
    return APPEAL_STAGES[i + 1] if i + 1 < len(APPEAL_STAGES) else "closed"


def appeal_due_at(opened_or_moved_at, sla_hours=24):
    return opened_or_moved_at + datetime.timedelta(hours=int(sla_hours or 24))


def appeal_overdue(stage_due_at, now):
    return stage_due_at is not None and now >= stage_due_at


def can_reject(reason):
    """A rejection with no written reason is refused. Silence from an approver reads to the
    employee exactly like contempt, which damages trust more than the original warning."""
    return bool((reason or "").strip())


# ================================================================== PHASE 2: «القفل»
# ONE question, asked once, after the moment the apartment should already have been done.
#
# This replaced a five-level ladder (T-3h, T-1h, T-0 repeating every 10 minutes, T+20 to the
# lead, T+40 to the ops room). The owner's read was that nudging somebody BEFORE the deadline
# is nagging, not help: the team closes turnovers in 1-3 hours as a matter of course, and the
# only moment worth a message is when that did not happen. Everything before it was noise.
#
# TRIGGER
#   check-in today  ->  the moment check-in passes
#   no check-in     ->  DAILY_CHECK_HOUR (16:00 Riyadh)
# The second case exists because turnovers with no arriving guest were getting NO reminder at
# all: the old shared-room loop is superseded, and a check-in-anchored trigger has nothing to
# anchor to. Same question, different clock.

DAILY_CHECK_HOUR_DEFAULT = 16

QUIET_START_DEFAULT = 0      # 00:00 Riyadh
QUIET_END_DEFAULT = 6        # 06:00 Riyadh
SLEEP_STRIKES = 2            # consecutive unanswered asks in the quiet window

# «لا» must come with a reason. These are the quick options; free text is always allowed.
REASONS = (
    ("team_missing", "الفريق ما وصل"),
    ("not_vacant", "الشقة ما كانت فاضية"),
    ("unit_problem", "فيه مشكلة في الشقة"),
    ("no_supplies", "نقص أدوات"),
    ("other", "سبب ثاني"),
)
REASON_AR = dict(REASONS)


def check_due_at(checkin_at, day, daily_hour=DAILY_CHECK_HOUR_DEFAULT, tzinfo=None):
    """When to ask about this turnover.

    The guest's arrival when there is one; otherwise a fixed hour, so an apartment with no
    arriving guest is not silently skipped."""
    if checkin_at is not None:
        return checkin_at
    z = tzinfo or tz()
    d = as_date(day)
    return datetime.datetime(d.year, d.month, d.day, int(daily_hour), 0, tzinfo=z)


def should_ask(checkin_at, day, now, daily_hour=DAILY_CHECK_HOUR_DEFAULT, already_asked=False):
    """One message, once, and only after the moment has passed. Never before."""
    if already_asked:
        return False
    return now >= check_due_at(checkin_at, day, daily_hour, getattr(now, "tzinfo", None))


def in_quiet_window(now, start=QUIET_START_DEFAULT, end=QUIET_END_DEFAULT):
    """Riyadh night hours. Handles a window that wraps past midnight."""
    h = now.hour
    if start == end:
        return False
    return (start <= h < end) if start < end else (h >= start or h < end)


def sleep_reassign(unacked_in_quiet, in_quiet, strikes=SLEEP_STRIKES):
    """Two unanswered asks in the small hours mean the person is ASLEEP.

    Being asleep at 3 AM is not misconduct. The unit is handed to the on-call backup and
    NOBODY IS WARNED — repeated occurrences are a staffing signal for the owner, not a
    disciplinary one."""
    return bool(in_quiet) and int(unacked_in_quiet or 0) >= strikes


def can_ack(has_photos):
    """«✅ نعم» is refused until cleaning photos exist for that unit and date.

    A yes with no photos closes the loop on a lie, which is worse than silence: it tells
    everyone the apartment is ready when nobody has evidence of it."""
    return bool(has_photos)


def valid_reason(reason_code, reason_text=""):
    """«❌ لا» without a reason is not accepted — the reason IS the feature. The owner has no
    data today on WHY apartments go unclean, and a bare «no» would keep it that way."""
    code = (reason_code or "").strip()
    if code not in REASON_AR:
        return False
    if code == "other":
        return bool((reason_text or "").strip())
    return True


def minutes_to(when, now):
    """Signed minutes until `when` (negative once it has passed)."""
    return int(round((when - now).total_seconds() / 60.0))


# ================================================================== RESPONSE CLOCK
# The work window is ONE definition and it is bot.py's: WORK_START_HOUR=11,
# WORK_END_HOUR=25, WORK_END_MIN=30 — i.e. 11:00 → 01:30 the next morning. Those constants
# are passed in by the caller (wired from bot.py) rather than re-declared here, because a
# second copy of a business rule is a second thing to forget to change.
#
# One "work day" D is the span [D 11:00, D+1 01:30]. Consecutive spans do NOT overlap: the
# dead zone from 01:30 to 11:00 is when nobody is expected to be awake, so it costs nobody
# anything. A guest message at 02:00 does not start its clock until 11:00.

WORK_START_DEFAULT = 11
WORK_END_HOUR_DEFAULT = 25        # 25:30 == 01:30 the following day
WORK_END_MIN_DEFAULT = 30


def work_span(day, work_start=WORK_START_DEFAULT, work_end_hour=WORK_END_HOUR_DEFAULT,
              work_end_min=WORK_END_MIN_DEFAULT, tzinfo=None):
    """The one working span that OPENS on `day`, as (start, end) aware datetimes."""
    z = tzinfo or tz()
    start = datetime.datetime(day.year, day.month, day.day, work_start, 0, tzinfo=z)
    minutes = (work_end_hour * 60 + work_end_min) - work_start * 60
    return start, start + datetime.timedelta(minutes=minutes)


def worked_minutes(start, end, work_start=WORK_START_DEFAULT,
                   work_end_hour=WORK_END_HOUR_DEFAULT, work_end_min=WORK_END_MIN_DEFAULT,
                   tzinfo=None):
    """Minutes between two moments that fall INSIDE working hours. Pure.

    This is the number the response line is scored on, and the reason is fairness: a guest
    message that lands at 02:00 and is answered at 11:15 took nine hours by the clock and
    fifteen minutes by any measure a human would accept. Scoring wall-clock time would
    punish people for the hours we tell them not to work.

    Accepts aware datetimes or ISO strings. Returns 0.0 when end <= start."""
    s, e = _as_dt(start, tzinfo), _as_dt(end, tzinfo)
    if s is None or e is None or e <= s:
        return 0.0
    total = 0.0
    # start one day early: the span opening on the previous day can still be running
    day = s.date() - datetime.timedelta(days=1)
    last = e.date()
    while day <= last:
        ws, we = work_span(day, work_start, work_end_hour, work_end_min, s.tzinfo)
        lo, hi = max(s, ws), min(e, we)
        if hi > lo:
            total += (hi - lo).total_seconds() / 60.0
        day += datetime.timedelta(days=1)
    return round(total, 2)


def _as_dt(v, tzinfo=None):
    if v is None or v == "":
        return None
    if isinstance(v, datetime.datetime):
        return v if v.tzinfo else v.replace(tzinfo=tzinfo or tz())
    try:
        d = datetime.datetime.fromisoformat(str(v).replace("T", " ").strip()[:19])
        return d if d.tzinfo else d.replace(tzinfo=tzinfo or tz())
    except Exception:
        return None


def response_pairs(msgs, is_inbound, msg_time, is_automated=None):
    """One event per RUN of consecutive guest messages, paired with the first real reply.

    Keying on the run's FIRST message, not on every message, is deliberate: if a guest sends
    three messages in a row and we answer once, that is ONE person waiting once — counting it
    three times would make a chatty guest look like three failures by whoever owns that unit.

    An automated welcome does not close a run: it answers nobody, so the guest is still
    waiting and the clock keeps running.

    A run with no reply yet is still returned, with responded_at None — it belongs in the
    denominator, or a team could score 100% by answering nothing.

    Pure: the three callables are passed in so this never imports bot.py."""
    out, pending = [], None
    for m in msgs or []:
        if is_inbound(m):
            if pending is None:
                pending = m
            continue
        if is_automated and is_automated(m):
            continue
        if pending is not None:
            out.append({"incoming": pending, "incoming_at": msg_time(pending),
                        "outgoing": m, "responded_at": msg_time(m)})
            pending = None
    if pending is not None:
        out.append({"incoming": pending, "incoming_at": msg_time(pending),
                    "outgoing": None, "responded_at": None})
    return out


def answered_in_target(minutes_worked, target_minutes):
    """Did this one message get its first reply inside the target, in WORKING minutes?
    An unanswered message (None) is never 'answered'."""
    if minutes_worked is None:
        return False
    return float(minutes_worked) <= float(target_minutes)


# ----------------------------------------------------------------- public summary

def public_summary_counts(reports_done, reports_total, warnings_issued, warnings_voided,
                          multipliers):
    """The ONLY public output: counts, never names. Returns plain numbers; the Arabic
    sentence is built in ops.notify. There is deliberately no employee field anywhere in
    this return value and no flag that could add one."""
    ms = [float(m) for m in (multipliers or [])]
    avg = round(100.0 * sum(ms) / len(ms)) if ms else 100
    return {"done": int(reports_done), "total": int(reports_total),
            "warnings": int(warnings_issued), "voided": int(warnings_voided),
            "avg_commission_pct": int(avg)}
