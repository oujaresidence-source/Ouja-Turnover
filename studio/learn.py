# -*- coding: utf-8 -*-
"""studio.learn — the performance learning loop (spec Section I). PURE math.

Reads the owner's own posted videos + their view counts and answers one question:
what actually works for THIS account? Not what works on TikTok in general — the
playbook already covers that. This is the part that compounds: every video Faisal
logs makes the next batch of ideas a little more his.

Design rules that keep it honest:
  * MIN_SAMPLE — a dimension value with fewer posts than this is invisible. Two
    lucky videos must never rewrite the strategy.
  * lift is measured against the account's OWN mean, so a slow week doesn't look
    like a failing trigger.
  * no history => neutral. The system never pretends to know.
"""

MIN_SAMPLE = 3            # posts needed before a value becomes a finding
NEUTRAL_STRENGTH = 55     # score used when there's nothing to learn from yet

# The dimensions the owner asked to learn (I2), mapped to the idea-row keys.
DIMENSIONS = (
    ("trigger", ("trigger_kind", "trigger")),
    ("audience", ("audience",)),
    ("format", ("video_type", "format")),
    ("source", ("signal_family", "family")),
    ("story_type", ("story_type",)),
)

TRIGGER_AR = {
    "curiosity": "فجوة الفضول", "loss": "الخوف من الخسارة", "identity": "نداء الهوية",
    "provocation": "الرأي المخالف", "authority": "خبرة من الداخل",
    "social_proof": "أرقام ونتائج", "news": "خبر وتوقيت", "emotion": "عاطفة",
}
AUDIENCE_AR = {"niche": "ملّاك ومشغّلين", "escape": "جمهور عام"}
FORMAT_AR = {
    "talking": "كلام أمام الكاميرا", "tour": "جولة شقة", "before_after": "قبل وبعد",
    "story_voiceover": "قصة بتعليق صوتي", "onsite": "تصوير ميداني",
    "data_reveal": "كشف أرقام", "news_reaction": "رد فعل على خبر",
}
SOURCE_AR = {"internal": "بيانات عوجا", "external": "خبر/سوق خارجي", "manual": "موقف كتبته بنفسك"}
LABELS = {"trigger": ("المحفّز", TRIGGER_AR), "audience": ("الجمهور", AUDIENCE_AR),
          "format": ("الشكل", FORMAT_AR), "source": ("المصدر", SOURCE_AR),
          "story_type": ("نوع القصة", {})}


def _val(row, keys):
    for k in keys:
        v = row.get(k)
        if v:
            return str(v)
    return ""


def _views(row):
    try:
        return max(0, int(row.get("views") or 0))
    except (TypeError, ValueError):
        return 0


def stats(rows):
    """{'n':posts, 'mean':overall mean views, 'dims':{dim:{value:{n,mean,lift}}}}.

    Only POSTED rows with a real view count count — an unlogged video teaches nothing."""
    posted = [r for r in (rows or [])
              if isinstance(r, dict)
              and str(r.get("status") or "") == "posted" and _views(r) > 0]
    if not posted:
        return {"n": 0, "mean": 0.0, "dims": {}}
    mean = sum(_views(r) for r in posted) / float(len(posted))
    dims = {}
    for dim, keys in DIMENSIONS:
        buckets = {}
        for r in posted:
            v = _val(r, keys)
            if v:
                buckets.setdefault(v, []).append(_views(r))
        out = {}
        for v, vals in buckets.items():
            m = sum(vals) / float(len(vals))
            out[v] = {"n": len(vals), "mean": round(m),
                      "lift": round(m / mean, 2) if mean else 1.0}
        if out:
            dims[dim] = out
    return {"n": len(posted), "mean": round(mean), "dims": dims}


def _ranked(st, dim):
    """[(value, info)] with enough sample, best lift first."""
    d = (st.get("dims") or {}).get(dim) or {}
    ok = [(v, i) for v, i in d.items() if i["n"] >= MIN_SAMPLE]
    return sorted(ok, key=lambda kv: kv[1]["lift"], reverse=True)


def insights_ar(st):
    """Owner-readable findings (spec I4). Empty until the data earns a sentence."""
    lines = []
    for dim, _keys in DIMENSIONS:
        ranked = _ranked(st, dim)
        if len(ranked) < 2:
            continue
        label, names = LABELS.get(dim, (dim, {}))
        best_v, best = ranked[0]
        worst_v, worst = ranked[-1]
        if best["lift"] < 1.15 or not worst["mean"]:
            continue
        times = best["mean"] / float(worst["mean"])
        lines.append(
            "%s: «%s» يجيب %s× مشاهدات «%s» (متوسط %s مقابل %s · %s فيديو)" % (
                label, names.get(best_v, best_v), round(times, 1),
                names.get(worst_v, worst_v), f"{best['mean']:,}", f"{worst['mean']:,}",
                best["n"]))
    return lines


def bias_hint_ar(st):
    """One prompt line telling the generator what already wins for this account (I3)."""
    parts = []
    for dim in ("trigger", "audience", "format", "source"):
        ranked = _ranked(st, dim)
        if ranked and ranked[0][1]["lift"] >= 1.15:
            parts.append("%s=%s" % (dim, ranked[0][0]))
    if not parts:
        return ""
    return ("\n\nإشارة تعلّم من أداء حسابك الفعلي (%s فيديو مسجّل): الأفضل أداءً حتى الآن %s — "
            "مِل لها إذا ناسبت الإشارة، ولا تجبرها إجبار." % (st.get("n", 0), " · ".join(parts)))


def strength_of(card, st):
    """Predicted strength 0-100 for an idea card (spec F9), from what already worked.
    With no history every card scores NEUTRAL_STRENGTH — an honest 'we don't know yet'."""
    if not st or not st.get("n"):
        return NEUTRAL_STRENGTH
    lifts = []
    for dim, keys in DIMENSIONS:
        d = (st.get("dims") or {}).get(dim) or {}
        v = _val(card if isinstance(card, dict) else {}, keys)
        info = d.get(v)
        if info and info["n"] >= MIN_SAMPLE:
            lifts.append(info["lift"])
    if not lifts:
        return NEUTRAL_STRENGTH
    avg = sum(lifts) / float(len(lifts))
    # lift 1.0 (average) -> NEUTRAL; each 0.1 of lift moves the score ~7 points.
    return int(max(0, min(100, round(NEUTRAL_STRENGTH + (avg - 1.0) * 70))))
