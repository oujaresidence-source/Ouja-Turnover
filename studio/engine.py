# -*- coding: utf-8 -*-
"""studio.engine — pure story-mining logic. No network, no db, no host access.

Everything here is deterministic and TDD-locked by tests/test_studio_engine.py:
qualification (which conversations are worth reading), transcript building
(what Claude actually sees), and strict-but-tolerant parsing of the three
model outputs (triage / story / idea cards). Keep it pure."""

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

TRIGGERS = ("curiosity", "loss", "identity", "provocation", "emotion")
AUDIENCES = ("niche", "escape")
VIDEO_TYPES = ("talking", "tour", "before_after", "story_voiceover", "onsite")

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
        aud = _s(raw.get("audience"), 20)
        trg = _s(raw.get("trigger"), 20)
        vt = _s(raw.get("video_type"), 30)
        out.append({
            "hook_spoken": hook,
            "visual_title": title,
            "visual_sub": _s(raw.get("visual_sub"), 160),
            "angle": _s(raw.get("angle"), 400),
            "why_it_works": why,
            "script": [_s(x, 400) for x in script if _s(x, 400)][:10],
            "video_type": vt if vt in VIDEO_TYPES else "talking",
            "cta": _s(raw.get("cta"), 200),
            "audience": aud if aud in AUDIENCES else "niche",
            "trigger": trg if trg in TRIGGERS else "curiosity",
        })
    return out


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
