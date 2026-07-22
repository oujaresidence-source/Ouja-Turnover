# -*- coding: utf-8 -*-
"""studio.engine — pure story-mining logic. No network, no db, no host access.

Everything here is deterministic and TDD-locked by tests/test_studio_engine.py:
qualification (which conversations are worth reading), transcript building
(what Claude actually sees), and strict-but-tolerant parsing of the three
model outputs (triage / story / idea cards). Keep it pure."""

import hashlib
import re
from datetime import date as _date

# conversation qualification -------------------------------------------------

# Hostaway reservation statuses that mean "a real stay happened / was booked".
# 'cancelled' intentionally qualifies — a last-minute cancellation IS a story.
STAY_STATUSES = ("new", "modified", "confirmed", "checked-in", "checked-out",
                 "cancelled", "ownerStay")

MIN_MSGS = 6          # owner rule: threads that died after 4–5 messages = no story
MIN_INBOUND = 2       # need a real back-and-forth, not an automation blast

# v2 taxonomy — POSITIVE, brand-forward archetypes only. The retired negative
# buckets (sad_exit/conflict/cancellation/angry_to_happy/emergency) fall through
# to "other" so no old label survives; a problem is a story ONLY as a hero_save.
STORY_TYPES = ("hero_save", "transformation", "transparency_numbers", "day_in_life",
               "hospitality_wow", "weird_delight", "heartwarming", "loyal_return",
               "operational_craft", "other")

# v3 (spec Section G): the owner's 7 psychological triggers. 'emotion' is the v2
# label and stays accepted forever so rows already in brain.db remain valid.
TRIGGERS = ("curiosity", "loss", "identity", "provocation",
            "authority", "social_proof", "news", "emotion")
AUDIENCES = ("niche", "escape")
# v3 adds the two signal-native formats (spec F6): a numbers reveal and a news reaction.
VIDEO_TYPES = ("talking", "tour", "before_after", "story_voiceover", "onsite",
               "data_reveal", "news_reaction")

# ---------------------------------------------------------------------------
# v3 SIGNAL BUS — the spine. Spec Section C: an idea with no real signal behind it
# does not get made. Signals are the only currency the generator may spend.
# ---------------------------------------------------------------------------

SIGNAL_FAMILIES = ("internal", "external", "manual")

# Ouja's own live data (spec D1–D6). 'guest_story' is the v2 conversation miner,
# now just one source among many instead of the whole system.
INTERNAL_SOURCES = ("occupancy", "pricing", "reviews", "ops", "season",
                    "insider", "guest_story")
# Live web search (spec D7–D10).
EXTERNAL_SOURCES = ("regulation", "market", "global_trend", "trend")

SIGNAL_SOURCES = INTERNAL_SOURCES + EXTERNAL_SOURCES + ("manual",)

_FAMILY_OF_SOURCE = {}
for _s_ in INTERNAL_SOURCES:
    _FAMILY_OF_SOURCE[_s_] = "internal"
for _s_ in EXTERNAL_SOURCES:
    _FAMILY_OF_SOURCE[_s_] = "external"
_FAMILY_OF_SOURCE["manual"] = "manual"

# Burned-out 2025–26 hook clichés (research brief) — any hook containing one of
# these substrings is dropped. Substring match on normalized text (Arabic + English).
BANNED_HOOK_PATTERNS = (
    "لن تصدق", "ما راح تصدق", "ما تتوقع", "انتظر للنهاية", "استنى النهاية", "شوف الآخر",
    "شوف النهاية", "قصة صادمة", "صادم", "هل تعلم", "تخيل انك",
    "you won't believe", "you wont believe", "wait for it", "wait till the end",
    "wait until the end", "pov:", "did you know", "shocking",
)

TRIM_MARK = "— … (قصّينا وسط المحادثة) … —"


def _res_status(convo):
    r = (convo or {}).get("reservation")
    if isinstance(r, dict):
        return str(r.get("status") or "").strip()
    return str((convo or {}).get("reservationStatus") or "").strip()


def _is_inbound(m):
    try:
        return int(m.get("isIncoming", m.get("incoming", 0)) or 0) == 1
    except Exception:
        return False


def _msg_ts(m):
    return str(m.get("date") or m.get("insertedOn") or m.get("latestMessageDate") or "")


def is_stay(status):
    """True when the reservation status means a real stay was booked."""
    return str(status or "").strip() in STAY_STATUSES


def reservation_id(convo):
    c = convo or {}
    r = c.get("reservation")
    rid = c.get("reservationId") or (r.get("id") if isinstance(r, dict) else None)
    return str(rid) if rid else ""


def qualifies_msgs(msgs, min_msgs=MIN_MSGS):
    """(ok, reason) on the thread alone. reason in ('ok','short','monologue')."""
    real = [m for m in (msgs or []) if (m.get("body") or "").strip()]
    if len(real) < min_msgs:
        return False, "short"
    if sum(1 for m in real if _is_inbound(m)) < MIN_INBOUND:
        return False, "monologue"
    return True, "ok"


def qualifies(convo, msgs, min_msgs=MIN_MSGS):
    """(ok, reason). reason in ('ok','inquiry','short','monologue').
    NOTE: only trusts a status embedded on the conversation — live Hostaway
    conversations usually DON'T embed one, so the miner resolves the status
    via /reservations/{id} instead of calling this (2026-07-06 fix: the first
    live scan skipped all 1500 conversations as 'inquiry')."""
    if not is_stay(_res_status(convo)):
        return False, "inquiry"
    return qualifies_msgs(msgs, min_msgs)


# transcript ------------------------------------------------------------------

def build_transcript(msgs, max_msgs=60, max_chars=7000, body_cap=400):
    """Chronological «الضيف:/الفريق:» transcript. Long threads keep the head
    (context: who booked, what was promised) and the tail (the resolution) and
    trim the middle — both ends carry the story."""
    real = sorted([m for m in (msgs or []) if (m.get("body") or "").strip()],
                  key=_msg_ts)
    if len(real) > max_msgs:
        head = max_msgs // 3
        real = real[:head] + [None] + real[-(max_msgs - head):]
    lines = []
    for m in real:
        if m is None:
            lines.append(TRIM_MARK)
            continue
        body = (m.get("body") or "").strip()[:body_cap]
        lines.append(("الضيف: " if _is_inbound(m) else "الفريق: ") + body)
    # char cap: drop middle lines until we fit
    def _len():
        return sum(len(x) + 1 for x in lines)
    trimmed = False
    while _len() > max_chars and len(lines) > 4:
        lines.pop(len(lines) // 2)
        trimmed = True
    if trimmed and TRIM_MARK not in lines:
        lines.insert(len(lines) // 2, TRIM_MARK)
    return "\n".join(lines)


# model-output parsing ---------------------------------------------------------

def _s(v, cap=600):
    return str(v).strip()[:cap] if v is not None else ""


def parse_triage(d):
    """{story:bool, score:0-10, type, brand_safe:bool, positive:bool, one_line} or None.

    brand_safe/positive FAIL CLOSED (default False when absent) so an unjudged story
    can never slip through the brand gate."""
    if not isinstance(d, dict):
        return None
    try:
        score = int(float(d.get("score")))
    except (TypeError, ValueError):
        return None
    score = max(0, min(10, score))
    typ = _s(d.get("type"), 40)
    if typ not in STORY_TYPES:
        typ = "other"
    return {"story": bool(d.get("story")), "score": score, "type": typ,
            "brand_safe": bool(d.get("brand_safe")), "positive": bool(d.get("positive")),
            "one_line": _s(d.get("one_line"), 300)}


def brand_ok(triage):
    """True only when the story is a real, POSITIVE, brand-safe story of a known
    positive type — the single gate between triage and a premium/idea pass."""
    if not isinstance(triage, dict):
        return False
    return bool(triage.get("story")) and bool(triage.get("brand_safe")) \
        and bool(triage.get("positive")) and triage.get("type") in STORY_TYPES


def hook_is_clean(hook):
    """False if the hook is empty or contains a burned-out cliché (BANNED_HOOK_PATTERNS)."""
    t = str(hook or "").strip().lower()
    if not t:
        return False
    return not any(p in t for p in BANNED_HOOK_PATTERNS)


def parse_story(d):
    """{title, summary, beats[], quotes[], emotion, lesson} or None."""
    if not isinstance(d, dict):
        return None
    title = _s(d.get("title"), 120)
    if not title:
        return None
    def _lst(key, cap):
        v = d.get(key)
        if not isinstance(v, list):
            return []
        return [_s(x, cap) for x in v if _s(x, cap)][:12]
    return {"title": title,
            "summary": _s(d.get("summary"), 2500),
            "angle": _s(d.get("angle"), 400),
            "beats": _lst("beats", 300),
            "quotes": _lst("quotes", 300),
            "emotion": _s(d.get("emotion"), 200),
            "lesson": _s(d.get("lesson"), 400)}


def parse_ideas(d):
    """List of validated idea cards (possibly empty)."""
    if not isinstance(d, dict) or not isinstance(d.get("ideas"), list):
        return []
    out = []
    for raw in d["ideas"][:6]:
        if not isinstance(raw, dict):
            continue
        hook = _s(raw.get("hook_spoken"), 200)
        title = _s(raw.get("visual_title"), 120)
        why = _s(raw.get("why_it_works"), 400)
        if not hook or not title or not why:
            continue
        # every card must justify itself, and neither the spoken hook nor the
        # on-screen title may contain a burned-out cliché.
        if not hook_is_clean(hook) or not hook_is_clean(title):
            continue
        script = raw.get("script")
        if not isinstance(script, list):
            script = []
        # kill any timed-beat grid the model slipped in — the script must read like
        # talking, never like a storyboard (owner verdict 2026-07-24).
        script = [strip_timestamps(x) for x in script]
        aud = _s(raw.get("audience"), 20)
        trg = _s(raw.get("trigger"), 20)
        vt = _s(raw.get("video_type"), 30)
        out.append({
            "hook_spoken": hook,
            "visual_title": title,
            "visual_sub": _s(raw.get("visual_sub"), 160),
            "angle": _s(raw.get("angle"), 400),
            "why_it_works": why,
            "script": [_s(x, 400) for x in script if _s(x, 400)][:8],
            "video_type": vt if vt in VIDEO_TYPES else "talking",
            "cta": _s(raw.get("cta"), 200),
            "audience": aud if aud in AUDIENCES else "niche",
            "trigger": trg if trg in TRIGGERS else "curiosity",
            "shape": _s(raw.get("shape"), 30),   # validated against shapes in ideas.py
        })
    return out


# v3 signals -------------------------------------------------------------------

def _norm_arabic(text):
    """Fold Arabic spelling variants so two wordings of the same angle compare equal:
    Arabic-Indic digits -> ASCII, alef/ya/ta-marbuta unified, diacritics + tatweel
    dropped, definite article and common possessive suffixes stripped."""
    t = str(text or "")
    for i, d in enumerate("٠١٢٣٤٥٦٧٨٩"):
        t = t.replace(d, str(i))
    t = re.sub("[ً-ْـ]", "", t)          # harakat + tatweel
    t = t.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    t = t.replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي")
    t = re.sub("[^0-9a-zA-Zء-ي]+", " ", t)
    return t.strip()


# Function words carry no angle — dropping them keeps the comparison on content.
_STOP = {"من", "في", "على", "عن", "الى", "او", "و", "ان", "انه", "هذا", "هذي", "هذه",
         "الي", "اللي", "مع", "كل", "بس", "لكن", "ما", "لا", "هو", "هي", "يا",
         "the", "a", "an", "of", "to", "in", "for", "and", "is", "are"}


def _tokens(text):
    out = set()
    for w in _norm_arabic(text).lower().split():
        if len(w) > 3 and w.startswith("ال"):
            w = w[2:]
        for suf in ("هم", "ها", "نا", "كم"):
            if len(w) > 4 and w.endswith(suf):
                w = w[:-2]
                break
        if len(w) >= 2 and w not in _STOP:
            out.add(w)
    return out


def novelty_key(text):
    """Storable, comparable fingerprint of an angle. Empty text -> ''."""
    return " ".join(sorted(_tokens(text)))


# A timed beat-grid — «(٠-٣ث)», «(3-8s)», «٠-٣ث:», «(ثانية 5)» — is exactly the
# AI-artifact shape the owner rejected. Strip it so a script reads like talking, not
# like a storyboard, no matter what the model emits (defense in depth behind the prompt).
_TS_PATTERNS = (
    re.compile(r"[（(]\s*\d+\s*[-–—]\s*\d+\s*(?:ث|ثانية|ثواني|s|sec|secs|seconds)?\s*[)）]"),
    re.compile(r"[（(]\s*(?:ث|ثانية|ثواني|s|sec|second)\s*\d+[^)）]*[)）]"),
    re.compile(r"^\s*\d+\s*[-–—]\s*\d+\s*(?:ث|ثانية|ثواني|s|sec)?\s*[:：\-–—]\s*"),
    re.compile(r"[（(]\s*\d+\s*(?:ث|ثانية|ثواني|sec|s)\s*[)）]"),
)


def strip_timestamps(text):
    """Remove any timed-beat markers from one script line, then tidy whitespace."""
    t = _norm_digits(str(text or ""))
    for pat in _TS_PATTERNS:
        t = pat.sub(" ", t)
    return re.sub(r"\s{2,}", " ", t).strip(" -–—:•").strip()


def _norm_digits(text):
    t = str(text or "")
    for i, d in enumerate("٠١٢٣٤٥٦٧٨٩"):
        t = t.replace(d, str(i))
    return t


def numbers_in(text):
    """The quantity tokens in a text (Arabic-Indic folded to ASCII), years dropped.
    A bare year is not a statistic; a percent sign counts as a number."""
    t = _norm_digits(text)
    t = re.sub(r"[（(][^)）]*[)）]", " ", t)      # ignore anything already parenthesised
    out = []
    for m in re.finditer(r"\d+(?:[.,]\d+)?", t):
        v = m.group(0)
        if len(v) == 4 and v.startswith(("19", "20")):
            continue
        out.append(v)
    if "%" in t or "٪" in str(text or ""):
        out.append("%")
    return out


def leads_with_number(hook, fact, head_words=5):
    """spec S3: when the grounding fact carries a number, the FIRST spoken line must
    LEAD with a number — inside the opening few words, before any sentence break, not
    buried after a rhetorical question. Vacuously true when the fact has no number."""
    if not numbers_in(fact):
        return True
    raw = str(hook or "")
    # cut at the first sentence break so a number after «؟»/«.» doesn't count as leading
    first = re.split(r"[؟?!.،,:\n]", raw, 1)[0]
    head = " ".join(_norm_digits(first).split()[:head_words])
    if "%" in head or "٪" in " ".join(first.split()[:head_words]):
        return True
    return bool(re.search(r"\d", head))


def is_novel(key, recent_keys, threshold=0.55):
    """False when `key` restates something already in `recent_keys` (token Jaccard).
    An empty key is never novel — an angle we can't fingerprint isn't a fresh one."""
    a = set(str(key or "").split())
    if not a:
        return False
    for other in recent_keys or []:
        b = set(str(other or "").split())
        if not b:
            continue
        inter = len(a & b)
        if inter and inter / float(len(a | b)) >= threshold:
            return False
    return True


def signal_id(family, source, fact):
    """Content-addressed id: the same fact is the same signal forever, whatever
    title the model wrapped it in. Keeps re-scans from duplicating the feed."""
    h = hashlib.sha1(("%s|%s|%s" % (family, source, novelty_key(fact))).encode("utf-8"))
    return h.hexdigest()[:16]


def signal_ok(sig):
    """The anti-fabrication gate (spec Section K). FAILS CLOSED.
    A signal with no fact is nothing; an EXTERNAL claim with no source url or no
    date is exactly the unverifiable stat the owner banned."""
    if not isinstance(sig, dict):
        return False
    if sig.get("family") not in SIGNAL_FAMILIES:
        return False
    if sig.get("source") not in SIGNAL_SOURCES:
        return False
    if not str(sig.get("fact") or "").strip():
        return False
    if sig.get("family") == "external":
        url = str(sig.get("url") or "").strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            return False
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(sig.get("as_of") or "").strip()):
            return False
    return True


def make_signal(family, source, title, fact, detail="", url="", as_of="",
                strength=50, ref=""):
    """Build a validated signal, or None. None means: do NOT make content from this."""
    if source in SIGNAL_SOURCES and _FAMILY_OF_SOURCE.get(source) != family:
        return None                          # a source can't change families
    try:
        strength = max(0, min(100, int(strength)))
    except (TypeError, ValueError):
        strength = 50
    sig = {"family": str(family or ""), "source": str(source or ""),
           "title": _s(title, 160), "fact": _s(fact, 700), "detail": _s(detail, 900),
           "url": str(url or "").strip()[:400], "as_of": str(as_of or "").strip()[:10],
           "strength": strength, "ref": _s(ref, 80), "status": "new"}
    if not signal_ok(sig):
        return None
    sig["sid"] = signal_id(sig["family"], sig["source"], sig["fact"])
    return sig


def parse_signals(d, family, default_source=None):
    """Validated signals out of a model's {"signals":[…]} JSON. Anything ungrounded
    is dropped silently — an empty list is a correct answer."""
    if not isinstance(d, dict) or not isinstance(d.get("signals"), list):
        return []
    fallback = default_source or (
        "manual" if family == "manual" else
        ("market" if family == "external" else "insider"))
    out, seen = [], set()
    for raw in d["signals"][:20]:
        if not isinstance(raw, dict):
            continue
        src = _s(raw.get("source"), 40)
        if src not in SIGNAL_SOURCES or _FAMILY_OF_SOURCE.get(src) != family:
            src = fallback
        sig = make_signal(family, src, raw.get("title"), raw.get("fact"),
                          detail=raw.get("detail") or raw.get("why") or "",
                          url=raw.get("url") or raw.get("source_url") or "",
                          as_of=raw.get("as_of") or raw.get("date") or "",
                          strength=raw.get("strength", 50))
        if sig and sig["sid"] not in seen:
            seen.add(sig["sid"])
            out.append(sig)
    return out


def freshness_days(as_of, today):
    """Age of a signal in days, or None when the date is missing/unparseable.
    None must never be read as 'fresh today' — callers show «بدون تاريخ» instead."""
    def _d(v):
        try:
            y, m, dd = str(v).strip()[:10].split("-")
            return _date(int(y), int(m), int(dd))
        except Exception:
            return None
    a, b = _d(as_of), _d(today)
    if not a or not b:
        return None
    return (b - a).days


# privacy ----------------------------------------------------------------------

def scrub_names(text, guest_name):
    """Replace the guest's name (full + each token >=3 chars) with «الضيف».
    Cards must never leak a real guest name."""
    t = str(text or "")
    name = str(guest_name or "").strip()
    if not name:
        return t
    if len(name) >= 3 and name in t:
        t = t.replace(name, "الضيف")
    for tok in name.split():
        if len(tok) >= 3 and tok in t:
            t = t.replace(tok, "الضيف")
    return t
