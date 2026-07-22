# -*- coding: utf-8 -*-
"""studio.plan — the daily set + weekly calendar (spec Section H).

Answers «وش أصوّر اليوم؟» with 3 cards a day, chosen so the week doesn't turn into
seven versions of the same video. The selection maths is PURE (`choose`) and
TDD-locked; only `build_day` touches the db.

The balance rule, in order of what it protects:
  1. NOVELTY  — never re-serve an angle already served recently.
  2. FRESHNESS — a dated external signal decays fast; film the news while it's news.
  3. SPREAD   — prefer a set that mixes audience (niche vs escape), source family
                (Ouja data vs outside news vs Faisal's own day) and trigger.
  4. STRENGTH — among equals, the card the account's own history likes best.
"""

from . import db, engine

DAILY_N = 3
FRESH_BONUS_DAYS = 7        # an external signal younger than this is still "hot"
SPREAD_WEIGHT = 40.0        # how hard we push for variety vs raw strength


def _card_keys(card):
    return (str(card.get("audience") or ""),
            str(card.get("signal_family") or ""),
            str(card.get("trigger_kind") or card.get("trigger") or ""))


def _freshness_bonus(card, today):
    """Points for a time-sensitive card, so news outranks evergreen (spec H5)."""
    if str(card.get("signal_family") or "") != "external":
        return 0.0
    age = engine.freshness_days(card.get("signal_date"), today)
    if age is None or age < 0:
        return 0.0
    if age > FRESH_BONUS_DAYS:
        return 0.0
    return 30.0 * (1.0 - (age / float(FRESH_BONUS_DAYS)))


def choose(candidates, recent_keys=(), n=DAILY_N, today=""):
    """Pick up to `n` cards. Greedy: each pick re-scores the rest against what the
    set already covers, so the second pick is chosen to be *different*, not just
    next-best. Pure — no db, no clock."""
    pool = [c for c in (candidates or []) if isinstance(c, dict)]
    # 1. novelty gate against history
    fresh = []
    seen = list(recent_keys or [])
    for c in pool:
        key = c.get("nkey") or engine.novelty_key(
            "%s %s" % (c.get("visual_title", ""), c.get("angle", "")))
        if engine.is_novel(key, seen):
            fresh.append((c, key))
    picked, covered = [], {0: set(), 1: set(), 2: set()}
    while fresh and len(picked) < int(n):
        best, best_score, best_key = None, None, ""
        for c, key in fresh:
            keys = _card_keys(c)
            # spread: reward every dimension this card adds that the set lacks
            new_dims = sum(1 for i in range(3) if keys[i] and keys[i] not in covered[i])
            try:
                strength = float(c.get("strength") or 0)
            except (TypeError, ValueError):
                strength = 0.0
            score = strength + (new_dims * SPREAD_WEIGHT) + _freshness_bonus(c, today)
            if best_score is None or score > best_score:
                best, best_score, best_key = c, score, key
        if best is None:
            break
        picked.append(best)
        for i, v in enumerate(_card_keys(best)):
            if v:
                covered[i].add(v)
        # a chosen card's angle also blocks its own near-duplicates in this set
        fresh = [(c, k) for c, k in fresh
                 if c is not best and engine.is_novel(k, [best_key])]
    return picked


def build_day(day=None, n=DAILY_N, force=False):
    """Persist today's set. Idempotent: an existing plan is returned untouched
    unless force=True, so opening the page ten times doesn't reshuffle the day."""
    now = None
    try:
        now = HOST_now()
    except Exception:
        pass
    day = day or (now.strftime("%Y-%m-%d") if now else "")
    if not day:
        return []
    if not force:
        existing = db.plan_for(day)
        if existing:
            return existing
    pool = [i for i in db.ideas(status="new", limit=120)]
    picked = choose(pool, recent_keys=_planned_keys(exclude_day=day), n=n, today=day)
    ts = now.strftime("%Y-%m-%d %H:%M:%S") if now else ""
    db.set_plan(day, [c["id"] for c in picked if c.get("id")], ts)
    return db.plan_for(day)


def _planned_keys(exclude_day="", days=14):
    """Angles already put on the calendar recently — the repeat guard's memory."""
    rows = db.q(
        "SELECT i.nkey nkey FROM studio_plan p JOIN studio_ideas i ON i.id = p.idea_id "
        "WHERE p.day <> ? ORDER BY p.day DESC LIMIT ?", (str(exclude_day), int(days) * 6))
    return [r["nkey"] for r in rows if r.get("nkey")]


def week(start_day, days=7):
    """[{day, cards:[…]}] for the calendar view. Reads only what's already planned."""
    out = []
    try:
        y, m, d = [int(x) for x in str(start_day)[:10].split("-")]
    except Exception:
        return out
    from datetime import date, timedelta
    d0 = date(y, m, d)
    for i in range(int(days)):
        dd = (d0 + timedelta(days=i)).isoformat()
        out.append({"day": dd, "cards": db.plan_for(dd)})
    return out


def instant(n=1):
    """«أعطني فكرة الحين» (spec H3) — Faisal is standing in an empty apartment and
    needs something to shoot NOW. Serve the best card that isn't already on today's
    plan; only if the shelf is empty do we pay for a fresh generation off the
    strongest unused signal."""
    from . import ideas as ideas_mod
    now = None
    try:
        now = HOST_now()
    except Exception:
        pass
    today = now.strftime("%Y-%m-%d") if now else ""
    used = {c.get("id") for c in (db.plan_for(today) if today else [])}
    pool = [c for c in db.ideas(status="new", limit=80) if c.get("id") not in used]
    picked = choose(pool, recent_keys=[], n=n, today=today)
    if picked:
        return picked, False
    for sig in db.signals(status="new", limit=5):
        cards = ideas_mod.generate_for_signal(sig["sid"])
        if cards:
            return cards[:n], True
    return [], False


def HOST_now():
    from .host import HOST
    return HOST.require("now")()
