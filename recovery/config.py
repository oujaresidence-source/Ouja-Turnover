# -*- coding: utf-8 -*-
"""
recovery.config — §14. Every value the owner confirmed, in one place, env-overridable.

WHY THE NAMES MATTER AS MUCH AS THE IDS
The Discord id is how we MENTION an agent. The `name` is how we detect a CONFLICT: it is
matched against the Employee Calendar's permanent apartment owner
(schedule_apartments.owner_id -> schedule_employees.name) through schedule.owners. If a name
here stops matching a name there, conflict detection silently stops working and the person
who owns the problem starts taking their own recovery calls. Nothing crashes — which is
exactly why tests/test_recovery_config.py asserts both names resolve against the calendar.

Confirmed by the owner 2026-08-08:
    OHD       = عهود          1514200235302195211
    Mohammed  = محمد اليامي   894222545274945548
«محمد» is read as «محمد اليامي» because that is the only محمد in the calendar. If a second
one is ever hired, this line becomes ambiguous — set RECOVERY_AGENT_B_NAME explicitly then.

STILL UNCONFIRMED (the feature cannot post to Discord until these are set):
    supervisor_role_id, ops_leadership_role_id, public_base
"""

import os


def _env(key, default=""):
    return (os.environ.get(key) or default).strip()


AGENTS = [
    {"id": _env("RECOVERY_AGENT_A_ID", "1514200235302195211"),
     "name": _env("RECOVERY_AGENT_A_NAME", "عهود"),
     "label": "OHD"},
    {"id": _env("RECOVERY_AGENT_B_ID", "894222545274945548"),
     "name": _env("RECOVERY_AGENT_B_NAME", "محمد اليامي"),
     "label": "Mohammed"},
]

# Roles. Zero means "not configured" — notify.py must degrade to a plain message rather
# than posting a broken <@&0> mention, the way MAINT_URGENT_ROLE_ID already does.
SUPERVISOR_ROLE_ID = int(_env("RECOVERY_SUPERVISOR_ROLE_ID", "0") or 0)
OPS_LEADERSHIP_ROLE_ID = int(_env("RECOVERY_OPS_LEAD_ROLE_ID", "0") or 0)

# §10 — a config value, not a constant, because Ramadan and Eid move the working day.
WINDOW_START = _env("RECOVERY_WINDOW_START", "16:00")
WINDOW_DEADLINE = _env("RECOVERY_WINDOW_DEADLINE", "20:00")
REMINDER_1 = _env("RECOVERY_REMINDER_1", "17:30")
REMINDER_2 = _env("RECOVERY_REMINDER_2", "19:00")
IN_HOUSE_DEADLINE_HOURS = float(_env("RECOVERY_INHOUSE_DEADLINE_HOURS", "3") or 3)

TIMEZONE = _env("RECOVERY_TZ", "Asia/Riyadh")
SCORE_THRESHOLD = float(_env("RECOVERY_SCORE_THRESHOLD", "7.0") or 7.0)
DAILY_TICKET_CAP = int(_env("RECOVERY_DAILY_CAP", "15") or 15)
LOOKBACK_DAYS = int(_env("RECOVERY_LOOKBACK_DAYS", "7") or 7)

EQUITY_GAP_ALERT_THRESHOLD = int(_env("RECOVERY_EQUITY_GAP_ALERT", "4") or 4)
REPEAT_UNIT_WINDOW_DAYS = int(_env("RECOVERY_REPEAT_WINDOW_DAYS", "30") or 30)
REPEAT_UNIT_THRESHOLD = int(_env("RECOVERY_REPEAT_THRESHOLD", "2") or 2)

# Rooms, not threads (owner, 2026-08-06) — matching the decoration module's decision and
# the only ticket-room helper this codebase has.
CATEGORY_NAME = _env("RECOVERY_CATEGORY", "استرداد التجربة")
ALERTS_CHANNEL = _env("RECOVERY_ALERTS_CHANNEL", "تنبيهات-الاسترداد")
LOG_CHANNEL = _env("RECOVERY_LOG_CHANNEL", "سجل-الاسترداد")
REPORT_CHANNEL = _env("RECOVERY_REPORT_CHANNEL", "تقرير-الاسترداد")

# Ships OFF, like ops/ and decor/ did. 1 = compute and log, post nothing.
DRYRUN = _env("RECOVERY_DRYRUN", "1") in ("1", "true", "True", "yes")
ENABLED = _env("RECOVERY_ENABLED", "1") in ("1", "true", "True", "yes")

PUBLIC_BASE = _env("PUBLIC_BASE_URL", "")     # the call link's origin; unset = no button


def agent_ids():
    return [a["id"] for a in AGENTS if a["id"]]


def agent_by_id(agent_id):
    return next((a for a in AGENTS if a["id"] == str(agent_id)), None)


def is_agent(user_id):
    return str(user_id) in agent_ids()


def ready_for_discord():
    """(ok, missing) — what still has to be answered before anything may post.
    Called at wire time so a half-configured feature refuses loudly instead of posting a
    card with a broken mention in it."""
    missing = []
    for a in AGENTS:
        if not a["id"] or not a["id"].isdigit():
            missing.append("agent id for %s" % (a.get("label") or a.get("name")))
        if not a["name"]:
            missing.append("agent name for %s" % (a.get("label") or a.get("id")))
    if not SUPERVISOR_ROLE_ID:
        missing.append("RECOVERY_SUPERVISOR_ROLE_ID")
    if not OPS_LEADERSHIP_ROLE_ID:
        missing.append("RECOVERY_OPS_LEAD_ROLE_ID")
    if not PUBLIC_BASE:
        missing.append("PUBLIC_BASE_URL (the call button needs it)")
    return (not missing), missing
