"""brain.util — shared time/format helpers. All time is Riyadh-local via HOST.now()."""

from datetime import timedelta
from .host import HOST


def now_dt():
    """Tz-aware 'now' in Riyadh, from the host clock."""
    fn = HOST.now
    if fn is not None:
        return fn()
    # Fallback only used in isolated tests that didn't wire a clock.
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


def now_iso():
    return now_dt().isoformat(timespec="seconds")


def today_iso():
    return now_dt().date().isoformat()


def date_iso(d):
    return d.isoformat() if hasattr(d, "isoformat") else str(d)[:10]


def days_from_now(n):
    return (now_dt().date() + timedelta(days=n)).isoformat()


def first_name_of(name):
    """Take a clean first name (handles Arabic 'أبو فلان' politely by taking the first token)."""
    s = (name or "").strip()
    if not s:
        return ""
    return s.split()[0]


def parse_date(s):
    """'2026-06-13' (or longer ISO) -> date, or None."""
    if not s:
        return None
    try:
        from datetime import datetime
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def clampi(v, lo, hi):
    try:
        v = int(v)
    except (ValueError, TypeError):
        return lo
    return max(lo, min(hi, v))
