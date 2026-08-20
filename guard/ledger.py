"""The send ledger — an append-only record of everything WE actually sent.

32.1% of outbound messages in the export (1,289 of 4,015) have no known author. That
number caps every other metric in the audit: you cannot measure «مساعد»'s language
mismatch rate, or its collision rate, on messages you cannot prove it wrote.

The cause is that attribution reads two bounded in-memory stores:

    _learning_log = deque(maxlen=3000)    # bot.py:12393
    _auto_replies = deque(maxlen=500)     # bot.py:12384

and the volume load at bot.py:58864 is `_learning_log.extend(...)` — extending a bounded
deque silently drops the oldest. Once either rolls, authorship is gone forever, and
_train_code_for falls back to the signature heuristic. That heuristic then labels the
message «مساعد · موقّع باسمه» with confidence "certain".

It is worse than a guess. _TRAIN_SIGN_TOKENS (bot.py:34197) contains «فريق عوجا» and
«ouja team» — tokens the TEAM's own canned templates also carry. So a team template with
no surviving record is labelled as the assistant, with certainty. That is how two
byte-identical canned checkout reminders (T053 i11, T101 i4) became «مساعد» messages.

This file is the root fix: one append-only line per real send, on the volume, never
rolled. record_send() is called from INSIDE send_guest_message() on success — one call
site, impossible to forget.

Imports nothing from bot. Never raises: a ledger that can crash the send path is worse
than no ledger.
"""

import json
import os
import re
import threading
import time

_LOCK = threading.Lock()
_INDEX = {}            # (cid, normalised body) -> record
_LOADED = False
_FILENAME = "send_ledger.jsonl"


def _state_dir():
    return os.environ.get("STATE_DIR", "/data")


def path():
    return os.path.join(_state_dir(), _FILENAME)


def norm(s):
    """Whitespace-insensitive lowercase form — identical to bot._train_norm, because the
    two have to agree on whether a delivered body is one we sent."""
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def _key(conversation_id, body):
    return (str(conversation_id or ""), norm(body))


def _load():
    """Read the ledger off the volume once per process. A missing or half-written file is
    not an error — a truncated last line just means that send is unattributed, which is
    exactly the state we were already in."""
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    try:
        with open(path(), "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue          # torn line — skip it, keep the rest
                _INDEX[_key(rec.get("conversation_id"), rec.get("body"))] = rec
    except FileNotFoundError:
        pass
    except Exception as e:
        print("[ledger] load failed:", e)


def record_send(conversation_id, body, *, via, actor, ticket_id=None, ts=None):
    """Record one delivered outbound. Returns the send id.

    via    — how it left: discord_send · discord_edit · dashboard_send · auto ·
             escalation_ack · hostaway_human
    actor  — who is accountable: a Discord name, "(auto)", or "musaed"
    """
    with _LOCK:
        _load()
        stamp = float(ts if ts is not None else time.time())
        rec = {
            "id": f"s{int(stamp * 1000)}",
            "conversation_id": str(conversation_id or ""),
            "body": body or "",
            "via": via or "",
            "actor": actor or "",
            "ticket_id": ticket_id,
            "ts": stamp,
        }
        _INDEX[_key(rec["conversation_id"], rec["body"])] = rec
        try:
            os.makedirs(_state_dir(), exist_ok=True)
            with open(path(), "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception as e:
            # The in-memory index still has it, so this process stays correct even when
            # the volume is read-only. Never let bookkeeping break a guest reply.
            print("[ledger] append failed:", e)
        return rec["id"]


def lookup(conversation_id, body):
    """Our record of this outbound, or None. Falls back to a body-only match because the
    same text in the same thread is ours regardless of which id Hostaway reports."""
    with _LOCK:
        _load()
        rec = _INDEX.get(_key(conversation_id, body))
        if rec:
            return rec
        k = norm(body)
        if not k:
            return None
        for (_cid, bkey), r in _INDEX.items():
            if bkey == k:
                return r
        return None


def is_ours(conversation_id, body):
    return lookup(conversation_id, body) is not None


def reset_for_tests():
    """Drop the in-memory index so a test can point STATE_DIR somewhere else."""
    global _LOADED
    with _LOCK:
        _INDEX.clear()
        _LOADED = False
