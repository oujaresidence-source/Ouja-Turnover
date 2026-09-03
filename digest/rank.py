# -*- coding: utf-8 -*-
"""digest.rank — which candidates make a guest decide (brief §10). Pure, no I/O.

score = 0.30 decision_value + 0.20 source_confidence + 0.15 proximity
      + 0.15 audience_fit + 0.10 novelty + 0.10 owner_history

then SPREAD: no two event primaries share a district or a category — three concerts in
Boulevard lose to one concert, one exhibition and one market even if each concert
scores higher (studio/shapes.py's idea). Alternates are pre-built per slot so «بدائل»
is instant, and each alternate respects the spread against the OTHER primaries.
owner_history reads digest_rulings: a district / source / category he dropped twice
sinks; what he approved rises. Every score carries Arabic reasons he can audit."""

from . import places, schema
from .voice import normalize

WEIGHTS = {"decision": 0.30, "confidence": 0.20, "proximity": 0.15,
           "audience": 0.15, "novelty": 0.10, "history": 0.10}

DECISION_PRIOR = {"podcast": 0.80, "exhibition": 0.90, "museum": 0.85, "season": 0.80, "family": 0.75,
                  "concert": 0.70, "market": 0.60, "comedy": 0.65, "theatre": 0.65,
                  "park": 0.70, "sport": 0.75, "cinema": 0.70, "other": 0.40, "b2b": 0.10}
DAY_FIT = {"thu": 1.0, "fri": 1.0, "sat": 0.85}
TARGET_AUDIENCE = ("family", "couples", "young")
CATEGORY_AUDIENCE = {
    "family": ("family",), "exhibition": ("couples", "young"), "museum": ("family", "couples"),
    "season": ("family", "couples", "young"), "concert": ("young", "couples"), "market": ("family", "couples"),
    "comedy": ("young", "couples"), "theatre": ("couples", "family"), "park": ("family", "couples"),
    "sport": ("young", "family"), "cinema": ("family", "couples", "young"), "other": ("couples",), "b2b": (),
    "podcast": ("young", "couples", "family"),
}
HISTORY_DROP, HISTORY_APPROVE = -0.5, 0.25
CAPS = {"events": 4, "cinema": 3, "worth": 1, "fixtures": 6, "podcast": 1}
MINS = {"events": 2, "cinema": 3, "worth": 0, "fixtures": 0, "podcast": 0}
ALTERNATES_PER_SLOT = 3


def _cat(c):
    return ((c.get("tags") or {}).get("category")) or "other"


def _district(c):
    return ((c.get("tags") or {}).get("district")) or ""


def decision_value(c):
    if c.get("sold_out"):
        return 0.0
    v = DECISION_PRIOR.get(_cat(c), DECISION_PRIOR["other"]) * DAY_FIT.get(c.get("day"), 0.9)
    if c.get("section") == "cinema":
        v = 1.0 if c.get("new_this_week") else 0.6
    return round(min(1.0, v), 3)


def audience_fit(c):
    aud = set(c.get("audience") or CATEGORY_AUDIENCE.get(_cat(c), ()))
    return round(len(aud & set(TARGET_AUDIENCE)) / float(len(TARGET_AUDIENCE)), 3)


def proximity(c, ctx):
    return round(places.proximity_score(c.get("latlng"), (ctx or {}).get("points")), 3)


def novelty(c, ctx):
    ctx = ctx or {}
    if c.get("url") in (ctx.get("recent_urls") or set()):
        return 0.0
    key = normalize(c.get("ttl") or "").strip()
    if key and key in (ctx.get("recent_titles") or set()):
        return 0.0
    return 1.0


def owner_history(c, rulings):
    h = 0.0
    d, cat, src = _district(c), _cat(c), (c.get("source") or {}).get("name", "")
    for r in rulings or []:
        det = r.get("detail") or {}
        hit = (d and d == det.get("district")) or (cat and cat == det.get("category")) or (src and src == det.get("source"))
        if r.get("action") == "drop" and hit:
            h += HISTORY_DROP
        elif r.get("action") == "approve":
            if d and d in (det.get("districts") or ()):
                h += HISTORY_APPROVE
            if cat and cat in (det.get("categories") or ()):
                h += HISTORY_APPROVE
    return max(-1.0, min(1.0, round(h, 3)))


def score(c, ctx=None):
    parts = {
        "decision": decision_value(c),
        "confidence": round(float(c.get("confidence", 0.0)), 3),
        "proximity": proximity(c, ctx),
        "audience": audience_fit(c),
        "novelty": novelty(c, ctx),
        "history": owner_history(c, (ctx or {}).get("rulings")),
    }
    total = sum(WEIGHTS[k] * v for k, v in parts.items())
    return round(total, 4), parts


def reasons_ar(c, parts):
    out = []
    if parts["decision"] >= 0.75:
        out.append("نوع يحرّك الضيف: %s" % _cat(c))
    if parts["confidence"] >= 0.85:
        out.append("مصدر رسمي ومتأكدين من الموعد")
    elif parts["confidence"] < 0.75:
        out.append("مصدر واحد بس — بديل مو أساسي")
    if parts["proximity"] >= 0.7:
        out.append("قريب من شققنا")
    if parts["novelty"] == 0:
        out.append("نشرناه قبل")
    if parts["history"] < 0:
        out.append("فيصل حذف مثله قبل")
    elif parts["history"] > 0:
        out.append("فيصل اعتمد مثله قبل")
    return out


def _ranked(cands, ctx):
    out = []
    for i, c in enumerate(cands):
        s, parts = score(c, ctx)
        d = dict(c)
        d["score"], d["score_parts"], d["reasons"] = s, parts, reasons_ar(c, parts)
        out.append((s, i, d))
    out.sort(key=lambda t: (-t[0], t[1]))
    return [d for _, _, d in out]


def _clashes(c, chosen, strict=True):
    for p in chosen:
        if _cat(c) == _cat(p):
            return True
        if strict and _district(c) and _district(c) == _district(p):
            return True
    return False


def _pick_events(ranked, cap, floor):
    """Tier 1: no shared district AND no shared category. Tier 2 (fill the remaining
    slots): no shared category — many good Riyadh venues cluster in one district, and a
    family show next to a concert in the same district is still a spread. Tier 3 (any)
    only to reach the floor: two concerts beat an empty digest."""
    chosen = []
    for strict in (True, False):
        for c in ranked:
            if len(chosen) >= cap:
                break
            if c not in chosen and not _clashes(c, chosen, strict):
                chosen.append(c)
    if len(chosen) < floor:
        for c in ranked:
            if len(chosen) >= floor:
                break
            if c not in chosen:
                chosen.append(c)
    return chosen[:cap]


def _eligible(c):
    return float(c.get("confidence", 0.0)) >= schema.MIN_PRIMARY_CONFIDENCE


def choose(cands_by_section, ctx=None):
    """-> {"primary": {section: [cand]}, "alternates": {"section.slot": [cand]}}."""
    ctx = ctx or {}
    primary, alternates = {}, {}
    for section, cands in (cands_by_section or {}).items():
        cap, floor = CAPS.get(section, 4), MINS.get(section, 0)
        ranked = _ranked([c for c in cands if c], ctx)
        eligible = [c for c in ranked if _eligible(c)]
        if section == "events":
            chosen = _pick_events(eligible, cap, floor)
        elif section == "fixtures":
            chosen = sorted(eligible, key=lambda f: (0 if f.get("in_riyadh") else 1, f.get("kickoff_iso", "")))[:cap]
            chosen.sort(key=lambda f: f.get("kickoff_iso", ""))
        else:
            chosen = eligible[:cap]
        if section == "cinema" and len(chosen) < 3:
            chosen = []
        if len(chosen) < floor:
            chosen = []
        primary[section] = chosen
        for slot in range(len(chosen)):
            others = [p for i, p in enumerate(chosen) if i != slot]
            alts = []
            # spread-respecting first (district + category), then category-only, then any —
            # «بدائل» must always offer something, best-behaved first.
            for strict in ((True, False, None) if section == "events" else (None,)):
                for c in ranked:
                    if c in chosen or c in alts:
                        continue
                    if strict is not None and _clashes(c, others, strict):
                        continue
                    alts.append(c)
                    if len(alts) >= ALTERNATES_PER_SLOT:
                        break
                if len(alts) >= ALTERNATES_PER_SLOT:
                    break
            alternates["%s.%d" % (section, slot)] = alts
    return {"primary": primary, "alternates": alternates}
