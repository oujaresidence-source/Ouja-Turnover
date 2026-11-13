# -*- coding: utf-8 -*-
"""
hatif.parse — PURE. One WhatsApp message → what the guest is asking for.

    parse_request(text, today, neighborhoods) ->
        {"ok": True, "check_in": "YYYY-MM-DD", "check_out": "YYYY-MM-DD", "nights": n,
         "assumed_nights": bool, "guests": n|None, "type": "studio|1br|2br|3br"|None,
         "bedrooms": n|None, "neighborhood": key|None}
      | {"ok": False, "reason": "no_dates|past|bad_range|monthly|too_far", ...same extras}

Rules that matter:
    * Saudi order: 20/11 is 20 November. A date without a year that already passed rolls to
      next year; a date WITH a year never rolls (an explicit past date is refused).
    * A bare number is never a date ("3 غرف", "4 أشخاص", "500").
    * One date with no nights ⇒ one night, flagged assumed_nights so the reply says so.
    * A weekday means its next occurrence, today included.
    * More than `max_nights` or the word «شهر» ⇒ reason "monthly" (the monthly team answers).
"""
import datetime
import re

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_DIACRITICS = re.compile("[\u064b-\u0652\u0670\u0640]")

_MONTHS = {
    "يناير": 1, "فبراير": 2, "مارس": 3, "ابريل": 4, "مايو": 5, "يونيو": 6, "يوليو": 7,
    "اغسطس": 8, "سبتمبر": 9, "اكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7,
    "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9,
    "oct": 10, "nov": 11, "dec": 12,
}
_MONTH_RE = "(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + ")"
_SEP = r"(?:الي|لين|حتي|ل|to|until|till|-|–|—)"
_NB = r"(?<![\d/.])"            # not glued to another date fragment
_AL = "\u0621-\u064a"          # Arabic letters only, so punctuation never glues to a word
_WORD_SEP = r"(?:الي|لين|حتي|to|until|till)"
# a number followed by one of these is a count, never a day of the month
_UNITS = (r"(?!\s*(?:اشخاص|شخص|افراد|نفر|غرف|غرفه|ليالي|ليال|ليله|ايام|يوم|ريال|ر\.س|الف|الليل|الصبح|العصر|الظهر"
          r"|people|guests?|persons?|nights?|rooms?|bedrooms?|br\b|sar|pm|am|%))")
_WEEKEND_RE = r"ويكند|الويك اند|نهايه الاسبوع|weekend"

# Monday=0 … Sunday=6
_WEEKDAYS = [
    (6, ("الاحد", "sunday")), (0, ("الاثنين", "الاثنين", "monday")),
    (1, ("الثلاثاء", "الثلوث", "tuesday")), (2, ("الاربعاء", "الربوع", "wednesday")),
    (3, ("الخميس", "thursday")), (4, ("الجمعه", "friday")), (5, ("السبت", "saturday")),
]
_NUM_WORDS = {"ثلاث": 3, "ثلاثه": 3, "اربع": 4, "اربعه": 4, "خمس": 5, "خمسه": 5, "ست": 6,
              "سته": 6, "سبع": 7, "سبعه": 7, "ثمان": 8, "ثمانيه": 8, "تسع": 9, "تسعه": 9,
              "عشر": 10, "عشره": 10}
_NUM_WORD_RE = "(" + "|".join(sorted(_NUM_WORDS, key=len, reverse=True)) + ")"


def normalize(text):
    s = str(text or "").translate(_DIGITS).lower()
    s = _DIACRITICS.sub("", s)
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ي"), ("ة", "ه")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


def _mk(y, m, d):
    try:
        return datetime.date(int(y), int(m), int(d))
    except (TypeError, ValueError):
        return None


def _year(y):
    y = int(y)
    return y + 2000 if y < 100 else y


class _Found(object):
    """A date as written: day, month, and the year only if the guest wrote one."""
    __slots__ = ("pos", "d", "m", "y")

    def __init__(self, pos, d, m, y=None):
        # m None: the guest wrote only a day ("يوم 25", "من 28 الى 30"), meaning the coming one
        self.pos, self.d, self.y = pos, int(d), (_year(y) if y else None)
        self.m = int(m) if m else None


def _explicit_dates(s):
    """Every written date, in reading order. Returns (found, remaining_text)."""
    found = []
    buf = [s]

    def take(pattern, build):
        def repl(mo):
            for f in build(mo):
                found.append(f)
            return " " * (mo.end() - mo.start())
        buf[0] = re.sub(pattern, repl, buf[0])

    # 2026-11-20
    take(r"(\d{4})-(\d{1,2})-(\d{1,2})",
         lambda mo: [_Found(mo.start(), mo.group(3), mo.group(2), mo.group(1))])
    # 20-11-2026
    take(_NB + r"(\d{1,2})-(\d{1,2})-(\d{4})(?!\d)",
         lambda mo: [_Found(mo.start(), mo.group(1), mo.group(2), mo.group(3))])
    # 20-22/11[/2026]
    take(_NB + r"(\d{1,2})\s*[-–—]\s*(\d{1,2})\s*[/.]\s*(\d{1,2})(?:\s*[/.]\s*(\d{4}|\d{2}))?(?!\d)",
         lambda mo: [_Found(mo.start(), mo.group(1), mo.group(3), mo.group(4)),
                     _Found(mo.start() + 1, mo.group(2), mo.group(3), mo.group(4))])
    # من 20 الى 23 نوفمبر
    take(_NB + r"(\d{1,2})\s*" + _SEP + r"\s*(\d{1,2})\s*" + _MONTH_RE + r"(?:\s+(\d{4}))?",
         lambda mo: [_Found(mo.start(), mo.group(1), _MONTHS[mo.group(3)], mo.group(4)),
                     _Found(mo.start() + 1, mo.group(2), _MONTHS[mo.group(3)], mo.group(4))])
    # 20/11[/2026]
    take(_NB + r"(\d{1,2})\s*[/.]\s*(\d{1,2})(?:\s*[/.]\s*(\d{4}|\d{2}))?(?![\d/.])",
         lambda mo: [_Found(mo.start(), mo.group(1), mo.group(2), mo.group(3))])
    # 20 نوفمبر / 5 dec
    take(_NB + r"(\d{1,2})\s*" + _MONTH_RE + r"(?![a-z])(?:\s+(\d{4}))?",
         lambda mo: [_Found(mo.start(), mo.group(1), _MONTHS[mo.group(2)], mo.group(3))])
    # nov 20-23
    take(r"(?<![a-z])" + _MONTH_RE + r"\s+(\d{1,2})\s*" + _SEP + r"\s*(\d{1,2})(?![\d/.])(?:\s*,?\s*(\d{4}))?",
         lambda mo: [_Found(mo.start(), mo.group(2), _MONTHS[mo.group(1)], mo.group(4)),
                     _Found(mo.start() + 1, mo.group(3), _MONTHS[mo.group(1)], mo.group(4))])
    # dec 5
    take(r"(?<![a-z])" + _MONTH_RE + r"\s+(\d{1,2})(?!\d)(?:\s*,?\s*(\d{4}))?",
         lambda mo: [_Found(mo.start(), mo.group(2), _MONTHS[mo.group(1)], mo.group(3))])
    # ---- days written without a month: only after every dated form above was consumed ----
    # من 28 الى 30
    take(_NB + r"(\d{1,2})\s*" + _WORD_SEP + r"\s*(\d{1,2})(?![\d/.-])" + _UNITS,
         lambda mo: [_Found(mo.start(), mo.group(1), None), _Found(mo.start() + 1, mo.group(2), None)])

    # 20-11 (day-month) or 20-22 (two days)
    def _dash(mo):
        a, b = int(mo.group(1)), int(mo.group(2))
        if b <= 12 and a > b:
            return [_Found(mo.start(), a, b)]
        if b > a:
            return [_Found(mo.start(), a, None), _Found(mo.start() + 1, b, None)]
        return []
    take(_NB + r"(\d{1,2})\s*[-–—]\s*(\d{1,2})(?![\d/.-])" + _UNITS, _dash)
    # يوم 25 / تاريخ 25
    take(r"(?:يوم|تاريخ)\s*(\d{1,2})(?![\d/.-])" + _UNITS,
         lambda mo: [_Found(mo.start(), mo.group(1), None)])
    found = [f for f in found if 1 <= f.d <= 31]
    found.sort(key=lambda f: f.pos)
    return found, buf[0]


def _coming_day(day, after, inclusive):
    """The next calendar date whose day-of-month is `day`, on/after (or strictly after) `after`."""
    y, m = after.year, after.month
    for _ in range(14):
        d = _mk(y, m, day)
        if d and (d >= after if inclusive else d > after):
            return d
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return None


def _nights(s):
    """(nights or None, monthly?)"""
    monthly = bool(re.search(r"(?<!\S)(?:ال)?(?:شهر|شهرين|شهري|اشهر|شهور)(?!\S)|\bmonth", s))
    if re.search(r"اسبوعين|two weeks|2 weeks", s):
        return 14, monthly
    if re.search(r"(?<!\S)(?:ال)?اسبوع(?!\S)|\bweek\b|\ba week\b", s):
        return 7, monthly
    if re.search(r"ليلتين|يومين", s):
        return 2, monthly
    mo = re.search(r"(\d{1,3})\s*(?:ليالي|ليال|ليله|ليل|nights?|ايام|يوم|days?)(?![" + _AL + r"a-z])", s)
    if mo:
        return int(mo.group(1)), monthly
    mo = re.search(_NUM_WORD_RE + r"\s*(?:ليالي|ليال|ايام)", s)
    if mo:
        return _NUM_WORDS[mo.group(1)], monthly
    if re.search(r"(?<!\S)(?:ال)?ليله(?!\S)|\b(?:one|a|1)\s+night\b|\btonight\b", s):
        return 1, monthly
    return None, monthly


def _weekdays(s, today):
    hits = []
    for wd, names in _WEEKDAYS:
        for n in names:
            for mo in re.finditer(r"(?<![" + _AL + r"a-z])(و?)" + re.escape(n) + r"(?![" + _AL + r"a-z])", s):
                hits.append((mo.start(), wd, bool(mo.group(1))))
    hits.sort()
    out, base = [], today
    for _pos, wd, joined in hits[:2]:
        delta = (wd - base.weekday()) % 7           # base already moved past the first day
        d = base + datetime.timedelta(days=delta)
        base = d + datetime.timedelta(days=1)
        if out and joined:
            d = d + datetime.timedelta(days=1)      # «الجمعه والسبت» = both nights, out Sunday
        out.append(d)
    return out


def _relative(s, today):
    if re.search(r"بعد\s*(?:بكره|بكرا|باكر|غد|غدا)|day after tomorrow", s):
        return today + datetime.timedelta(days=2)
    if re.search(r"(?<![" + _AL + r"])(?:بكره|بكرا|باكر|غدا|غد)(?![" + _AL + r"])|\btomorrow\b", s):
        return today + datetime.timedelta(days=1)
    if re.search(r"(?<![" + _AL + r"])(?:اليوم|الليله)(?![" + _AL + r"])|\btoday\b|\btonight\b", s):
        return today
    return None


def _guests(s):
    if re.search(r"شخصين|نفرين", s):
        return 2
    mo = re.search(r"(\d{1,2})\s*(?:اشخاص|شخص|افراد|انفار|نفر|ضيوف|ضيف|guests?|people|persons?|adults?|pax)", s)
    return int(mo.group(1)) if mo else None


def _size(s):
    """(site type key or None, bedrooms or None)"""
    if re.search(r"استديو|استوديو|ستوديو|studio", s):
        return "studio", None
    if re.search(r"غرفه\s*و\s*صاله|غرفه واحده|غرفه وحده|\b1\s*br\b|\b(?:1|one)[ -]bedroom", s):
        return "1br", 1
    if re.search(r"غرفتين|غرفتان|\b2\s*br\b|\b(?:2|two)[ -]bedrooms?", s):
        return "2br", 2
    n = None
    mo = re.search(r"(\d)\s*(?:غرف|bedrooms?|br\b)", s)
    if mo:
        n = int(mo.group(1))
    else:
        mo = re.search(_NUM_WORD_RE + r"\s*غرف", s)
        if mo:
            n = _NUM_WORDS[mo.group(1)]
    if n is None:
        return None, None
    if n == 0:
        return "studio", None
    return ({1: "1br", 2: "2br", 3: "3br"}.get(n), n)


def _neighborhood(s, neighborhoods):
    best = None
    for item in (neighborhoods or []):
        try:
            key, ar, en = item[0], item[1], item[2]
        except (IndexError, TypeError):
            continue
        names = set()
        a = normalize(ar)
        if a:
            names.add(a)
            if a.startswith("ال") and len(a) >= 5:
                names.add(a[2:])
        e = str(en or "").lower().strip()
        if e:
            names.add(e)
            if e.startswith("al ") and len(e) >= 6:
                names.add(e[3:])
        for n in names:
            if len(n) >= 3 and n in s and (best is None or len(n) > best[0]):
                best = (len(n), key)
    return best[1] if best else None


def parse_request(text, today, neighborhoods=None, max_nights=30):
    s = normalize(text)
    found, rest = _explicit_dates(s)
    weekend = bool(re.search(_WEEKEND_RE, s))
    if weekend:
        rest = re.sub(_WEEKEND_RE, " ", rest)       # «نهايه الاسبوع» is not «اسبوع» = 7 nights
    nights, monthly = _nights(rest)
    typ, bedrooms = _size(rest)
    extras = {"guests": _guests(rest), "type": typ, "bedrooms": bedrooms,
              "neighborhood": _neighborhood(s, neighborhoods)}

    def no(reason):
        return dict({"ok": False, "reason": reason}, **extras)

    ci = co = None
    explicit_year = False
    if found:
        f = found[0]
        explicit_year = f.y is not None
        if f.m is None:
            ci = _coming_day(f.d, today, True)
        else:
            ci = _mk(f.y or today.year, f.m, f.d)
            if ci is not None and f.y is None and ci < today:
                ci = _mk(today.year + 1, f.m, f.d)
        if ci is None:
            return no("no_dates")
        if len(found) >= 2:
            g = found[1]
            if g.m is None:
                co = _coming_day(g.d, ci, False)
            else:
                co = _mk(g.y or ci.year, g.m, g.d)
                if co is not None and g.y is None and co <= ci:
                    co = _mk(ci.year + 1, g.m, g.d) or co
            if co is None:
                return no("no_dates")
    else:
        if weekend:
            ci = today + datetime.timedelta(days=(3 - today.weekday()) % 7)      # Thursday
            if nights is None:
                nights = 2
        else:
            days = _weekdays(s, today)
            if len(days) >= 2:
                ci, co = days[0], days[1]
            elif days:
                ci = days[0]
            else:
                ci = _relative(s, today)
    if ci is None:
        return no("monthly" if monthly else "no_dates")

    assumed = False
    if co is None:
        if nights is None:
            if monthly:
                return no("monthly")
            nights, assumed = 1, True
        if nights < 1:
            return no("bad_range")
        if nights > max_nights:
            return no("monthly")
        co = ci + datetime.timedelta(days=nights)
    if co <= ci:
        return no("bad_range")
    if ci < today:
        return no("past" if (explicit_year or found) else "no_dates")
    n = (co - ci).days
    if monthly or n > max_nights:
        return no("monthly")
    if (ci - today).days > 365:
        return no("too_far")
    return dict({"ok": True, "check_in": ci.isoformat(), "check_out": co.isoformat(), "nights": n,
                 "assumed_nights": assumed}, **extras)
