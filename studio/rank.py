# -*- coding: utf-8 -*-
"""studio.rank — «أقرب فكرة تشتغل» : one honest 0-100 number per idea card. PURE.

The owner reads this on a phone, in a hurry, and films the top card. So the ranking
has to be defensible on day one — before a single view has been logged — and it has
to get better, not noisier, once history exists.

Four ingredients, in descending trustworthiness:
  1. HISTORY  — what actually earned views on HIS account (studio.learn). Weighted
     to zero when there isn't enough of it; this is the only ingredient that can
     ever dominate, and only once it's earned.
  2. SIGNAL   — how content-worthy the underlying fact is (the collector's own call).
  3. FRESHNESS— a dated external signal decays; news filmed late is not news.
  4. PRIOR    — the researched playbook's read on trigger/format, as a light nudge.

The prior is deliberately weak. It is a guess about TikTok in general; ingredient 1
is a fact about Faisal. As history accumulates, 1 grows and 4 stays where it is.
"""

from . import engine, learn, virality

# Prior pull from the verified research (playbook.py). Kept close to 1.0 on purpose —
# these are nudges, not verdicts, and they must never outvote real performance data.
TRIGGER_PRIOR = {
    "identity": 1.10,        # "لو عندك شقة…" — strongest opener in the research
    "news": 1.08,            # timeliness earns reach, and decays fast
    "authority": 1.05,
    "social_proof": 1.05,
    "curiosity": 1.00,
    "loss": 1.00,
    "provocation": 0.95,     # works, but narrows the audience
    "emotion": 0.95,
}
FORMAT_PRIOR = {
    "news_reaction": 1.05,
    "data_reveal": 1.05,
    "before_after": 1.05,    # visual hook is built in
    "tour": 1.00,
    "onsite": 1.00,
    "talking": 1.00,
    "story_voiceover": 0.95,
}

FRESH_WINDOW = 7             # days an external signal stays "hot"
BASE = 50


def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def freshness_points(card, today):
    """0..15. Only external signals decay — an occupancy number is true all week."""
    if str(card.get("signal_family") or "") != "external":
        return 0.0
    age = engine.freshness_days(card.get("signal_date"), today)
    if age is None or age < 0 or age > FRESH_WINDOW:
        return 0.0
    return 15.0 * (1.0 - (age / float(FRESH_WINDOW)))


def prior_points(card):
    """-10..+10 from the playbook's read on this trigger + format pairing."""
    t = TRIGGER_PRIOR.get(str(card.get("trigger_kind") or card.get("trigger") or ""), 1.0)
    f = FORMAT_PRIOR.get(str(card.get("video_type") or ""), 1.0)
    return max(-10.0, min(10.0, ((t * f) - 1.0) * 100.0))


def history_points(card, stats):
    """-25..+25, and exactly 0 until the account has enough logged videos to speak."""
    if not stats or not stats.get("n"):
        return 0.0
    s = learn.strength_of(card, stats)
    if s == learn.NEUTRAL_STRENGTH:
        return 0.0
    return max(-25.0, min(25.0, (s - learn.NEUTRAL_STRENGTH) * 0.8))


def signal_points(card):
    """-12..+12 from how strong the collector judged the underlying fact.
    A card with no signal at all sits slightly below neutral — being ungrounded is
    a real mark against it, not a neutral fact."""
    if not str(card.get("signal_text") or "").strip():
        return -6.0
    strength = _f(card.get("signal_strength"), 50.0)
    return max(-12.0, min(12.0, (strength - 50.0) * 0.24))


def craft_points(card):
    """-20..+20 from studio.virality — is the card BUILT the way the research says
    short-form has to be built (hook in 3s, loop-closing end, a real number, a
    length in the completion band)? This is the only ingredient that judges the
    card itself rather than its context, and it is the one he can act on."""
    v = virality.score(card)
    return max(-20.0, min(20.0, (v - 55) * 0.45))


def score(card, stats=None, today=""):
    """0-100. Higher = likelier to work for Faisal specifically."""
    if not isinstance(card, dict):
        return 0
    total = (BASE + history_points(card, stats) + craft_points(card)
             + signal_points(card) + freshness_points(card, today)
             + prior_points(card))
    return int(max(0, min(100, round(total))))


def reasons_ar(card, stats=None, today=""):
    """Why it ranked where it did — short lines the owner can sanity-check.
    Ranking he can't audit is ranking he won't trust."""
    out = []
    h = history_points(card, stats)
    if h > 2:
        out.append("يشبه اللي نجح لك سابقاً")
    elif h < -2:
        out.append("يشبه اللي ما أدّى لك زين")
    fr = freshness_points(card, today)
    if fr >= 10:
        out.append("خبر طازج — صوّره اليوم")
    elif fr > 0:
        out.append("لسا في وقته")
    s = signal_points(card)
    if s <= -5:
        out.append("بدون إشارة حقيقية وراها")
    elif s >= 5:
        out.append("مبنية على رقم/خبر قوي")
    p = prior_points(card)
    if p >= 5:
        out.append("شكل وهوك مثبت أداؤه")
    cr = craft_points(card)
    if cr >= 8:
        out.append("مبنية صح: هوك سريع ونهاية ترجع للبداية")
    elif cr <= -8:
        out.append("البناء ضعيف — شوف «وش تعدّل»")
    return out


def audit(card):
    """The full explainable breakdown for one card: the rank, plus the structural
    audit with concrete fixes. This is what the phone page opens when he taps «ليش»."""
    v = virality.audit(card)
    return {"virality": v["score"], "fixes": v["fixes"], "wins": v["wins"],
            "factors": v["factors"]}


def rank(cards, stats=None, today=""):
    """Cards sorted best-first, each stamped with `rank_score` + `rank_why`.
    Stable: equal scores keep their incoming order instead of shuffling per refresh."""
    out = []
    for i, c in enumerate(cards or []):
        if not isinstance(c, dict):
            continue
        d = dict(c)
        d["rank_score"] = score(c, stats, today)
        d["rank_why"] = reasons_ar(c, stats, today)
        va = virality.audit(c)
        d["virality"] = va["score"]
        d["fixes"] = va["fixes"]
        d["wins"] = va["wins"]
        out.append((-d["rank_score"], i, d))
    out.sort(key=lambda t: (t[0], t[1]))
    return [d for _s, _i, d in out]
