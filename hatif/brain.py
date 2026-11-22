# -*- coding: utf-8 -*-
"""
hatif.brain — the WhatsApp «reader»: one typed guest message → one composed reply.

The AI does ONE job: read the message and pick a door. It never writes the words a guest sees.
    answer   one or two approved answers from the bank (answers.py), sent word for word
    dates    the dates parse → the live availability reply (engine.build_reply, same as the site)
    unit     the guest means a specific apartment → that unit's page, asked as «تقصد هذي؟»
    near     near a named place → the closest units by map distance («حوالي», straight line)
    human    anything else, low confidence, or the AI unreachable → a person, with a summary
    menu     a bare greeting → the Hatif menu answers it; the reader stays out

Every reply passes firewall.check before it can go anywhere. PURE except the injected
`classify(system, user) -> dict|None` and `search(...)` callables, so tests need no network.
"""
import json
import math
import re

from . import answers, engine, firewall, parse

MIN_CONF = 0.6
MAX_ANSWERS = 2
# Riyadh box: a place the AI locates outside it is not trusted for «near».
_LAT = (24.3, 25.2)
_LNG = (46.3, 47.1)


def system_prompt(bank):
    lines = ["%s: %s" % (k, v["about"]) for k, v in bank.items()]
    return (
        "You route WhatsApp messages sent to Ouja Residence, a serviced-apartment company in "
        "Riyadh (Najdi Arabic, sometimes English). You do NOT write replies. Return ONLY JSON:\n"
        '{"door": "answer|dates|unit|near|human|menu", "answers": [ids], "unit_hint": "", '
        '"place": "", "place_lat": null, "place_lng": null, "city": "", '
        '"confidence": 0.0, "summary_ar": ""}\n'
        "Rules:\n"
        "- door=menu only for a bare greeting or thanks with no question.\n"
        "- door=dates when the guest gives or asks about specific dates/nights to stay.\n"
        "- door=unit when they mean one specific apartment (a name, 'the penthouse', 'the one in "
        "the TikTok video'); put their words in unit_hint.\n"
        "- door=near when they want to be close to a named place in Riyadh; give place and its "
        "approximate coordinates ONLY if you are sure, else leave them null.\n"
        "- door=answer with 1-2 ids from the list below when those answers fully cover the "
        "question. Use other_city for any city that is not Riyadh and put it in city.\n"
        "- door=human for complaints, meetings, urgent problems you cannot map, or anything unsure.\n"
        "- confidence: how sure you are the chosen answers fully answer the guest.\n"
        "- summary_ar: one short Arabic line for staff describing what the guest wants. No phone "
        "numbers.\n"
        "Answer ids:\n" + "\n".join(lines))


def decide(text, classify, bank):
    """The AI's routing decision, validated. Never raises; failure → human."""
    raw = None
    try:
        raw = classify(system_prompt(bank), "Guest message:\n" + str(text)[:1500])
    except Exception as e:                       # network, quota, parse — all become «human»
        print("[hatif] reader classify failed:", type(e).__name__)
    if not isinstance(raw, dict):
        return {"door": "human", "answers": [], "confidence": 0.0, "why": "ai_unavailable",
                "summary_ar": ""}
    door = raw.get("door") if raw.get("door") in ("answer", "dates", "unit", "near", "human", "menu") else "human"
    ids = [a for a in (raw.get("answers") or []) if isinstance(a, str) and a in bank][:MAX_ANSWERS]
    try:
        conf = max(0.0, min(1.0, float(raw.get("confidence") or 0)))
    except (TypeError, ValueError):
        conf = 0.0
    d = {"door": door, "answers": ids, "confidence": conf,
         "unit_hint": str(raw.get("unit_hint") or "")[:120], "place": str(raw.get("place") or "")[:80],
         "city": str(raw.get("city") or "")[:40], "summary_ar": str(raw.get("summary_ar") or "")[:200],
         "lat": _coord(raw.get("place_lat"), _LAT), "lng": _coord(raw.get("place_lng"), _LNG)}
    if door == "answer" and not ids:
        d.update(door="human", why="no_known_answer")
    elif door in ("answer", "unit", "near") and conf < MIN_CONF:
        d.update(door="human", why="low_confidence")
    elif door == "near" and (d["lat"] is None or d["lng"] is None):
        d.update(door="human", why="place_unknown")
    return d


def _coord(v, box):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if box[0] <= f <= box[1] else None


def _km(a_lat, a_lng, b_lat, b_lng):
    p = math.radians
    h = (math.sin(p(b_lat - a_lat) / 2) ** 2
         + math.cos(p(a_lat)) * math.cos(p(b_lat)) * math.sin(p(b_lng - a_lng) / 2) ** 2)
    return 6371 * 2 * math.asin(math.sqrt(h))


_TOKEN = re.compile(r"[ء-يA-Za-z0-9]{2,}")
_STOP = {"اللي", "الي", "في", "من", "على", "شقة", "شقه", "الشقة", "الشقه", "هذي", "ابي", "عندكم",
         "the", "in", "apartment", "flat", "unit", "with", "and"}
_ALIASES = {"بنتهاوس": "سطح", "بنت": "سطح", "penthouse": "rooftop", "روف": "سطح"}


def _tokens(s):
    s = parse.normalize(s)
    out = set()
    for t in _TOKEN.findall(s):
        t = t.lower()
        if t.startswith("ال") and len(t) > 4:
            t = t[2:]
        if t in _STOP:
            continue
        out.add(_ALIASES.get(t, t))
    return out


def match_unit(hint, catalog):
    """Best catalogue unit for the guest's words, or None. Needs a real word overlap."""
    want = _tokens(hint)
    if not want:
        return None
    best, score = None, 0
    for u in catalog or []:
        have = _tokens(" ".join(str(u.get(k) or "") for k in ("name_ar", "name_en", "area")))
        s = len(want & have)
        if s > score:
            best, score = u, s
    return best if score >= 1 else None


def nearest(lat, lng, catalog, k=2):
    pts = []
    for u in catalog or []:
        try:
            pts.append((_km(lat, lng, float(u["lat"]), float(u["lng"])), u))
        except (KeyError, TypeError, ValueError):
            continue
    pts.sort(key=lambda x: x[0])
    return pts[:k]


def _card(u, site):
    name = str(u.get("name_ar") or u.get("name_en") or "").strip()[:48]
    area = str(u.get("area") or "").strip()[:24]
    return "• %s%s\n%s/apartments/%s" % (name, (" | " + area) if area and area not in name else "", site, u.get("id"))


def compose(text, today, hoods, decision, bank, catalog, search, site, max_units=6, max_nights=30):
    """{'door','reply','handoff','team','urgent','allowed','violations'}. reply may be None (menu)."""
    d = decision
    allowed = set()
    for a in bank.values():
        allowed |= firewall.money_in(a["text"])
    req = parse.parse_request(text, today, hoods, max_nights)
    out = {"door": d["door"], "reply": None, "handoff": False, "team": "", "urgent": False}

    if req.get("ok") and d["door"] in ("dates", "answer", "unit", "near", "menu"):
        res = search(req["check_in"], req["check_out"], req.get("guests"), req.get("type"),
                     req.get("neighborhood"))
        for u in (res or {}).get("results") or []:
            for f in ("est_total", "est_avg"):
                if u.get(f):
                    allowed.add(int(round(float(u[f]))))
        out.update(door="dates", reply=engine.build_reply(req, res, site, max_units))
    elif d["door"] == "dates":
        out["reply"] = engine.help_text(req.get("reason") or "no_dates")
        if req.get("reason") == "monthly":
            out.update(handoff=True, team="الحجوزات")
    elif d["door"] == "menu":
        out["reply"] = None
    elif d["door"] == "unit":
        u = match_unit(d.get("unit_hint") or text, catalog)
        if u:
            out["reply"] = "تقصد هذي؟ 👇\n%s\n\nإذا مو هي، أرسل لي رابط المقطع أو اسم الشقة وأحددها لك." % _card(u, site)
        else:
            out.update(door="human", reply=bank["human"]["text"], handoff=True, team="الحجوزات")
    elif d["door"] == "near":
        near = nearest(d["lat"], d["lng"], catalog)
        if near:
            km = int(round(near[0][0]))
            lines = ["أقرب شققنا لـ%s (حوالي %s كم):" % (d.get("place") or "المكان", max(km, 1))]
            lines += [_card(u, site) for _, u in near]
            lines += ["", "اكتب تواريخك وعدد الليالي وأشيك لك إذا متاحة وبكم 🤍"]
            out["reply"] = "\n".join(lines)
        else:
            out.update(door="human", reply=bank["human"]["text"], handoff=True, team="الحجوزات")
    elif d["door"] == "answer":
        parts = [bank[i] for i in d["answers"]]
        out["reply"] = "\n\n".join(p["text"] for p in parts)
        for p in parts:
            if p["kind"] in ("collect", "human"):
                out.update(handoff=p["kind"] == "human", team=out["team"] or p["team"],
                           urgent=out["urgent"] or p["urgent"])
    else:
        out.update(door="human", reply=bank["human"]["text"], handoff=True, team="الفريق")

    out["allowed"] = sorted(allowed)
    out["violations"] = firewall.check(out["reply"], allowed) if out["reply"] else []
    return out


def explain(decision, composed):
    """One-line Arabic «why» for the Discord shadow post."""
    door = {"answer": "جواب معتمد", "dates": "توفر حقيقي", "unit": "شقة معيّنة", "near": "قريب من",
            "human": "لموظف", "menu": "القائمة ترد"}.get(composed["door"], composed["door"])
    bits = [door]
    if decision.get("answers"):
        bits.append("، ".join(decision["answers"]))
    bits.append("ثقة %d%%" % int(round(decision.get("confidence", 0) * 100)))
    if decision.get("why"):
        bits.append(decision["why"])
    if composed.get("team"):
        bits.append("الفريق: " + composed["team"] + (" (عاجل)" if composed.get("urgent") else ""))
    return " · ".join(bits)


def dump(decision):
    return json.dumps({k: decision.get(k) for k in ("door", "answers", "confidence", "why")}, ensure_ascii=False)
