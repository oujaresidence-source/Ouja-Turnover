# -*- coding: utf-8 -*-
"""
owner_meet.engine — PURE comparison rules. No I/O, no HOST, no clock. TDD-locked
(tests/test_owner_meet_engine.py).

R1 lives here: a peer comparison leaves this module only as a BAND — {p25, p50, p75, value,
pct10, tone, label, scope}. The peer list, its length and every other unit's value stay inside
`peer_bands()`; the count goes to the presenter-only half, never into the band.
"""

from fractions import Fraction

PEER_MIN_DEFAULT = 6

LABEL_TOP = "أعلى من %d٪ من %s"
LABEL_LOW = "أقل من أغلب %s"
LABEL_MID = "ضمن النصف الأوسط من %s"
SCOPE_PEERS = "الشقق المشابهة"
SCOPE_ALL = "شققنا"


# ------------------------------------------------------------------ percentiles
def percentile(value, peers):
    """Share of peers below `value` (ties count half), 0..100. None when undefined."""
    vals = [v for v in peers if v is not None]
    if value is None or not vals:
        return None
    below = sum(1 for v in vals if v < value)
    ties = sum(1 for v in vals if v == value)
    return (below + 0.5 * ties) * 100.0 / len(vals)


def round10(p):
    """Nearest 10, halves up (55 -> 60). R1: a raw percentile can betray the group size."""
    if p is None:
        return None
    return int((Fraction(p).limit_denominator(10 ** 6) / 10 + Fraction(1, 2)) // 1) * 10


def percentile_label(p10, scope="peers", top_at=60, low_at=30):
    """-> (tone, arabic label). tone in top | mid | low. Never a number below `top_at`."""
    where = SCOPE_PEERS if scope == "peers" else SCOPE_ALL
    if p10 is None:
        return None, None
    if p10 >= top_at:
        return "top", LABEL_TOP % (min(p10, 90), where)
    if p10 <= low_at:
        return "low", LABEL_LOW % where
    return "mid", LABEL_MID % where


def quartiles(values):
    """(p25, p50, p75), linear interpolation between order statistics (spreadsheet PERCENTILE)."""
    xs = sorted(v for v in values if v is not None)
    if not xs:
        return None, None, None

    def q(f):
        pos = (len(xs) - 1) * f
        lo = int(pos)
        hi = min(lo + 1, len(xs) - 1)
        return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)

    return q(0.25), q(0.5), q(0.75)


def peer_bands(values_by_lid, unit_lid, peer_lids, portfolio_lids,
               min_peers=PEER_MIN_DEFAULT, top_at=60, low_at=30):
    """One metric -> (band | None, internal).

    values_by_lid : {lid: number|None} for every unit we could measure
    peer_lids     : same-bedroom units active the whole period (the unit itself may be in it)
    portfolio_lids: every unit active the whole period (the fallback group)

    band     : {value, p25, p50, p75, pct10, tone, label, scope}   — owner-safe, no count
    internal : {n, scope, reason}                                  — presenter only
    """
    value = values_by_lid.get(unit_lid)
    if value is None:
        return None, {"n": 0, "scope": None, "reason": "no_value"}

    def group(lids):
        return [values_by_lid.get(l) for l in lids
                if l != unit_lid and values_by_lid.get(l) is not None]

    scope, vals = "peers", group(peer_lids)
    if len(vals) < min_peers:
        scope, vals = "portfolio", group(portfolio_lids)
    if len(vals) < min_peers:
        return None, {"n": len(vals), "scope": scope, "reason": "too_few"}
    p25, p50, p75 = quartiles(vals)
    p10 = round10(percentile(value, vals))
    tone, label = percentile_label(p10, scope, top_at, low_at)
    band = {"value": value, "p25": p25, "p50": p50, "p75": p75,
            "pct10": p10 if (p10 is not None and p10 >= top_at) else None,
            "tone": tone, "label": label, "scope": scope}
    return band, {"n": len(vals), "scope": scope, "reason": None}


def fair_share_index(unit_revpar, median_revpar):
    """Unit RevPAR / comparison-group median RevPAR x 100, an int (halves up). 100 = the unit earns
    exactly its fair share (STR's RevPAR index, our own portfolio as the comp set)."""
    if unit_revpar is None or not median_revpar:
        return None
    r = Fraction(unit_revpar).limit_denominator(10 ** 9) * 100 / Fraction(median_revpar).limit_denominator(10 ** 9)
    return int(r + Fraction(1, 2))


# ------------------------------------------------------------------ exact ratings
def review_raw(r):
    """A review's 10-point score as an int, or None. 0 / empty / junk is NOT a review
    (owner ruling 2026-10-03, same as reviewask.engine.review_score)."""
    v = r.get("rating_raw")
    if v in (None, ""):
        v = (r.get("raw") or {}).get("rating")
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f <= 0:
        return None
    return Fraction(f).limit_denominator(1000)


def rating_stats(reviews):
    """{lid: (n, R)} with R the exact sum of 10-point scores. Mean on 5 = R / (2n)."""
    out = {}
    for r in reviews:
        s = review_raw(r)
        try:
            lid = int(r.get("listing_id") or (r.get("raw") or {}).get("listingMapId"))
        except (TypeError, ValueError):
            continue
        if s is None:
            continue
        n, tot = out.get(lid, (0, Fraction(0)))
        out[lid] = (n + 1, tot + s)
    return out


def rating5(n, R):
    return None if not n else float(R / (2 * n))


# ------------------------------------------------------------------ promotions test split
def promo_split(rows):
    """The October 2026 plan's A/B split (plan PDF p.11), reproduced exactly.

    Group by bedroom count in ascending order; inside each group sort by Gross Booking Value YTD,
    highest first (ties: lower opportunity rank first) and alternate. The starting letter flips
    with each successive bedroom group (1-bed A first, 2-bed B first, 3-bed A first, …), which
    keeps the two halves equal in size. Rows without bedrooms or an Airbnb id are left out.
    -> (a_ids, b_ids) as lists of Airbnb listing ids (strings), in assignment order.
    """
    usable = [r for r in rows if r.get("airbnb_id") and r.get("bedrooms") is not None]
    a, b = [], []
    for gi, br in enumerate(sorted({r["bedrooms"] for r in usable})):
        grp = sorted((r for r in usable if r["bedrooms"] == br),
                     key=lambda r: (-(r.get("gbv_usd") or 0), r.get("rank") or 10 ** 6))
        first_a = (gi % 2 == 0)
        for k, r in enumerate(grp):
            (a if ((k % 2 == 0) == first_a) else b).append(r["airbnb_id"])
    return a, b


def promo_confirmed(rules):
    """The `test` action speaks only after Faisal confirmed group A once (2026-10-06 ruling)."""
    g = (rules or {}).get("promo_test_group_a") or {}
    return bool(g.get("airbnb_ids")) and bool(g.get("confirmed_by")) and bool(g.get("confirmed_at"))


# ------------------------------------------------------------------ the headline (spec §8.1)
WEAKNESS = (("rating", "التقييم"), ("ctr", "صورة الإعلان"), ("page", "صفحة الإعلان"), ("pace", "حجوزات الأسبوعين القادمين"),
            ("occupancy", "الإشغال"), ("adr", "سعر الليلة"))


def weakness(unit, rating_target=4.75):
    """The first weak point, in the owner-approved order: rating below target, then the Airbnb
    funnel actions (cover/title, page, pace), then a low occupancy band, then a low nightly-rate band.
    -> (key, arabic) | (None, None)."""
    r = (unit.get("rating") or {}).get("value")
    if r is not None and r < rating_target:
        return WEAKNESS[0]
    acts = {a.get("key") for a in (unit.get("actions") or [])}
    for key, word in WEAKNESS[1:4]:
        if key in acts:
            return key, word
    peers = unit.get("peers") or {}
    for key, word in WEAKNESS[4:]:
        if (peers.get(key) or {}).get("tone") == "low":
            return key, word
    return None, None


def headline(unit, degraded=False, rating_target=4.75):
    """One sentence for chapter 2, as parts [(text, emphasised)] so the page can colour the key
    phrase. None when the data is degraded — a headline over half the bookings would lie."""
    if degraded:
        return None
    inc = (unit.get("peers") or {}).get("income")
    _wk, w = weakness(unit, rating_target)
    if not inc:
        net = ((unit.get("money") or {}).get("total") or {}).get("owner_net")
        if net is None:
            return None
        return [("صافي شقتك في هذه الفترة ", False), ("{:,}".format(int(round(net))) + " ريال", True)]
    where = "الشقق المشابهة" if inc.get("scope") == "peers" else "شققنا"
    if inc["tone"] == "top":
        head = [("دخل شقتك ", False), ("أعلى من %d٪" % min(inc.get("pct10") or 60, 90), True),
                (" من " + where, False)]
        tail = ("، و%s أول ما نعمل عليه." % w) if w else "، ونعمل على أن تبقى هناك."
    elif inc["tone"] == "mid":
        head = [("دخل شقتك ", False), ("ضمن النصف الأوسط", True), (" بين " + where, False)]
        tail = ("، و%s هو ما يرفعها." % w) if w else "، والهدف أن ننقلها إلى الربع الأعلى."
    else:
        head = [("دخل شقتك ", False), ("أقل من أغلب " + where, True)]
        tail = ("، ونبدأ من %s." % w) if w else "، وهذه خطتنا لرفعه."
    return head + [(tail, False)]


# ------------------------------------------------------------------ the Airbnb funnel (chapter 6)
def funnel(row):
    """Per 10,000 search appearances: views = 10,000·s/v, bookings = 10,000·s, where s = search→booking
    and v = view→booking (both YTD, as Airbnb reports them). None when either rate is missing/zero."""
    s, v = (row or {}).get("search_to_booking"), (row or {}).get("view_to_booking")
    if not s or not v:
        return None
    return {"appear": 10000, "views": round(10000.0 * s / v), "bookings": round(10000.0 * s, 1),
            "ctr100": round(100.0 * s / v, 1), "conv": round(100.0 * v, 2)}


def funnel_peers(rows, me, min_peers=PEER_MIN_DEFAULT):
    """Median funnel of comparable listings in the SAME report (same bedrooms; < min → all), plus the
    lowest-quarter cut-offs the ctr/page actions use. -> (peer, internal) — no count in `peer`."""
    def group(pred):
        return [f for f in (funnel(r) for r in rows if r is not me and r.get("airbnb_id") != (me or {}).get("airbnb_id")
                                         and pred(r)) if f]
    scope, g = "peers", group(lambda r: r.get("bedrooms") == (me or {}).get("bedrooms"))
    if len(g) < min_peers:
        scope, g = "portfolio", group(lambda r: True)
    if len(g) < min_peers:
        return None, {"n": len(g), "scope": scope}
    q = lambda key: quartiles([f[key] for f in g])
    ctr, conv, views, book = q("ctr100"), q("conv"), q("views"), q("bookings")
    return ({"views": round(views[1]), "bookings": round(book[1], 1), "ctr100": round(ctr[1], 1), "conv": round(conv[1], 2),
             "ctr_p25": ctr[0], "conv_p25": conv[0], "scope": scope}, {"n": len(g), "scope": scope})


# ------------------------------------------------------------------ actions (spec §8.2)
ACTION_ROLE = {"rate": "مدير الحساب", "new": "مدير الحساب", "ctr": "المحتوى", "page": "المنصة", "pace": "المنصة",
               "maint_open": "العمليات", "rr_open": "التعويضات", "permit": "العمليات", "floor": "المنصة", "test": "المنصة"}
ACTION_ORDER = ("rate", "new", "ctr", "page", "pace", "maint_open", "rr_open", "permit", "floor", "test")


def _pct(x, nd=1):
    return ("%." + str(nd) + "f") % (x * 100.0) if x is not None else "—"


def actions(ctx, rules, today):
    """ctx keys: rating (lifetime, 5-scale), bookings_365, funnel, peer_funnel, income_tone, open14,
    maint_open, rr_open (list of {deadline}), permit ({days_left, end_date} | None), min_price,
    in_test_group (bool, already AND-ed with the confirmation).
    -> [{key, owner_text, evidence, due, role, side, internal_note}] in the owner-approved order."""
    import datetime
    th = rules.get("thresholds") or {}
    out = []

    def due(days):
        return (today + datetime.timedelta(days=days)).isoformat()

    def add(key, owner_text, evidence, d, side="ouja", note=""):
        out.append({"key": key, "owner_text": owner_text, "evidence": evidence, "due": d, "role": ACTION_ROLE[key],
                    "side": side, "internal_note": note})

    r = ctx.get("rating")
    if r is not None and r < float(th.get("rate_below", 4.75)):
        add("rate", "نرفع تقييم الشقة: نتواصل مع كل ضيف عند مغادرته، ونعالج سبب آخر التقييمات الأقل من خمس نجوم.",
            "التقييم %.2f والهدف أعلى من %.2f" % (r, float(th.get("rate_below", 4.75))), due(30))
    b = ctx.get("bookings_365")
    if b is not None and b < int(th.get("new_bookings_365_below", 25)):
        add("new", "نبني أول عشرة تقييمات للشقة قبل أي خصم إضافي.", "%d حجزاً في آخر 365 يوماً" % b, due(60))
    f, pf = ctx.get("funnel"), ctx.get("peer_funnel")
    if f and pf and f["ctr100"] <= pf["ctr_p25"]:
        add("ctr", "صورة غلاف جديدة وعنوان جديد يبدأ بـ «Ouja |» ويذكر الدخول الذاتي، في أقل من خمسين حرفاً.",
            "يفتح الإعلانَ %.1f من كل 100 ظهور في البحث، والوسيط %.1f" % (f["ctr100"], pf["ctr100"]), due(14))
    if f and pf and f["conv"] <= pf["conv_p25"] and ctx.get("income_tone") in ("low", "mid"):
        add("page", "نراجع سعر الشقة مقارنة بالشقق المشابهة، ونعيد ترتيب الصور.",
            "يحجز %.2f٪ ممن يفتحون الإعلان، والوسيط %.2f٪" % (f["conv"], pf["conv"]), due(14))
    o = ctx.get("open14")
    if o is not None and o >= int(th.get("pace_open_of_14", 13)):
        add("pace", "مراجعة يومية لسعر الليالي المفتوحة في الأسبوعين القادمين.",
            "%d من 14 ليلة قادمة غير محجوزة" % o, due(1))
    mo = ctx.get("maint_open") or 0
    if mo:
        add("maint_open", "نغلق تذاكر الصيانة المفتوحة ونرسل لك صورة بعد الإصلاح.", "%d تذكرة مفتوحة الآن" % mo, due(7))
    rr = ctx.get("rr_open") or []
    if rr:
        dls = sorted(x["deadline"]["date"] for x in rr if x.get("deadline"))
        add("rr_open", "نتابع طلب التعويض حتى يصل رد Airbnb.", "%d طلب قيد المراجعة" % len(rr), dls[0] if dls else due(14))
    pm = ctx.get("permit")
    lim = int(th.get("permit_days", 90))
    if pm is None:
        add("permit", "تصريح وزارة السياحة للشقة باسمك: نحتاج صورة التصريح الحالي لنسجّله ونتابع تجديده.",
            "التصريح غير مسجّل لدينا", due(14), side="owner")
    elif pm.get("days_left") is not None and pm["days_left"] <= lim:
        end = datetime.date.fromisoformat(str(pm["end_date"])[:10]) if pm.get("end_date") else today
        add("permit", "تجديد تصريح وزارة السياحة باسمك: نحتاج مستندات التجديد قبل الموعد.",
            "باقي %d يوماً على انتهاء التصريح" % pm["days_left"],
            max(today, end - datetime.timedelta(days=30)).isoformat(), side="owner")
    if not ctx.get("min_price"):
        add("floor", "نضع حداً أدنى لسعر الليلة يحمي الشقة من تراكم خصومات المنصة.", "لا يوجد حد أدنى مسجّل لسعر الشقة", due(7))
    if ctx.get("in_test_group"):
        g = rules.get("promo_test_group_a") or {}
        add("test", "تجربة خصم مدروسة لمدة 45 يوماً، نقيس أثرها ونوقفها في اليوم الحادي والعشرين إذا لم ترفع دخل الشقة.",
            "الشقة ضمن تجربة الخصومات المدروسة", g.get("starts") or due(30),
            note="المجموعة A — لا تذكر المجموعة B للمالك")
    return out


# ------------------------------------------------------------------ forecast (spec §8.3)
def forecast(trailing, ly_trailing, ly_next, triggered, rules, season_next):
    """trailing: the last three FULL months' owner net (oldest first). ly_*: the same months a year
    earlier and the coming quarter a year earlier (None where unknown). -> dict | None."""
    if len(trailing) < 3 or any(x is None for x in trailing):
        return None
    base = sum(trailing)
    method = "pace"
    if (ly_trailing and ly_next and len(ly_trailing) == 3 and len(ly_next) == 3
            and all(x is not None for x in ly_trailing + ly_next) and sum(ly_trailing) > 0):
        base = sum(ly_next) * sum(trailing) / float(sum(ly_trailing))
        method = "seasonal"
    up = rules.get("uplifts_pct") or {}
    items = [{"key": k, "pct": float(up[k])} for k in ACTION_ORDER if k in triggered and k in up]
    if season_next and "season" in up:
        items.append({"key": "season", "pct": float(up["season"])})
    raw = sum(i["pct"] for i in items)
    cap = float(rules.get("uplift_total_cap_pct", 15))
    total = min(raw, cap)
    return {"base": round(base, 2), "target": round(base * (1 + total / 100.0), 2), "method": method,
            "uplifts": items, "total_pct": total, "capped": raw > cap}


# ------------------------------------------------------------------ discount stacking (presenter only)
def discount_stack(row, rules):
    """Airbnb applies ONE of new-listing / custom / length-of-stay / early-bird / last-minute per night,
    then stacks top-rated-guest and non-refundable on top. Worst case = the biggest current one-of
    discount, plus every stacking discount the listing is eligible for. -> dict."""
    row = row or {}
    one = [x for x in (row.get("weekly_current"), row.get("monthly_current"), row.get("early_bird_current"),
                       row.get("last_minute_current")) if x]
    worst_one = max(one) if one else 0.0
    trg = float(rules.get("trg_pct", 15)) / 100.0 if row.get("trg_eligible") else 0.0
    nr = float(rules.get("nonref_pct", 10)) / 100.0 if row.get("nonref_eligible") else 0.0
    combined = 1 - (1 - worst_one) * (1 - trg) * (1 - nr)
    ceiling = float(rules.get("discount_ceiling_pct", 30)) / 100.0
    return {"one_of": round(worst_one, 4), "trg": trg, "nonref": nr, "combined": round(combined, 4),
            "ceiling": ceiling, "warn": combined > ceiling}
