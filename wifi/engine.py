# -*- coding: utf-8 -*-
"""
wifi.engine — the date maths for «اشتراكات النت». PURE: stdlib only, no database,
no HTTP, and no clock. The caller always passes `today`. That is what makes every
number here testable, and tests/test_wifi_engine.py locks them.

THE RULE THIS MODULE EXISTS TO PROTECT
--------------------------------------
Trust the label first. Correct it only with evidence.

    label_days     what the package SAYS: 30, 60 or 90. Taken from the form.
    learned_days   the MEDIAN real duration Ouja has actually observed for this exact
                   (provider, source, label_days) combination. None until 3 observations.
    expected_days  learned_days if we have it, else label_days.
    confidence     'learned' when our own data drives it, 'label' when we are still
                   believing a stranger.

So a package sold as 90 days counts down from 90 days. The system never invents a
shorter number out of thin air — it shortens only after Ouja's own data has proven,
three separate times, that this seller short-changes us. `confidence == 'label'` is
the risky state and is surfaced in the UI as «حسب كلام البائع».

PRECEDENCE, which is the heart of it: a typed real date always beats a calculation,
and a calculation never overwrites a fact.
    1. real_end    it actually died          — fact
    2. stated_end  read off the telco app    — near-fact
    3. computed from expected_days           — estimate
"""

import datetime
import os

# ---- policy constants (env read ONCE here, safe defaults; §11 of the build spec) ----


def _int_env(name, default):
    try:
        return int(str(os.environ.get(name, "")).strip() or default)
    except (TypeError, ValueError):
        return default


#: How many real observations we need before our own number overrides the seller's label.
MIN_OBSERVATIONS = max(1, _int_env("WIFI_MIN_OBSERVATIONS", 3))

#: At or below this many days left, a new order for the same unit is a RENEWAL, not a
#: duplicate. The old one is about to die anyway; blocking there is the system being
#: annoying for no reason.
LOCK_GRACE_DAYS = max(0, _int_env("WIFI_LOCK_GRACE_DAYS", 5))

#: The bands every surface colours from. One function, one source — Phase 2 reads it too.
BAND_URGENT_MAX = 3      # 0..3   يقرب جداً
BAND_SOON_MAX = 14       # 4..14  يقرب

VALID_CHECK_KINDS = ("exact_expiry", "died", "days_left", "still_working")


# ---- date helpers ----

def _d(value):
    """A date object from 'YYYY-MM-DD', or None. Blank, malformed and None all mean
    'we do not know' — never a silent 1970 or today()."""
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _iso(d):
    return d.isoformat() if d else None


# ---- the pure functions ----

def real_days(sub, check):
    """The observed real duration one check proves, or None when it proves nothing.

        exact_expiry / died : end_date      - activation_date
        days_left           : (observed_on + days_left) - activation_date
        still_working       : None — it says the package is alive, not when it ends.

    Returns None rather than a number for anything underivable, and rejects a negative
    duration outright: an end before activation is a typo, not a very short package.
    """
    start = _d((sub or {}).get("activation_date"))
    if not start:
        return None
    kind = (check or {}).get("kind")
    end = None
    if kind in ("exact_expiry", "died"):
        end = _d(check.get("end_date"))
    elif kind == "days_left":
        seen = _d(check.get("observed_on"))
        left = check.get("days_left")
        if seen is not None and left is not None:
            try:
                end = seen + datetime.timedelta(days=int(left))
            except (TypeError, ValueError):
                end = None
    if end is None:
        return None
    n = (end - start).days
    return n if n >= 0 else None


def learned_days(observations):
    """The MEDIAN of the real durations we have observed, or None below the minimum.

    Median, not mean — one weird row (a unit switched off for a month, a mistyped
    year) must not move the number. `None` entries are dropped, never counted toward
    the minimum: a 'still working' check is not evidence of a duration.
    """
    vals = sorted(int(v) for v in (observations or []) if v is not None)
    if len(vals) < MIN_OBSERVATIONS:
        return None
    mid = len(vals) // 2
    if len(vals) % 2:
        return vals[mid]
    # Even count: truncate the .5 downward rather than round — we would rather be a day
    # early than a day late on something that dies silently.
    return int((vals[mid - 1] + vals[mid]) / 2)


def expected_days(label_days, learned):
    """(days, confidence). THE OWNER RULE: no learning data means the label stands."""
    if learned is not None:
        return int(learned), "learned"
    try:
        return int(label_days), "label"
    except (TypeError, ValueError):
        return 0, "label"


def expected_end(activation_date, days):
    """activation_date + days, as 'YYYY-MM-DD'. None when we have no activation date —
    a blank date stays blank; we never substitute today and call it an estimate."""
    start = _d(activation_date)
    if not start:
        return None
    try:
        return _iso(start + datetime.timedelta(days=int(days)))
    except (TypeError, ValueError, OverflowError):
        return None


def days_left(end_date, today):
    """Whole days from today to the end. Negative = overdue. None = we do not know."""
    end, now = _d(end_date), _d(today)
    if not end or not now:
        return None
    return (end - now).days


def status_band(left):
    """'dead' | 'urgent' | 'soon' | 'ok' | 'unknown'. The ONE band function — the
    dashboard, the fill page and any future reminder all colour from this."""
    if left is None:
        return "unknown"
    if left < 0:
        return "dead"
    if left <= BAND_URGENT_MAX:
        return "urgent"
    if left <= BAND_SOON_MAX:
        return "soon"
    return "ok"


def effective_end(sub, learned):
    """(end_date, source) where source is 'real' | 'stated' | 'estimate' | 'unknown'.

    Precedence, highest first: a typed real date always beats a calculation.
    """
    sub = sub or {}
    real = _d(sub.get("real_end"))
    if real:
        return _iso(real), "real"
    stated = _d(sub.get("stated_end"))
    if stated:
        return _iso(stated), "stated"
    days, _conf = expected_days(sub.get("label_days"), learned)
    est = expected_end(sub.get("activation_date"), days)
    return (est, "estimate") if est else (None, "unknown")


def learning_key(sub):
    """The key a subscription learns under: (provider, source, label_days).

    Mobily bought from a shop is NOT the same seller as Mobily bought from Mobily, and
    a 30-day pack teaches us nothing about a 90-day one. Normalised so the same shop
    typed with different spacing or case stays one key.
    """
    sub = sub or {}
    provider = str(sub.get("provider") or "").strip().lower()
    kind = str(sub.get("source_kind") or "").strip().lower()
    name = " ".join(str(sub.get("source_name") or "").split()).lower()
    try:
        label = int(sub.get("label_days") or 0)
    except (TypeError, ValueError):
        label = 0
    return (provider, kind, name, label)


def describe(sub, learned, today):
    """Everything a surface needs for ONE subscription, computed once.

    The dashboard row, the fill page and the manager counters all render from this, so
    they cannot drift apart. A dead/replaced/cancelled row reports the 'dead' band no
    matter what the arithmetic would say.
    """
    sub = sub or {}
    days, confidence = expected_days(sub.get("label_days"), learned)
    end, source = effective_end(sub, learned)
    left = days_left(end, today)
    band = status_band(left)
    if str(sub.get("status") or "") in ("dead", "replaced", "cancelled"):
        band = "dead"
    return {
        "expected_days": days,
        "confidence": confidence,
        "end_date": end,
        "end_source": source,
        "days_left": left,
        "band": band,
    }


def lock_decision(existing_desc, override_reason):
    """Should a new order for this unit be allowed? PURE, so the rule is testable
    without HTTP.

    Returns (allowed, kind) where kind is:
        'free'      no active subscription — a plain insert
        'renewal'   one exists but is at/under the grace window, or we do not know its
                    date. About to die anyway (or undated) — never block on that.
        'override'  one exists with real life left, and a written reason was given.
        'blocked'   one exists with real life left and no reason. HTTP 409.

    A blank or whitespace-only reason is not a reason.
    """
    if not existing_desc:
        return True, "free"
    left = existing_desc.get("days_left")
    if left is None or left <= LOCK_GRACE_DAYS:
        return True, "renewal"
    if str(override_reason or "").strip():
        return True, "override"
    return False, "blocked"
