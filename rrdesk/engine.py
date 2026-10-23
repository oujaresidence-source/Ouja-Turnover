# -*- coding: utf-8 -*-
"""
rrdesk.engine — the PURE rules of «طلبات سام». No Discord, no database, no clock: every
function takes `now` (or a time) as an argument, so a test can place it anywhere.

What lives here, and the owner rule each part protects
    * language direction + skip rules        every message is translated, nothing twice
    * the phrase table                        the cheapest call is the one never made
    * the request state machine               first-final-wins, rework keeps the original due
    * working-minute arithmetic               nobody is accused while asleep (11:00 → 01:30)
    * the ladder + due_step                   each step once; after downtime, only the latest
    * eligibility + the judge                 only explicit or measured requests cost money;
                                              1st miss = notice, 2nd = ONE warning, 3rd = KPI
    * owner choice                            one owner, decided once, rule number recorded
    * KPIs                                    fixed targets, «بيانات ناقصة» under 3, no ranking
    * calibration                             the history study's numbers, never loosened
The structure test forbids backslashes in this package (the DASHBOARD_HTML trap): newlines
are chr(10), and no regex here needs an escape.
"""

import datetime
import hashlib
import math
import unicodedata

from ops import engine as oeng

NL = chr(10)
INVISIBLE_MARK = chr(0x2063)          # appended to everything rrdesk posts (own-message skip)

# ------------------------------------------------------------------ vocabulary

ASKS = ("photos", "video", "invoice", "quote", "guest_chat", "airbnb_screens", "ops_report",
        "receipt", "info", "action", "other")
# Asks that are satisfied by a FILE. «سلّمت» on one of these refuses unless a file was posted.
FILE_ASKS = frozenset(("photos", "video", "invoice", "quote", "guest_chat", "airbnb_screens",
                       "receipt", "ops_report"))

OPEN, ACK, DELIVERED = "open", "acknowledged", "delivered"
CONFIRMED, CONFIRMED_AUTO = "confirmed", "confirmed_auto"
CANCELLED, CLOSED_WITH_TICKET = "cancelled", "closed_with_ticket"
STATES = (OPEN, ACK, DELIVERED, CONFIRMED, CONFIRMED_AUTO, CANCELLED, CLOSED_WITH_TICKET)
TERMINAL = frozenset((CONFIRMED, CONFIRMED_AUTO, CANCELLED, CLOSED_WITH_TICKET))
LIVE = frozenset((OPEN, ACK))         # still owed something

# How a request was born. Only these can ever turn into a miss (brief §5.B.1).
PATH_COMMAND, PATH_PIN, PATH_DETECTED, PATH_CONFIRMED = "command", "pin", "detected", "confirmed"
PATHS = (PATH_COMMAND, PATH_PIN, PATH_DETECTED, PATH_CONFIRMED)
MISS_PATHS = frozenset(PATHS)

AUTO_CONFIRM_HOURS = 48               # delivered + 48 wall-clock hours of silence = confirmed

DEFAULT_SLA = {"resp_min": 60, "deliv_min": 480, "urg_resp_min": 30, "urg_deliv_min": 180}
URGENT_DAYS_LEFT = 3                  # AirCover deadline this close (or passed) = urgent

# ------------------------------------------------------------------ language

_AR_RANGES = ((0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF), (0xFB50, 0xFDFF),
              (0xFE70, 0xFEFF))


def _is_arabic(ch):
    o = ord(ch)
    return any(a <= o <= b for a, b in _AR_RANGES)


def _is_letter(ch):
    return unicodedata.category(ch).startswith("L")


def arabic_share(text):
    """Arabic letters ÷ all letters, or None when there are no letters at all."""
    letters = [c for c in (text or "") if _is_letter(c)]
    if not letters:
        return None
    return sum(1 for c in letters if _is_arabic(c)) / float(len(letters))


def direction(text):
    """'ar2en' when more than 30% of the letters are Arabic, 'en2ar' otherwise, None for a
    message with no letters. A mixed line follows this one threshold (brief §5.A.2)."""
    s = arabic_share(text)
    if s is None:
        return None
    return "ar2en" if s > 0.30 else "en2ar"


def _is_mention(tok):
    t = tok.strip(".,!?؟،:;()[]")
    if t.startswith("<") and t.endswith(">"):
        body = t[1:-1].lstrip("@#!&:")
        return body.split(":")[-1].isdigit() or body.isdigit()
    return t.startswith("@") and len(t) > 1


def _is_code(tok):
    """A reservation code (HM + 8), a Hostaway id, an RR number — copied, never translated."""
    t = tok.strip(".,!?؟،:;()[]#").upper()
    if t.startswith("HM") and len(t) == 10 and t.isalnum():
        return True
    if t.startswith("RR-") or t.startswith("RR#"):
        return True
    return any(c.isdigit() for c in t) and all(c.isalnum() or c in "-_/" for c in t)


def meaningful_letters(text):
    """Letters left after removing links, mentions, custom emoji, codes and numbers."""
    n = 0
    for tok in (text or "").split():
        low = tok.lower()
        if low.startswith("http://") or low.startswith("https://") or low.startswith("www."):
            continue
        if _is_mention(tok) or _is_code(tok):
            continue
        n += sum(1 for c in tok if _is_letter(c))
    return n


def is_single_code_block(text):
    t = (text or "").strip()
    return t.startswith("```") and t.endswith("```") and len(t) > 6 and t.count("```") == 2


def skip_reason(text, is_bot=False, is_ours=False, has_embeds=False):
    """Why this message gets NO translation (None = translate it). Order matters: our own
    messages are checked first so a translation can never be translated."""
    t = text or ""
    if is_ours or INVISIBLE_MARK in t:
        return "own"
    if is_single_code_block(t):
        return "code_block"
    if meaningful_letters(t) < 2:
        return "embeds_only" if has_embeds else "trivial"
    if is_bot and direction(t) == "en2ar":
        return "bot_english"
    return None


def normalize(text):
    """Cache / phrase-table key: lower case, Arabic letter variants folded, punctuation and
    emoji dropped, whitespace collapsed."""
    fold = {"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه", "ـ": ""}
    out = []
    for c in (text or "").lower():
        c = fold.get(c, c)
        cat = unicodedata.category(c)
        if cat.startswith("L") or cat.startswith("N"):
            out.append(c)
        elif cat.startswith("Z") or c in (" ", NL, chr(9)):
            out.append(" ")
        elif cat == "Mn":
            continue                          # Arabic diacritics
        else:
            out.append(" ")
    return " ".join("".join(out).split())


def cache_key(text, direction_, glossary_version):
    raw = "|".join((normalize(text), direction_ or "", str(glossary_version or "0")))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# Free answers — no model call. Keys are normalize()d. The history study adds every phrase
# it saw five times or more (texts.py merges those in at import).
PHRASES = {
    "ar2en": {
        "تم": "Done.", "تمام": "OK.", "ابشر": "On it.", "ابشر طال عمرك": "On it, sir.",
        "ابشر ان شاء الله": "On it, God willing.", "شكرا": "Thanks.", "شكرا لك": "Thank you.",
        "وصل": "Received.", "وصلت": "Received.", "يعطيك العافيه": "Thank you for your effort.",
        "حاضر": "Will do.", "ان شاء الله": "God willing.", "اوكي": "OK.", "تم الرفع": "Uploaded.",
        "تم الارسال": "Sent.", "جاري": "In progress.", "جاري العمل": "Working on it.",
    },
    "en2ar": {
        "ok": "تمام", "okay": "تمام", "done": "تم", "thanks": "شكراً", "thank you": "شكراً لك",
        "noted": "تم، واضح", "received": "وصل", "got it": "وصل، واضح", "on it": "أبشر",
        "perfect": "ممتاز", "great": "ممتاز", "yes": "نعم", "no": "لا", "sure": "أكيد",
        "thank you so much": "شكراً جزيلاً", "well done": "عافية عليك",
    },
}


def phrase_lookup(text, direction_, extra=None):
    key = normalize(text)
    if not key or not direction_:
        return None
    hit = (extra or {}).get(direction_, {}).get(key)
    return hit or PHRASES.get(direction_, {}).get(key)


# ------------------------------------------------------------------ working time

def work_kwargs(cfg=None):
    c = cfg or {}
    return {"work_start": int(c.get("work_start", oeng.WORK_START_DEFAULT)),
            "work_end_hour": int(c.get("work_end_hour", oeng.WORK_END_HOUR_DEFAULT)),
            "work_end_min": int(c.get("work_end_min", oeng.WORK_END_MIN_DEFAULT))}


def worked_minutes(start, end, cfg=None):
    return oeng.worked_minutes(start, end, **work_kwargs(cfg))


def in_work_hours(now, cfg=None):
    kw = work_kwargs(cfg)
    for day in (now.date() - datetime.timedelta(days=1), now.date()):
        ws, we = oeng.work_span(day, tzinfo=now.tzinfo, **kw)
        if ws <= now < we:
            return True
    return False


def add_work_minutes(start, minutes, cfg=None):
    """The moment `minutes` WORKING minutes after `start` — the inverse of worked_minutes.
    A request asked at 01:00 with a 60-minute SLA is due at 11:30 the same morning, not
    02:00: the dead zone 01:30 → 11:00 costs nobody anything."""
    kw = work_kwargs(cfg)
    left = float(minutes)
    day = start.date() - datetime.timedelta(days=1)
    for _ in range(400):
        ws, we = oeng.work_span(day, tzinfo=start.tzinfo, **kw)
        if start < we:
            s = max(start, ws)
            avail = (we - s).total_seconds() / 60.0
            if left <= avail:
                return s + datetime.timedelta(minutes=left)
            left -= avail
        day += datetime.timedelta(days=1)
    raise ValueError("add_work_minutes ran past 400 days")


# ------------------------------------------------------------------ SLA + urgency

def sla(cfg=None):
    out = dict(DEFAULT_SLA)
    for k in out:
        try:
            v = int((cfg or {}).get(k, out[k]))
            if v > 0:
                out[k] = v
        except (TypeError, ValueError):
            pass
    return out


def is_urgent(flag=False, enrich=None):
    """Sam flagged it, or the AirCover filing deadline is ≤ 3 days away or already passed."""
    if flag:
        return True
    e = enrich or {}
    if e.get("deadline_passed"):
        return True
    dl = e.get("days_left")
    try:
        return dl is not None and int(dl) <= URGENT_DAYS_LEFT
    except (TypeError, ValueError):
        return False


def sla_minutes(urgent, cfg=None):
    s = sla(cfg)
    return (s["urg_resp_min"], s["urg_deliv_min"]) if urgent else (s["resp_min"], s["deliv_min"])


def dues(clock_at, urgent, cfg=None):
    """(response due, delivery due) for a clock that started at `clock_at`."""
    r, d = sla_minutes(urgent, cfg)
    return add_work_minutes(clock_at, r, cfg), add_work_minutes(clock_at, d, cfg)


# ------------------------------------------------------------------ the state machine

_TRANSITIONS = {
    ("team_message", OPEN): ACK,
    ("ack", OPEN): ACK,
    ("deliver", OPEN): DELIVERED,
    ("deliver", ACK): DELIVERED,
    ("got_it", DELIVERED): CONFIRMED,
    ("auto_confirm", DELIVERED): CONFIRMED_AUTO,
    ("not_what", DELIVERED): ACK,
}


def transition(state, event):
    """The next state, or None when this event does nothing in this state. Terminal states
    accept nothing — the first final answer wins."""
    if state in TERMINAL:
        return None
    if event in ("cancel", "ticket_closed"):
        return CANCELLED if event == "cancel" else CLOSED_WITH_TICKET
    return _TRANSITIONS.get((event, state))


# ------------------------------------------------------------------ the ladder

LADDER = ("R1", "R2", "D1", "D2", "MISS")


def step_key(step, gen=1):
    """Ladder rows are UNIQUE(request_id, step). A reassignment bumps gen, so the new owner
    gets a fresh ladder while the old owner's sent steps stay recorded."""
    return step if int(gen or 1) <= 1 else "%s#%d" % (step, int(gen))


def ladder(state, clock_at, urgent, cfg=None):
    """The steps that APPLY in this state, as [{step, at}] sorted by time.
        R1   50% of the response SLA      still open
        R2  100% of the response SLA      still open
        D1   75% of the delivery SLA      not delivered
        D2  100% of the delivery SLA      not delivered
        MISS 200% of the delivery SLA, or 200% of the response SLA with no acknowledgement
    """
    if state not in LIVE:
        return []
    r, d = sla_minutes(urgent, cfg)
    at = lambda m: add_work_minutes(clock_at, m, cfg)   # noqa: E731
    out = []
    if state == OPEN:
        out.append({"step": "R1", "at": at(r * 0.5)})
        out.append({"step": "R2", "at": at(r)})
    out.append({"step": "D1", "at": at(d * 0.75)})
    out.append({"step": "D2", "at": at(d)})
    miss_at = at(d * 2)
    if state == OPEN:
        miss_at = min(miss_at, at(r * 2))
    # the miss ends the ladder: a reminder scheduled after it would remind nobody of anything
    out = [s for s in out if s["at"] < miss_at] + [{"step": "MISS", "at": miss_at}]
    out.sort(key=lambda s: s["at"])
    return out


def due_step(state, clock_at, urgent, now, sent=(), cfg=None):
    """The ONE step to send right now, or None: the latest step whose time has come and that
    was not sent. A bot asleep through R1 and R2 wakes and sends only the latest — it never
    machine-guns the backlog at somebody's phone (ops.engine.due_step, same rule)."""
    sent = set(sent or ())
    steps = ladder(state, clock_at, urgent, cfg)
    # never go backwards: a step earlier than one already sent is history, not a reminder
    last = max([i for i, s in enumerate(steps) if s["step"] in sent] or [-1])
    ready = [s for s in steps[last + 1:] if s["at"] <= now]
    return ready[-1] if ready else None


def auto_confirm_due(delivered_at, now):
    return delivered_at is not None and now - delivered_at >= datetime.timedelta(
        hours=AUTO_CONFIRM_HOURS)


# ------------------------------------------------------------------ misses + the judge

def miss_eligible(path, state, owner_did, unowned=False, owner_is_admin=False,
                  owner_on_leave=False):
    """Can this request cost its owner anything? Only an explicit or confirmed (or measured
    detected) request, still owed, owned by a reachable non-admin who was working that day."""
    if path not in MISS_PATHS or state not in LIVE:
        return False
    if unowned or not str(owner_did or "").strip():
        return False
    return not owner_is_admin and not owner_on_leave


NOTICE, WARN, KPI_ONLY = "notice", "warn", "kpi"


def judge(nth_miss_this_week):
    """1st miss in an ISO week = a private notice; 2nd = ONE ops warning for the week;
    later misses that week = KPI only (ops' UNIQUE keys make a second warning impossible)."""
    n = int(nth_miss_this_week or 0)
    if n <= 0:
        return None
    return NOTICE if n == 1 else (WARN if n == 2 else KPI_ONLY)


def week_key(d):
    return oeng.iso_week_key(d)


def period_key(d):
    """The ops period key. 'RR-' keeps it apart from 'wr' (bare week) and 'OC-' (night) —
    the warning id is wn_<employee>_<period_key>, so keys must be unique across kinds."""
    return "RR-" + week_key(d)


# ------------------------------------------------------------------ who owns it

def choose_owner(mentioned=(), replied=None, role_mentioned=False, opener=None,
                 responsible=None, lead=None, excluded=(), calendar_dids=()):
    """Decide once, freeze it on the row. Returns {did, name, rule, unowned}.
        1  a person Sam mentioned (or replied to) who is not Sam and not a bot
        2  Sam mentioned a ROLE → the apartment's responsible person today
        3  the ticket opener, if they are in the Employee Calendar
        4  the apartment's responsible person today
        5  the ops lead, flagged unowned (counted against routing, never warned)
    `opener` / `responsible` / `lead` are (did, name) pairs or None."""
    ex = {str(x) for x in (excluded or ()) if x}
    for did in list(mentioned or ()) + ([replied] if replied else []):
        d = str(did or "")
        if d and d not in ex:
            return {"did": d, "name": "", "rule": 1, "unowned": False}
    resp = responsible or (None, None)
    if role_mentioned and resp[0]:
        return {"did": str(resp[0]), "name": resp[1] or "", "rule": 2, "unowned": False}
    op = opener or (None, None)
    cal = {str(x) for x in (calendar_dids or ()) if x}
    if op[0] and str(op[0]) in cal and str(op[0]) not in ex:
        return {"did": str(op[0]), "name": op[1] or "", "rule": 3, "unowned": False}
    if resp[0]:
        return {"did": str(resp[0]), "name": resp[1] or "", "rule": 4, "unowned": False}
    ld = lead or (None, None)
    return {"did": str(ld[0] or ""), "name": ld[1] or "", "rule": 5, "unowned": True}


# ------------------------------------------------------------------ KPIs

TARGETS = {"resp_on_time": 0.90, "deliv_on_time": 0.85, "rework": 0.10, "misses": 0,
           "voice": 0}
MIN_SAMPLE = 3
INSUFFICIENT_AR = "بيانات ناقصة"


def percentile(values, p):
    v = sorted(x for x in values if x is not None)
    if not v:
        return None
    k = (len(v) - 1) * (p / 100.0)
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return v[int(k)]
    return v[f] + (v[c] - v[f]) * (k - f)


def _dt(v):
    if v is None or v == "":
        return None
    if isinstance(v, datetime.datetime):
        return v
    return datetime.datetime.fromisoformat(str(v))


def kpis(rows, now, voice_count=0, misses=0, cfg=None):
    """One person's numbers for a period. rows: their requests (dicts with asked_at,
    clock_at, resp_due, deliv_due, acked_at, delivered_at, state, rework). A request whose
    due has not arrived and that is not answered yet is not counted either way."""
    rows = list(rows or [])
    resp_hit = resp_n = deliv_hit = deliv_n = 0
    resp_mins, deliv_hours, delivered = [], [], 0
    rework = 0
    for r in rows:
        if r.get("state") in (CANCELLED,):
            continue
        clock = _dt(r.get("clock_at") or r.get("asked_at"))
        ack, dlv = _dt(r.get("acked_at")), _dt(r.get("delivered_at"))
        rdue, ddue = _dt(r.get("resp_due")), _dt(r.get("deliv_due"))
        first = ack or dlv
        if first is not None or (rdue is not None and rdue <= now):
            resp_n += 1
            if first is not None and rdue is not None and first <= rdue:
                resp_hit += 1
            if first is not None and clock is not None:
                resp_mins.append(worked_minutes(clock, first, cfg))
        if dlv is not None or (ddue is not None and ddue <= now):
            deliv_n += 1
            if dlv is not None and ddue is not None and dlv <= ddue:
                deliv_hit += 1
            if dlv is not None and clock is not None:
                deliv_hours.append(worked_minutes(clock, dlv, cfg) / 60.0)
        if dlv is not None:
            delivered += 1
        rework += int(r.get("rework") or 0)
    owned = len([r for r in rows if r.get("state") != CANCELLED])
    out = {"owned": owned, "voice": int(voice_count or 0), "misses": int(misses or 0),
           "insufficient": owned < MIN_SAMPLE}
    if out["insufficient"]:
        out.update({"resp_on_time": None, "median_resp_min": None, "deliv_on_time": None,
                    "median_deliv_h": None, "rework_rate": None})
        return out
    out["resp_on_time"] = round(resp_hit / float(resp_n), 3) if resp_n else None
    out["median_resp_min"] = round(percentile(resp_mins, 50), 1) if resp_mins else None
    out["deliv_on_time"] = round(deliv_hit / float(deliv_n), 3) if deliv_n else None
    out["median_deliv_h"] = round(percentile(deliv_hours, 50), 2) if deliv_hours else None
    out["rework_rate"] = round(rework / float(delivered), 3) if delivered else None
    return out


def meets(k, cfg=None):
    """{metric: True|False|None} against the fixed published targets (None = no data)."""
    if not k or k.get("insufficient"):
        return {}
    s = sla(cfg)
    f = lambda v, ok: None if v is None else bool(ok(v))   # noqa: E731
    return {"resp_on_time": f(k.get("resp_on_time"), lambda v: v >= TARGETS["resp_on_time"]),
            "median_resp_min": f(k.get("median_resp_min"), lambda v: v <= s["resp_min"]),
            "deliv_on_time": f(k.get("deliv_on_time"), lambda v: v >= TARGETS["deliv_on_time"]),
            "median_deliv_h": f(k.get("median_deliv_h"), lambda v: v <= s["deliv_min"] / 60.0),
            "rework_rate": f(k.get("rework_rate"), lambda v: v <= TARGETS["rework"]),
            "misses": k.get("misses", 0) <= TARGETS["misses"],
            "voice": k.get("voice", 0) <= TARGETS["voice"]}


# ------------------------------------------------------------------ calibration (§4.5)

def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def calibrate(first_response_min, delivery_min, min_points=5):
    """The SLA numbers from the history, by the brief's rules. Returns a dict with the
    chosen values, the source ('history' | 'default') and the breach share of the old data."""
    fr = [x for x in (first_response_min or []) if x is not None]
    dl = [x for x in (delivery_min or []) if x is not None]
    out = {"resp_min": DEFAULT_SLA["resp_min"], "deliv_min": DEFAULT_SLA["deliv_min"],
           "resp_source": "default", "deliv_source": "default",
           "n_resp": len(fr), "n_deliv": len(dl)}
    if len(fr) >= min_points:
        p = percentile(fr, 60)
        out["resp_min"] = int(_clamp(int(round(p / 15.0)) * 15, 30, 120))
        out["resp_source"] = "history"
        out["resp_p60"] = round(p, 1)
    if len(dl) >= min_points:
        p = percentile(dl, 60)
        out["deliv_min"] = int(_clamp(int(round(p / 60.0)) * 60, 240, 960))
        out["deliv_source"] = "history"
        out["deliv_p60"] = round(p, 1)
    out["resp_breach_share"] = (round(sum(1 for x in fr if x > out["resp_min"]) / float(len(fr)), 3)
                                if fr else None)
    out["deliv_breach_share"] = (round(sum(1 for x in dl if x > out["deliv_min"]) / float(len(dl)), 3)
                                 if dl else None)
    return out


def choose_threshold(samples, target=0.95, floor_precision=0.90, start=0.40, min_positive=5):
    """samples: [(confidence, model_says_request, truly_request)]. Returns
    {threshold, mode, table}. mode 'auto' = detected requests open by themselves; 'confirm'
    = they only ask Sam; 'explicit' = the classifier never reaches 90% precision."""
    table = []
    t = start
    while t <= 0.99 + 1e-9:
        pred = [(c, y) for c, p, y in samples if p and c is not None and c >= t]
        tp = sum(1 for _c, y in pred if y)
        prec = (tp / float(len(pred))) if pred else None
        pos = sum(1 for _c, _p, y in samples if y)
        rec = (tp / float(pos)) if pos else None
        table.append({"t": round(t, 2), "n": len(pred), "precision": prec, "recall": rec})
        t += 0.05
    ok = [r for r in table if r["precision"] is not None and r["n"] >= min_positive
          and r["precision"] >= target]
    if ok:
        return {"threshold": ok[0]["t"], "mode": "auto", "table": table}
    near = [r for r in table if r["precision"] is not None and r["n"] >= min_positive
            and r["precision"] >= floor_precision]
    if near:
        return {"threshold": near[0]["t"], "mode": "confirm", "table": table}
    return {"threshold": None, "mode": "explicit", "table": table}


def majority(ids):
    counts = {}
    for i in ids or ():
        s = str(i or "").strip()
        if s:
            counts[s] = counts.get(s, 0) + 1
    if not counts:
        return None
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


# ------------------------------------------------------------------ time text

AR_DAYS = ("الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد")
_AR_DIGITS = "٠١٢٣٤٥٦٧٨٩"


def ar_num(n):
    return "".join(_AR_DIGITS[int(c)] if c.isdigit() else c for c in str(n))


def fmt_time(dt):
    """'12:30 PM' — the brief's format for Sam and staff alike."""
    h = dt.hour % 12 or 12
    return "%d:%02d %s" % (h, dt.minute, "AM" if dt.hour < 12 else "PM")


def fmt_due_en(dt, now):
    d = (dt.date() - now.date()).days
    day = "today" if d == 0 else ("tomorrow" if d == 1 else dt.strftime("%a %d %b"))
    return "%s %s" % (fmt_time(dt), day)


def fmt_due_ar(dt, now):
    d = (dt.date() - now.date()).days
    day = "اليوم" if d == 0 else ("بكرة" if d == 1 else AR_DAYS[dt.weekday()])
    t = fmt_time(dt).replace("AM", "ص").replace("PM", "م")
    return "%s %s" % (day, t)


def fmt_age(minutes):
    m = int(max(0, minutes or 0))
    if m < 60:
        return "%dm" % m
    if m < 60 * 48:
        return "%dh" % (m // 60)
    return "%dd" % (m // 1440)
