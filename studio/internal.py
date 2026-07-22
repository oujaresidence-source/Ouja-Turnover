# -*- coding: utf-8 -*-
"""studio.internal — v3 stage 3: INTERNAL signal collectors (spec D1–D6).

Turns Ouja's own live operational data into signals: concrete, quotable facts a
video can be built on. Six sources land here — occupancy, pricing, reviews, ops,
season, insider — while 'guest_story' stays with the v2 conversation miner
(studio/mine.py).

Shape of the module, and why:
  * the COMPUTATIONS are pure functions over already-fetched rows, so every number
    is unit-testable with synthetic data (CLAUDE.md: synthetic-data logic test for
    any new computation — tests/test_studio_internal.py);
  * `gather()` is the only thing that touches the network, and each data tap is
    guarded on its own so one failing Hostaway call never kills the rest;
  * `collect()` runs every collector inside its own try/except, drops anything that
    restates a recent signal (engine.novelty_key / is_novel), persists and prunes.

Nothing here writes to Hostaway. Read-only, additive, and safe to fail."""

import threading
import traceback
from datetime import date as _date, timedelta

from . import db, engine
from .host import HOST

# Reservation statuses that mean a real, money-carrying booking. 'cancelled' is a
# story for the miner but must never count as occupancy or revenue.
BOOKED_STATUSES = ("new", "modified", "confirmed", "checked-in", "checked-out",
                   "ownerStay")

CAL_DAYS = 45           # forward-calendar horizon we reason over
WINDOW_DAYS = 60        # ± days of reservations pulled for lead-time / turnover math
MIN_LEAD_SAMPLE = 5     # below this many datable bookings, the median isn't a fact
TURNOVER_HORIZON = 14   # "coming up" for same-day turnovers
SEASON_HORIZON = 45     # an event further out than this is not "near"

PROGRESS = {"running": False}
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def _p(**kw):
    with _lock:
        PROGRESS.update(kw)


def snapshot():
    with _lock:
        return dict(PROGRESS)


def _now():
    try:
        return HOST.require("now")()
    except Exception:
        return None


def _today():
    n = _now()
    try:
        return n.date() if n is not None else _date.today()
    except Exception:
        return _date.today()


def _now_iso():
    n = _now()
    try:
        return n.strftime("%Y-%m-%d %H:%M:%S") if n is not None else ""
    except Exception:
        return ""


def _pdate(v):
    """Parse a Hostaway date-ish value to a date, or None. Never raises."""
    try:
        s = str(v or "").strip()[:10]
        y, m, d = s.split("-")
        return _date(int(y), int(m), int(d))
    except Exception:
        return None


def _num(v, default=0.0):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    if f != f:                      # NaN
        return default
    return f


def _booked(r):
    return str((r or {}).get("status") or "").strip() in BOOKED_STATUSES


def _n(x):
    """Format a number the way it should be spoken on camera: no trailing .0."""
    f = _num(x)
    if abs(f - round(f)) < 0.05:
        return str(int(round(f)))
    return ("%.1f" % f)


def _unit_name(listings, lid):
    return (listings or {}).get(lid) or (listings or {}).get(str(lid)) or ("وحدة %s" % lid)


AR_WEEKDAYS = ("الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد")


def _ar_weekday(iso):
    d = _pdate(iso)
    return AR_WEEKDAYS[d.weekday()] if d else ""


def _norm(text):
    """Fold Arabic spelling variants + lowercase, so keyword tallies actually match."""
    t = str(text or "").lower()
    t = t.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    t = t.replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي")
    return t


# ---------------------------------------------------------------------------
# PURE computations (spec D1–D5) — all unit-tested with synthetic data
# ---------------------------------------------------------------------------

def median_lead_days(reservations):
    """Median (booking date -> arrival date) gap in days, or None.

    The owner's hero fact is that Ouja is booked ~1 day ahead. It only counts as a
    fact if the data can carry it: bookings with no parseable booking date or no
    arrival date are dropped, negative gaps (booked after arrival = dirty row) are
    dropped, and fewer than MIN_LEAD_SAMPLE usable rows returns None."""
    leads = []
    for r in reservations or []:
        if not _booked(r):
            continue
        arr = _pdate((r or {}).get("arrivalDate"))
        booked_on = _pdate((r or {}).get("reservationDate")) or _pdate((r or {}).get("insertedOn"))
        if not arr or not booked_on:
            continue
        gap = (arr - booked_on).days
        if gap < 0:
            continue
        leads.append(gap)
    if len(leads) < MIN_LEAD_SAMPLE:
        return None
    leads.sort()
    mid = len(leads) // 2
    if len(leads) % 2:
        return float(leads[mid])
    return (leads[mid - 1] + leads[mid]) / 2.0


def tonight_occupancy(rows, total_units):
    """{'occupied','total','pct'} for tonight from an in-house query.

    A unit is occupied tonight when a booked reservation covers it; the same unit
    appearing twice (a turnover row) counts once."""
    total = int(total_units or 0)
    lids = set()
    for r in rows or []:
        if not _booked(r):
            continue
        lid = (r or {}).get("listingMapId")
        if lid is not None:
            lids.add(lid)
    occ = len(lids)
    if not total:
        total = occ
    pct = int(round((occ / float(total)) * 100)) if total else 0
    return {"occupied": occ, "total": total, "pct": pct}


def busiest_unit(reservations, today=None, horizon_days=WINDOW_DAYS):
    """(listing_id, bookings) for the unit booked most often in the forward window,
    or None. Requires a real gap over the runner-up — otherwise it isn't a story."""
    today = today or _date.today()
    end = today + timedelta(days=horizon_days)
    tally = {}
    for r in reservations or []:
        if not _booked(r):
            continue
        arr = _pdate((r or {}).get("arrivalDate"))
        lid = (r or {}).get("listingMapId")
        if not arr or lid is None or not (today <= arr <= end):
            continue
        tally[lid] = tally.get(lid, 0) + 1
    if not tally:
        return None
    ranked = sorted(tally.items(), key=lambda kv: (-kv[1], str(kv[0])))
    top_lid, top_n = ranked[0]
    runner = ranked[1][1] if len(ranked) > 1 else 0
    if top_n < 3 or top_n <= runner:
        return None
    return (top_lid, top_n)


def same_day_turnovers(reservations, today=None, horizon_days=TURNOVER_HORIZON):
    """[{'lid','date','out','in'}] — a unit with a checkout AND a check-in on the
    same upcoming date. Two different reservations, same listing, same day."""
    today = today or _date.today()
    end = today + timedelta(days=horizon_days)
    outs, ins = {}, {}
    for r in reservations or []:
        if not _booked(r):
            continue
        lid = (r or {}).get("listingMapId")
        if lid is None:
            continue
        rid = str((r or {}).get("id") or id(r))
        dep, arr = _pdate((r or {}).get("departureDate")), _pdate((r or {}).get("arrivalDate"))
        if dep and today <= dep <= end:
            outs.setdefault((lid, dep), set()).add(rid)
        if arr and today <= arr <= end:
            ins.setdefault((lid, arr), set()).add(rid)
    found = []
    for key, out_ids in outs.items():
        in_ids = ins.get(key)
        if not in_ids:
            continue
        # a single reservation can't check itself out and back in on the same day
        if len(out_ids | in_ids) < 2:
            continue
        found.append({"lid": key[0], "date": key[1].isoformat(),
                      "out": sorted(out_ids), "in": sorted(in_ids)})
    found.sort(key=lambda x: (x["date"], str(x["lid"])))
    return found


def weekend_uplift_pct(cal):
    """How much more a weekend night averages vs a weekday night, in %, or None.

    Averages the per-day avg_price of weekend days and of weekday days (days with
    no price are skipped); needs at least one of each side."""
    wk, wd = [], []
    for d in cal or []:
        price = (d or {}).get("avg_price")
        if not price:
            continue
        p = _num(price)
        if p <= 0:
            continue
        (wk if (d or {}).get("is_weekend") else wd).append(p)
    if not wk or not wd:
        return None
    a, b = sum(wk) / len(wk), sum(wd) / len(wd)
    if b <= 0:
        return None
    return round(((a - b) / b) * 100.0, 1)


def price_extremes(cal):
    """(highest_day, lowest_day) by avg nightly price across the forward calendar,
    or (None, None). Days with no price are ignored."""
    priced = [d for d in (cal or []) if _num((d or {}).get("avg_price")) > 0]
    if not priced:
        return (None, None)
    hi = max(priced, key=lambda d: _num(d.get("avg_price")))
    lo = min(priced, key=lambda d: _num(d.get("avg_price")))
    if hi is lo:
        return (hi, None)
    return (hi, lo)


def fullest_weekend(cal):
    """The most-booked upcoming weekend day, or None. Ties break to the nearer date."""
    wknd = [d for d in (cal or []) if (d or {}).get("is_weekend") and _num((d or {}).get("total")) > 0]
    if not wknd:
        return None
    return max(wknd, key=lambda d: (_num(d.get("pace_pct")), -_num(d.get("total"))))


def pace_outlier(cal):
    """The upcoming day whose pace is furthest ABOVE the portfolio average, or None.
    Only a real outlier (>= 15 points above the mean and >= 70% booked) qualifies."""
    days = [d for d in (cal or []) if _num((d or {}).get("total")) > 0]
    if len(days) < 7:
        return None
    mean = sum(_num(d.get("pace_pct")) for d in days) / len(days)
    top = max(days, key=lambda d: _num(d.get("pace_pct")))
    pace = _num(top.get("pace_pct"))
    if pace < 70 or (pace - mean) < 15:
        return None
    return {"day": top, "mean": round(mean, 1), "gap": round(pace - mean, 1)}


def near_events(cal, today=None, horizon_days=SEASON_HORIZON):
    """[{'date','name','kind','boost','in_days'}] for events actually coming up.
    De-duplicated by event name, nearest first — never a generic 'it's summer'."""
    today = today or _date.today()
    seen, out = set(), []
    for d in cal or []:
        dd = _pdate((d or {}).get("date"))
        if not dd:
            continue
        in_days = (dd - today).days
        if in_days < 0 or in_days > horizon_days:
            continue
        for e in (d or {}).get("events") or []:
            name = str((e or {}).get("name") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            out.append({"date": d.get("date"), "name": name,
                        "kind": str((e or {}).get("kind") or ""),
                        "boost": _num((e or {}).get("boost"), 1.0),
                        "in_days": in_days})
    out.sort(key=lambda x: x["in_days"])
    return out


def salary_cycle_days(today=None):
    """Days until the Saudi end-of-month salary cycle lifts demand, or None when it
    isn't near. Salaries land around the 27th; the lift runs to the 2nd."""
    today = today or _date.today()
    day = today.day
    if day >= 25:
        # next month's 1st
        nxt = (today.replace(day=28) + timedelta(days=7)).replace(day=1)
        return max(0, (nxt - today).days)
    if day <= 2:
        return 0
    return None


def review_stats(reviews):
    """{'count','avg','five_pct'} over reviews carrying a real 1–5 rating."""
    rated = []
    for r in reviews or []:
        v = _num((r or {}).get("rating"))
        if 1 <= v <= 5:
            rated.append(v)
    if not rated:
        return {"count": 0, "avg": 0.0, "five_pct": 0}
    avg = sum(rated) / len(rated)
    five = sum(1 for v in rated if v >= 5)
    return {"count": len(rated), "avg": round(avg, 2),
            "five_pct": int(round((five / float(len(rated))) * 100))}


# Deliberately SMALL, explicit keyword lists — a tally we can defend, not an NLP guess.
REVIEW_THEMES = (
    ("النظافة", ("نظيف", "نظيفه", "نظافه", "مرتب", "clean", "cleanliness", "spotless", "tidy")),
    ("الموقع", ("الموقع", "موقع", "قريب", "قريبه", "location", "central", "close to")),
    ("التصميم والديكور", ("ديكور", "تصميم", "جميله", "جميل", "انيق", "فخم", "design", "decor",
                          "beautiful", "stylish", "modern", "gorgeous")),
    ("سرعة الرد", ("الرد", "سريع", "سريعه", "تجاوب", "متعاون", "المضيف", "host", "responsive",
                   "communication", "helpful", "quick reply")),
)


def top_theme(reviews):
    """(theme_name, hits, share_pct) for the most repeated compliment, or None.
    Only counts reviews rated 4+, and only wins when it clears the runner-up."""
    tally = {name: 0 for name, _ in REVIEW_THEMES}
    scanned = 0
    for r in reviews or []:
        if _num((r or {}).get("rating")) < 4:
            continue
        text = _norm((r or {}).get("public_review"))
        if not text.strip():
            continue
        scanned += 1
        for name, words in REVIEW_THEMES:
            if any(_norm(w) in text for w in words):
                tally[name] += 1
    if not scanned:
        return None
    ranked = sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))
    name, hits = ranked[0]
    runner = ranked[1][1] if len(ranked) > 1 else 0
    if hits < 3 or hits <= runner:
        return None
    return (name, hits, int(round((hits / float(scanned)) * 100)))


def pick_quote(reviews):
    """{'text','date','channel'} — a genuinely quotable recent 5-star line, or None.
    The guest name is scrubbed here, at the source, so no caller can leak it."""
    best = None
    for r in reviews or []:
        if _num((r or {}).get("rating")) < 5:
            continue
        raw = str((r or {}).get("public_review") or "").strip()
        if not (25 <= len(raw) <= 220):
            continue
        low = raw.lower()
        if "http" in low or "@" in low:
            continue
        text = engine.scrub_names(raw, (r or {}).get("guest_name"))
        cand = {"text": text, "date": str((r or {}).get("date") or "")[:10],
                "channel": str((r or {}).get("channel") or "").strip()}
        if best is None or cand["date"] > best["date"]:
            best = cand
    return best


# ---------------------------------------------------------------------------
# COLLECTORS — pure over a gathered context dict; each returns a list of signals
# ---------------------------------------------------------------------------

def _sig(source, title, fact, detail="", strength=50, as_of="", ref=""):
    return engine.make_signal("internal", source, title, fact, detail=detail,
                              as_of=as_of, strength=strength, ref=ref)


def _keep(out, sig):
    if sig:
        out.append(sig)


def collect_occupancy(ctx):
    """spec D1 — tonight's occupancy, the fullest weekend, a hot unit, lead time."""
    out = []
    today, as_of = ctx["today"], ctx["as_of"]
    occ = tonight_occupancy(ctx["inhouse"], len(ctx["listings"] or {}))
    if occ["total"] and occ["occupied"]:
        _keep(out, _sig(
            "occupancy", "إشغال الليلة",
            "الليلة %s شقة محجوزة من أصل %s — إشغال %s%%."
            % (_n(occ["occupied"]), _n(occ["total"]), _n(occ["pct"])),
            detail="رقم مباشر من نظام الحجوزات لليلة %s." % today.isoformat(),
            strength=70 if occ["pct"] >= 85 else 55, as_of=as_of, ref="occ_tonight"))

    fw = fullest_weekend(ctx["cal"])
    if fw and _num(fw.get("pace_pct")) >= 60:
        _keep(out, _sig(
            "occupancy", "أقرب نهاية أسبوع ممتلئة",
            "نهاية الأسبوع الجاية (%s %s) محجوزة %s%% ومتبقّي %s شقة بس."
            % (_ar_weekday(fw.get("date")), fw.get("date"), _n(fw.get("pace_pct")),
               _n(fw.get("available"))),
            detail="الخميس والجمعة هما نهاية الأسبوع في السعودية — الطلب يرتفع فيهما.",
            strength=65, as_of=as_of, ref="occ_weekend_%s" % fw.get("date")))

    hot = busiest_unit(ctx["res"], today)
    if hot:
        lid, cnt = hot
        _keep(out, _sig(
            "occupancy", "الشقة الأكثر طلباً",
            "«%s» محجوزة %s مرة خلال الشهرين الجايين — أكثر شقة طلباً عندنا."
            % (_unit_name(ctx["listings"], lid), _n(cnt)),
            detail="عدد حجوزات مؤكدة على نفس الوحدة داخل النافذة الأمامية.",
            strength=60, as_of=as_of, ref="occ_hot_%s" % lid))

    lead = median_lead_days(ctx["res"])
    if lead is not None:
        _keep(out, _sig(
            "occupancy", "مدة الحجز قبل الوصول",
            "وسيط المدة بين الحجز والوصول عندنا %s يوم — الناس تحجز في آخر لحظة."
            % _n(lead),
            detail="الوسيط (median) على كل الحجوزات المؤكدة في نافذة ±%s يوم." % WINDOW_DAYS,
            strength=90 if lead <= 2 else 70, as_of=as_of, ref="occ_lead"))
    return out


def collect_pricing(ctx):
    """spec D2 — highest/lowest nightly rate, weekend uplift, pace/event outlier."""
    out = []
    as_of = ctx["as_of"]
    hi, lo = price_extremes(ctx["cal"])
    if hi is not None and lo is not None:
        _keep(out, _sig(
            "pricing", "أعلى وأقل سعر ليلة",
            "أغلى ليلة في التقويم القادم متوسطها %s ر.س (%s) وأرخص ليلة %s ر.س (%s)."
            % (_n(hi.get("avg_price")), hi.get("date"),
               _n(lo.get("avg_price")), lo.get("date")),
            detail="متوسط سعر الليلة للوحدات المتاحة — السعر يتحرك يومياً حسب الطلب.",
            strength=65, as_of=as_of, ref="price_range"))

    up = weekend_uplift_pct(ctx["cal"])
    if up is not None and abs(up) >= 3:
        if up > 0:
            up_fact = ("ليلة الخميس والجمعة أغلى بـ %s%% من ليالي وسط الأسبوع." % _n(up))
        else:
            up_fact = ("ليالي وسط الأسبوع أغلى بـ %s%% من نهاية الأسبوع." % _n(abs(up)))
        _keep(out, _sig(
            "pricing", "فرق سعر نهاية الأسبوع", up_fact,
            detail="مقارنة متوسط سعر ليالي نهاية الأسبوع بمتوسط ليالي وسط الأسبوع "
                   "على %s يوم قادمة." % CAL_DAYS,
            strength=75, as_of=as_of, ref="price_weekend_uplift"))

    po = pace_outlier(ctx["cal"])
    if po:
        d = po["day"]
        names = "، ".join(str((e or {}).get("name") or "") for e in (d.get("events") or []))
        _keep(out, _sig(
            "pricing", "يوم استثنائي في التقويم",
            "يوم %s محجوز %s%% بينما متوسط الأيام %s%% — أعلى يوم عندنا."
            % (d.get("date"), _n(d.get("pace_pct")), _n(po["mean"])),
            detail=("سبب الارتفاع: %s." % names) if names else
                   "قفزة طلب واضحة على هذا التاريخ.",
            strength=70, as_of=as_of, ref="price_pace_%s" % d.get("date")))
    return out


def collect_reviews(ctx):
    """spec D3 — portfolio rating, a quotable 5-star line, the repeated compliment."""
    out = []
    as_of = ctx["as_of"]
    st = review_stats(ctx["reviews"])
    if st["count"] >= 10:
        _keep(out, _sig(
            "reviews", "تقييم عوجا",
            "متوسط تقييمنا %s من ٥ على %s تقييم ضيف حقيقي."
            % (_n(st["avg"]), _n(st["count"])),
            detail="%s%% من التقييمات خمس نجوم." % _n(st["five_pct"]),
            strength=80 if st["avg"] >= 4.7 else 60, as_of=as_of, ref="rev_avg"))

    q = pick_quote(ctx["reviews"])
    if q:
        _keep(out, _sig(
            "reviews", "اقتباس من ضيف",
            "ضيف كتب لنا بالحرف: «%s»." % q["text"],
            detail="تقييم خمس نجوم%s%s."
                   % ((" على " + q["channel"]) if q["channel"] else "",
                      (" بتاريخ " + q["date"]) if q["date"] else ""),
            strength=70, as_of=as_of, ref="rev_quote"))

    th = top_theme(ctx["reviews"])
    if th:
        name, hits, share = th
        _keep(out, _sig(
            "reviews", "أكثر مديح يتكرر",
            "أكثر شي يتكرر في تقييمات ضيوفنا هو %s — ذُكر في %s تقييم (%s%% منها)."
            % (name, _n(hits), _n(share)),
            detail="عدّ مباشر لكلمات المديح في نص التقييمات العامة (٤ نجوم فأعلى).",
            strength=65, as_of=as_of, ref="rev_theme"))
    return out


def collect_ops(ctx):
    """spec D4 — same-day turnovers coming up (checkout + check-in, same unit, same day)."""
    out = []
    as_of = ctx["as_of"]
    tos = same_day_turnovers(ctx["res"], ctx["today"])
    if not tos:
        return out
    first = tos[0]
    _keep(out, _sig(
        "ops", "تسليم واستقبال في نفس اليوم",
        "عندنا %s حالة تنظيف وتجهيز كامل بين خروج ضيف ودخول ضيف في نفس اليوم خلال %s يوم الجاية."
        % (_n(len(tos)), _n(TURNOVER_HORIZON)),
        detail="أقربها «%s» يوم %s — ضيف يطلع الصبح وضيف يدخل بعد الظهر."
               % (_unit_name(ctx["listings"], first["lid"]), first["date"]),
        strength=80, as_of=as_of, ref="ops_turnover"))
    return out


# Saudi demand spikes the owner named. Fixed-date ones we can compute honestly;
# the lunar ones (Eid) only ever come from the calendar's own event rows.
FIXED_SAUDI_DAYS = ((9, 23, "اليوم الوطني السعودي"), (2, 22, "يوم التأسيس"))


def collect_season(ctx):
    """spec D5 — Saudi calendar timing, only when something is genuinely near."""
    out = []
    today, as_of = ctx["today"], ctx["as_of"]

    for ev in near_events(ctx["cal"], today)[:2]:
        boost_txt = ""
        if ev["boost"] and ev["boost"] > 1.0:
            boost_txt = " ونرفع التسعير بنسبة %s%%." % _n((ev["boost"] - 1.0) * 100)
        _keep(out, _sig(
            "season", "موسم قادم: %s" % ev["name"],
            "باقي %s يوم على %s (%s) والطلب على الشقق يبدأ يرتفع من الحين.%s"
            % (_n(ev["in_days"]), ev["name"], ev["date"], boost_txt),
            detail="حدث فعلي في تقويم التسعير عندنا، مو تخمين موسمي.",
            strength=75 if ev["in_days"] <= 21 else 60, as_of=as_of,
            ref="season_%s" % ev["date"]))

    for month, day, name in FIXED_SAUDI_DAYS:
        target = _date(today.year, month, day)
        if target < today:
            target = _date(today.year + 1, month, day)
        in_days = (target - today).days
        if 0 <= in_days <= SEASON_HORIZON:
            _keep(out, _sig(
                "season", name,
                "باقي %s يوم على %s (%s) — من أقوى مواسم الحجز في الرياض."
                % (_n(in_days), name, target.isoformat()),
                detail="تاريخ ثابت في التقويم السعودي.",
                strength=70, as_of=as_of, ref="season_fixed_%s" % target.isoformat()))

    sal = salary_cycle_days(today)
    if sal is not None:
        if sal:
            sal_fact = ("باقي %s يوم على نزول الرواتب — وهي أوضح قفزة طلب شهرية عندنا."
                        % _n(sal))
        else:
            sal_fact = "الرواتب نزلت هالأيام — وهي أوضح قفزة طلب شهرية عندنا."
        _keep(out, _sig(
            "season", "دورة الرواتب", sal_fact,
            detail="نهاية الشهر تحرّك الحجوزات القصيرة داخل الرياض.",
            strength=55, as_of=as_of, ref="season_salary_%s" % today.strftime("%Y-%m")))
    return out


def collect_insider(ctx):
    """spec D6 — a SHORT, honest set of operator truths, grounded in real numbers."""
    out = []
    as_of = ctx["as_of"]
    units = len(ctx["listings"] or {})
    if units:
        _keep(out, _sig(
            "insider", "حجم التشغيل",
            "ندير %s شقة مفروشة في الرياض تحت اسم واحد — كلها دخول ذاتي بدون استقبال."
            % _n(units),
            detail="عدد الوحدات المربوطة فعلياً بنظامنا اليوم.",
            strength=60, as_of=as_of, ref="ins_units"))
        _keep(out, _sig(
            "insider", "قرارات التسعير اليومية",
            "كل يوم نراجع سعر %s ليلة (%s شقة × %s يوم قدام) — السعر ما يثبت أبداً."
            % (_n(units * CAL_DAYS), _n(units), _n(CAL_DAYS)),
            detail="التسعير الديناميكي يمشي على كل وحدة وكل ليلة في النافذة الأمامية.",
            strength=55, as_of=as_of, ref="ins_pricing_ops"))

    lead = median_lead_days(ctx["res"])
    if lead is not None and lead <= 3:
        _keep(out, _sig(
            "insider", "سوق آخر لحظة",
            "سوق الشقق في الرياض سوق «آخر لحظة»: وسيط الحجز عندنا %s يوم قبل الوصول."
            % _n(lead),
            detail="يعني الشقة لازم تكون جاهزة دايماً، مو جاهزة قبل الحجز بأسبوع.",
            strength=70, as_of=as_of, ref="ins_lastminute"))
    return out


COLLECTORS = (
    ("occupancy", collect_occupancy),
    ("pricing", collect_pricing),
    ("reviews", collect_reviews),
    ("ops", collect_ops),
    ("season", collect_season),
    ("insider", collect_insider),
)

SOURCES = tuple(name for name, _ in COLLECTORS)


# ---------------------------------------------------------------------------
# fetch layer + collect()
# ---------------------------------------------------------------------------

def _tap(name, fn, default):
    """Call one read-only data tap. A failing tap yields its empty default so the
    other five collectors still produce signals."""
    try:
        v = fn()
        return default if v is None else v
    except Exception as e:
        print("[studio.internal] tap %s failed: %s" % (name, e))
        return default


def gather(cal_days=CAL_DAYS, window_days=WINDOW_DAYS):
    """Fetch every internal data tap once. THE only network-touching function here."""
    today = _today()
    return {
        "today": today,
        "as_of": today.isoformat(),
        "listings": _tap("listings", lambda: HOST.require("listings")() or {}, {}),
        "inhouse": _tap("inhouse", lambda: HOST.require("inhouse")(today) or [], []),
        "res": _tap("res_window", lambda: HOST.require("res_window")(
            today - timedelta(days=window_days), today + timedelta(days=window_days)) or [], []),
        "cal": _tap("forward_calendar",
                    lambda: HOST.require("forward_calendar")(cal_days) or [], []),
        "reviews": _tap("reviews", lambda: HOST.require("reviews")() or [], []),
    }


def build_signals(ctx, sources=None):
    """Run the collectors over an already-gathered context. Returns (signals, errors).
    One collector raising never stops the others."""
    wanted = set(sources or SOURCES)
    sigs, errors = [], {}
    for name, fn in COLLECTORS:
        if name not in wanted:
            continue
        try:
            for s in fn(ctx) or []:
                if s:
                    sigs.append(s)
        except Exception as e:
            errors[name] = "%s: %s" % (type(e).__name__, e)
            print("[studio.internal] collector %s failed: %s" % (name, e))
    return sigs, errors


def collect(sources=None, cal_days=CAL_DAYS, window_days=WINDOW_DAYS):
    """Gather → collect → novelty-filter → persist → prune. Returns the NEW signals."""
    _p(running=True, phase="gather", done=False, error="", errors={},
       collected=0, kept=0, started_at=_now_iso(), finished_at="")
    fresh = []
    try:
        ctx = gather(cal_days=cal_days, window_days=window_days)
        _p(phase="collect")
        sigs, errors = build_signals(ctx, sources)
        _p(collected=len(sigs), errors=errors, phase="store")

        try:
            recent = list(db.signal_nkeys() or [])
        except Exception as e:
            print("[studio.internal] signal_nkeys failed: %s" % e)
            recent = []

        ts = _now_iso()
        seen_sids = set()
        for s in sigs:
            if s["sid"] in seen_sids:
                continue
            nkey = engine.novelty_key("%s %s" % (s.get("title", ""), s["fact"]))
            if not engine.is_novel(nkey, recent):
                continue
            try:
                db.add_signal(s, nkey=nkey, ts=ts)
            except Exception as e:
                print("[studio.internal] add_signal failed: %s" % e)
                continue
            seen_sids.add(s["sid"])
            recent.append(nkey)
            fresh.append(s)

        try:
            db.prune_signals()
        except Exception as e:
            print("[studio.internal] prune_signals failed: %s" % e)

        _p(running=False, phase="done", done=True, kept=len(fresh), finished_at=_now_iso())
        print("[studio.internal] collected=%s kept=%s errors=%s"
              % (len(sigs), len(fresh), sorted(errors)))
    except Exception as e:
        traceback.print_exc()
        _p(running=False, phase="error", done=True,
           error="%s: %s" % (type(e).__name__, e), finished_at=_now_iso())
    finally:
        try:
            if HOST.save_json:
                HOST.save_json("studio_internal.json", snapshot())
        except Exception:
            pass
    return fresh


def start_collect_thread(**kw):
    """Kick a collection in a daemon thread. False if one is already running."""
    with _lock:
        if PROGRESS.get("running"):
            return False
        PROGRESS["running"] = True

    t = threading.Thread(target=lambda: collect(**kw),
                         name="studio-internal", daemon=True)
    t.start()
    return True
