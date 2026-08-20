"""No commitment without an object behind it.

27.4% of «مساعد»'s messages (17 of 62) promised something with nothing anywhere in the
system to back it. «فريقنا المختص اتنبّه لموضوعك الحين وبيتواصل معك خلال دقائق» (T007 i13)
created no ticket, no owner, no deadline. Nobody was ever going to contact that guest.

WHY NOT JUST LET THE ASSISTANT OPEN TICKETS
_wm_promise_allowed (bot.py:63845) returns False for "ai-assistant", "team", "musaid" and
«مساعد». That is an owner rule and it is RIGHT: an AI must not create accountability for a
human who never agreed to it. So do not flip it. Invert the flow instead — detect the
commitment BEFORE the send and refuse to make it unbacked. The escalate path already
creates a real ticket with a real owner; route through that and quote the id.

C7: if the object cannot be created, the system stays silent and escalates. It does not
send a softer promise.
"""

import re
from collections import namedtuple

Commitment = namedtuple("Commitment", "kind span")

# followup — "someone will get back to you"
# action   — "I will raise/escalate this"
# callback — an explicit promise to make contact
_PATTERNS = [
    ("callback", r"بيتواصل\s+معك|بيتواصلون\s+معك|راح\s+نتواصل|بنتواصل\s+معك|"
                 r"بيكلمك|راح\s+يكلمك|بنرجع\s+لك"),
    ("action",   r"أرفع\s+طلبك|ارفع\s+طلبك|رافع\s+طلبك|برفع\s+طلبك|بصعّد|بصعد|"
                 r"راح\s+أرفع|راح\s+ارفع|بفتح\s+لك\s+طلب"),
    ("followup", r"بتابع|بأتابع|أتابعها|اتابعها|بنتابع|راح\s+أتابع|راح\s+اتابع|"
                 r"بأشوف\s+لك|بشوف\s+لك"),
    ("callback", r"\bwill\s+(?:reach\s+out|contact\s+you|get\s+back\s+to\s+you)\b|"
                 r"\bsomeone\s+will\s+(?:call|contact|reach)\b"),
    ("action",   r"\b(?:i'?ll|i\s+will|let\s+me)\s+(?:pass\s+this\s+along|escalate|"
                 r"raise\s+this|forward\s+this)\b|\bpass\s+this\s+along\b"),
    ("followup", r"\bwill\s+follow\s+up\b|\b(?:i'?ll|i\s+will|let\s+me)\s+(?:check|"
                 r"look\s+into\s+(?:it|this)|find\s+out)\b"),
]
_COMPILED = [(kind, re.compile(p, re.IGNORECASE)) for kind, p in _PATTERNS]


def detect_commitment(reply, lang="ar"):
    """{'kind': 'followup'|'action'|'callback', 'span': str} or None.

    Ordinary Saudi warmth is NOT a commitment. «حياك الله 🤍», «يعطيك العافية», «أبشر»
    and «ولا يهمك» promise nothing specific and must pass through — a guard that treats
    politeness as a debt escalates every friendly message and gets switched off.
    """
    text = (reply or "").strip()
    if not text:
        return None
    for kind, rx in _COMPILED:
        m = rx.search(text)
        if m:
            # widen to the sentence so a human reads the promise in context
            start = max(0, text.rfind(".", 0, m.start()) + 1)
            start = max(start, text.rfind("،", 0, m.start()) + 1)
            end = len(text)
            for stop in (".", "،", "\n"):
                i = text.find(stop, m.end())
                if i != -1:
                    end = min(end, i + 1)
            span = text[start:end].strip() or m.group(0)
            return {"kind": kind, "span": span[:200]}
    return None


def is_backed(commitment, ticket_id):
    """A promise is backed only by a real ticket id. Not by good intentions."""
    return commitment is None or bool(str(ticket_id or "").strip())
