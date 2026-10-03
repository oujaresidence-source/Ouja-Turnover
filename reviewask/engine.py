# -*- coding: utf-8 -*-
"""
reviewask.engine — the PURE rules of «رفع التقييم». No I/O, no discord, no bot import.

    which apartments   apartment_status: exact integer math on Hostaway's 10-point scale
                       (avg > 4.75 ⇔ 2R > 19n), fewer than 3 reviews = in, owner pins win
    which stays        eligibility: review mode (weak apartment) or care mode (a maintenance
                       ticket during the stay), every skip has a reason code
    the clock          next_action(row, now, cfg): stage / ping / remind / miss / expire
    the presses        press(row, kind, now, cfg): the field changes one button makes
    the words          render_template: owner-written text, unknown {placeholders} left visible

Owner rulings encoded here (spec §2 + «ابدأ» 2026-10-03):
  * a 0 / empty / None score is NOT a review — not in R, not in n (review_score → None)
  * staff misses never burn a guest attempt; «كلمني بعدين» is free once
  * nothing guest-facing 22:00–13:00
  * NO discount, offer or template text lives in code — the owner owns every word
"""

import datetime
import re
from fractions import Fraction

try:
    from zoneinfo import ZoneInfo
except ImportError:                     # pragma: no cover — Python < 3.9
    ZoneInfo = None

RIYADH = "Asia/Riyadh"
NL = chr(10)

# ------------------------------------------------------------------ states (spec §6)

WAITING = "waiting"
WA_DUE = "wa_due"
WA_SENT = "wa_sent"
CALL_DUE = "call_due"
CALL_RETRY = "call_retry"
CARE_DUE = "care_due"
PROMISED = "promised"                  # open: waiting for the review to land

REVIEWED = "reviewed"
PROMISED_EXPIRED = "promised_expired"
DECLINED = "declined"
WRONG_NUMBER = "wrong_number"
NO_ANSWER_FINAL = "no_answer_final"
COMPLAINT = "complaint"
EXPIRED = "expired"
CANCELLED = "cancelled"
VOID = "void"

OPEN = (WAITING, WA_DUE, WA_SENT, CALL_DUE, CALL_RETRY, CARE_DUE, PROMISED)
TERMINAL = (REVIEWED, PROMISED_EXPIRED, DECLINED, WRONG_NUMBER, NO_ANSWER_FINAL, COMPLAINT,
            EXPIRED, CANCELLED, VOID)
DUE_STATES = (WA_DUE, CARE_DUE, CALL_DUE)          # a prompt with buttons is live

# What a press may move from. Terminal states are never in here (first-final-wins).
ALLOWED_FROM = {
    "sent": (WAITING, WA_DUE),
    "no_phone": (WAITING, WA_DUE),
    "replied_will": (WAITING, WA_DUE, WA_SENT),
    "replied_no": (WAITING, WA_DUE, WA_SENT),
    "replied_quiet": (WAITING, WA_DUE, WA_SENT),
    "rated": (CALL_DUE, CALL_RETRY),
    "promise": (CALL_DUE, CALL_RETRY),
    "noanswer": (CALL_DUE, CALL_RETRY, CARE_DUE),
    "later": (CALL_DUE, CALL_RETRY, CARE_DUE),
    "complaint": (WAITING, WA_DUE, WA_SENT, CALL_DUE, CALL_RETRY, CARE_DUE),
    "decline": (CALL_DUE, CALL_RETRY),
    "wrong": (CALL_DUE, CALL_RETRY, CARE_DUE),
    "satisfied": (CARE_DUE, CALL_RETRY),
}

# Buttons per stage, in display order. "wa" is the link button (flow builds its URL).
WA_BUTTONS = ("wa", "sent", "replied", "no_phone")
WA_SENT_BUTTONS = ("wa", "replied")
CALL_BUTTONS = ("rated", "promise", "noanswer", "later", "complaint", "decline", "wrong", "wa")
CARE_BUTTONS = ("satisfied", "complaint", "noanswer", "later", "wrong")

SKIP_AR = {
    "out_of_program": "الشقة فوق ٤.٧٥",
    "cancelled": "الحجز ملغي",
    "not_airbnb": "مو Airbnb",
    "duplicate": "لها غرفة من قبل",
    "no_listing": "ما عرفنا الشقة",
    "already_reviewed": "الضيف قيّم من قبل",
}

# Review filter (spec §3). The G12 live print decides the exact type value; a row WITHOUT a
# type (the shipped Airbnb CSV seed) is a guest review.
GUEST_TYPES = ("guest-to-host", "guest_to_host", "guesttohost")
HOST_TYPES = ("host-to-guest", "host_to_guest", "hosttoguest")
AIRBNB_CHANNEL_IDS = (2018,)

# ------------------------------------------------------------------ config shape

def default_cfg():
    """Every knob the clock reads, with the spec's defaults (config.snapshot() fills from env)."""
    return {
        "threshold": "4.75", "min_reviews": 3, "wa_at": "17:00", "call_at": "auto",
        "max_calls": 2, "window_days": 14, "quiet_from": "22:00", "quiet_to": "13:00",
        "ramadan": [], "hijri_month": None, "wa_reminders": ("18:00", "19:30"),
        "call_remind_after_min": 45, "call_last_remind": "21:30",
    }


# ------------------------------------------------------------------ time helpers

def tz():
    return ZoneInfo(RIYADH) if ZoneInfo else datetime.timezone(datetime.timedelta(hours=3))


def parse_dt(v):
    if v is None or v == "":
        return None
    if isinstance(v, datetime.datetime):
        return v if v.tzinfo else v.replace(tzinfo=tz())
    try:
        d = datetime.datetime.fromisoformat(str(v))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=tz())


def iso(d):
    return d.isoformat(timespec="seconds") if d else None


def parse_day(v):
    if isinstance(v, datetime.datetime):
        return v.date()
    if isinstance(v, datetime.date):
        return v
    try:
        return datetime.date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def parse_hhmm(s):
    m = re.match("^([0-9]{1,2}):([0-9]{2})$", str(s or "").strip())
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        return None
    return h, mi


def at_clock(day, hhmm):
    d = parse_day(day)
    h, m = parse_hhmm(hhmm) or (0, 0)
    return datetime.datetime(d.year, d.month, d.day, h, m, tzinfo=tz())


def in_quiet(now, quiet_from="22:00", quiet_to="13:00"):
    """True inside [quiet_from, quiet_to) — the window wraps midnight."""
    qf, qt = parse_hhmm(quiet_from) or (22, 0), parse_hhmm(quiet_to) or (13, 0)
    t = (now.hour, now.minute)
    if qf <= qt:
        return qf <= t < qt
    return t >= qf or t < qt


def expires_at(day, cfg):
    """Airbnb closes reviews 14 days after checkout: the last open minute is D+13 23:59."""
    d = parse_day(day) + datetime.timedelta(days=max(1, int(cfg.get("window_days") or 14)) - 1)
    return at_clock(d, "23:59")


# ------------------------------------------------------------------ §3 the 4.75 line

def _frac(v):
    return v if isinstance(v, Fraction) else Fraction(str(v))


def review_score(r):
    """The 10-point score as an exact Fraction, or None when it is not a review.
    Owner ruling (2026-10-03): 0, empty, None and junk are excluded completely."""
    raw = (r or {}).get("rating_raw")
    if raw is None or isinstance(raw, bool):
        return None
    try:
        f = Fraction(str(raw).strip())
    except (ValueError, ZeroDivisionError):
        return None
    if f <= 0:
        return None
    return int(f) if f.denominator == 1 else f


def is_guest_review(r):
    raw = (r or {}).get("raw") or {}
    t = raw.get("type") if isinstance(raw, dict) else None
    if t is None or str(t).strip() == "":
        return True
    return str(t).strip().lower() in GUEST_TYPES


def is_airbnb_review(r):
    raw = (r or {}).get("raw") or {}
    if isinstance(raw, dict):
        try:
            if int(raw.get("channelId") or 0) in AIRBNB_CHANNEL_IDS:
                return True
        except (TypeError, ValueError):
            pass
        ch = str(raw.get("channelName") or "").lower()
        if ch:
            return "airbnb" in ch
    return "airbnb" in str((r or {}).get("channel") or "").lower()


def type_audit(reviews):
    """{types, channels, unknown_types, total} over the raw review list — counts only, no names.
    A `type` that is neither a guest nor a host value means our filter does not understand the
    data: the caller must refuse to decide anything on it (fail closed)."""
    types, channels = {}, {}
    with_res = 0
    for r in reviews or []:
        if str((r or {}).get("reservation_id") or "").strip():
            with_res += 1
        raw = (r or {}).get("raw") or {}
        t = raw.get("type") if isinstance(raw, dict) else None
        key = "(بدون نوع)" if t is None or str(t).strip() == "" else str(t).strip()
        types[key] = types.get(key, 0) + 1
        ch = (raw.get("channelName") if isinstance(raw, dict) else None) or (r or {}).get("channel") or "—"
        channels[str(ch)] = channels.get(str(ch), 0) + 1
    unknown = sorted(k for k in types if k != "(بدون نوع)"
                     and k.lower() not in GUEST_TYPES and k.lower() not in HOST_TYPES)
    return {"types": types, "channels": channels, "unknown_types": unknown,
            "total": len(reviews or []), "with_reservation": with_res}


def newest_live_review(reviews, today=None):
    """The newest date of a REAL guest review that came from Hostaway itself (rows with `raw`,
    a score, guest-to-host), never after `today` — or None. The CSV seed has no `raw` and is
    months old (the 2026-10-03 incident); Hostaway also pre-creates EMPTY review rows for every
    booking, future ones included (seen live: 2027-02-23), so only scored, past rows count."""
    best = None
    for r in reviews or []:
        if not isinstance((r or {}).get("raw"), dict) or not r.get("raw"):
            continue
        if review_score(r) is None or not is_guest_review(r):
            continue
        d = parse_day(r.get("date") or r["raw"].get("submittedAt") or r["raw"].get("departureDate"))
        if d is None or (today is not None and d > today):
            continue
        if best is None or d > best:
            best = d
    return best


def counted_reviews(reviews):
    """Guest-to-host Airbnb reviews with a real score, one per reservation (a live Hostaway row
    beats the CSV seed copy of the same stay)."""
    best = {}
    loose = []
    for r in reviews or []:
        if not (is_guest_review(r) and is_airbnb_review(r)):
            continue
        if review_score(r) is None:
            continue
        res = str(r.get("reservation_id") or "").strip()
        if not res:
            loose.append(r)
            continue
        prev = best.get(res)
        if prev is None or (str(prev.get("source")) == "csv" and str(r.get("source")) != "csv"):
            best[res] = r
    return list(best.values()) + loose


def _lid(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def listing_stats(reviews):
    """{lid: (n, R)} — R is the exact sum of the 10-point scores."""
    out = {}
    for r in counted_reviews(reviews):
        lid = _lid(r.get("listing_id"))
        if lid is None:
            continue
        n, total = out.get(lid, (0, 0))
        out[lid] = (n + 1, total + review_score(r))
    return out


def in_program(n, R, threshold="4.75", min_reviews=3):
    """In when avg <= threshold (on Hostaway's 10-point scale: R <= 2·T·n), or fewer than
    min_reviews reviews (Airbnb shows no rating until 3)."""
    if n < int(min_reviews):
        return True
    return _frac(R) <= 2 * _frac(threshold) * n


def reviews_needed(n, R, threshold="4.75"):
    """Smallest k of 5★ (10) reviews with (R + 10k) / (n + k) > 2T. At 4.75: k = 19n − 2R + 1."""
    two_t = 2 * _frac(threshold)
    gap = two_t * n - _frac(R)
    if gap < 0:
        return 0
    step = 10 - two_t
    if step <= 0:
        return 0
    return int(gap // step) + 1


def apartment_status(reviews, overrides=None, open_tickets=None, threshold="4.75",
                     min_reviews=3):
    """{lid: {n, R, avg, computed_in, pinned, pin_reason, in_program, needed, open_tickets}}."""
    stats = listing_stats(reviews)
    overrides = overrides or {}
    open_tickets = open_tickets or {}
    lids = set(stats) | {_lid(k) for k in overrides} | {_lid(k) for k in open_tickets}
    out = {}
    for lid in sorted(x for x in lids if x is not None):
        n, total = stats.get(lid, (0, 0))
        computed = in_program(n, total, threshold, min_reviews)
        ov = overrides.get(lid) or overrides.get(str(lid)) or {}
        pinned = ov.get("mode") if ov.get("mode") in ("in", "out") else None
        needed = reviews_needed(n, total, threshold) if n else 0
        if n < int(min_reviews):
            needed = max(needed, int(min_reviews) - n)
        avg = float(Fraction(total) / (2 * n)) if n else None
        out[lid] = {
            "lid": lid, "n": n, "R": total if isinstance(total, int) else float(total),
            "avg": round(avg, 2) if avg is not None else None,
            "computed_in": computed, "pinned": pinned, "pin_reason": ov.get("reason") or "",
            "in_program": (pinned == "in") if pinned else computed,
            "needed": needed,
            "open_tickets": int(open_tickets.get(lid) or open_tickets.get(str(lid)) or 0),
        }
    return out


# ------------------------------------------------------------------ §4 eligibility

def care_from_tickets(tickets, arrival, departure):
    """A maintenance ticket that was open at any moment of the stay (created before departure
    and not closed before arrival)."""
    a = parse_day(arrival)
    d = parse_day(departure)
    if not (a and d):
        return False
    for t in tickets or []:
        created = parse_dt(t.get("created_at"))
        if created is None or created.date() > d:
            continue
        closed = parse_dt(t.get("closed_at"))
        if closed is not None and closed.date() < a:
            continue
        return True
    return False


def eligibility(res, in_program, care, exists=False):
    """-> (mode, skip_code). mode is 'review' | 'care' | None."""
    if exists:
        return None, "duplicate"
    if str(res.get("status") or "").lower() not in ("new", "modified"):
        return None, "cancelled"
    if str(res.get("channel") or "").lower() != "airbnb":
        return None, "not_airbnb"
    if _lid(res.get("lid")) is None:
        return None, "no_listing"
    if care:
        return "care", ""
    if in_program:
        return "review", ""
    return None, "out_of_program"


# ------------------------------------------------------------------ §8 call time

def parse_ramadan(text):
    """'YYYY-MM-DD:YYYY-MM-DD, …' → [(start, end)]. Junk is skipped, never fatal."""
    out = []
    for part in str(text or "").split(","):
        bits = part.strip().split(":")
        if len(bits) != 2:
            continue
        a, b = parse_day(bits[0].strip()), parse_day(bits[1].strip())
        if a and b and a <= b:
            out.append((a, b))
    return out


def is_ramadan(day, cfg):
    fn = cfg.get("hijri_month")
    if fn is not None:
        try:
            return int(fn(day)) == 9
        except Exception:
            pass
    return any(a <= day <= b for a, b in (cfg.get("ramadan") or []))


def call_time(day, cfg):
    """20:00 Sep–Apr · 20:45 May–Aug (Isha moves late) · 21:30 in Ramadan (after Taraweeh) ·
    an HH:MM env override wins over everything."""
    v = str(cfg.get("call_at") or "auto").strip()
    if parse_hhmm(v):
        h, m = parse_hhmm(v)
        return "%02d:%02d" % (h, m)
    d = parse_day(day)
    if is_ramadan(d, cfg):
        return "21:30"
    if 5 <= d.month <= 8:
        return "20:45"
    return "20:00"


def call_at(day, cfg):
    return at_clock(day, call_time(day, cfg))


# ------------------------------------------------------------------ §6 the clock

def _reminder_times(state, stage_due, cfg):
    day = stage_due.date()
    cutoff = at_clock(day, cfg.get("quiet_from") or "22:00")
    if state == WA_DUE or (state == CARE_DUE and stage_due.strftime("%H:%M") ==
                           str(cfg.get("wa_at") or "17:00")):
        times = [at_clock(day, t) for t in cfg.get("wa_reminders") or ()]
    else:
        times = [stage_due + datetime.timedelta(minutes=int(cfg.get("call_remind_after_min") or 45)),
                 at_clock(day, cfg.get("call_last_remind") or "21:30")]
    return sorted({t for t in times if stage_due < t < cutoff})


def next_action(row, now, cfg):
    """What the clock owes this ticket right now, or None.
    -> {"act": "expire"|"stage"|"ping"|"remind"|"miss", "state"?, "fields": {...}}"""
    st = row.get("state")
    if st not in OPEN:
        return None
    if now >= expires_at(row["day"], cfg):
        return {"act": "expire", "state": PROMISED_EXPIRED if st == PROMISED else EXPIRED,
                "fields": {}}
    if st == PROMISED:
        return None
    quiet = in_quiet(now, cfg.get("quiet_from") or "22:00", cfg.get("quiet_to") or "13:00")

    if st == WAITING:
        due = parse_dt(row.get("next_due_at")) or at_clock(row["day"], cfg.get("wa_at") or "17:00")
        if now >= due and not quiet:
            return _stage(row, WA_DUE if row.get("mode") != "care" else CARE_DUE, now, cfg)
        return None

    if st in (WA_SENT, CALL_RETRY):
        due = parse_dt(row.get("next_due_at"))
        if due and now >= due and not quiet:
            to = CARE_DUE if (st == CALL_RETRY and row.get("mode") == "care"
                              and not row.get("care_ok")) else CALL_DUE
            return _stage(row, to, now, cfg)
        return None

    # a live prompt: WA_DUE / CARE_DUE / CALL_DUE
    sd = parse_dt(row.get("stage_due_at"))
    if sd is None:
        return _stage(row, st, now, cfg) if not quiet else None
    pinged = parse_dt(row.get("pinged_at"))
    if pinged is None or pinged < sd:
        if now >= sd and not quiet:
            return {"act": "ping", "fields": {"pinged_at": iso(now)}}
        return None
    cutoff = at_clock(sd.date(), cfg.get("quiet_from") or "22:00")
    if now >= cutoff:
        if row.get("missed_at") != iso(sd):
            fields = {"missed_at": iso(sd)}
            if st != WA_DUE:
                # the window passed with no press: the SAME attempt rolls to the next call time
                nxt = call_at(sd.date() + datetime.timedelta(days=1), cfg)
                fields.update({"stage_due_at": iso(nxt), "remind_count": 0})
            return {"act": "miss", "fields": fields}
        if st == WA_DUE:
            due = parse_dt(row.get("next_due_at"))
            if due and now >= due and not quiet:
                return _stage(row, CALL_DUE, now, cfg)
        return None
    if quiet:
        return None
    times = _reminder_times(st, sd, cfg)
    n = int(row.get("remind_count") or 0)
    if n < len(times) and now >= times[n]:
        return {"act": "remind", "fields": {"remind_count": n + 1}}
    return None


def _stage(row, state, now, cfg):
    fields = {"state": state, "stage_due_at": iso(now), "pinged_at": iso(now),
              "remind_count": 0, "missed_at": None, "next_due_at": None}
    if state == WA_DUE:
        fields["next_due_at"] = iso(call_at(now.date() + datetime.timedelta(days=1), cfg))
    return {"act": "stage", "state": state, "fields": fields}


# ------------------------------------------------------------------ §7 presses

def press(row, kind, now, cfg):
    """-> {"kind": <logged kind>, "allowed_from": (...), "fields": {...}} for one button.
    The flow applies it with db.transition (conditional UPDATE) — first final wins."""
    calls = int(row.get("calls_used") or 0)
    tomorrow_call = iso(call_at(now.date() + datetime.timedelta(days=1), cfg))
    if kind == "later" and int(row.get("later_used") or 0):
        kind = "noanswer"                     # «كلمني بعدين» is free ONCE, then it is «ما رد»
    f = {}
    # pressed straight from the silent card (before 17:00): the call still comes the evening
    # after checkout — a press must never leave a row with no next step
    call_after_checkout = tomorrow_call
    if row.get("day"):
        call_after_checkout = iso(call_at(parse_day(row["day"]) + datetime.timedelta(days=1), cfg))
    wa_next = row.get("next_due_at") or call_after_checkout
    if kind == "sent":
        f = {"state": WA_SENT, "next_due_at": wa_next}
    elif kind == "no_phone":
        f = {"state": WA_SENT, "wa_note": "no_phone", "next_due_at": wa_next}
    elif kind == "replied_quiet":
        f = {"state": WA_SENT, "wa_note": "replied_quiet", "next_due_at": wa_next}
    elif kind in ("replied_will", "rated", "promise"):
        f = {"state": PROMISED}
    elif kind in ("replied_no", "decline"):
        f = {"state": DECLINED}
    elif kind == "complaint":
        f = {"state": COMPLAINT}
    elif kind == "wrong":
        f = {"state": WRONG_NUMBER}
    elif kind == "noanswer":
        calls += 1
        if calls >= int(cfg.get("max_calls") or 2):
            f = {"state": NO_ANSWER_FINAL, "calls_used": calls}
        else:
            f = {"state": CALL_RETRY, "calls_used": calls, "next_due_at": tomorrow_call}
    elif kind == "later":
        f = {"state": CALL_RETRY, "later_used": 1, "next_due_at": tomorrow_call}
    elif kind == "satisfied":
        f = {"state": WA_DUE, "care_ok": 1, "stage_due_at": iso(now), "pinged_at": iso(now),
             "remind_count": 0, "missed_at": None, "next_due_at": tomorrow_call}
    else:
        raise ValueError("unknown press %r" % kind)
    allowed = ALLOWED_FROM["later" if kind == "later" else kind]
    return {"kind": kind, "allowed_from": allowed, "fields": f}


def stage_buttons(row):
    st = row.get("state")
    if st in (WAITING, WA_DUE):
        return list(WA_BUTTONS)
    if st == WA_SENT:
        return list(WA_SENT_BUTTONS)
    if st == CARE_DUE or (st == CALL_RETRY and row.get("mode") == "care" and not row.get("care_ok")):
        return list(CARE_BUTTONS)
    if st in (CALL_DUE, CALL_RETRY):
        return list(CALL_BUTTONS)
    return []


# ------------------------------------------------------------------ §10 words

_PH = re.compile("{([^{}]+)}")
PLACEHOLDERS = ("الاسم", "الموظف", "الشقة", "رابط_التقييم")


def render_template(text, values):
    """-> (rendered, [unknown placeholder names]). Unknown ones stay visible, never crash."""
    unknown = []

    def sub(m):
        key = m.group(1).strip()
        if key in values:
            return str(values[key] if values[key] is not None else "")
        if key not in unknown:
            unknown.append(key)
        return m.group(0)
    return _PH.sub(sub, str(text or "")), unknown


def pick_template(templates, lang):
    t = templates or {}
    if lang == "en" and str(t.get("en") or "").strip():
        return t["en"]
    return t.get("ar") or ""


def language(number):
    """'wa.me/9665…' or digits → 'ar' when Saudi (966…), else 'en'. No number → 'ar'."""
    d = "".join(c for c in str(number or "") if c.isdigit())
    if not d or d.startswith("966"):
        return "ar"
    return "en"


def unit_short(unit):
    """«Ouja | Narjis 101» → «Narjis 101» (apartment names always start with «Ouja |»)."""
    u = str(unit or "").strip()
    if u.lower().startswith("ouja"):
        rest = u[4:].lstrip()
        if rest.startswith("|"):
            return rest[1:].strip()
    return u


def guest_first(guest):
    """First name only, never a digit (checkout.texts.guest_first logic)."""
    clean = "".join(c for c in str(guest or "") if not c.isdigit())
    words = [w for w in clean.replace("|", " ").split() if w.strip()]
    return words[0] if words else ""


def _slug(s):
    out = []
    for ch in str(s or "").lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in " -_|.":
            out.append("-")
    s2 = "-".join(p for p in "".join(out).split("-") if p)
    return s2


def room_name(unit, guest):
    base = "تقييم-" + (_slug(unit_short(unit)) or "شقة")
    g = _slug(guest_first(guest))
    if g:
        base += "-" + g
    return base[:90]


def topic(res_id, lid, seq):
    return "ouja-rv:%s lid:%s seq:%s" % (res_id, lid, seq)


def topic_reservation(topic_text):
    m = re.match("^ouja-rv:([^ ]+)", str(topic_text or "").strip())
    return m.group(1) if m else None
