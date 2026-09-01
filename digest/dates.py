# -*- coding: utf-8 -*-
"""digest.dates — which weekend, in Riyadh, and how to say it in Arabic.

The digest always covers the next Thursday–Saturday. Computed from a tz-aware clock
(HOST.now in production, a frozen datetime in tests) and converted to Asia/Riyadh
BEFORE looking at the weekday — a UTC clock at 21:30 is already Thursday here.
Pure: no host, no I/O."""

from collections import namedtuple
from datetime import timedelta
from zoneinfo import ZoneInfo

RIYADH = ZoneInfo("Asia/Riyadh")

Week = namedtuple("Week", "thu fri sat iso label_ar")

AR_MONTHS = {1: "يناير", 2: "فبراير", 3: "مارس", 4: "أبريل", 5: "مايو", 6: "يونيو",
             7: "يوليو", 8: "أغسطس", 9: "سبتمبر", 10: "أكتوبر", 11: "نوفمبر", 12: "ديسمبر"}
AR_DAY = {"thu": "الخميس", "fri": "الجمعة", "sat": "السبت"}
DAY_KEYS = ("thu", "fri", "sat")

_AR = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


def ar_digits(s):
    """Western → Arabic-Indic digits (prose rule). Leaves everything else alone."""
    return str(s).translate(_AR)


def ar_date(d):
    """date → «٣ سبتمبر»."""
    return "%s %s" % (ar_digits(d.day), AR_MONTHS[d.month])


def ar_time(hour, minute=0):
    """24h → «٩:٠٠م» / «٩:٣٠ص» (12-hour, Arabic-Indic, م/ص suffix, no space)."""
    h12 = hour % 12
    if h12 == 0:
        h12 = 12
    suffix = "م" if hour >= 12 else "ص"
    return "%s:%s%s" % (ar_digits(h12), ar_digits("%02d" % minute), suffix)


def label_ar(span):
    """(thu, sat) or a Week → «٣–٥ سبتمبر» / «٣١ ديسمبر – ٢ يناير»."""
    a, b = span[0], span[2] if len(span) > 2 else span[-1]
    if a.month == b.month:
        return "%s–%s %s" % (ar_digits(a.day), ar_digits(b.day), AR_MONTHS[a.month])
    return "%s %s – %s %s" % (ar_digits(a.day), AR_MONTHS[a.month], ar_digits(b.day), AR_MONTHS[b.month])


def week_for(now):
    """The Week (next Thu–Sat) for a tz-aware `now`. If today is already Thu/Fri/Sat,
    the weekend in progress is the one covered."""
    if now.tzinfo is None:
        raise ValueError("digest.dates.week_for needs a tz-aware datetime")
    d = now.astimezone(RIYADH).date()
    wd = d.weekday()                       # Mon=0 … Thu=3, Fri=4, Sat=5, Sun=6
    if wd in (3, 4, 5):
        thu = d - timedelta(days=wd - 3)
    else:
        thu = d + timedelta(days=(3 - wd) % 7)
    fri, sat = thu + timedelta(days=1), thu + timedelta(days=2)
    return Week(thu, fri, sat, thu.isoformat(), label_ar((thu, fri, sat)))


def day_key(week, d):
    """date → 'thu'|'fri'|'sat' inside the week, else None."""
    for key, day in zip(DAY_KEYS, (week.thu, week.fri, week.sat)):
        if d == day:
            return key
    return None


def in_week(week, d):
    return week.thu <= d <= week.sat
