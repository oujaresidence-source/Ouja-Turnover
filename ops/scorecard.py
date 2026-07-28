# -*- coding: utf-8 -*-
"""
ops.scorecard — PHASE 3 «كرت التقييم»: the monthly 1-5 scorecard.

THE ATTRIBUTION RULE (spec §3.1), and why it looks the way it does
    A live API dump proved Hostaway CANNOT tell us which human sent a reply: every outgoing
    message has sentUsingHostaway=0 and userId=null, because the team replies inside Airbnb.
    There is no field for it. So this module NEVER tries to identify a sender. It attributes
    by OWNERSHIP: for anything that happens on apartment X at time T, the responsible person
    is whoever schedule.engine.compute_day(T) assigns X to — the owner if working, the coverer
    if the owner is off. We measure whether YOUR units' guests were handled on YOUR watch.

THREE FAIRNESS RULES, all non-negotiable (spec §3.3)
  a. NORMALIZE BY LOAD. Every rate is PER APARTMENT UNDER MANAGEMENT that day. Loads differ
     hugely (12 apartments vs 8); absolute totals would make the hardest-working person score
     worst.
  b. COVERAGE ONLY ADDS. Covering a colleague can raise a score and can never lower it. If
     coverage days hurt, people stop covering and the roster collapses.
  c. MISSING DATA IS NOT A LOW SCORE. A line with no data — or below the minimum sample —
     renders «بيانات ناقصة» and its weight is REDISTRIBUTED across the remaining lines. Never
     score a zero for a gap that is our own instrumentation's fault.

FIXED STANDARDS, NOT RANKING (spec §3.4)
    Thresholds are absolute, published in advance, identical for everyone. All six people can
    score 5 in the same month. There is deliberately no forced distribution anywhere in this
    file: in a team of six, ranking guarantees somebody is last every month no matter how well
    they did, which destroys the mutual coverage the roster depends on.

MONEY (spec §3.5)
    The scorecard produces a BONUS multiplier only, on top of whatever commission survived
    Phase 1. `bonus_multiplier` can never return a value below 1.0. A low score is a
    conversation and an input to raises — never a deduction.
"""

import datetime
import json
import os

from . import db, engine
from .host import HOST

# ------------------------------------------------------------------ the six lines

# key, Arabic label, weight. «التغطية» is a BONUS: it is not part of the 100 and can only add.
LINES = (
    ("response",   "الاستجابة على وحداتك", 25),
    ("escalation", "التصعيد",             25),
    ("turnover",   "إغلاق التسليم",        20),
    ("compliance", "الالتزام",             15),
    ("review",     "رأي الضيف",            10),
)
COVERAGE_BONUS_MAX = 5           # percentage points, ADD ONLY

# Hostaway review sub-scores. Location and value are pricing and portfolio decisions, not
# field-manager work, so they are EXCLUDED — as is respect_house_rules, which is us rating
# the guest, not the guest rating us.
REVIEW_INCLUDE = ("cleanliness", "communication", "checkin", "check_in", "accuracy")
REVIEW_EXCLUDE = ("location", "value", "respect_house_rules")

MISSING_AR = "بيانات ناقصة"


# ------------------------------------------------------------------ env

def _env(name, default=""):
    return (os.environ.get(name, default) or default).strip()


def _int(name, default):
    try:
        return int(_env(name, str(default)))
    except Exception:
        return default


def enabled():
    return _env("SCORECARD_ENABLED", "1") == "1"


def dryrun():
    """DEFAULT ON. Nothing is released to any employee until the owner turns this off AND
    approves the month."""
    return _env("SCORECARD_DRYRUN", "1") == "1"


def min_sample():
    return _int("SCORECARD_MIN_SAMPLE", 5)


def work_start():
    return _int("SCORECARD_WORK_START", 11)


def work_end():
    """01:30 next day — stored as the hour 1; the half hour is fixed by the spec."""
    return _int("SCORECARD_WORK_END", 1)


# ================================================================== PURE SCORING
# Everything in this block is pure: no database, no clock, no network. The tests drive it
# directly, so the rules that decide somebody's bonus are provable without a bot running.

def in_working_hours(when, start=11, end=1, end_minute=30):
    """The team's working window, 11:00 → 01:30 the NEXT day. Anything outside it is not
    counted for or against anybody: nobody is scored on being asleep."""
    h, m = when.hour, when.minute
    if h >= start:
        return True
    if h < end:
        return True
    if h == end:
        return m <= end_minute
    return False


def per_apartment_rate(count, apartment_days):
    """RULE (a): every rate is per apartment under management that day.

    Two people with identical per-apartment performance and different loads must score the
    same — so the denominator is apartment-days, never the raw event count."""
    if not apartment_days:
        return None                      # no load = no opinion, NOT a zero
    return float(count) / float(apartment_days)


def score_from_thresholds(value, thresholds):
    """FIXED STANDARDS. `thresholds` is 4 cut-offs, best first, e.g. (0.95, 0.90, 0.80, 0.70):
    >= the first scores 5, then 4, 3, 2, and anything below scores 1.

    Absolute and published in advance — all six people can score 5 in the same month."""
    if value is None:
        return None
    for i, cut in enumerate(thresholds):
        if value >= cut:
            return 5 - i
    return 1


# The published standards. Same for everybody, every month.
THRESHOLDS = {
    "response":   (0.95, 0.90, 0.80, 0.65),    # share answered inside the target
    "escalation": (0.95, 0.85, 0.75, 0.60),    # share of your units' escalations you took
    "turnover":   (0.98, 0.95, 0.90, 0.80),    # share closed with photo before check-in
    "compliance": (1.00, 0.95, 0.85, 0.70),    # weekly reports filed, warnings clean
    "review":     (9.50, 9.00, 8.50, 8.00),    # Hostaway sub-score average, out of 10
}


def redistribute(scored):
    """RULE (c): drop the lines with no data and spread their weight over the rest, so the
    weights always total 100. A gap in OUR instrumentation must never read as a bad month.

    `scored` = [{key, score|None, weight}]. Returns the same list with an effective weight
    on each, plus the total (100 when anything at all is present, 0 when nothing is)."""
    present = [s for s in scored if s.get("score") is not None]
    missing = [s for s in scored if s.get("score") is None]
    base = sum(s["weight"] for s in present)
    out = []
    for s in scored:
        e = dict(s)
        if s.get("score") is None:
            e["effective_weight"] = 0
            e["label_ar"] = MISSING_AR
        else:
            # keep the ratio between the surviving lines, scaled back up to 100
            e["effective_weight"] = round(100.0 * s["weight"] / base, 4) if base else 0
        out.append(e)
    return {"lines": out, "total_weight": round(sum(x["effective_weight"] for x in out), 4),
            "missing": [m["key"] for m in missing]}


def weighted_score(scored):
    """The 1-5 headline. None when every single line is missing — a person we know nothing
    about does not get a number."""
    r = redistribute(scored)
    present = [s for s in r["lines"] if s.get("score") is not None]
    if not present:
        return None, r
    total = sum(s["score"] * s["effective_weight"] for s in present)
    return round(total / 100.0, 2), r


def coverage_bonus(coverage_days, working_days, cap=COVERAGE_BONUS_MAX):
    """RULE (b): COVERAGE ONLY ADDS. This returns points to ADD, never to subtract, and it is
    clamped at zero from below however strange the inputs are."""
    if not working_days:
        return 0.0
    share = max(0.0, float(coverage_days) / float(working_days))
    return round(min(cap, cap * share), 2)


def bonus_multiplier(score, bonus_points=0.0):
    """MONEY: a bonus multiplier ONLY. Never below 1.0, whatever the score.

    A low score is a conversation and an input to raises and promotion — not a deduction.
    Phase 1 is the only place money is ever taken away, and it is capped there."""
    if score is None:
        return 1.0
    over = max(0.0, float(score) - 3.0)          # 3/5 is "meeting the standard"
    return round(1.0 + (over / 2.0) * 0.10 + (float(bonus_points or 0) / 100.0), 4)


def review_average(reviews):
    """Hostaway sub-scores, cleanliness + communication + check-in/accuracy ONLY.

    Location and value are pricing and portfolio decisions the field manager does not
    control, so scoring them would be scoring somebody for our own choices."""
    vals = []
    for r in reviews or []:
        for cat, rating in (r or {}).items():
            c = str(cat).strip().lower()
            if c in REVIEW_EXCLUDE or c not in REVIEW_INCLUDE:
                continue
            try:
                vals.append(float(rating))
            except (TypeError, ValueError):
                continue
    return (sum(vals) / len(vals)) if vals else None


def line_score(key, value, sample, minimum):
    """One line: below the minimum sample it is EXCLUDED (score None), not scored badly."""
    if value is None or sample is None or sample < minimum:
        return None
    return score_from_thresholds(value, THRESHOLDS[key])


def build(person, facts, minimum=5):
    """Assemble one person's card from already-gathered facts. Pure.

    facts = {
      apartment_days, working_days, coverage_days,
      response: {answered, total}, escalation: {taken, total},
      turnover: {closed_before_checkin, total},
      compliance: {filed, expected, active_warnings},
      reviews: [ {category: rating, ...}, ... ],
    }
    """
    f = facts or {}
    scored = []

    resp = f.get("response") or {}
    scored.append({"key": "response", "weight": 25,
                   "score": line_score("response", _share(resp.get("answered"), resp.get("total")),
                                       resp.get("total"), minimum),
                   "sample": resp.get("total") or 0})

    esc = f.get("escalation") or {}
    scored.append({"key": "escalation", "weight": 25,
                   "score": line_score("escalation", _share(esc.get("taken"), esc.get("total")),
                                       esc.get("total"), minimum),
                   "sample": esc.get("total") or 0})

    tn = f.get("turnover") or {}
    scored.append({"key": "turnover", "weight": 20,
                   "score": line_score("turnover",
                                       _share(tn.get("closed_before_checkin"), tn.get("total")),
                                       tn.get("total"), minimum),
                   "sample": tn.get("total") or 0})

    cp = f.get("compliance") or {}
    # compliance has no minimum sample: four weeks in a month is the whole population, and
    # it is the one line where the data is definitely ours and definitely complete.
    cp_val = _share(cp.get("filed"), cp.get("expected"))
    if cp_val is not None and cp.get("active_warnings"):
        cp_val = max(0.0, cp_val - 0.15 * int(cp["active_warnings"]))
    scored.append({"key": "compliance", "weight": 15,
                   "score": (score_from_thresholds(cp_val, THRESHOLDS["compliance"])
                             if cp.get("expected") else None),
                   "sample": cp.get("expected") or 0})

    revs = f.get("reviews") or []
    scored.append({"key": "review", "weight": 10,
                   "score": line_score("review", review_average(revs), len(revs), minimum),
                   "sample": len(revs)})

    score, dist = weighted_score(scored)
    bonus = coverage_bonus(f.get("coverage_days", 0), f.get("working_days", 0))
    labels = dict((k, ar) for k, ar, _w in LINES)
    for ln in dist["lines"]:
        ln["label"] = labels.get(ln["key"], ln["key"])
    return {
        "employee": person,
        "score": score,
        "lines": dist["lines"],
        "missing": dist["missing"],
        "total_weight": dist["total_weight"],
        "coverage_bonus": bonus,
        "multiplier": bonus_multiplier(score, bonus),
        "apartment_days": f.get("apartment_days", 0),
        "working_days": f.get("working_days", 0),
        "coverage_days": f.get("coverage_days", 0),
    }


def _share(part, whole):
    if not whole:
        return None
    return float(part or 0) / float(whole)


# ================================================================== gathering + storage

def month_bounds(month_key):
    y, m = int(month_key[:4]), int(month_key[5:7])
    start = datetime.date(y, m, 1)
    end = (datetime.date(y + (m == 12), (m % 12) + 1, 1) - datetime.timedelta(days=1))
    return start, end


def attribution(day):
    """{listing id -> responsible name} for one date, straight from the coverage engine —
    the owner if working, the coverer if the owner is off. This IS the attribution rule."""
    out = {}
    try:
        from schedule import routes as _sroutes
        board = _sroutes.schedule_day(day.isoformat())
        for w in board.get("working") or []:
            for apt in (w.get("own") or []):
                if apt.get("listing_id"):
                    out[int(apt["listing_id"])] = {"name": w["name"], "kind": "own"}
            for entry in (w.get("coverage") or []):
                apt = entry.get("apartment") or {}
                if apt.get("listing_id"):
                    out[int(apt["listing_id"])] = {"name": w["name"], "kind": "coverage"}
    except Exception as e:
        print("[scorecard] attribution unavailable for", day, e)
    return out


def gather(month_key, minimum=None):
    """Collect the facts for every employee for one month, then build their cards.

    Any source that is unavailable simply yields no facts for its line, which becomes
    «بيانات ناقصة» and redistributes — never a zero."""
    minimum = min_sample() if minimum is None else minimum
    start, end = month_bounds(month_key)
    try:
        from . import notify as _n
        people = [e["name"] for e in _n.employees()]
    except Exception:
        people = []
    if not people:
        return {"month": month_key, "cards": [], "error": "no employees"}

    facts = {p: {"apartment_days": 0, "working_days": 0, "coverage_days": 0,
                 "response": {"answered": 0, "total": 0},
                 "escalation": {"taken": 0, "total": 0},
                 "turnover": {"closed_before_checkin": 0, "total": 0},
                 "compliance": {"filed": 0, "expected": 0, "active_warnings": 0},
                 "reviews": []} for p in people}

    # ---- load, per day, from the coverage engine (rule (a)'s denominator)
    day = start
    attrib_by_day = {}
    while day <= end:
        a = attribution(day)
        attrib_by_day[day.isoformat()] = a
        seen = set()
        for _lid, who in a.items():
            nm = who["name"]
            if nm in facts:
                facts[nm]["apartment_days"] += 1
                if who["kind"] == "coverage":
                    facts[nm]["coverage_days"] += 1
                seen.add(nm)
        for nm in seen:
            facts[nm]["working_days"] += 1
        day += datetime.timedelta(days=1)

    _gather_turnover(facts, attrib_by_day, start, end)
    _gather_compliance(facts, month_key, start, end)
    _gather_escalation(facts, attrib_by_day, start, end)
    _gather_response(facts, attrib_by_day, start, end)
    _gather_reviews(facts, attrib_by_day, start, end)

    cards = [build(p, facts[p], minimum) for p in people]
    return {"month": month_key, "cards": cards, "min_sample": minimum,
            "dryrun": dryrun(),
            # The owner may see the ranking PRIVATELY. It is never published, and it is not
            # used to score anybody — see the module docstring on forced distribution.
            "private_ranking": [c["employee"] for c in
                                sorted(cards, key=lambda c: (c["score"] is None, -(c["score"] or 0)))]}


def _gather_turnover(facts, attrib_by_day, start, end):
    """Phase 2's own record: closed with a photo BEFORE the guest arrived."""
    try:
        rows = db.q("SELECT * FROM ops_nudge_items WHERE date>=? AND date<=?",
                    (start.isoformat(), end.isoformat()))
    except Exception as e:
        print("[scorecard] turnover data unavailable:", e)
        return
    for r in rows:
        lid = str(r.get("work_item_id") or "").split(":")[0]
        who = (attrib_by_day.get(r.get("date")) or {}).get(_int_or(lid))
        name = (who or {}).get("name") or r.get("employee")
        if name not in facts:
            continue
        facts[name]["turnover"]["total"] += 1
        acked, ci = r.get("acked_at"), r.get("checkin_at")
        if acked and ci and str(acked) <= str(ci):
            facts[name]["turnover"]["closed_before_checkin"] += 1


def _gather_compliance(facts, month_key, start, end):
    """Phase 1's own record: weekly reports filed, and warnings still active."""
    try:
        obs = db.q("SELECT * FROM ops_obligations WHERE substr(due_at,1,10)>=? "
                   "AND substr(due_at,1,10)<=?", (start.isoformat(), end.isoformat()))
        for o in obs:
            nm = o.get("employee")
            if nm not in facts:
                continue
            facts[nm]["compliance"]["expected"] += 1
            if o.get("status") in ("done", "waived", "excused"):
                facts[nm]["compliance"]["filed"] += 1
        for nm in facts:
            facts[nm]["compliance"]["active_warnings"] = db.active_warning_count(nm)
    except Exception as e:
        print("[scorecard] compliance data unavailable:", e)


def _gather_escalation(facts, attrib_by_day, start, end):
    try:
        rows = HOST.escalations_window(start.isoformat(), end.isoformat()) if HOST.escalations_window else []
    except Exception as e:
        print("[scorecard] escalation data unavailable:", e)
        rows = []
    for r in rows or []:
        day = str(r.get("date") or "")[:10]
        who = (attrib_by_day.get(day) or {}).get(_int_or(r.get("listing_id")))
        name = (who or {}).get("name")
        if name not in facts:
            continue
        facts[name]["escalation"]["total"] += 1
        if r.get("taken"):
            facts[name]["escalation"]["taken"] += 1


def _gather_response(facts, attrib_by_day, start, end):
    """Guest response time inside working hours.

    Hostaway cannot tell us WHO replied (§3.1), so this is attributed by ownership like
    everything else. When bot.py has no response data to give — which is the case today —
    the line correctly becomes «بيانات ناقصة» and its 25% is redistributed. That is the
    specified behaviour: never score a zero for a gap in our own instrumentation."""
    try:
        rows = HOST.response_events(start.isoformat(), end.isoformat()) if HOST.response_events else []
    except Exception as e:
        print("[scorecard] response data unavailable:", e)
        rows = []
    for r in rows or []:
        day = str(r.get("date") or "")[:10]
        who = (attrib_by_day.get(day) or {}).get(_int_or(r.get("listing_id")))
        name = (who or {}).get("name")
        if name not in facts:
            continue
        at = r.get("at")
        if at is not None and not in_working_hours(at, work_start(), work_end()):
            continue                      # outside the window: not counted either way
        facts[name]["response"]["total"] += 1
        if r.get("answered"):
            facts[name]["response"]["answered"] += 1


def _gather_reviews(facts, attrib_by_day, start, end):
    try:
        rows = HOST.reviews_window(start.isoformat(), end.isoformat()) if HOST.reviews_window else []
    except Exception as e:
        print("[scorecard] review data unavailable:", e)
        rows = []
    for r in rows or []:
        day = str(r.get("date") or "")[:10]
        who = (attrib_by_day.get(day) or {}).get(_int_or(r.get("listing_id")))
        name = (who or {}).get("name")
        if name not in facts:
            continue
        cats = r.get("categories") or {}
        if cats:
            facts[name]["reviews"].append(cats)


def _int_or(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ owner approval

def save(month_key, cards, by=""):
    db.save_scorecards(month_key, cards, by)
    return db.scorecards(month_key)


def override(month_key, employee, line_key, score, reason, by):
    """The owner may override any line — with a WRITTEN REASON, always.

    Without it the scorecard degrades into «whatever the owner felt that day» and stops
    meaning anything, so an empty reason is refused rather than defaulted."""
    if not (reason or "").strip():
        return {"ok": False, "error": "لازم تكتب سبب التعديل — التعديل بدون سبب مرفوض"}
    row = db.scorecard(month_key, employee)
    if not row:
        return {"ok": False, "error": "ما لقينا الكرت"}
    if row.get("released_at"):
        return {"ok": False, "error": "الكرت انرسل للموظف — ما ينعدل بعد الإرسال"}
    card = json.loads(row["card_json"])
    hit = next((l for l in card["lines"] if l["key"] == line_key), None)
    if not hit:
        return {"ok": False, "error": "ما فيه بند بهذا الاسم"}
    try:
        val = int(score)
    except (TypeError, ValueError):
        return {"ok": False, "error": "الدرجة لازم رقم من ١ إلى ٥"}
    if not (1 <= val <= 5):
        return {"ok": False, "error": "الدرجة لازم من ١ إلى ٥"}
    hit["score"] = val
    hit["overridden"] = {"by": by, "reason": reason.strip(), "at": db.now_iso(),
                         "was": hit.get("score")}
    rescored = [{"key": l["key"], "weight": l["weight"], "score": l["score"]}
                for l in card["lines"]]
    card["score"], dist = weighted_score(rescored)
    for l, d in zip(card["lines"], dist["lines"]):
        l["effective_weight"] = d["effective_weight"]
    card["multiplier"] = bonus_multiplier(card["score"], card.get("coverage_bonus", 0))
    db.update_scorecard(month_key, employee, card)
    return {"ok": True, "card": card}


def release(month_key, by):
    """Only after the owner has seen the raw data and approved. In dry-run nothing is
    released to anybody, however many times this is called."""
    if dryrun():
        return {"ok": False, "error": "وضع التجربة شغّال — ما ينرسل شي للموظفين",
                "dryrun": True, "released": []}
    rows = db.scorecards(month_key)
    if not rows:
        return {"ok": False, "error": "ما فيه كروت لهذا الشهر"}
    released = []
    for r in rows:
        if r.get("released_at"):
            continue
        db.release_scorecard(month_key, r["employee"], by)
        released.append(r["employee"])
    return {"ok": True, "released": released}
