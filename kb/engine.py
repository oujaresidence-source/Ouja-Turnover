# -*- coding: utf-8 -*-
"""
kb.engine — PURE functions. No database, no aiohttp, no bot. Everything here takes plain
dicts and returns plain values, so tests/test_kb_search.py drives the real rules without
a web server (same pattern as schedule/engine.py and wifi/engine.py).

WHY SUBSTRING MATCHING AND NOT FTS5
-----------------------------------
The handoff schema proposed FTS5 virtual tables. We deliberately do not use them. FTS5
matches whole tokens (or token PREFIXES); the specified query semantics in the handoff's
DATA_MODEL §4 are explicitly "substring matching, not prefix — users type fragments from
the middle of names". Those two cannot both be true. At 56 units a folded haystack plus
`LIKE '%tok%'` answers in well under a millisecond, matches the specified behaviour
exactly, and removes a compile-time SQLite dependency from the Railway image. If the FAQ
layer ever passes a few thousand rows, revisit — not before.

THE FOLD IS THE WHOLE TRICK
---------------------------
Users type الملقى / الملقا / المقى / Al Malqa for one district, and أحمد / احمد for one
person. fold() flattens those differences, and the SAME fold runs on the stored haystack
and on the incoming query — if the two ever drift apart, search silently stops finding
things, so they are one function and there is only one.
"""

import re
import unicodedata

# Arabic diacritics (harakat) + tatweel — decoration that carries no search meaning.
_STRIP = re.compile(r"[ً-ْـ]")
_SPACE = re.compile(r"\s+")
_TIGHTEN = re.compile(r"[\s\-_]")

# District spellings seen in the source spreadsheet. Every variant must stay searchable;
# only the canonical form is ever stored on the unit.
DISTRICT_VARIANTS = {
    "الملقا": ["الملقى", "المقى", "Al Malqa"],
    "الغدير": ["الغديو", "Al Ghadeer"],
    "النرجس": ["نرجس", "Al Narjis"],
    "قرطبة": ["قرطبه", "Qurtubah"],
    "النزهة": ["النزهه", "Al Nuzha"],
    "عرقة": ["عرقه", "Irqah"],
}

# Enums are stored as the English key and rendered in Arabic. NEVER store the Arabic
# label: «ربع شهري» and «ربع سنوي» differ by one character and decide when an owner is
# paid, so the value that travels through the system must be unambiguous.
POLICY = ("ouja", "owner")
POLICY_AR = {"ouja": "علينا", "owner": "على المالك"}
CYCLE = ("monthly", "biweekly_quarter_month", "quarterly")
CYCLE_AR = {"monthly": "شهري", "biweekly_quarter_month": "ربع شهري", "quarterly": "ربع سنوي"}

GAP_DISTRICT = "الحي"
GAP_CYCLE = "دورة الدفع"
GAP_CLEANING = "النظافة"


def fold(s):
    """Normalise for search. Runs on stored text AND on the query — never one without
    the other."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", str(s).strip())
    s = _STRIP.sub("", s)
    s = s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    s = s.replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي")
    return _SPACE.sub(" ", s).strip().lower()


def tighten(s):
    """'HUE 202' -> 'hue202', so a user who types it without the space still finds it."""
    return _TIGHTEN.sub("", fold(s))


def build_hay(unit, owner=None):
    """The folded haystack one unit is searched through: its own name and code, its
    owner's name and every alias of it, its district in every known spelling, the English
    district, and a space-stripped copy of the name."""
    parts = [unit.get("unit_name"), unit.get("listing_code"), unit.get("district"),
             unit.get("district_en"), unit.get("note")]
    if owner:
        parts.append(owner.get("name_ar"))
        parts += list(owner.get("aliases") or [])
    d = unit.get("district")
    if d:
        parts += DISTRICT_VARIANTS.get(d, [])
    parts += list(unit.get("aliases") or [])
    hay = " ".join(fold(p) for p in parts if p)
    if unit.get("unit_name"):
        hay += " " + tighten(unit["unit_name"])
    return _SPACE.sub(" ", hay).strip()


def build_owner_hay(owner):
    return _SPACE.sub(" ", " ".join(
        fold(p) for p in [owner.get("name_ar")] + list(owner.get("aliases") or []) if p)).strip()


def query_tokens(q):
    """Split the folded query on whitespace. Every token must appear, so «ابو فهد 101»
    narrows instead of widening."""
    return [t for t in fold(q).split(" ") if t]


def matches(hay, toks):
    return all(t in (hay or "") for t in toks)


def gaps(unit):
    """Which facts are missing. Returns Arabic labels for direct display — the UI never
    shows a blank where a fact is missing, it shows the labelled gap."""
    if _truthy(unit.get("ouja_owned")):
        # Ouja's own unit: there is no owner to bill and no payout to schedule, so the
        # fields the completeness rule cares about genuinely do not apply.
        return []
    out = []
    if not unit.get("district"):
        out.append(GAP_DISTRICT)
    if not unit.get("payment_cycle"):
        out.append(GAP_CYCLE)
    pol = unit.get("cleaning_policy")
    if pol == "owner":
        # Policy known, amount not — still unanswerable, so still a gap.
        if unit.get("cleaning_monthly_sar") in (None, ""):
            out.append(GAP_CLEANING)
    elif pol != "ouja":
        out.append(GAP_CLEANING)
    return out


def is_complete(unit):
    return not gaps(unit)


def _truthy(v):
    return v in (1, True, "1", "true", "True")


def validate(patch):
    """Server-side enum + amount validation. Returns (cleaned, error_ar). A free-text
    payment cycle or an owner-paid subscription with no amount is refused here, not in
    the browser — the browser is not the guard."""
    out = {}
    for k, v in (patch or {}).items():
        if k in ("cleaning_policy",):
            v = (v or "").strip() or None
            if v is not None and v not in POLICY:
                return None, "نوع النظافة غير معروف"
        elif k in ("payment_cycle",):
            v = (v or "").strip() or None
            if v is not None and v not in CYCLE:
                return None, "دورة الدفع غير معروفة"
        elif k == "cleaning_monthly_sar":
            if v in (None, "", "—"):
                v = None
            else:
                try:
                    v = float(v)
                except (TypeError, ValueError):
                    return None, "مبلغ النظافة لازم يكون رقم"
                if v < 0:
                    return None, "مبلغ النظافة ما يصير بالسالب"
        elif k == "ouja_owned":
            v = 1 if _truthy(v) else 0
        elif isinstance(v, str):
            v = v.strip() or None
        out[k] = v
    return out, None


def check_amount_rule(unit_after):
    """«على المالك» without a number is a gap we SHOW, not an error we refuse — the
    accountant knowing the policy but not the amount is a real and common state, and
    refusing to save it would just push the half-fact back into someone's memory. What we
    refuse is the reverse: an amount recorded against «علينا», which would be a number
    nobody ever charges."""
    if unit_after.get("cleaning_policy") == "ouja" and unit_after.get("cleaning_monthly_sar"):
        return "«علينا» معناها عوجا تتحملها — ما ينكتب لها مبلغ على المالك"
    return None


def find_conflicts(units):
    """Duplicate Hostaway listing codes. Two units sharing one code means revenue can
    post to the wrong unit and an owner statement can be wrong. Reported, NEVER
    auto-resolved: picking a side in code would silently move money."""
    by_code = {}
    names = {}
    for u in units:
        names[u.get("unit_id")] = u.get("unit_name") or u.get("unit_id")
        code = (u.get("listing_code") or "").strip()
        if code:
            by_code.setdefault(code, []).append(u.get("unit_id"))
    out = {}
    for code, ids in by_code.items():
        if len(ids) > 1:
            for uid in ids:
                others = [x for x in ids if x != uid]
                out[uid] = [{"type": "duplicate_listing_code", "code": code,
                             "with": others,
                             # The team says «202B», not «UNT-473607-B». The warning has
                             # to name the unit the way the person reading it would.
                             "with_names": [names.get(x, x) for x in others]}]
    return out
