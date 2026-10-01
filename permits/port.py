# -*- coding: utf-8 -*-
"""
permits.port — the DiscordPort contract. bot.py implements it (_PermitsDiscordPort);
tests/permits_fakes.py fakes it with failure injection. The service never touches discord.py.

Every method is a coroutine and runs on the bot's event loop. A method either does its
whole job or RAISES — the outbox turns a raise into `failed` + backoff + a line in the
digest's «مشاكل النظام». A method never swallows an error and reports success.

    ready() -> bool
        The guild is reachable. False → the tick skips every Discord step and marks
        nothing done (nothing is lost; it all waits in the outbox).

    async create_ticket_channel(name, topic, card, responsible_id) -> {"channel_id", "card_msg_id"}
        Create a text channel under the maintenance category «صيانه» — spilling into
        «صيانه ٢…٨» when Discord's 50-channel cap is hit (bot.py's _tk_make_channel) —
        post `card` (engine.ticket_card dict) with the persistent PermitTicketView, pin it.

    async find_channel_by_tid(tid) -> channel_id | None
        Look across the maintenance category family for a channel whose topic is
        `ouja-permit: … tid:<tid>`. Used to ADOPT a channel created by a run that crashed
        before it could record it — never create a second one for the same tid.

    async ensure_card(channel_id, card) -> card_msg_id
        After ADOPTING a channel: return the id of the card already in it (matched by the
        footer «permit:… · ticket:…»), or post + pin it now. A crash between "channel made"
        and "card posted" must never leave a room with no card and no buttons.

    async channel_exists(channel_id) -> bool
        True/False when Discord ANSWERED. RAISES when it could not check (Discord down):
        "can't check" must never be read as "deleted" (F8).

    async post(channel_id, text, user_ids=(), role_ids=())
        Send `text` (≤ 2000 chars, already chunked by the caller) with AllowedMentions
        limited to exactly these users / roles; never @everyone.

    async close_channel(channel_id, card_msg_id, note)
        Post the closing note, disable the card's buttons, lock the channel
        (_tk_lock_channel) and rename it «مغلقة-…». The channel is KEPT (audit trail).

    async post_digest(chunks, user_ids)
        Post the daily digest into PERMITS_DIGEST_CHANNEL (created under «صيانه» if missing).
"""


class DiscordPort(object):
    """Documentation-only base class; see the module docstring for the contract."""

    def ready(self):
        raise NotImplementedError

    async def create_ticket_channel(self, name, topic, card, responsible_id=None):
        raise NotImplementedError

    async def find_channel_by_tid(self, tid):
        raise NotImplementedError

    async def ensure_card(self, channel_id, card):
        raise NotImplementedError

    async def channel_exists(self, channel_id):
        raise NotImplementedError

    async def post(self, channel_id, text, user_ids=(), role_ids=()):
        raise NotImplementedError

    async def close_channel(self, channel_id, card_msg_id, note):
        raise NotImplementedError

    async def post_digest(self, chunks, user_ids=()):
        raise NotImplementedError
