# -*- coding: utf-8 -*-
"""digest.schema — the frozen content contract (brief §4).

The ONLY interface between the research layer and the render layer. Renderers read a
payload that passed `assert_valid`; they never call the web. Caps and word limits are
rules here so a wrong item cannot reach a page by discipline failing. Pure."""

import re

MAX_TITLE_WORDS = 4
MAX_SUB_WORDS = 10
MIN_PRIMARY_CONFIDENCE = 0.75
DAYS = ("thu", "fri", "sat")
ART_KINDS = ("owned", "og", "generated", "none")

SECTIONS = {
    "events":   {"title": "فعاليات ومعارض", "min": 2, "max": 4, "exact": None},
    "cinema":   {"title": "جديد في السينما", "min": 0, "max": 3, "exact": (0, 3)},
    "worth":    {"title": "يستاهل الزيارة",  "min": 0, "max": 1, "exact": None},
    "fixtures": {"title": "مباريات الأسبوع", "min": 0, "max": 6, "exact": None},
}
SECTION_ORDER = ("events", "cinema", "worth", "fixtures")


class SchemaError(ValueError):
    """The payload violates the content contract — nothing renders."""


_WS = re.compile(r"\s+")


def word_count(s):
    return len([w for w in _WS.split((s or "").strip()) if w])


def layout_for(key, n):
    if key == "events":
        return {2: "g2h", 3: "g3v"}.get(n, "g2")
    if key == "cinema":
        return "g3"
    if key == "worth":
        return "g1"
    if key == "fixtures":
        return "fix"
    return "g1"


def empty_payload(week_of, date_label, issue_no, generated_at):
    from .dates import ar_digits
    return {
        "issue": ar_digits(issue_no),
        "issue_no": int(issue_no),
        "week_of": week_of,
        "dateLabel": date_label,
        "generated_at": generated_at,
        "verified_urls": [],
        "sections": [
            {"title": SECTIONS[k]["title"], "key": k, "layout": layout_for(k, 0), "items": []}
            for k in SECTION_ORDER
        ],
        "dropped": [],
        "alternates": {},
    }


def _check_source(errs, where, it, verified):
    src = it.get("source") or {}
    if not (src.get("name") and src.get("url") and src.get("fetched_at")):
        errs.append("%s: source must carry name, url and fetched_at" % where)
    url = it.get("url") or ""
    if not url.startswith("https://"):
        errs.append("%s: url must be https (%r)" % (where, url))
    elif url not in verified:
        errs.append("%s: url is not in verified_urls (%s)" % (where, url))
    conf = it.get("confidence")
    if not isinstance(conf, (int, float)) or conf < MIN_PRIMARY_CONFIDENCE:
        errs.append("%s: confidence %r below the primary floor %.2f" % (where, conf, MIN_PRIMARY_CONFIDENCE))
    if it.get("day") not in DAYS:
        errs.append("%s: day must be one of %s (got %r)" % (where, "/".join(DAYS), it.get("day")))


def _check_card(errs, where, it, verified):
    ttl = it.get("ttl") or ""
    sub = it.get("sub") or ""
    if not ttl:
        errs.append("%s: empty ttl" % where)
    elif word_count(ttl) > MAX_TITLE_WORDS:
        errs.append("%s: ttl over %d words: «%s»" % (where, MAX_TITLE_WORDS, ttl))
    if word_count(sub) > MAX_SUB_WORDS:
        errs.append("%s: sub over %d words: «%s»" % (where, MAX_SUB_WORDS, sub))
    if not it.get("chip"):
        errs.append("%s: chip (district) missing" % where)
    art = it.get("art") or {}
    if art.get("kind") not in ART_KINDS:
        errs.append("%s: art.kind must be one of %s" % (where, "/".join(ART_KINDS)))
    _check_source(errs, where, it, verified)


def _check_fixture(errs, where, it, verified):
    for k in ("home", "away", "when"):
        if not it.get(k):
            errs.append("%s: fixture missing %s" % (where, k))
    _check_source(errs, where, it, verified)


def validate(payload):
    """Return a list of human-readable errors; [] means the payload may render."""
    errs = []
    if not isinstance(payload, dict):
        return ["payload must be an object"]
    for k in ("issue", "week_of", "dateLabel", "generated_at"):
        if not payload.get(k):
            errs.append("missing %s" % k)
    verified = set(payload.get("verified_urls") or [])
    seen = set()
    for s in payload.get("sections") or []:
        key = s.get("key")
        if key not in SECTIONS:
            errs.append("unknown section key %r" % key)
            continue
        if key in seen:
            errs.append("section %s appears twice" % key)
        seen.add(key)
        rule = SECTIONS[key]
        items = s.get("items") or []
        n = len(items)
        if rule["exact"] and n not in rule["exact"]:
            errs.append("%s: needs exactly %s items, got %d" % (key, " or ".join(str(x) for x in rule["exact"]), n))
        elif n < rule["min"] or n > rule["max"]:
            errs.append("%s: needs %d–%d items, got %d" % (key, rule["min"], rule["max"], n))
        if s.get("title") != rule["title"]:
            errs.append("%s: title must be «%s»" % (key, rule["title"]))
        if n and s.get("layout") != layout_for(key, n):
            errs.append("%s: layout %r does not match %d items (want %s)" % (key, s.get("layout"), n, layout_for(key, n)))
        for i, it in enumerate(items):
            where = "%s[%d]" % (key, i)
            if key == "fixtures":
                _check_fixture(errs, where, it, verified)
            else:
                _check_card(errs, where, it, verified)
    if "events" not in seen:
        errs.append("events: section missing (needs %d–%d items)" % (SECTIONS["events"]["min"], SECTIONS["events"]["max"]))
    for d in payload.get("dropped") or []:
        if not (d.get("ttl") and d.get("reason")):
            errs.append("dropped entries need ttl and reason")
    return errs


def assert_valid(payload):
    errs = validate(payload)
    if errs:
        raise SchemaError("digest payload invalid:\n  " + "\n  ".join(errs))
    return payload


def section(payload, key):
    for s in payload.get("sections") or []:
        if s.get("key") == key:
            return s
    return None


def primaries(payload):
    """Flat list of (section_key, slot, item) for every primary item."""
    out = []
    for s in payload.get("sections") or []:
        for i, it in enumerate(s.get("items") or []):
            out.append((s.get("key"), i, it))
    return out
