# codegate/host.py
# -*- coding: utf-8 -*-
"""codegate.host — the ONE bridge to bot.py (checkout/host.py pattern). This package never
does `import bot`. BLOCKING hooks run on the package's own pool; Discord hooks are coroutines."""


class _Host:
    now = None             # () -> aware Riyadh datetime
    state_path = None      # (name) -> absolute path inside STATE_DIR
    today_arrivals = None  # BLOCKING () -> [{res_id, lid, day, unit, guest, conversation_id, checkin_at}]
    messages = None        # BLOCKING (conversation_id) -> [{inbound, body, at}]
    code_sent = None       # BLOCKING (conversation_id) -> bool   (bot.py's _was_code_sent_recently)
    cover = None           # BLOCKING (lid, day) -> {name, did, role_id, owner_did}
    channel = None         # async () -> channel id of «تسليم-الرموز» (fallback #escalations)
    post = None            # async (channel_id, text, embed=None, buttons=None) -> message id | None
    edit = None            # async (channel_id, message_id, embed=None, buttons=None) -> bool
    escalate = None        # async (title, detail) -> None   (bot.py's _post_system_escalation)


HOST = _Host()


def wire(caps):
    for k, v in (caps or {}).items():
        if not hasattr(HOST, k):
            raise AttributeError("codegate.wire: unknown capability %r" % k)
        setattr(HOST, k, v)
