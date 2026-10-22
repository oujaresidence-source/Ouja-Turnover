# codegate/host.py
# -*- coding: utf-8 -*-
"""codegate.host — the ONE bridge to bot.py (checkout/host.py pattern). This package never
does `import bot`. BLOCKING hooks run on the package's own pool; Discord hooks are coroutines."""


class _Host:
    now = None             # () -> aware Riyadh datetime
    state_path = None      # (name) -> absolute path inside STATE_DIR
    today_arrivals = None  # BLOCKING (day_iso) -> [{res_id, lid, day, unit, guest, conversation_id, checkin_at}]
    messages = None        # BLOCKING (conversation_id) -> [{inbound, body, at}]; RAISES on fetch failure
    code_sent = None       # BLOCKING (conversation_id) -> bool; RAISES when Hostaway fails (bot._cg_code_sent)
    code_in = None         # (messages as returned by `messages`) -> bool; PURE, no Hostaway call (go-live check)
    cover = None           # BLOCKING (lid, day) -> {name, did, role_id, owner_did}
    post = None            # async (channel_id, text, embed=None, buttons=None) -> message id | None
    edit = None            # async (channel_id, message_id, embed=None, buttons=None) -> bool
    #                        False ONLY when the card (or its room) is gone — Discord NotFound,
    #                        or Forbidden (we lost access to the room): live re-places the card.
    #                        Any other failure RAISES: the tick isolates it per item and the next
    #                        tick retries (a False there would post a duplicate card or close a
    #                        code-only room for nothing)
    escalate = None        # async (title, detail) -> None   (bot.py's _post_system_escalation)
    # ---- revision 2: the card lives in the unit's turnover room ----
    find_room = None       # BLOCKING (lid, day_iso) -> channel id of the turnover room keyed
    #                        `oujact-key:<lid>:<day>` (whole Turnovers category family) | None
    create_code_room = None  # async (item row) -> channel id | None. Opens the code-only room
    #                        in Turnovers (topic `codegate-room:1 codegate-res:<res_id>`); on
    #                        failure returns None and the BOT side alerts. MUST be idempotent:
    #                        when a room with topic `codegate-res:<res_id>` already exists, return
    #                        THAT room — a create that succeeded but returned None (timeout) is
    #                        retried next tick and must never open a duplicate (R3 implements)
    departures_today = None  # BLOCKING (day_iso) -> set[int] listing ids with a confirmed
    #                        departure that day (a turnover room is coming)
    send_code = None       # BLOCKING (res_id, conversation_id) -> (ok: bool, why: str), why in
    #                        "sent" | "no_code" | "killed" | "duplicate" | "error". Reads doorCode
    #                        from a FRESH GET /reservations/{id}, sends, never logs the body, and
    #                        RAISES nothing (flow still treats a raise as "error")
    delete_room = None     # async (channel_id, reason) -> bool. True when deleted OR when the
    #                        channel is ALREADY GONE (Discord NotFound: someone deleted it by
    #                        hand — the close is done). False only for a real error (Forbidden,
    #                        5xx, timeout): flow retries at most 3 times (at once gives up for a
    #                        row > 2 days old) and then writes «⚠️ ما قدرت أقفل الغرفة» (R3)
    log_review = None      # async (text) -> None: one audit line to #oujact-review
    release_send_claim = None  # BLOCKING (res_id) -> None. Optional: frees the sender's dedupe
    #                        claim `codegate-send:<res_id>` after an admin undo, so a legitimate
    #                        re-send is not refused as "duplicate"


HOST = _Host()


def wire(caps):
    for k, v in (caps or {}).items():
        if not hasattr(HOST, k):
            raise AttributeError("codegate.wire: unknown capability %r" % k)
        setattr(HOST, k, v)
