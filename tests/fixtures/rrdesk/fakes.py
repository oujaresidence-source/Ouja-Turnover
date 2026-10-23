# -*- coding: utf-8 -*-
"""Shared fakes for the rrdesk tests: a temp brain.db, a fake HOST and message builders.
No Discord, no network. Imported by tests/test_rrdesk_*.py."""

import datetime
import json
import os
import tempfile

from brain import db as bdb
from ops import db as odb, engine as oeng
from ops.host import HOST as OPS_HOST
from rrdesk import db, translate
from rrdesk.host import HOST

RIY = oeng.tz()
ROOM = "900"            # an RR room
THREAD = "901"          # a thread inside it
SAM = "555"
NASSER, ASEEL, NOURA, FAISAL = "111", "222", "333", "999"
BOT = "777"
EMPLOYEES = [{"name": "ناصر", "did": NASSER}, {"name": "اسيل", "did": ASEEL},
             {"name": "نورة", "did": NOURA}]


def at(y, mo, d, h, mi=0):
    return datetime.datetime(y, mo, d, h, mi, tzinfo=RIY)


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def setup(testcase, now=None, ticket=None):
    tmp = tempfile.mkdtemp(prefix="rrdesk_")
    bdb.set_db_path_for_tests(os.path.join(tmp, "brain.db"))
    db.reset_init_cache()
    odb.reset_init_cache()
    translate.reset_glossary_cache()
    clock = Clock(now or at(2026, 10, 20, 12, 0))
    rec = dict(ticket or {"kind": "rr", "seq": 47, "code": "HMWR4AS5WC", "status": "new",
                          "opener_id": ASEEL, "lid": 383921})
    state = {"leave": set(), "off": set(), "resp": ("نورة", NOURA, "owner"), "rec": rec}
    HOST.now = clock
    HOST.guild_id = 1448399100881014916
    HOST.rr_record = lambda cid: state["rec"] if str(cid) == ROOM else None
    HOST.rr_records = lambda: {ROOM: state["rec"]}
    HOST.enrich = lambda code: {"days_left": 10, "deadline_passed": False, "lid": 383921}
    HOST.responsible_for = lambda lid, day: state["resp"]
    HOST.lead_id = lambda: ASEEL
    HOST.on_leave = lambda name, day: name in state["leave"]
    HOST.off_today = lambda name, day: name in state["off"] or name in state["leave"]
    HOST.employees = lambda: list(EMPLOYEES)
    HOST.once_claim = lambda name, ttl=None: True
    HOST.watchdog_channel = lambda: "غرفة-المراقبة"
    HOST.public_base = lambda: "https://ouja.test"
    HOST.api_key = lambda: ""
    HOST.model = lambda: "claude-haiku-4-5-20251001"
    OPS_HOST.public_base = lambda: "https://ouja.test"
    OPS_HOST.discord_ids = lambda: {e["name"]: e["did"] for e in EMPLOYEES}
    db.set_setting("sam_ids", SAM)
    # the tests read the brief's round numbers (60 min / 8 h); the shipped defaults are the
    # calibrated ones and are locked separately in test_rrdesk_flow.Defaults
    db.set_setting("sla:resp_min", "60")
    db.set_setting("sla:deliv_min", "480")
    testcase.clock, testcase.state, testcase.tmp = clock, state, tmp
    testcase._orig_call = translate.call_model
    testcase.addCleanup(lambda: setattr(translate, "call_model", testcase._orig_call))
    return clock


def fake_model(testcase, classify=None, translation="TRANSLATED"):
    """translate.call_model replaced: Sam's messages get `classify` (dict) folded in."""
    calls = []

    def call(content, max_tokens=0, system=None, poster=None):
        calls.append(content)
        body = content if isinstance(content, str) else json.dumps(content)
        if "is_request" in body and classify is not None:
            d = dict(classify)
            d.setdefault("translation", translation)
            return json.dumps(d, ensure_ascii=False), 300, 50
        if body.startswith("Translate every string value"):
            obj = json.loads(body[body.index("{"):])
            return json.dumps(obj, ensure_ascii=False), 300, 80
        return json.dumps({"translation": translation}), 200, 30
    translate.call_model = call
    testcase.model_calls = calls
    return calls


def msg(mid, text, author=SAM, name="Sam1989", channel=ROOM, parent=None, is_bot=False,
        mentions=(), reply_author=None, media=(), voice=False, at_=None, embeds=None,
        is_self=False, role_mentioned=False):
    return {"id": str(mid), "channel_id": channel, "parent_id": parent, "author_id": author,
            "author_name": name, "is_bot": is_bot, "is_self": is_self, "text": text,
            "embeds": list(embeds or []), "media": list(media), "voice": voice,
            "mention_ids": list(mentions), "reference_author_id": reply_author,
            "role_mentioned": role_mentioned, "bot_ids": [BOT], "at": at_ or HOST.now()}


REQ_CLASSIFY = {"is_request": True, "confidence": 0.95, "asks": ["photos"], "urgent": False,
                "addressed_to_hint": "", "summary_en": "Send the check-in photos",
                "summary_ar": "أرسل صور الدخول"}


def deliver_all(results=None):
    """Pretend the outbox ran: every queued row is done, posts get message id = 'p:<ref>'."""
    from rrdesk import flow
    out = []
    for r in db.q("SELECT * FROM rrdesk_outbox WHERE state='queued' ORDER BY id"):
        r["payload"] = db.loads(r["payload_json"], {})
        mid = "p:" + r["ref"]
        res = {"message_ids": [mid]} if r["kind"] in ("post", "dm", "room", "board", "edit") else {}
        if r["kind"] == "board" and r["payload"].get("message_id"):
            res = {"message_ids": [r["payload"]["message_id"]]}
        db.execute("UPDATE rrdesk_outbox SET state='done' WHERE id=?", (r["id"],))
        flow.delivered(r, res)
        out.append(r)
    return out


def queued(kind=None, prefix=None):
    rows = db.q("SELECT * FROM rrdesk_outbox ORDER BY id")
    out = []
    for r in rows:
        r["payload"] = db.loads(r["payload_json"], {})
        if kind and r["kind"] != kind:
            continue
        if prefix and not r["ref"].startswith(prefix):
            continue
        out.append(r)
    return out
