# -*- coding: utf-8 -*-
"""
permits.dates — read every date a permit can arrive with, and say it back in words.

PURE: stdlib (+ the optional `hijridate`), no clock, no database.

THE RULE THIS MODULE EXISTS TO PROTECT
--------------------------------------
A wrong expiry date is how a permit gets missed. So nothing here guesses silently:

    parse_date(value) -> {"iso": 'YYYY-MM-DD' | None,
                          "issue": '' | 'ambiguous_day_month' | 'invalid' | 'hijri_unavailable',
                          "calendar": 'gregorian' | 'hijri' | None,
                          "raw": the cleaned text}

* Day-first, always (the way the team and the ministry write dates). When BOTH parts could be
  a month (5/3/2027) we still read it day-first, and we say so: 'ambiguous_day_month'.
* Hijri is Umm al-Qura via `hijridate`. The ministry format is a fixed DD/MM/YYYY, so a Hijri
  date is never flagged ambiguous.
* `hijridate` missing (local Python < 3.10) → 'hijri_unavailable', never a crash (F22).
"""

import datetime
import re

try:                                    # optional: 2.6 on Railway (3.13), 2.5 on a 3.9 laptop
    import hijridate as _HIJRI          # noqa: N812
except Exception:                       # pragma: no cover - environment dependent
    _HIJRI = None

_BIDI = re.compile("[\u200e\u200f\u202a-\u202e\u2069\ufeff]")
# An opening isolate (LRI/RLI/FSI) separates words visually - «F1<FSI>الأستاذ» must stay two words.
_ISOLATE_OPEN = re.compile("[\u2066-\u2068]")
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

MONTHS_AR = ["", "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
             "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
HIJRI_MONTHS_AR = ["", "محرم", "صفر", "ربيع الأول", "ربيع الآخر", "جمادى الأولى",
                   "جمادى الآخرة", "رجب", "شعبان", "رمضان", "شوال", "ذو القعدة", "ذو الحجة"]
WEEKDAYS_AR = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]

_MONTH_WORDS = {
    "يناير": 1, "فبراير": 2, "مارس": 3, "ابريل": 4, "أبريل": 4, "إبريل": 4, "مايو": 5,
    "يونيو": 6, "يوليو": 7, "اغسطس": 8, "أغسطس": 8, "سبتمبر": 9, "اكتوبر": 10,
    "أكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

# Excel's day zero (the 1900 leap-year bug is already folded into 1899-12-30).
_EXCEL_EPOCH = datetime.date(1899, 12, 30)
_EXCEL_MIN, _EXCEL_MAX = 20000, 80000          # 1954 … 2119 — anything else is not a date


def hijri_available():
    return _HIJRI is not None


def clean_text(value):
    """Strip bidi controls, unify digits, trim and collapse spaces."""
    s = _ISOLATE_OPEN.sub(" ", str(value if value is not None else ""))
    s = _BIDI.sub("", s)
    s = s.translate(_DIGITS)
    return " ".join(s.split())


def _out(iso=None, issue="", calendar=None, raw=""):
    return {"iso": iso, "issue": issue, "calendar": calendar, "raw": raw}


def _greg(y, m, d):
    try:
        return datetime.date(int(y), int(m), int(d)).isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def _hijri(y, m, d):
    """(iso, issue) for a Hijri y/m/d."""
    if _HIJRI is None:
        return None, "hijri_unavailable"
    try:
        g = _HIJRI.Hijri(int(y), int(m), int(d)).to_gregorian()
        return datetime.date(g.year, g.month, g.day).isoformat(), ""
    except Exception:
        return None, "invalid"


def _is_hijri_year(y):
    return 1300 <= int(y) <= 1600


def parse_date(value, calendar_hint=None):
    """See the module docstring. `calendar_hint` comes from a header like «(هجري)»."""
    if value is None:
        return _out()
    if isinstance(value, datetime.datetime):
        return _out(value.date().isoformat(), "", "gregorian", value.date().isoformat())
    if isinstance(value, datetime.date):
        return _out(value.isoformat(), "", "gregorian", value.isoformat())
    if isinstance(value, bool):
        return _out(None, "invalid", None, str(value))
    if isinstance(value, (int, float)):
        n = float(value)
        if _EXCEL_MIN <= n <= _EXCEL_MAX:
            d = _EXCEL_EPOCH + datetime.timedelta(days=int(n))
            return _out(d.isoformat(), "", "gregorian", str(value))
        return _out(None, "invalid", None, str(value))

    raw = clean_text(value)
    if not raw:
        return _out()
    s = raw
    hijri_marked = bool(re.search(r"(هـ|ه$|هجري)", s))
    s = re.sub(r"\s*(هـ|هجري|ه|م|ميلادي)\s*$", "", s).strip()

    # an Excel serial typed as text
    if re.fullmatch(r"\d{5}(\.0+)?", s):
        return parse_date(float(s), calendar_hint)

    # year first: 2026-10-11, 1448/03/15, 2026-10-11T09:30
    m = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?:$|[T\s])", s)
    if m:
        y, mo, d = m.group(1), m.group(2), m.group(3)
        if hijri_marked or calendar_hint == "hijri" or _is_hijri_year(y):
            iso, issue = _hijri(y, mo, d)
            return _out(iso, issue, "hijri", raw)
        iso = _greg(y, mo, d)
        return _out(iso, "" if iso else "invalid", "gregorian", raw)

    # day first: 11/10/2026, 07/07/1448, 5-3-2027
    m = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", s)
    if m:
        d, mo, y = m.group(1), m.group(2), m.group(3)
        if hijri_marked or calendar_hint == "hijri" or _is_hijri_year(y):
            iso, issue = _hijri(y, mo, d)
            return _out(iso, issue, "hijri", raw)
        iso = _greg(y, mo, d)
        if not iso:
            return _out(None, "invalid", "gregorian", raw)
        ambiguous = int(d) <= 12 and int(mo) <= 12 and int(d) != int(mo)
        return _out(iso, "ambiguous_day_month" if ambiguous else "", "gregorian", raw)

    # words: 11 أكتوبر 2026 / 11 October 2026
    m = re.fullmatch(r"(\d{1,2})\s+([^\d\s]+)\s+(\d{4})", s)
    if m:
        word = m.group(2).strip().lower().rstrip(".,")
        mo = _MONTH_WORDS.get(word) or _MONTH_WORDS.get(word[:3])
        if mo:
            iso = _greg(m.group(3), mo, m.group(1))
            return _out(iso, "" if iso else "invalid", "gregorian", raw)

    return _out(None, "invalid", None, raw)


# ---------------- saying a date back ----------------

def _d(iso):
    try:
        return datetime.date.fromisoformat(str(iso)[:10])
    except (TypeError, ValueError):
        return None


def ar_digits(n):
    return str(n).translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))


def words_ar(iso):
    """'2026-10-11' -> '١١ أكتوبر ٢٠٢٦' (blank for blank)."""
    d = _d(iso)
    if not d:
        return ""
    return "%s %s %s" % (ar_digits(d.day), MONTHS_AR[d.month], ar_digits(d.year))


def weekday_ar(iso):
    d = _d(iso)
    return WEEKDAYS_AR[d.weekday()] if d else ""


def to_hijri_parts(iso):
    """(year, month, day) in Umm al-Qura, or None."""
    d = _d(iso)
    if not d or _HIJRI is None:
        return None
    try:
        h = _HIJRI.Gregorian(d.year, d.month, d.day).to_hijri()
        return (h.year, h.month, h.day)
    except Exception:
        return None


def to_hijri_str(iso):
    """'2026-10-11' -> '٣٠ ربيع الآخر ١٤٤٨هـ' ('' when unknown or unavailable)."""
    p = to_hijri_parts(iso)
    if not p:
        return ""
    return "%s %s %sهـ" % (ar_digits(p[2]), HIJRI_MONTHS_AR[p[1]], ar_digits(p[0]))
