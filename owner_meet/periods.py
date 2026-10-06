# -*- coding: utf-8 -*-
"""
owner_meet.periods — PURE: a meeting period -> statement months + the exact date window.

Money always uses whole statement months (the statement is monthly; spec §5.2). The running month
is included as "حتى تاريخه" and flagged `partial`. Operational chapters (tickets, reviews, claims)
use the exact [start, end] window.
"""

import calendar
import datetime

KINDS = ("this_month", "last_month", "quarter", "ytd", "since_last", "custom")


def mkey(d):
    return "%04d-%02d" % (d.year, d.month)


def month_bounds(mk):
    y, m = int(mk[:4]), int(mk[5:7])
    return datetime.date(y, m, 1), datetime.date(y, m, calendar.monthrange(y, m)[1])


def add_months(mk, n):
    y, m = int(mk[:4]), int(mk[5:7]) - 1 + n
    return "%04d-%02d" % (y + m // 12, m % 12 + 1)


def month_keys(first, last):
    out, k = [], first
    while k <= last:
        out.append(k)
        k = add_months(k, 1)
    return out


def days(start, end):
    return (end - start).days + 1


def _as_date(v):
    if isinstance(v, datetime.date):
        return v
    return datetime.date.fromisoformat(str(v)[:10])


def resolve(kind, today, last_end=None, first_mkey=None, last_mkey=None):
    """-> {kind, start, end, months, partial}. `today` is a date (Riyadh).

    this_month : 1st of this month .. today
    last_month : the previous calendar month
    quarter    : the last three COMPLETE months
    ytd        : 1 January .. today
    since_last : the day after the previous meeting's period end .. today
    custom     : first_mkey .. last_mkey, clipped at today
    """
    today = _as_date(today)
    cur = mkey(today)
    if kind == "this_month":
        first = last = cur
    elif kind == "last_month":
        first = last = add_months(cur, -1)
    elif kind == "quarter":
        first, last = add_months(cur, -3), add_months(cur, -1)
    elif kind == "ytd":
        first, last = "%04d-01" % today.year, cur
    elif kind == "since_last":
        if not last_end:
            raise ValueError("لا يوجد اجتماع سابق لهذا المالك")
        start = _as_date(last_end) + datetime.timedelta(days=1)
        if start > today:
            raise ValueError("الاجتماع السابق يغطي حتى اليوم")
        first, last = mkey(start), cur
    elif kind == "custom":
        if not (first_mkey and last_mkey) or first_mkey > last_mkey:
            raise ValueError("اختر شهر البداية والنهاية")
        first, last = first_mkey, min(last_mkey, cur)
    else:
        raise ValueError("نوع فترة غير معروف")
    if first > cur:
        raise ValueError("الفترة في المستقبل")
    start = month_bounds(first)[0]
    if kind == "since_last":
        start = _as_date(last_end) + datetime.timedelta(days=1)
    end = min(month_bounds(last)[1], today)
    months = month_keys(first, last)
    return {"kind": kind, "start": start.isoformat(), "end": end.isoformat(), "months": months,
            "partial": cur if cur in months else None}


def window_days_in_month(mk, start, end):
    """Days of month `mk` that fall inside [start, end] (dates or ISO)."""
    a, b = month_bounds(mk)
    lo, hi = max(a, _as_date(start)), min(b, _as_date(end))
    return max(0, (hi - lo).days + 1)
