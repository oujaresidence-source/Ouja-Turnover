# -*- coding: utf-8 -*-
"""
recovery.engine — the PURE rules of «استرداد التجربة».

Nothing in this file touches the network, Discord, the clock or the database. Every
function takes its inputs and returns a value, which is the only reason the equity math
below can be trusted: it is proved by tests/test_recovery_engine.py rather than by
watching the live server for a month and hoping.

FOUR THINGS THIS FILE DECIDES
  1. WHO enters the pipeline            -> eligibility() / select_batch()
  2. WHICH ticket goes first            -> priority_key()
  3. WHAT the model is allowed to read  -> compact()   (the whole cost story lives here)
  4. WHO makes the call                 -> choose_agent()

ONE DELIBERATE DEVIATION FROM THE SPEC, DOCUMENTED BECAUSE IT IS A CORRECTNESS POINT
The spec says an agent carrying `conflict_debt > 0` should get *priority* on the next
non-conflicted ticket "until the debt clears". Taken literally that rule can make the very
gap it exists to close WORSE: an agent excluded three times early in a month, who then
overtakes their colleague on volume, would keep jumping the queue while already ahead.
Sorting on `assigned_count` ascending already repairs conflict skew on its own — every
ticket a conflict pushes onto B lowers A's relative count and pulls the next one back to A.
So `conflict_debt` is recorded, reported monthly, and used as the FIRST TIE-BREAK when
counts are level (which is exactly the case where the spec's intent bites), never as an
override of the count itself. tests/test_recovery_engine.py proves the ±2 month-end target
holds under a conflict-heavy month with this ordering.
"""

import hashlib
import re

# ---------------------------------------------------------------------------
# Text signals
# ---------------------------------------------------------------------------
# Seeded from bot.py's _GUEST_COMPLAINT_HINTS. Copied rather than imported because this
# package must never `import bot`; the host may override it via compact(complaint_hints=...).
#
# WHY THIS LIST IS LONGER THAN bot.py's
# Checked against the project's own eval set (golden_set.seed.jsonl, 89 real guest
# messages), bot.py's list matched 3 — and MISSED the case the eval set itself labels
# «شكوى» («المكيف ما يبرد والجو حر»), the «نزاع مالي» case, and the refund/cancel case.
# In this package a missed hint does not change a guest's score (that comes from /guest);
# it decides whether the complaint line SURVIVES COMPACTION. Drop it on a long stay and the
# model writes a headline about the wrong thing.
#
# The trade is deliberately asymmetric: a false positive keeps one extra line (a few
# tokens); a false negative hides the reason the ticket exists. Bias to recall.
# What is NOT in here matters too — bare «حر» and «صوت» are substring-matched and would
# fire inside «الحرم», «بحر», «صوتك»; the multi-word forms are used instead.
COMPLAINT_HINTS = (
    # bot.py's original set
    "ما قدرت", "ما اقدر", "ما أقدر", "ما يفتح", "ما اشتغل", "ما يشتغل", "وين الرد",
    "محد رد", "تأخر", "متأخر", "سيئ", "سيئة", "زعلان", "مشكلة", "شكوى", "نصب",
    "can't", "cannot", "couldn't", "not working", "no response", "still waiting",
    "terrible", "awful", "complaint", "locked out", "angry",
    # broken / not functioning
    "ما يبرد", "ما تبرد", "الجو حر", "ما ينفع", "ما يطلع", "ما في ماي", "معطل",
    "خربان", "مكسور", "طافي", "ما يجي", "ضعيف", "منقطع",
    # cleanliness
    "وسخ", "وسخة", "مو نظيف", "مب نظيف", "ريحة", "حشرات", "صراصير",
    # noise / sleep
    "إزعاج", "ازعاج", "صوت عالي", "ما نمنا", "ما قدرنا ننام",
    # money / disputes / leaving
    "ظلم", "خصمتوا", "خصمتم", "استرجاع", "أرجع فلوسي", "ارجع فلوسي", "ألغي", "الغي",
    "تعويض", "غير مقبول", "مو معقول",
    # exhaustion / anger
    "تعبنا", "زهقنا", "مستاء", "متضايق", "آخر مرة",
    # english
    "broken", "doesn't work", "does not work", "dirty", "smell", "noisy", "no water",
    "no hot water", "refund", "cancel", "unacceptable", "disappointed", "worst",
    "never again", "waiting for", "nobody came", "no one came",
)

# A turn that is ONLY a courtesy carries no information the extraction can use, and two of
# them cost as much as a real sentence. Matched against the whole stripped body, never as a
# substring — «شكرا بس المكيف ما يشتغل» is a complaint, not a pleasantry.
PLEASANTRIES = (
    "شكرا", "شكراً", "مشكور", "مشكورين", "تمام", "تمام تمام", "طيب", "اوك", "أوك",
    "ماشي", "يعطيك العافية", "يعطيكم العافية", "الله يعافيك", "تسلم", "تسلمون",
    "ok", "okay", "thanks", "thank you", "ty", "great", "perfect", "sure", "fine",
    "good", "noted", "alright",
)

# Template traffic: welcome messages, arrival instructions, codes. These are the bulk of a
# Hostaway thread by character count and none of it describes what went wrong. bot.py's
# AUTO_REPLY_MARKERS is only five English welcome phrases — too thin to cut a real thread —
# so this list is wider on purpose and is applied to OUTBOUND messages only, because a
# guest who types "the wifi password doesn't work" must never be filtered as a wifi
# template.
AUTO_PATTERNS = (
    r"truly delighted", r"we are truly", r"delighted by your", r"we've prepared",
    r"we have prepared", r"looking forward to hosting",
    r"wi[\s\-]?fi", r"واي[\s\-]?فاي", r"الشبكة", r"كلمة المرور", r"باسورد", r"password",
    r"door\s*code", r"access\s*code", r"رمز الدخول", r"كود الدخول", r"الرمز",
    r"check[\s\-]?in\s*(instructions|time|is)", r"تعليمات الدخول", r"موعد الدخول",
    r"check[\s\-]?out\s*(time|is)", r"موعد الخروج",
    r"دليل الوصول", r"arrival guide", r"oujaguide", r"self[\s\-]?check[\s\-]?in",
    r"your reservation (is )?(confirmed|has been)", r"تم تأكيد الحجز",
    r"this is an automated", r"رسالة تلقائية",
)
_AUTO_RE = re.compile("|".join(AUTO_PATTERNS), re.IGNORECASE)

GUEST_LABEL = "الضيف"
STAFF_LABEL = "عوجا"
ELLIPSIS = "…"

ROOT_CAUSES = ("maintenance", "cleanliness", "checkin", "noise", "amenity",
               "staff", "pricing", "expectation", "other")


def _norm(s):
    """Lowercase, strip tatweel/diacritics-lite, collapse whitespace. Used for MATCHING
    only — never for anything the guest or the team will read back."""
    s = str(s or "").strip().lower()
    s = s.replace("ـ", "")                      # tatweel
    s = re.sub(r"[ً-ٰٟ]", "", s)      # harakat
    s = re.sub(r"[أإآ]", "ا", s)
    s = re.sub(r"ى", "ي", s)
    s = re.sub(r"ة", "ه", s)
    s = re.sub(r"\s+", " ", s)
    return s


def looks_automated(text):
    """True for template/system outbound traffic. Callers must only apply this to STAFF
    turns — see AUTO_PATTERNS."""
    return bool(_AUTO_RE.search(str(text or "")))


def is_pleasantry(text):
    """True when the whole turn is courtesy and nothing else."""
    body = _norm(text)
    body = re.sub(r"[!?.,،؛:\-…\s]+", " ", body).strip()
    body = re.sub(r"[\U0001F300-\U0001FAFF☀-➿️‍]", "", body).strip()
    if not body:
        return True
    for p in PLEASANTRIES:
        if body == _norm(p):
            return True
    # "شكرا جزيلا" / "thanks a lot" — a pleasantry plus a filler word, still no content.
    words = body.split()
    if len(words) <= 3 and any(body.startswith(_norm(p)) for p in PLEASANTRIES):
        return True
    return False


def has_complaint(text, hints=None):
    body = _norm(text)
    return any(_norm(h) in body for h in (hints or COMPLAINT_HINTS))


# ---------------------------------------------------------------------------
# 3. Compaction — §3.2. This is the whole cost story.
# ---------------------------------------------------------------------------

def _blocks(messages):
    """Drop template + pleasantry turns, then collapse consecutive same-sender turns.

    messages: [{"who": "guest"|"staff", "text": str, "ts": str}] — the host normalizes
    Hostaway's shape into this so the engine stays pure and testable.
    """
    kept = []
    for m in messages or []:
        who = "guest" if str(m.get("who")) == "guest" else "staff"
        text = str(m.get("text") or "").strip()
        if not text:
            continue
        if who == "staff" and looks_automated(text):
            continue
        if is_pleasantry(text):
            continue
        kept.append({"who": who, "text": text, "ts": m.get("ts") or ""})

    blocks = []
    for m in kept:
        if blocks and blocks[-1]["who"] == m["who"]:
            blocks[-1]["text"] += " " + m["text"]
            blocks[-1]["ts_end"] = m["ts"]
        else:
            blocks.append({"who": m["who"], "text": m["text"],
                           "ts": m["ts"], "ts_end": m["ts"]})
    return blocks


def _keep_indexes(blocks, tail=8, hints=None):
    """§3.2's keep-set: the first guest block, every complaint block plus the staff block
    that answered it, and the last `tail` blocks."""
    keep = set()
    first_guest = next((i for i, b in enumerate(blocks) if b["who"] == "guest"), None)
    if first_guest is not None:
        keep.add(first_guest)
    for i, b in enumerate(blocks):
        if b["who"] == "guest" and has_complaint(b["text"], hints):
            keep.add(i)
            if i + 1 < len(blocks) and blocks[i + 1]["who"] == "staff":
                keep.add(i + 1)
    for i in range(max(0, len(blocks) - tail), len(blocks)):
        keep.add(i)
    return keep


def _render(blocks, keep):
    lines, gap = [], False
    for i, b in enumerate(blocks):
        if i in keep:
            if gap:
                lines.append(ELLIPSIS)
                gap = False
            label = GUEST_LABEL if b["who"] == "guest" else STAFF_LABEL
            lines.append("%s: %s" % (label, b["text"]))
        else:
            gap = True
    return "\n".join(lines)


def _trim_middle(text, max_chars):
    """Cap length by removing whole lines from the MIDDLE — never the ends. The opening of
    a stay says what the guest arrived expecting and the last lines say where it stands
    right now; the middle is the most compressible part of any complaint thread.

    Only INTERIOR lines are ever eligible. An earlier version computed a midpoint and
    walked it when it landed on an existing marker, which on a short list walked all the
    way to index 0 and ate the first line — the exact thing this function exists to
    protect. Indices 0 and -1 are now structurally out of reach.
    """
    if len(text) <= max_chars:
        return text
    lines = text.split("\n")
    dropped = False
    while len(lines) > 2 and len("\n".join(lines)) > max_chars:
        interior = [i for i in range(1, len(lines) - 1) if lines[i] != ELLIPSIS]
        if not interior:
            break
        lines.pop(interior[len(interior) // 2])
        dropped = True
    if dropped and ELLIPSIS not in lines:
        lines.insert(max(1, len(lines) // 2), ELLIPSIS)
    out = "\n".join(lines)
    if len(out) <= max_chars:
        return out
    # Degenerate case: two lines that are themselves over the cap. Something has to give,
    # so give from the middle of the text as well — both ends still survive.
    half = max(1, (max_chars - len(ELLIPSIS) - 2) // 2)
    return out[:half] + "\n" + ELLIPSIS + "\n" + out[-half:]


def compact(messages, max_chars=6000, tail=8, complaint_hints=None):
    """The exact string that goes to the model. Deterministic: same messages in, same
    string out, which is what makes the cache key in content_hash() honest."""
    blocks = _blocks(messages)
    if not blocks:
        return ""
    keep = _keep_indexes(blocks, tail=tail, hints=complaint_hints)
    return _trim_middle(_render(blocks, keep), max_chars)


def content_hash(compacted):
    """§3.1's cache key half. Hashing the COMPACTED text, not the raw thread, is
    deliberate: a new template message or a bare «شكرا» changes the raw thread but changes
    nothing the model would see, and must not buy a second API call."""
    return hashlib.sha256(str(compacted or "").encode("utf-8")).hexdigest()


def cache_key(reservation_id, compacted):
    return "%s:%s" % (str(reservation_id or ""), content_hash(compacted))


# ---------------------------------------------------------------------------
# 2. Eligibility + priority — §2
# ---------------------------------------------------------------------------

def eligibility(cand, threshold=7.0):
    """(ok, reason). `reason` is a machine key, logged for every rejection so an owner
    asking «ليش ما فتحت تذكرة لهذا الضيف؟» gets an answer instead of a shrug.

    cand: {reservation_id, score, in_house, phone_e164, has_open_ticket, ...}
    """
    if not cand.get("reservation_id"):
        return False, "no_reservation"
    score = cand.get("score")
    if score is None or cand.get("evidence_state") == "unknown":
        return False, "no_score"
    try:
        score = float(score)
    except (TypeError, ValueError):
        return False, "no_score"
    if score >= float(threshold):
        return False, "score_ok"
    if cand.get("has_open_ticket"):
        return False, "already_open"
    # v1 scope: /guest only produces in-house guests. The flag is still checked so the day
    # the scope widens, a stale departure cannot slip in unnoticed.
    if not cand.get("in_house"):
        return False, "not_in_house"
    return True, "eligible"


def priority_key(cand):
    """Sort key — LOWER sorts first. §2's order: in-house, then lowest score, then repeat
    guest, then highest value."""
    try:
        score = float(cand.get("score"))
    except (TypeError, ValueError):
        score = 10.0
    try:
        value = float(cand.get("total_price") or 0)
    except (TypeError, ValueError):
        value = 0.0
    return (
        0 if cand.get("in_house") else 1,
        score,
        0 if cand.get("repeat_guest") else 1,
        -value,
        str(cand.get("reservation_id") or ""),
    )


def select_batch(cands, cap=15, threshold=7.0):
    """Split today's candidates into {taken, deferred, skipped}.

    `deferred` is what the cap pushed to tomorrow — it is RETURNED, not dropped, because a
    silently truncated queue reads as «كل شي تمام» when it is not.
    """
    eligible, skipped = [], []
    for c in cands or []:
        ok, reason = eligibility(c, threshold)
        (eligible if ok else skipped).append(
            c if ok else dict(c, skip_reason=reason))
    eligible.sort(key=priority_key)
    cap = max(0, int(cap or 0))
    return {"taken": eligible[:cap], "deferred": eligible[cap:], "skipped": skipped}


# ---------------------------------------------------------------------------
# 4. Assignment — §4
# ---------------------------------------------------------------------------

def _same_person(a, b):
    """Arabic names arrive from two different stores (the calendar and the agent config),
    so compare normalized. «محمد اليامي» must match «محمد اليامي » and «محمد اليامى»."""
    na, nb = _norm(a), _norm(b)
    return bool(na) and na == nb


def conflicted_agents(agents, unit_owner_name):
    """The recovery agents who are the responsible staff for this apartment. §4.1: the
    person who owns the problem never makes the recovery call."""
    if not unit_owner_name:
        return []
    return [a for a in agents or [] if _same_person(a.get("name"), unit_owner_name)]


def choose_agent(agents, stats, unit_owner_name=None, absent_ids=(), now_iso=""):
    """Pick the agent for one ticket.

    agents:  [{"id": "<discord id>", "name": "..."}]
    stats:   {agent_id: {"assigned_count": int, "conflict_debt": int,
                         "last_assigned_at": iso|None}}
    returns: {"agent_id", "agent_name", "excluded_id", "excluded_name",
              "fallback" (None|"supervisor"), "reason"}
    """
    agents = list(agents or [])
    stats = stats or {}
    conflicted = conflicted_agents(agents, unit_owner_name)
    conflicted_ids = {a["id"] for a in conflicted}
    absent = {str(x) for x in (absent_ids or [])}

    pool = [a for a in agents if a["id"] not in conflicted_ids and str(a["id"]) not in absent]
    excluded_id = conflicted[0]["id"] if conflicted else None
    excluded_name = conflicted[0]["name"] if conflicted else None

    if not pool:
        # §4.4 — every agent conflicted (or away). Never assign to the person who owns the
        # problem just to keep a slot filled; the supervisor takes it and the card says so.
        reason = "all_conflicted" if conflicted_ids else "all_absent"
        if conflicted_ids and absent:
            reason = "conflicted_and_absent"
        return {"agent_id": None, "agent_name": None,
                "excluded_id": excluded_id, "excluded_name": excluded_name,
                "fallback": "supervisor", "reason": reason}

    def rank(a):
        s = stats.get(a["id"], {})
        return (
            int(s.get("assigned_count") or 0),          # 1. equity: fewest tickets first
            -int(s.get("conflict_debt") or 0),          # 2. the excluded agent wins ties
            str(s.get("last_assigned_at") or ""),       # 3. longest since last (blank first)
            str(a["id"]),                               # 4. deterministic, so it is auditable
        )

    pick = sorted(pool, key=rank)[0]
    return {"agent_id": pick["id"], "agent_name": pick.get("name"),
            "excluded_id": excluded_id, "excluded_name": excluded_name,
            "fallback": None,
            "reason": "conflict_reassigned" if excluded_id else "equity"}


def apply_assignment(stats, agent_id, now_iso):
    """The stat mutation that follows a pick. Returned as a NEW dict — the caller writes it
    to the DB, so a failed write can never leave the in-memory counters ahead of the file."""
    out = {k: dict(v) for k, v in (stats or {}).items()}
    s = out.setdefault(agent_id, {"assigned_count": 0, "conflict_debt": 0,
                                  "last_assigned_at": None})
    s["assigned_count"] = int(s.get("assigned_count") or 0) + 1
    s["last_assigned_at"] = now_iso
    if int(s.get("conflict_debt") or 0) > 0:
        s["conflict_debt"] = int(s["conflict_debt"]) - 1   # "until the debt clears"
    return out


def apply_exclusion(stats, agent_id):
    """§4.3 — record that an agent was passed over for a conflict."""
    out = {k: dict(v) for k, v in (stats or {}).items()}
    s = out.setdefault(agent_id, {"assigned_count": 0, "conflict_debt": 0,
                                  "last_assigned_at": None})
    s["conflict_debt"] = int(s.get("conflict_debt") or 0) + 1
    return out


def equity_gap(stats, agent_ids):
    counts = [int((stats or {}).get(a, {}).get("assigned_count") or 0) for a in agent_ids]
    return (max(counts) - min(counts)) if counts else 0


# ---------------------------------------------------------------------------
# Extraction output validation — §3.5
# ---------------------------------------------------------------------------

def validate_extraction(raw):
    """(clean, error). Returns error text when the model's JSON does not fit the schema so
    the caller can retry once, then escalate, exactly as §3.3 requires."""
    if not isinstance(raw, dict):
        return None, "not an object"
    headline = str(raw.get("headline_ar") or "").strip()
    if not headline:
        return None, "headline_ar missing"
    timeline = raw.get("timeline")
    if not isinstance(timeline, list) or not timeline:
        return None, "timeline missing"
    clean_timeline = []
    for item in timeline[:5]:
        if not isinstance(item, dict):
            continue
        clean_timeline.append({"when": str(item.get("when") or "")[:40],
                               "what_ar": str(item.get("what_ar") or "")[:160]})
    if not clean_timeline:
        return None, "timeline empty"
    quotes = raw.get("quotes")
    quotes = [str(q)[:160] for q in quotes[:2]] if isinstance(quotes, list) else []
    root = str(raw.get("root_cause") or "").strip().lower()
    if root not in ROOT_CAUSES:
        root = "other"
    try:
        severity = int(raw.get("severity"))
    except (TypeError, ValueError):
        return None, "severity not an int"
    if not 1 <= severity <= 5:
        return None, "severity out of range"
    promised = raw.get("already_promised_ar")
    promised = str(promised).strip()[:300] if promised not in (None, "", "null") else None
    return {
        "headline_ar": headline[:200],
        "timeline": clean_timeline,
        "quotes": quotes,
        "root_cause": root,
        "physical_issue": bool(raw.get("physical_issue")),
        "already_promised_ar": promised,
        "unresolved_ar": str(raw.get("unresolved_ar") or "").strip()[:300],
        "severity": severity,
        "call_opener_ar": str(raw.get("call_opener_ar") or "").strip()[:400],
    }, None


SEVERITY_COLORS = {5: 0xC0392B, 4: 0xE67E22, 3: 0xF1C40F, 2: 0x95A5A6, 1: 0x95A5A6}


def severity_color(severity):
    try:
        return SEVERITY_COLORS.get(int(severity), 0x95A5A6)
    except (TypeError, ValueError):
        return 0x95A5A6
