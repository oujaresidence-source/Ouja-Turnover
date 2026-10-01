# -*- coding: utf-8 -*-
"""
FakePort — an in-memory Discord for the permits service tests.

Channels, messages, pins, locks and renames live in plain dicts. Failure injection:
    fail_create  = Exception(...)   create_ticket_channel raises
    fail_exists  = Exception(...)   channel_exists raises (Discord unreachable, F8)
    fail_post    = Exception(...)   post / post_digest raise
    crash_after_create = True       the channel IS created, then the call raises — a bot
                                    crash between "channel made" and "row recorded" (F4)
    crash_before_card = True        the channel is created EMPTY (no card), then the call raises
Every call is appended to `calls` as (method, args...) so a test can assert "zero calls".
"""

import itertools

from permits import engine


class FakePort(object):

    def __init__(self, ready=True):
        self._ready = ready
        self.calls = []
        self.channels = {}          # channel_id -> {name, topic, messages:[...], locked, card}
        self.digests = []           # [(chunks, user_ids)]
        self._ids = itertools.count(1000)
        self.fail_create = None
        self.fail_exists = None
        self.fail_post = None
        self.crash_after_create = False
        self.crash_before_card = False

    # ---- helpers for tests ----
    def open_channels(self):
        return {cid: c for cid, c in self.channels.items() if not c["name"].startswith("مغلقة-")}

    def delete_channel(self, cid):
        self.channels.pop(str(cid), None)

    def messages(self, cid):
        return self.channels[str(cid)]["messages"]

    # ---- the contract ----
    def ready(self):
        return self._ready

    async def create_ticket_channel(self, name, topic, card, responsible_id=None):
        self.calls.append(("create", name, topic))
        if self.fail_create:
            raise self.fail_create
        cid = str(next(self._ids))
        if self.crash_before_card:
            self.crash_before_card = False
            self.channels[cid] = {"name": name, "topic": topic, "card": None, "card_msg_id": "",
                                  "messages": [], "locked": False, "buttons": False}
            raise RuntimeError("bot died before the card was posted")
        mid = str(next(self._ids))
        self.channels[cid] = {"name": name, "topic": topic, "card": card, "card_msg_id": mid,
                              "messages": [{"id": mid, "card": card, "pinned": True}],
                              "locked": False, "buttons": True}
        if self.crash_after_create:
            self.crash_after_create = False
            raise RuntimeError("bot died right after creating the channel")
        return {"channel_id": cid, "card_msg_id": mid}

    async def find_channel_by_tid(self, tid):
        self.calls.append(("find", tid))
        for cid, c in self.channels.items():
            parsed = engine.parse_topic(c["topic"])
            if parsed and parsed[1] == int(tid):
                return cid
        return None

    async def ensure_card(self, channel_id, card):
        self.calls.append(("ensure_card", channel_id))
        c = self.channels[str(channel_id)]
        for m in c["messages"]:
            if m.get("card") and m["card"].get("footer") == card.get("footer"):
                return m["id"]
        mid = str(next(self._ids))
        c["messages"].insert(0, {"id": mid, "card": card, "pinned": True})
        c["card"], c["card_msg_id"], c["buttons"] = card, mid, True
        return mid

    async def channel_exists(self, channel_id):
        self.calls.append(("exists", channel_id))
        if self.fail_exists:
            raise self.fail_exists
        return str(channel_id) in self.channels

    async def post(self, channel_id, text, user_ids=(), role_ids=()):
        self.calls.append(("post", channel_id, text, tuple(user_ids), tuple(role_ids)))
        if self.fail_post:
            raise self.fail_post
        if str(channel_id) not in self.channels:
            raise RuntimeError("Unknown Channel")
        self.channels[str(channel_id)]["messages"].append(
            {"text": text, "users": list(user_ids), "roles": list(role_ids)})

    async def close_channel(self, channel_id, card_msg_id, note):
        self.calls.append(("close", channel_id, note))
        c = self.channels.get(str(channel_id))
        if c is None:
            raise RuntimeError("Unknown Channel")
        c["messages"].append({"text": note})
        c["locked"] = True
        c["buttons"] = False
        if not c["name"].startswith("مغلقة-"):
            c["name"] = "مغلقة-" + c["name"]

    async def post_digest(self, chunks, user_ids=()):
        self.calls.append(("digest", len(chunks)))
        if self.fail_post:
            raise self.fail_post
        self.digests.append((list(chunks), list(user_ids)))
