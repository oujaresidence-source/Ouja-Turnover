"""A harm tier above maintenance.

_MUSAED_ISSUE_TOPICS_DEFAULT (bot.py:13004) covers ac, leak, hot_water, elevator, door,
wifi, appliance. There is no tier for a person being hurt. Grep confirmed it across all
66,090 lines before this file existed: `injury` 0 · `blood` 0 · `إصابة` 0 · `نزيف` 0 ·
`ambulance` 0.

That absence has a cost with a name. T014 i25 — the guest writes «the blood on the pillow
due to my head injury». The next system message is a 10% discount-for-review offer. No
escalation, no record, thread ends.

Three tiers, highest wins:
    harm          somebody is hurt or in danger
    habitability  the unit is not livable right now — no water, no power, locked out
    security      the unit is not secure — broken lock, a stranger inside, theft

Config-first: STATE_DIR/incident_terms.json overrides the defaults live, mirroring
_musaed_issue_terms, so the team can add a word without a deploy.
"""

import json
import os
import re
import time

HARM, HABITABILITY, SECURITY = "harm", "habitability", "security"
TIERS = (HARM, HABITABILITY, SECURITY)          # highest first — order is the precedence

# Arabic terms match as SUBSTRINGS (there is no \b that behaves for Arabic), so a harm
# term must not be a prefix of an ordinary word. «كهربا» was in this list and matched
# «مافي كهرباء» — a power cut, which is habitability — as harm. Electric SHOCK is named
# explicitly instead. Check new Arabic terms against their innocent longer forms.
DEFAULT_TERMS = {
    HARM: [
        "إصابة", "اصابة", "جرح", "دم", "نزيف", "وقعت", "طاح", "طاحت", "حروق", "حرق",
        "حريق", "دخان", "غاز", "تسمم", "صعقة", "صعقني", "صعقتني", "انصعق", "انصعقت", "ضربتني الكهرباء", "كهربتني",
        "إسعاف", "اسعاف", "مستشفى",
        "injury", "injured", "blood", "bleeding", "burn", "burned", "fire", "smoke",
        "gas leak", "poison", "electric shock", "ambulance", "hospital", "fell",
    ],
    HABITABILITY: [
        "ما فيه ماء", "مافيه ماء", "ما فيه مويه", "انقطع الماء", "انقطعت المياه",
        "ما فيه كهرب", "مافي كهرباء", "انقطعت الكهرباء", "الباب مايفتح", "الباب ما يفتح",
        "محبوس", "ما أقدر أدخل", "ما اقدر ادخل",
        "no water", "no power", "no electricity", "locked out", "can't get in",
        "cannot get in", "cant get in",
    ],
    SECURITY: [
        "القفل مكسور", "القفل خربان", "حد دخل", "أحد دخل", "شخص غريب", "سرقة", "سرقوا",
        "كاميرا",
        "broken lock", "someone entered", "someone came in", "stranger", "theft",
        "stolen", "camera",
    ],
}

_FILENAME = "incident_terms.json"
_CACHE = {"mtime": None, "terms": None, "compiled": None}


def _state_dir():
    return os.environ.get("STATE_DIR", "/data")


def path():
    return os.path.join(_state_dir(), _FILENAME)


def _load_terms():
    """Owner-editable overrides win; a broken edit keeps serving the last good copy, and
    a missing file means the built-in list. Never raises."""
    try:
        mtime = os.path.getmtime(path())
    except Exception:
        mtime = None
    if _CACHE["mtime"] == mtime and _CACHE["terms"] is not None:
        return _CACHE["terms"], _CACHE["compiled"]

    terms = {k: list(v) for k, v in DEFAULT_TERMS.items()}
    if mtime is not None:
        try:
            with open(path(), "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                for tier in TIERS:
                    extra = data.get(tier)
                    if isinstance(extra, list) and extra:
                        terms[tier] = [str(x) for x in extra if str(x).strip()]
        except Exception as e:
            print("[incident] bad incident_terms.json, keeping defaults:", e)
            if _CACHE["terms"]:
                return _CACHE["terms"], _CACHE["compiled"]

    compiled = {}
    for tier, words in terms.items():
        pats = []
        for w in words:
            w = str(w).strip()
            if not w:
                continue
            # ASCII words get word boundaries so "fell" does not fire inside "fellow";
            # Arabic has no \b that behaves, so those match as substrings by design.
            pats.append(rf"\b{re.escape(w)}\b" if w.isascii() else re.escape(w))
        compiled[tier] = re.compile("|".join(pats), re.IGNORECASE) if pats else None
    _CACHE.update({"mtime": mtime, "terms": terms, "compiled": compiled})
    return terms, compiled


def classify_incident(text):
    """'harm' | 'habitability' | 'security' | None. Highest tier wins.

    Deliberately blunt. A false positive costs one human glance at a Discord card; a
    false negative is T014 — a guest reporting blood and getting a discount offer.
    """
    t = (text or "").strip()
    if not t:
        return None
    try:
        _, compiled = _load_terms()
        for tier in TIERS:                       # TIERS is ordered: harm first
            rx = compiled.get(tier)
            if rx and rx.search(t):
                return tier
    except Exception as e:
        print("[incident] classify failed:", e)
    return None


def match_detail(text):
    """(tier, matched_phrase) — for the Discord card, so a human sees WHY it fired."""
    t = (text or "").strip()
    if not t:
        return (None, "")
    try:
        _, compiled = _load_terms()
        for tier in TIERS:
            rx = compiled.get(tier)
            if rx:
                m = rx.search(t)
                if m:
                    return (tier, m.group(0))
    except Exception:
        pass
    return (None, "")


# ── the harm hold ────────────────────────────────────────────────────────────
# The ONLY in-repo defence against the Hostaway review-request template firing on an
# injury thread. It CANNOT stop Hostaway's own send — it stops OURS, and it surfaces the
# hold so a human goes and pauses the automation on that reservation. Say that out loud
# on the card; never let anyone believe the Hostaway automation is under control.
_HOLDS_FILE = "harm_holds.json"


def _holds_path():
    return os.path.join(_state_dir(), _HOLDS_FILE)


def _read_holds():
    try:
        with open(_holds_path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_holds(holds):
    try:
        os.makedirs(_state_dir(), exist_ok=True)
        tmp = _holds_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(holds, fh, ensure_ascii=False)
        os.replace(tmp, _holds_path())
    except Exception as e:
        print("[incident] could not persist harm holds:", e)


def set_hold(conversation_id, *, tier=HARM, ticket_id=None, detail=""):
    holds = _read_holds()
    holds[str(conversation_id or "")] = {
        "tier": tier, "ticket_id": ticket_id, "detail": str(detail or "")[:300],
        "at": time.time(), "cleared_by": None,
    }
    _write_holds(holds)
    return holds[str(conversation_id or "")]


def held(conversation_id):
    """The active hold on this conversation, or None."""
    h = _read_holds().get(str(conversation_id or ""))
    return h if h and not h.get("cleared_by") else None


def clear_hold(conversation_id, *, actor):
    """Only a human clears a harm hold, and their name is recorded."""
    if not str(actor or "").strip():
        raise ValueError("clearing a harm hold requires a named human")
    holds = _read_holds()
    h = holds.get(str(conversation_id or ""))
    if not h:
        return None
    h["cleared_by"] = str(actor)[:80]
    h["cleared_at"] = time.time()
    _write_holds(holds)
    return h


def reset_for_tests():
    _CACHE.update({"mtime": None, "terms": None, "compiled": None})
