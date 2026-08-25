# -*- coding: utf-8 -*-
"""promises.engine — PURE decision logic (no I/O, no Discord, no DB).

Every rule the accountability loop and the dashboard rely on lives here so it
can be TDD-locked:
  * due_from_hint      — a free-text due hint → a concrete ISO datetime
  * needs_reping       — is this open promise due for another nudge?
  * is_expired         — 24h past due with nobody pressing ✅ → expired
  * leaderboard        — per-person open/overdue/kept counts (لوحة الوفاء)
"""

import datetime
import re

REPING_INTERVAL_H = 4.0     # re-ping the promiser (and ops lead) every 4h once overdue
EXPIRE_AFTER_H = 24.0       # 24h overdue → expired + red summary
DEFAULT_DUE_H = 4.0         # a promise with no due hint is due in 4h

_HINT_RULES = (
    (re.compile(r"checkout|المغادرة|تسجيل الخروج", re.I), ("checkout", 12.0)),
    (re.compile(r"tonight|الليلة|هالليلة", re.I), ("tonight", 6.0)),
    (re.compile(r"today|اليوم|هاليوم", re.I), ("today", 6.0)),
    (re.compile(r"tomorrow|بكرة|بكره|غداً|غدا", re.I), ("tomorrow", 24.0)),
    (re.compile(r"an? hour|ساعة|ساعه|شوي", re.I), ("hour", 1.0)),
    (re.compile(r"(\d+)\s*(?:hours?|ساعات|ساعة)", re.I), ("n_hours", None)),
    (re.compile(r"(\d+)\s*(?:minutes?|دقايق|دقائق|دقيقة)", re.I), ("n_minutes", None)),
)


def due_from_hint(hint, now):
    """Free-text due hint («today 6pm», «at checkout», «بكرة») → ISO datetime.
    Conservative: unknown/empty hints fall back to now + DEFAULT_DUE_H."""
    h = (hint or "").strip()
    for rx, (kind, hours) in _HINT_RULES:
        m = rx.search(h)
        if not m:
            continue
        if kind == "n_hours":
            hours = max(0.5, float(m.group(1)))
        elif kind == "n_minutes":
            hours = max(0.25, float(m.group(1)) / 60.0)
        return (now + datetime.timedelta(hours=hours)).isoformat(timespec="seconds")
    return (now + datetime.timedelta(hours=DEFAULT_DUE_H)).isoformat(timespec="seconds")


def _parse_dt(s):
    try:
        return datetime.datetime.fromisoformat(str(s)[:19])
    except (TypeError, ValueError):
        return None


def overdue_hours(rec, now):
    """Hours past due (negative = not due yet; None = no parseable due)."""
    due = _parse_dt(rec.get("due_at"))
    if due is None:
        return None
    return (now - due).total_seconds() / 3600.0


def needs_reping(rec, now, interval_h=REPING_INTERVAL_H):
    """An OPEN, overdue promise gets a nudge every `interval_h` hours."""
    if (rec.get("status") or "open") != "open":
        return False
    oh = overdue_hours(rec, now)
    if oh is None or oh < 0:
        return False
    last = _parse_dt(rec.get("last_nudge_at"))
    if last is None:
        return True
    return (now - last).total_seconds() / 3600.0 >= interval_h


def is_expired(rec, now, expire_h=EXPIRE_AFTER_H):
    """OPEN + more than `expire_h` past due → nobody kept it: expired."""
    if (rec.get("status") or "open") != "open":
        return False
    oh = overdue_hours(rec, now)
    return oh is not None and oh >= expire_h


def leaderboard(rows, now=None):
    """Per-person accountability: open / overdue / kept / expired + kept-rate.
    «لوحة الوفاء بالوعد» — sorted best keepers first, unnamed rows under «غير معروف»."""
    now = now or datetime.datetime.now()
    people = {}
    for r in rows or []:
        name = (r.get("promised_by") or "").strip() or "غير معروف"
        p = people.setdefault(name, {"person": name, "open": 0, "overdue": 0,
                                     "kept": 0, "expired": 0, "total": 0})
        p["total"] += 1
        st = r.get("status") or "open"
        if st == "done":
            p["kept"] += 1
        elif st == "expired":
            p["expired"] += 1
        else:
            p["open"] += 1
            oh = overdue_hours(r, now)
            if oh is not None and oh > 0:
                p["overdue"] += 1
    out = list(people.values())
    for p in out:
        closed = p["kept"] + p["expired"]
        p["kept_rate"] = round(100.0 * p["kept"] / closed) if closed else None
    out.sort(key=lambda p: (-(p["kept_rate"] if p["kept_rate"] is not None else -1), p["overdue"]))
    return out
