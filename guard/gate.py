"""Silence as a real output.

54.8% of «مساعد»'s messages (34 of 62) were not preceded by a guest message. It spoke
into silence, into one of our own templates, or straight over a teammate. That is not a
prompt failure — one env default causes it:

    ASSISTANT_ALWAYS_DRAFT = os.environ.get("ASSISTANT_ALWAYS_DRAFT", "1")   # bot.py:473

and in _conv_to_item (bot.py:9720) BOTH guards sit behind `if not ASSISTANT_ALWAYS_DRAFT`,
so with the shipped default neither ever runs.

This module is pure: it imports nothing from bot. Every accessor it needs is passed in,
so the same function grades a live Hostaway thread and a list of dicts in a unittest.

KEEP DRAFTING, STOP SENDING. A card a human can read costs nothing; a message a guest
did not need costs trust. `speak=False` is never a reason to skip the draft.

── A CONTRADICTION IN THE BUILD ORDER, resolved here and flagged in the report ──
§4/T4's rule table says template_echo fires when "previous message is a system template,
guest silent since" (T010 i4). Its test list says "Only an automated template after →
speak=True (that is the case Musaid exists for)." Both cannot hold: if a template is the
last message and the guest has not spoken since, those two rules disagree.

Resolved by asking what the guest is actually doing:
  • Guest asked something, a template fired after it, nobody answered the question
    → the guest is still waiting → SPEAK. This is the case Musaid exists for.
  • Guest's message was already answered, or is old enough that nobody is waiting, and a
    template is the newest thing in the thread → TEMPLATE_ECHO. Nobody is waiting; a
    template is not a conversation partner.
So template_echo means "the newest thing here is a template and no live question is
attached to it", not merely "the last message is a template".
"""

from collections import namedtuple

# speak: bool · reason: str
Decision = namedtuple("Decision", "speak reason")

REASONS = ("ok", "already_answered", "human_active", "claimed",
           "own_echo", "template_echo", "stale")

DEFAULT_HUMAN_WINDOW_SEC = 900      # 15 minutes — T006 i11 landed inside this
DEFAULT_STALE_HOURS = 12


def _body(m):
    return (m.get("body") or "") if isinstance(m, dict) else ""


def _default_is_outbound(m):
    """Hostaway marks the guest side with isIncoming=1."""
    return not (isinstance(m, dict) and str(m.get("isIncoming", "")) in ("1", "True", "true"))


def _default_msg_time(m):
    """Epoch seconds, or None when the message carries no usable timestamp."""
    if not isinstance(m, dict):
        return None
    t = m.get("ts", m.get("_ts"))
    return float(t) if isinstance(t, (int, float)) else None


def should_speak(*, msgs, guest_idx, claimed, now,
                 looks_automated,
                 is_outbound=None, msg_time=None, is_ours=None,
                 human_window_sec=DEFAULT_HUMAN_WINDOW_SEC,
                 stale_hours=DEFAULT_STALE_HOURS):
    """Should the assistant SEND into this thread right now?

    msgs           — the conversation, oldest first
    guest_idx      — index of the guest's most recent inbound message, or None
    claimed        — a human has claimed this conversation (bot._claimed_convos)
    now            — epoch seconds
    looks_automated(body) -> bool   — bot._looks_automated, injected
    is_ours(msg)   -> bool          — the send ledger (T5); default "we cannot tell"

    Never raises. On anything unexpected it returns speak=False: the safe answer to
    "should I talk?" is no.
    """
    is_outbound = is_outbound or _default_is_outbound
    msg_time = msg_time or _default_msg_time
    is_ours = is_ours or (lambda m: False)
    msgs = list(msgs or [])

    try:
        # A human has the conversation. Nothing below matters.
        # (bot.py checks this at 11687 — inside the escalate branch ONLY. can_auto at
        # 11806 has no such check, so today an auto-send can land on a claimed thread.)
        if claimed:
            return Decision(False, "claimed")

        # No guest message anywhere: we would be answering a template.
        if guest_idx is None or not (0 <= guest_idx < len(msgs)):
            return Decision(False, "template_echo")

        after = msgs[guest_idx + 1:]

        # Did anyone actually ANSWER the guest? A template does not count as an answer.
        for m in after:
            if not is_outbound(m):
                continue
            if looks_automated(_body(m)):
                continue
            # Label it by who: talking after ourselves is a different failure from
            # talking after a teammate, and the metrics need to tell them apart.
            return Decision(False, "own_echo" if is_ours(m) else "already_answered")

        # Is a teammate live in this thread right now? T006 i11: a human wrote «تنورنا»
        # and the bot piped up anyway. Their message may sit BEFORE the guest's.
        for m in msgs:
            if not is_outbound(m) or looks_automated(_body(m)) or is_ours(m):
                continue
            t = msg_time(m)
            if t is not None and 0 <= (now - t) <= human_window_sec:
                return Decision(False, "human_active")

        # Nobody is waiting on an old question.
        gt = msg_time(msgs[guest_idx])
        if gt is not None and (now - gt) > stale_hours * 3600:
            # A template is the newest thing and the question behind it went cold.
            return Decision(False, "template_echo" if after else "stale")

        # Guest asked, only templates followed (or nothing did). They are still waiting.
        # THIS is the case the assistant exists for.
        return Decision(True, "ok")
    except Exception:
        return Decision(False, "template_echo")
