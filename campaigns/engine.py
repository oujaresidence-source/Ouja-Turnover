# -*- coding: utf-8 -*-
"""
campaigns.engine — PURE. No network, no database, no Discord, no clock of its own.

    normalize(text)                 Arabic folding used by every matcher here
    match_codeword(text, words)     → {"code", "title", "phrase", ...} or None
    second_night_offer(...)         → the B1 Special Offer price (night 1 full, night 2 at
                                      50 %, never below the floor) + every eligibility check
    button_kind(label)              → "owner_call" | "show_units" | ... | None
    templates_for(label)            → the templates that carry this button label
    is_stop_message(text)           → a typed «ايقاف» / «stop» (whole message only)
    phone_key(phone, salt)          → the only form a phone number is ever stored in
    week_window(now)                → the 7 days a Sunday report covers
    report_text(stats)              → the Discord weekly report
"""
import datetime
import hashlib
import hmac
import re
import unicodedata

from hatif import engine as _hatif_engine

from . import config

_TASHKEEL = re.compile("[ؐ-ًؚ-ٰٟۖ-ۭـ]")
_SPACES = re.compile(r"\s+")
_PUNCT = re.compile(r"[،؛؟?!.,:;\"'()\[\]{}«»‏‎\-_/]+")
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

WEEKDAY_AR = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
WEEKEND_NIGHTS = (3, 4)          # Thursday and Friday nights — the Saudi weekend


def normalize(text):
    """Fold Arabic spelling variants so «عرض النصّ» == «عرض النص» and «إيقاف» == «ايقاف»."""
    s = unicodedata.normalize("NFKC", str(text or ""))
    s = _TASHKEEL.sub("", s)
    s = (s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ٱ", "ا")
          .replace("ة", "ه").replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي"))
    s = s.translate(_AR_DIGITS).lower()
    return _SPACES.sub(" ", s).strip()


def _label_key(text):
    """Button labels: normalised, punctuation dropped («إيه، كلموني» == «ايه كلموني»)."""
    return _SPACES.sub(" ", _PUNCT.sub(" ", normalize(text))).strip()


def _phrase_regex(phrase, not_before):
    words = [re.escape(w) for w in normalize(phrase).split(" ") if w]
    body = r"\s*".join(words)
    guard = ""
    if not_before:
        alts = "|".join(re.escape(normalize(w)) for w in not_before if w)
        guard = r"(?!\s*(?:%s)(?!\w))" % alts
    # optional و / ب / ف glued in front («وعرض نص»), whole words only
    return re.compile(r"(?<!\w)[وبف]?%s(?!\w)%s" % (body, guard))


def match_codeword(text, words=None):
    """The first campaign whose code word is in the message, or None."""
    words = config.CODEWORDS if words is None else words
    s = normalize(text)
    if not s:
        return None
    for code, spec in words.items():
        for phrase in spec.get("phrases") or []:
            if _phrase_regex(phrase, spec.get("not_before") or []).search(s):
                out = dict(spec)
                out.update({"code": code, "phrase": phrase})
                return out
    return None


# ---------------------------------------------------------------- the B1 price
def _d(v):
    if isinstance(v, datetime.datetime):
        return v.date()
    if isinstance(v, datetime.date):
        return v
    try:
        return datetime.date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def half_up(x):
    return int(float(x) + 0.5)


def second_night_offer(arrival, departure, days, floor=0, discount_pct=50,
                       nights=(6, 0, 1, 2), fallback_price=None):
    """The B1 Special Offer for one stay request.

    arrival / departure: what the guest asked for (night 1 = arrival).
    days: Hostaway calendar rows {date, isAvailable, price, ...} covering night 1 and night 2.
    floor: the unit's minimum (SAR). Night 2 is never priced under it.
    fallback_price: night-1 price when the calendar has none (e.g. the booking's own rate).

    Returns {eligible, reasons[], night1, night2, night1_price, night2_price, night2_full,
             floored, total, nights_requested, night1_weekday, night2_weekday,
             night2_weekend, night2_free, offer_checkin, offer_checkout}.
    `eligible` is False with a reason instead of guessing; the price is still computed when
    the numbers exist, so a supervisor can decide.
    """
    a, dep = _d(arrival), _d(departure)
    reasons = []
    out = {"eligible": False, "reasons": reasons, "night1": None, "night2": None,
           "night1_price": None, "night2_price": None, "night2_full": None, "floored": False,
           "total": None, "nights_requested": None, "night1_weekday": None,
           "night2_weekday": None, "night2_weekend": False, "night2_free": None,
           "offer_checkin": None, "offer_checkout": None, "floor": int(floor or 0)}
    if a is None:
        reasons.append("ما عرفنا تاريخ الدخول")
        return out
    n2 = a + datetime.timedelta(days=1)
    out.update({"night1": a.isoformat(), "night2": n2.isoformat(),
                "offer_checkin": a.isoformat(),
                "offer_checkout": (a + datetime.timedelta(days=2)).isoformat(),
                "night1_weekday": WEEKDAY_AR[a.weekday()], "night2_weekday": WEEKDAY_AR[n2.weekday()],
                "night2_weekend": n2.weekday() in WEEKEND_NIGHTS})
    if dep is not None:
        out["nights_requested"] = max(0, (dep - a).days)
    if a.weekday() not in tuple(nights):
        reasons.append("الليلة الأولى %s — العرض للأحد إلى الأربعاء بس" % WEEKDAY_AR[a.weekday()])
    if out["nights_requested"] is not None and out["nights_requested"] > 2:
        reasons.append("طلب %d ليالي — العرض لليلتين" % out["nights_requested"])

    by_date = {}
    for row in days or []:
        d = _d((row or {}).get("date"))
        if d is not None:
            by_date[d] = row
    r1, r2 = by_date.get(a) or {}, by_date.get(n2) or {}
    p1 = _num(r1.get("price")) or _num(fallback_price)
    p2_full = _num(r2.get("price")) or p1

    # night 2 must be empty (or already part of this same request)
    if not r2:
        out["night2_free"] = None
        reasons.append("ما قدرنا نقرأ تقويم الليلة الثانية")
    else:
        free = bool(int(r2.get("isAvailable") or 0)) and not r2.get("reservationId")
        out["night2_free"] = free
        if not free:
            reasons.append("الليلة الثانية (%s) مو فاضية" % WEEKDAY_AR[n2.weekday()])
    if p1 is None:
        reasons.append("ما فيه سعر لليلة الأولى بالتقويم")
        return out

    pct = max(0, min(100, int(discount_pct)))
    floor = int(floor or 0)
    n1_price = half_up(p1)
    raw2 = p2_full * (100 - pct) / 100.0
    n2_price = half_up(raw2)
    if floor and n2_price < floor:
        n2_price = floor
        out["floored"] = True
    out.update({"night1_price": n1_price, "night2_full": half_up(p2_full),
                "night2_price": n2_price, "total": n1_price + n2_price})
    out["eligible"] = not reasons
    return out


# ---------------------------------------------------------------- Hatif buttons
def _button_index():
    return {_label_key(k): v for k, v in config.BUTTONS.items()}


def button_kind(label):
    return _button_index().get(_label_key(label))


def templates_for(label):
    key = _label_key(label)
    return sorted(t for t, labels in config.TEMPLATES.items()
                  if any(_label_key(x) == key for x in labels))


def resolve_template(label, hinted=None):
    """The template a tap came from: Hatif's own hint when it names a known template, else the
    only template that carries the label, else None (the label is shared)."""
    if hinted and str(hinted) in config.TEMPLATES:
        return str(hinted)
    cands = templates_for(label)
    if len(cands) == 1:
        return cands[0]
    # the photo version («…_img») is the same campaign as its text twin: report it as one
    bases = {c[:-4] if c.endswith("_img") else c for c in cands}
    return bases.pop() if len(bases) == 1 else None


def is_stop_message(text):
    key = _label_key(text)
    return bool(key) and key in {_label_key(w) for w in config.STOP_WORDS}


# ---------------------------------------------------------------- privacy
def normalize_phone(raw):
    """The SAME normalisation the Hatif package uses (9665XXXXXXXX), so keys always agree."""
    return _hatif_engine.normalize_phone(raw) or ""


def phone_key(phone, salt):
    """HMAC of the normalised number with a per-install salt. The number itself is never
    stored; the same number always gives the same key, so opt-outs and booking matches work."""
    n = normalize_phone(phone)
    if not n or not salt:
        return ""
    return hmac.new(str(salt).encode("utf-8"), n.encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def last4(phone):
    n = normalize_phone(phone)
    return n[-4:] if n else ""


def name_key(name):
    """Guest name folded for a loose match (first + last token)."""
    toks = [t for t in _label_key(name).split(" ") if t and t not in ("guest", "ضيف")]
    if not toks:
        return ""
    return toks[0] if len(toks) == 1 else toks[0] + " " + toks[-1]


# ---------------------------------------------------------------- weekly report
def week_window(now):
    """[start, end) — the 7 days that end at this report's run (Sunday 09:00)."""
    end = now.replace(minute=0, second=0, microsecond=0)
    return end - datetime.timedelta(days=7), end


def should_fire(now, last_key, day=6, hour=9):
    """True once per week, from `hour` on `day` (Riyadh). `last_key` is the persisted latch."""
    if now.weekday() != day or now.hour < hour:
        return False
    return str(last_key or "") != now.date().isoformat()


_KIND_AR = {"owner_call": "إيه، كلموني", "owner_later": "مو الحين", "show_units": "وريني الشقق",
            "elite_info": "وش إيليت؟", "show_packages": "وريني الباقات", "opt_out": "إيقاف العروض"}


def report_text(stats):
    """stats = {start, end, hits:{code:{title,n,booked}}, taps:{template:{kind:n}},
    taps_booked, taps_total, optouts, unknown_taps}."""
    s, e = stats["start"], stats["end"]
    lines = ["📊 **تقرير حملات عوجا** — من %s إلى %s" % (s.strftime("%d/%m"), e.strftime("%d/%m")), ""]
    hits = stats.get("hits") or {}
    lines.append("**كلمات السر (Airbnb):**")
    if not hits:
        lines.append("• ما وصلنا أي كلمة سر هالأسبوع")
    for code, h in sorted(hits.items()):
        lines.append("• %s «%s»: %d رسالة — انحجز منها %d" % (code, h.get("title") or "", h["n"],
                                                             h.get("booked", 0)))
    lines.append("")
    lines.append("**ضغطات أزرار الواتساب:**")
    taps = stats.get("taps") or {}
    if not taps:
        lines.append("• ما فيه ضغطات هالأسبوع")
    for tpl, kinds in sorted(taps.items()):
        bits = " · ".join("%s %d" % (_KIND_AR.get(k, k), n) for k, n in sorted(kinds.items()))
        lines.append("• %s: %s" % (tpl if tpl != "?" else "قالب غير محدد", bits))
    lines.append("")
    lines.append("• انحجز بعد ضغطة زر: %d من %d" % (stats.get("taps_booked", 0), stats.get("taps_total", 0)))
    lines.append("• طلبوا إيقاف العروض: %d" % stats.get("optouts", 0))
    if stats.get("unknown_taps"):
        lines.append("• ضغطات بزر ما نعرفه: %d (شوف /api/campaigns/status)" % stats["unknown_taps"])
    lines.append("")
    lines.append("«انحجز» = حجز مؤكد انعمل خلال %d أيام بنفس الاسم أو الرقم أو المحادثة. "
                 "الضغطات الأخيرة ممكن تنحجز بعد التقرير." % stats.get("match_days", 7))
    return "\n".join(lines)[:1990]
