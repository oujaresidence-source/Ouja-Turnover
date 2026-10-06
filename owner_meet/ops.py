# -*- coding: utf-8 -*-
"""
owner_meet.ops — PURE joins of the unit's operational record (chapters 7–10). No I/O, no HOST:
snapshot.py fetches the raw rows through caps and hands them here with a Redactor.

Every function returns an OWNER half (redacted, no person, no code) and, where needed, a
PRESENTER half (private feedback, untranslated answers). Sources for each record are printed as a
role — «الضيف» / «فريق عوجا» / «مكالمة تقييم» — never as a person (R4).
"""

import datetime
import re
from fractions import Fraction

from . import engine
from .redact import first_name

AIRCOVER_DAYS = 14

SOURCE_AR = {"guest": "الضيف", "team": "فريق عوجا", "review": "مكالمة تقييم"}
CHIP_AR = {"full": "استُلم كاملاً", "partial": "استُلم جزئياً", "denied": "رُفض", "received": "استُلم",
           "open": "قيد المراجعة"}
PAYER_AR = {"ouja": "الإصلاح على حساب عوجا", "owner": "الإصلاح على حساب المالك", "none": "لا يوجد إصلاح مدفوع"}
SUBSCORE_AR = (("cleanliness", "النظافة"), ("accuracy", "دقة الوصف"), ("checkin", "تسجيل الدخول"),
               ("communication", "التواصل"), ("location", "الموقع"), ("value", "القيمة"))
CLOSED_RR = ("paid", "denied", "closed")


_AR = chr(0x0600) + "-" + chr(0x06FF)
_KEEP = re.compile("[^A-Za-z0-9" + _AR + " ،,.()/+-]")


def clean_label(text):
    """A label as words only: emoji and pictographs off (an owner page carries no emoji)."""
    return " ".join(_KEEP.sub("", str(text or "")).split())


def _category(c):
    c = clean_label(c)
    return c if re.search("[" + _AR + "]", c) else ("صيانة" if c else "")


# ------------------------------------------------------------------ time helpers
def _dt(v):
    if not v:
        return None
    try:
        s = str(v).replace("Z", "+00:00")
        d = datetime.datetime.fromisoformat(s[:32])
    except ValueError:
        try:
            d = datetime.datetime.fromisoformat(str(v)[:10])
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=3)))
    return d


def _day(v):
    d = _dt(v)
    return d.date().isoformat() if d else None


def _in(day, start, end):
    return bool(day) and str(start)[:10] <= day <= str(end)[:10]


def _num(v):
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    digits = "".join(ch for ch in str(v) if ch.isdigit() or ch == ".")
    try:
        return float(digits) if digits and digits != "." else None
    except ValueError:
        return None


def _median(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2.0


# ------------------------------------------------------------------ maintenance (chapter 8)
def _source(rec, dash):
    if (rec or {}).get("origin") == "review_call" or (dash or {}).get("source") == "review":
        return "review"
    if (dash or {}).get("source") == "escalation" or (dash or {}).get("guest"):
        return "guest"
    return "team"


def maintenance(dtk_recs, dash_rows, start, end, now, redactor):
    """dtk_recs: _dtk maint records for the unit; dash_rows: the unit's dashboard tickets (the
    tracker). A Discord ticket and its dashboard twin (linked by dash_id) count ONCE. Included: every
    ticket opened inside the period, plus any still open at the period end (carried over)."""
    dash_by_id = {d.get("id"): d for d in dash_rows if d.get("id")}
    linked = set()
    rows = []

    def add(created, closed, status_open, category, summary, src, cost):
        cday = _day(created)
        if not cday or cday > str(end)[:10]:
            return
        if not (_in(cday, start, end) or status_open):
            return
        hours = None
        if not status_open and _dt(created) and _dt(closed):
            hours = max(0.0, (_dt(closed) - _dt(created)).total_seconds() / 3600.0)
        rows.append({"date": cday, "category": _category(category), "summary": redactor(summary) or "",
                     "source": src, "source_ar": SOURCE_AR[src], "open": status_open,
                     "hours": None if hours is None else round(hours, 1),
                     "cost": cost if (cost is not None and cost > 0) else None})

    for r in dtk_recs:
        d = dash_by_id.get(r.get("dash_id")) or {}
        if r.get("dash_id"):
            if r["dash_id"] in linked:
                continue
            linked.add(r["dash_id"])
        is_open = r.get("status") != "closed"
        add(r.get("created_at"), r.get("closed_at"), is_open, r.get("category") or d.get("category"),
            r.get("summary") or d.get("title"), _source(r, d), _num(d.get("cost")))
    for d in dash_rows:
        if d.get("id") in linked or d.get("status") == "cancelled":
            continue
        is_open = d.get("status") in ("open", "in_progress")
        log = [x for x in (d.get("log") or []) if isinstance(x, dict) and x.get("ts")]
        closed = d.get("closed_at") or (log[-1]["ts"] if (log and not is_open) else None)
        add(d.get("created_at"), closed, is_open, d.get("category"), d.get("title"), _source(None, d), _num(d.get("cost")))
    rows.sort(key=lambda x: x["date"], reverse=True)
    n = len(rows)
    team = sum(1 for x in rows if x["source"] == "team")
    stats = {"count": n, "open_now": sum(1 for x in rows if x["open"]),
             "median_hours": _median([x["hours"] for x in rows if x["hours"] is not None]),
             "total_cost": round(sum(x["cost"] or 0 for x in rows), 2),
             "team_share": (round(team * 100.0 / n) if n else None)}
    return rows, stats


def purchases(proc_recs, start, end, redactor):
    out = []
    for r in proc_recs:
        day = _day(r.get("created_at"))
        if not _in(day, start, end):
            continue
        out.append({"date": day, "items": redactor(r.get("items") or r.get("reason") or ""),
                    "amount": _num(r.get("amount_raw")), "done": r.get("status") == "closed"})
    out.sort(key=lambda x: x["date"], reverse=True)
    return out


# ------------------------------------------------------------------ reimbursements (chapter 9)
def claims(rr_recs, start, end, now, outcome_fn, item_lines_fn, ar_texts_fn, types_ar, redactor):
    """-> (owner_rows, ring, presenter_notes). Never the reservation code, the guest or a person."""
    rows, notes = [], []
    today = (now.date() if hasattr(now, "date") else now)
    for r in rr_recs:
        co = r.get("closeout") or {}
        closed = r.get("status") in CLOSED_RR or bool(co.get("at"))
        cday = _day(r.get("created_at"))
        if not cday or cday > str(end)[:10]:
            continue
        if not (_in(cday, start, end) or not closed):
            continue
        claimed = _num(co.get("claimed")) if co.get("claimed") not in (None, "") else _num(r.get("total_raw"))
        received = _num(co.get("received")) if closed else None
        outcome = outcome_fn(claimed, received) if closed else "open"
        chip = "full" if outcome in ("full", "over") else outcome
        if chip not in CHIP_AR:
            chip = "open" if not closed else "received"
        lines, hidden = item_lines_fn(r.get("items_raw") or "")
        answer = None
        if closed and (co.get("less_reason") or co.get("note")):
            t = ar_texts_fn(r) or {}
            if t.get("ok"):
                answer = redactor(" ".join(x for x in (t.get("reason"), t.get("note")) if x)) or None
            else:
                notes.append({"key": "rr_translation", "text_ar": "رد Airbnb على طلب تعويض بتاريخ %s لم يُترجم — راجعه قبل العرض" % cday})
        deadline = None
        dep = _dt(r.get("departure"))
        if not closed and dep:
            dl = dep.date() + datetime.timedelta(days=AIRCOVER_DAYS)
            deadline = {"date": dl.isoformat(), "days_left": (dl - today).days}
        rows.append({"date": cday, "type_ar": clean_label(types_ar.get(r.get("type"), types_ar.get("other", "أخرى"))),
                     "items": [redactor(x) for x in (lines or []) if redactor(x)], "items_hidden": hidden or 0,
                     "claimed": claimed, "received": received, "chip": chip, "chip_ar": CHIP_AR[chip],
                     "payer_ar": PAYER_AR.get(co.get("payer")) if closed else None,
                     "answer_ar": answer, "deadline": deadline, "closed": closed})
    rows.sort(key=lambda x: x["date"], reverse=True)
    done = [x for x in rows if x["closed"] and x["claimed"]]
    c = round(sum(x["claimed"] for x in done), 2)
    g = round(sum(x["received"] or 0 for x in done), 2)
    ring = {"claimed": c, "received": g, "rate": (round(g / c, 4) if c else None), "closed": len(done),
            "open": sum(1 for x in rows if not x["closed"]),
            "claimed_all": round(sum(x["claimed"] or 0 for x in rows), 2)}
    return rows, ring, notes


# ------------------------------------------------------------------ reviews (chapter 10)
def _cats(r):
    raw = r.get("raw") or {}
    for key in ("reviewCategory", "reviewCategories", "categories"):
        v = raw.get(key)
        if isinstance(v, list) and v:
            return v
    return []


def reviews(all_reviews, lid, start, end, followed, redactor, rating_target=4.75):
    """-> (owner_rows, summary, private_rows). Only reviews with a real score (>0) count."""
    rows, private, cats = [], [], {}
    n, R = 0, Fraction(0)
    for r in all_reviews:
        try:
            rl = int(r.get("listing_id") or (r.get("raw") or {}).get("listingMapId"))
        except (TypeError, ValueError):
            continue
        if rl != int(lid):
            continue
        s = engine.review_raw(r)
        day = _day(r.get("date") or (r.get("raw") or {}).get("submittedAt") or (r.get("raw") or {}).get("departureDate"))
        if s is None or not _in(day, start, end):
            continue
        n += 1
        R += s
        res = str(r.get("reservation_id") or (r.get("raw") or {}).get("reservationId") or "")
        rows.append({"date": day, "stars": round(float(s) / 2.0, 1), "first_name": first_name(r.get("guest_name")) or "ضيف",
                     "text": redactor((r.get("public_review") or "").strip()) or "",
                     "followed": "تابعنا مع الضيف بعد المغادرة" if res and res in followed else None})
        if (r.get("private_review") or "").strip():
            private.append({"date": day, "stars": round(float(s) / 2.0, 1), "text": r["private_review"].strip()})
        for c in _cats(r):
            name = str(c.get("category") or c.get("categoryName") or "").lower().replace("_", "").replace("-", "")
            try:
                v = float(c.get("rating"))
            except (TypeError, ValueError):
                continue
            if v > 0:
                cats.setdefault(name, []).append(v)
    rows.sort(key=lambda x: x["date"], reverse=True)
    private.sort(key=lambda x: x["date"], reverse=True)
    sub = []
    for key, ar in SUBSCORE_AR:
        vs = cats.get(key) or cats.get(key.replace("checkin", "check_in"))
        if vs:
            avg = sum(vs) / len(vs)
            sub.append({"key": key, "label": ar, "value": round(avg / 2.0 if avg > 5 else avg, 2)})
    mean = engine.rating5(n, R)
    return rows, {"count": n, "mean": None if mean is None else round(mean, 2), "target": rating_target,
                  "subscores": sub}, private


# ------------------------------------------------------------------ the unit log (chapter 7)
def price_weeks(entries):
    """Non-dry price changes grouped by ISO week of the NIGHT changed -> [{date, nights}]."""
    weeks = {}
    for e in entries:
        d = _dt(e.get("night"))
        if not d:
            continue
        monday = (d.date() - datetime.timedelta(days=d.weekday())).isoformat()
        weeks.setdefault(monday, set()).add(e.get("night"))
    return [{"date": k, "nights": len(v)} for k, v in sorted(weeks.items(), reverse=True)]


def timeline(maint_rows, purchases_rows, claim_rows, review_rows, recovery_rows, price_rows, permit,
             directpay_rows, cleaning_rows, start, end):
    """-> (events newest first, counters). Every event is a role-level sentence, never a person."""
    ev = []
    for m in maint_rows:
        ev.append({"date": m["date"], "kind": "maint", "text": "صيانة · %s%s" % (
            m["category"] or "بلاغ", ("، " + m["summary"]) if m["summary"] else "")})
    for p in purchases_rows:
        ev.append({"date": p["date"], "kind": "proc", "text": "شراء للشقة" + ((" · " + p["items"]) if p["items"] else "")})
    for c in claim_rows:
        ev.append({"date": c["date"], "kind": "rr", "text": "طلب تعويض · %s · %s" % (c["type_ar"], c["chip_ar"])})
    for r in review_rows:
        ev.append({"date": r["date"], "kind": "review", "text": "تقييم %s من 5" % (("%g" % r["stars"]))})
    for r in recovery_rows:
        day = _day(r.get("created_at"))
        if _in(day, start, end):
            ev.append({"date": day, "kind": "recovery", "text": "اتصلنا بضيف بعد ملاحظة على إقامته"
                       + (" وتابعنا حتى الحل" if r.get("resolved_at") else "")})
    for w in price_rows:
        ev.append({"date": w["date"], "kind": "price", "text": "مراجعة سعر %d ليلة" % w["nights"]})
    if permit and permit.get("end_date") and _in(str(permit["end_date"])[:10], start, end):
        ev.append({"date": str(permit["end_date"])[:10], "kind": "permit", "text": "موعد تجديد تصريح وزارة السياحة"})
    for d in directpay_rows:
        day = str(d.get("arrival") or "")[:10]
        if _in(day, start, end):
            ev.append({"date": day, "kind": "direct", "text": "حجز مباشر"
                       + (" · مُحصّل" if d.get("status") == "verified" else "")})
    ev.sort(key=lambda x: (x["date"], x["kind"]), reverse=True)
    scores = [float(c["score"]) for c in cleaning_rows if c.get("score")]
    counters = {"maint": len(maint_rows), "rr": len(claim_rows), "reviews": len(review_rows),
                "price_nights": sum(w["nights"] for w in price_rows), "recovery": len(recovery_rows),
                "direct": len(directpay_rows),
                "direct_collected": round(sum(float(d.get("received_sar") or 0) for d in directpay_rows
                                              if d.get("status") == "verified"), 2),
                "cleaning_score": (round(sum(scores) / len(scores), 2) if scores else None),
                "cleaning_count": len(scores)}
    return ev, counters
