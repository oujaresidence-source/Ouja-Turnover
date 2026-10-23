# -*- coding: utf-8 -*-
"""
rrdesk.translate — the cheapest faithful translation we can buy.

Order of attempts for every message (each one cheaper than the next):
    1. the phrase table          (engine.PHRASES + study phrases + owner phrases) — free
    2. the cache                 sha256(normalized text + direction + glossary version) — free
    3. the daily cap             RRDESK_DAILY_CALLS (stored setting wins) — over it, no call
    4. ONE Haiku call            12 s timeout, one retry after 3 s; Sam's messages get the
                                 request classification folded into the same call
Numbers, codes, mentions, links and custom emoji are swapped for ⟦n⟧ placeholders before the
call and put back after, so the model cannot change a claim amount or a reservation code even
if it tries. A missing placeholder is appended back, never lost.

We make our own HTTP call instead of bot.py's claude_json because the brief needs real token
usage (cost accounting) and a 12-second budget; claude_json returns neither.
"""

import hashlib
import json
import os
import re
import time

from . import db, engine
from .host import HOST

NL = chr(10)
API_URL = "https://api.anthropic.com/v1/messages"
TIMEOUT_S = 12
RETRY_AFTER_S = 3
SAR_PER_USD = 3.75
SEED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "glossary.seed.json")


class CapReached(Exception):
    pass


class TranslateFailed(Exception):
    pass


# ------------------------------------------------------------------ config

def _env_float(name, default):
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return float(default)


def price_in():
    """USD per million input tokens. Default = Anthropic's published Haiku 4.5 price
    (platform.claude.com/docs/en/about-claude/pricing, checked 2026-10-24: $1 in / $5 out)."""
    return _env_float("RRDESK_PRICE_IN_USD", 1.0)


def price_out():
    return _env_float("RRDESK_PRICE_OUT_USD", 5.0)


def cost_usd(tokens_in, tokens_out):
    return round((tokens_in or 0) * price_in() / 1e6 + (tokens_out or 0) * price_out() / 1e6, 6)


def daily_cap():
    v = db.setting("daily_calls")
    try:
        return max(0, int(v if v is not None else (os.environ.get("RRDESK_DAILY_CALLS") or 1500)))
    except ValueError:
        return 1500


def _day_key(now):
    return "calls:" + now.date().isoformat()


def calls_today(now):
    try:
        return int(db.setting(_day_key(now), "0") or 0)
    except ValueError:
        return 0


def cap_reached(now):
    return calls_today(now) >= daily_cap()


# ------------------------------------------------------------------ glossary

_gcache = {"at": 0.0, "terms": [], "version": "0"}


def glossary():
    """[{term_ar, term_en, note}] — the seed file plus the owner's edits (a stored list wins
    term by term). Cached 30 s."""
    if time.time() - _gcache["at"] < 30 and _gcache["terms"]:
        return _gcache["terms"], _gcache["version"]
    seed = []
    try:
        with open(SEED_PATH, encoding="utf-8") as f:
            seed = json.load(f) or []
    except Exception as e:
        print("[rrdesk] glossary seed unreadable:", e)
    edits = db.loads(db.setting("glossary"), []) or []
    by = {}
    for t in list(seed) + list(edits):
        k = engine.normalize(t.get("term_ar") or "") + "|" + engine.normalize(t.get("term_en") or "")
        if t.get("deleted"):
            by.pop(k, None)
            continue
        if (t.get("term_ar") or "").strip() and (t.get("term_en") or "").strip():
            by[k] = {"term_ar": t["term_ar"].strip(), "term_en": t["term_en"].strip(),
                     "note": (t.get("note") or "").strip()}
    terms = sorted(by.values(), key=lambda t: t["term_en"].lower())
    version = hashlib.sha256(json.dumps(terms, ensure_ascii=False, sort_keys=True)
                             .encode("utf-8")).hexdigest()[:12]
    _gcache.update({"at": time.time(), "terms": terms, "version": version})
    return terms, version


def reset_glossary_cache():
    _gcache.update({"at": 0.0, "terms": [], "version": "0"})


CORE_TERMS = ("aircover", "claim", "invoice", "receipt", "quote", "evidence")


def relevant_terms(text, limit=25):
    """The glossary terms that actually appear in this message, plus a few claim words the
    model must always render the same way. Keeps the prompt small (cost) and on point."""
    terms, _v = glossary()
    norm = " " + engine.normalize(text) + " "
    hit, core = [], []
    for t in terms:
        a, en = engine.normalize(t["term_ar"]), engine.normalize(t["term_en"])
        if (a and " " + a + " " in norm) or (en and " " + en + " " in norm):
            hit.append(t)
        elif en in CORE_TERMS:
            core.append(t)
    return (hit + core)[:limit]


def extra_phrases():
    """Owner/study phrases for the free table: {'ar2en': {...}, 'en2ar': {...}}."""
    raw = db.loads(db.setting("phrases"), {}) or {}
    out = {"ar2en": {}, "en2ar": {}}
    for d in out:
        for k, v in (raw.get(d) or {}).items():
            if engine.normalize(k) and v:
                out[d][engine.normalize(k)] = v
    return out


# ------------------------------------------------------------------ placeholders

_PROTECT = re.compile(
    r"(<a?:[A-Za-z0-9_]+:[0-9]+>"              # custom emoji
    r"|<[@#][!&]?[0-9]+>"                       # user / channel / role mentions
    r"|https?://[^ <>" + NL + r"]+"             # links
    r"|HM[A-Z0-9]{8}"                           # Airbnb reservation codes
    r"|[0-9٠-٩][0-9٠-٩,.:/-]*[0-9٠-٩]|[0-9٠-٩])")  # numbers, amounts, dates


def protect(text):
    keep = []

    def sub(m):
        keep.append(m.group(0))
        return "⟦%d⟧" % (len(keep) - 1)
    return _PROTECT.sub(sub, text or ""), keep


def restore(text, keep):
    out = text or ""
    missing = []
    for i, tok in enumerate(keep):
        ph = "⟦%d⟧" % i
        if ph in out:
            out = out.replace(ph, tok)
        else:
            missing.append(tok)
    if missing:
        out = out.rstrip() + " (" + " ".join(missing) + ")"
    return out


# ------------------------------------------------------------------ the prompt

SYSTEM = NL.join((
    "You translate messages inside an internal damage-claim ticket room of Ouja Residence, a "
    "short-term-rental company in Riyadh. The operations team writes Saudi (Najdi) Arabic; Sam, "
    "who files Airbnb AirCover claims, writes English.",
    "Rules:",
    "- Keep the meaning exactly. Never add, soften, explain or drop facts, amounts, dates, "
    "unit names, reservation codes, names or numbers.",
    "- Tokens like ⟦0⟧, ⟦1⟧ stand for numbers, codes, mentions and links. Copy every one of "
    "them unchanged into the translation, in the right place.",
    "- Apartment names that start with 'Ouja |' stay exactly as written.",
    "- Arabic output: simple modern standard Arabic with a natural Saudi feel, short.",
    "- English output: plain, short, natural.",
    "- Use the glossary translations whenever a glossary term appears.",
    "- Output ONLY the JSON object requested. No prose, no code fences.",
))

CLASSIFY = (
    "Also decide whether Sam is ASKING the team for something (a request they must act on or "
    "answer), as opposed to informing, thanking, or chatting. Return these keys too: "
    "is_request (true/false), confidence (0..1, how sure you are), asks (list, any of: photos, "
    "video, invoice, quote, guest_chat, airbnb_screens, ops_report, receipt, info, action, "
    "other), urgent (true only if Sam says it is urgent / now / asap / today deadline), "
    "addressed_to_hint (a name he addresses, or ''), summary_en (one short line: what he wants), "
    "summary_ar (the same line in Arabic)."
)


def _user_prompt(text, direction_, classify):
    target = "English" if direction_ == "ar2en" else "Arabic"
    terms = relevant_terms(text)
    g = NL.join("- %s = %s%s" % (t["term_ar"], t["term_en"], (" (" + t["note"] + ")") if t["note"] else "")
                for t in terms)
    keys = '{"translation": "..."}' if not classify else (
        '{"translation": "...", "is_request": true, "confidence": 0.0, "asks": [], '
        '"urgent": false, "addressed_to_hint": "", "summary_en": "", "summary_ar": ""}')
    parts = ["Translate into %s." % target]
    if g:
        parts.append("Glossary:" + NL + g)
    if classify:
        parts.append(CLASSIFY)
    parts.append("Return JSON shaped like: " + keys)
    parts.append("MESSAGE:" + NL + text)
    return (NL + NL).join(parts)


def _embed_prompt(obj, direction_):
    target = "English" if direction_ == "ar2en" else "Arabic"
    return ("Translate every string value of this JSON object into %s. Keep the same keys, the "
            "same list lengths and the same order. Return ONLY the translated JSON object." % target
            + NL + NL + json.dumps(obj, ensure_ascii=False))


# ------------------------------------------------------------------ the HTTP call

def _post(payload):
    import requests
    key = HOST.api_key() if HOST.api_key else os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise TranslateFailed("no api key")
    r = requests.post(API_URL, timeout=TIMEOUT_S, json=payload,
                      headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                               "content-type": "application/json"})
    if r.status_code >= 400:
        raise TranslateFailed("HTTP %s" % r.status_code)
    return r.json()


def call_model(user_content, max_tokens=700, system=SYSTEM, poster=None):
    """One call, one retry after 3 s. Returns (text, tokens_in, tokens_out). `poster` is the
    test seam (a fake that returns the API's JSON)."""
    model = (HOST.model() if HOST.model else "") or os.environ.get(
        "CLAUDE_MODEL", "claude-haiku-4-5-20251001")
    payload = {"model": model, "max_tokens": max_tokens, "system": system,
               "messages": [{"role": "user", "content": user_content}]}
    post = poster or _post
    last = None
    for attempt in (1, 2):
        try:
            data = post(payload)
            blocks = data.get("content") or []
            text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
            u = data.get("usage") or {}
            return text, int(u.get("input_tokens") or 0), int(u.get("output_tokens") or 0)
        except Exception as e:
            last = e
            if attempt == 1:
                time.sleep(RETRY_AFTER_S if poster is None else 0)
    raise TranslateFailed(str(last))


def _parse_json(text):
    t = (text or "").replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(t)
    except ValueError:
        i, j = t.find("{"), t.rfind("}")
        if i >= 0 and j > i:
            try:
                return json.loads(t[i:j + 1])
            except ValueError:
                pass
    raise TranslateFailed("unparseable model output")


def clean_classify(d):
    """Validate the classification half of the JSON contract. Anything malformed becomes the
    SAFE answer: not a request (a wrong 'yes' can cost somebody money; a wrong 'no' cannot)."""
    try:
        conf = float(d.get("confidence"))
    except (TypeError, ValueError):
        conf = 0.0
    conf = max(0.0, min(1.0, conf))
    asks = [a for a in (d.get("asks") or []) if a in engine.ASKS] if isinstance(d.get("asks"), list) else []
    is_req = d.get("is_request") is True
    return {"is_request": is_req, "confidence": conf,
            "asks": asks or (["other"] if is_req else []), "urgent": d.get("urgent") is True,
            "addressed_to_hint": str(d.get("addressed_to_hint") or "")[:80],
            "summary_en": str(d.get("summary_en") or "")[:300],
            "summary_ar": str(d.get("summary_ar") or "")[:300]}


NOT_A_REQUEST = {"is_request": False, "confidence": 0.0, "asks": [], "urgent": False,
                 "addressed_to_hint": "", "summary_en": "", "summary_ar": ""}


# ------------------------------------------------------------------ public

def translate_text(text, direction_, classify=False, now=None, poster=None):
    """{translation, source: phrase|cache|model, tokens_in, tokens_out, cost_usd, classify}
    Raises CapReached (no call made) or TranslateFailed (call made and failed)."""
    now = now or db.now()
    phrase = engine.phrase_lookup(text, direction_, extra_phrases())
    if phrase:
        return {"translation": phrase, "source": "phrase", "tokens_in": 0, "tokens_out": 0,
                "cost_usd": 0.0, "classify": dict(NOT_A_REQUEST) if classify else None}
    _terms, gver = glossary()
    key = engine.cache_key(text, direction_ + (":c" if classify else ""), gver)
    hit = db.cache_get(key)
    if hit and hit.get("translation"):
        return {"translation": hit["translation"], "source": "cache", "tokens_in": 0,
                "tokens_out": 0, "cost_usd": 0.0, "classify": hit.get("classify")}
    if cap_reached(now):
        raise CapReached()
    masked, keep = protect(text)
    db.incr(_day_key(now))
    out, tin, tout = call_model(_user_prompt(masked, direction_, classify),
                                max_tokens=900 if classify else 700, poster=poster)
    data = _parse_json(out)
    tr = data.get("translation")
    if not isinstance(tr, str) or not tr.strip():
        raise TranslateFailed("no translation in model output")
    result = {"translation": restore(tr.strip(), keep),
              "classify": clean_classify(data) if classify else None}
    db.cache_put(key, direction_, result)
    return {"translation": result["translation"], "source": "model", "tokens_in": tin,
            "tokens_out": tout, "cost_usd": cost_usd(tin, tout), "classify": result["classify"]}


def translate_embed(emb, direction_, now=None, poster=None):
    """Bot embeds: title, description and every field name/value, in one call. Cached by
    template (identical status lines are paid for once). Returns (embed_dict, meta)."""
    now = now or db.now()
    obj = {"title": emb.get("title") or "", "description": emb.get("description") or "",
           "fields": [{"name": f.get("name") or "", "value": f.get("value") or ""}
                      for f in (emb.get("fields") or [])][:25]}
    flat = json.dumps(obj, ensure_ascii=False, sort_keys=True)
    _t, gver = glossary()
    key = engine.cache_key("embed:" + flat, direction_, gver)
    hit = db.cache_get(key)
    if hit and hit.get("embed"):
        return hit["embed"], {"source": "cache", "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0}
    if cap_reached(now):
        raise CapReached()
    keeps = {}

    def mask(s, tag):
        m, k = protect(s)
        keeps[tag] = k
        return m
    masked = {"title": mask(obj["title"], "t"), "description": mask(obj["description"], "d"),
              "fields": [{"name": mask(f["name"], "n%d" % i), "value": mask(f["value"], "v%d" % i)}
                         for i, f in enumerate(obj["fields"])]}
    db.incr(_day_key(now))
    out, tin, tout = call_model(_embed_prompt(masked, direction_), max_tokens=1500, poster=poster)
    data = _parse_json(out)
    fields_in = data.get("fields") if isinstance(data.get("fields"), list) else []
    res = {"title": restore(str(data.get("title") or ""), keeps["t"]),
           "description": restore(str(data.get("description") or ""), keeps["d"]),
           "fields": []}
    for i, f in enumerate(obj["fields"]):
        tf = fields_in[i] if i < len(fields_in) and isinstance(fields_in[i], dict) else {}
        res["fields"].append({"name": restore(str(tf.get("name") or f["name"]), keeps["n%d" % i]),
                              "value": restore(str(tf.get("value") or f["value"]), keeps["v%d" % i])})
    db.cache_put(key, direction_, {"embed": res})
    return res, {"source": "model", "tokens_in": tin, "tokens_out": tout,
                 "cost_usd": cost_usd(tin, tout)}


def translate_media(url, content_type, now=None, poster=None):
    """The on-demand «Translate image text» button: one vision call, English out."""
    now = now or db.now()
    if cap_reached(now):
        raise CapReached()
    is_pdf = "pdf" in (content_type or "").lower()
    block = ({"type": "document", "source": {"type": "url", "url": url}} if is_pdf
             else {"type": "image", "source": {"type": "url", "url": url}})
    db.incr(_day_key(now))
    out, tin, tout = call_model(
        [block, {"type": "text", "text": "Read all the text in this document (it is claim evidence:"
                 " an invoice, receipt or screenshot). Translate it into plain English. Keep every"
                 " amount, date, name and number exactly. Return JSON: "
                 '{"translation": "..."}'}],
        max_tokens=1200, poster=poster)
    data = _parse_json(out)
    tr = str(data.get("translation") or "").strip()
    if not tr:
        raise TranslateFailed("no text found")
    return {"translation": tr, "tokens_in": tin, "tokens_out": tout,
            "cost_usd": cost_usd(tin, tout)}


def split_for_embeds(text, size=4000):
    """Long text across embeds of ≤ 4,000 characters, cut at a line or space when possible."""
    t = text or ""
    out = []
    while len(t) > size:
        cut = t.rfind(NL, 0, size)
        if cut < size // 2:
            cut = t.rfind(" ", 0, size)
        if cut < size // 2:
            cut = size
        out.append(t[:cut].rstrip())
        t = t[cut:].lstrip()
    out.append(t)
    return [x for x in out if x] or [""]
